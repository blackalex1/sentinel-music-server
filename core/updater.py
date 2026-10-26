"""
Модуль автоматического обновления Sentinel Music Server (1-Click Update).
Позволяет администратору одной кнопкой обновить сервер:
- Получить свежие коммиты и релизы из репозитория GitHub
- Использовать проверенные зеркала при сетевых сбоях/блокировках
- Обновить рабочее дерево через git fetch / git reset --hard
- Планировать чистый перезапуск процесса/контейнера
"""

import os
import sys
import time
import shutil
import logging
import threading
import subprocess
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger("sentinel.updater")

SERVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VERSION_FILE = os.path.join(SERVER_ROOT, "VERSION")


def get_current_app_version() -> str:
    """Читает актуальную версию из server/VERSION (Single Source of Truth)."""
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
    except Exception:
        pass
    return "0.0.3"


CURRENT_VERSION = get_current_app_version()

# Проверенные высокоскоростные зеркала GitHub для устойчивости в любых сетях
GITHUB_REPO_PATH = "blackalex1/sentinel-music-server"
MIRRORS = [
    f"https://github.com/{GITHUB_REPO_PATH}.git",
    f"https://ghfast.top/https://github.com/{GITHUB_REPO_PATH}.git",
    f"https://gh-proxy.com/https://github.com/{GITHUB_REPO_PATH}.git",
    f"https://githubproxy.cc/https://github.com/{GITHUB_REPO_PATH}.git",
]


def is_git_repository() -> bool:
    """Проверяет, запущен ли сервер из git-репозитория."""
    if not shutil.which("git"):
        return False
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=SERVER_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except Exception:
        return False


def get_current_git_commit() -> Optional[str]:
    """Возвращает короткий хэш текущего коммита."""
    if not is_git_repository():
        return None
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=SERVER_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def is_in_docker() -> bool:
    """Проверяет, запущен ли сервер внутри изолированного Docker-контейнера."""
    if os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "1":
        return True
    try:
        if os.path.exists("/proc/1/cgroup"):
            with open("/proc/1/cgroup", "r", encoding="utf-8", errors="ignore") as f:
                if "docker" in f.read():
                    return True
    except Exception:
        pass
    return False


def write_update_trigger(target_version: str = "") -> str:
    """Записывает файл-триггер в постоянный том data для автообновления хостом."""
    from core.config import settings
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    trigger_file = os.path.join(settings.DATA_DIR, "update.trigger")
    with open(trigger_file, "w", encoding="utf-8") as f:
        f.write(f"target_version={target_version}\ntimestamp={time.time()}\n")
    return trigger_file


def get_version_info() -> Dict[str, Any]:
    """Возвращает информацию о текущей версии сервера и поддержке обновления."""
    git_repo = is_git_repository()
    in_docker = is_in_docker()
    commit = get_current_git_commit() if git_repo else None
    return {
        "version": get_current_app_version(),
        "is_git": git_repo,
        "in_docker": in_docker,
        "commit": commit,
        "can_auto_update": git_repo or in_docker,
    }


def find_working_remote(branch: str = "main") -> Optional[str]:
    """
    Проверяет официальный репозиторий GitHub и резервные зеркала.
    Возвращает первый рабочий URL с таймаутом проверки 5 секунд.
    """
    for url in MIRRORS:
        try:
            res = subprocess.run(
                ["git", "ls-remote", "--heads", url, branch],
                cwd=SERVER_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            if res.returncode == 0:
                logger.info(f"[Updater] Доступно зеркало для обновления: {url}")
                return url
        except Exception:
            continue
    return None


def perform_server_update(branch: str = "main", target_version: str = "") -> Tuple[bool, str]:
    """
    Загружает актуальный код из GitHub и применяет изменения (git fetch & git reset --hard).
    В среде Docker регистрирует файл-триггер в общем томе data для фоновой пересборки хостом.
    """
    if is_in_docker():
        trigger_path = write_update_trigger(target_version)
        logger.info(f"[Updater] В Docker-окружении создан триггер обновления: {trigger_path}")
        return True, "Сигнал обновления передан хост-демону. Сервер пересобирается и перезапускается..."

    if not is_git_repository():
        trigger_path = write_update_trigger(target_version)
        return True, "Флаг обновления зарегистрирован в томе данных для обработки хостом."

    # Находим доступный адрес (официальный GitHub или зеркало)
    remote_url = find_working_remote(branch)
    if not remote_url:
        return False, "Не удалось связаться ни с официальным GitHub, ни с резервными зеркалами. Проверьте сеть."

    try:
        # Fetch изменений
        fetch_res = subprocess.run(
            ["git", "fetch", remote_url, branch],
            cwd=SERVER_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=40
        )
        if fetch_res.returncode != 0:
            err = fetch_res.stderr.strip() or fetch_res.stdout.strip()
            return False, f"Ошибка загрузки обновления (git fetch): {err}"

        # Применение изменений
        reset_res = subprocess.run(
            ["git", "reset", "--hard", "FETCH_HEAD"],
            cwd=SERVER_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20
        )
        if reset_res.returncode != 0:
            err = reset_res.stderr.strip() or reset_res.stdout.strip()
            return False, f"Ошибка применения обновления (git reset): {err}"

        new_commit = get_current_git_commit()
        return True, f"Обновление успешно загружено. Текущий коммит: {new_commit or 'latest'}"
    except subprocess.TimeoutExpired:
        return False, "Таймаут при загрузке обновления с GitHub"
    except Exception as e:
        logger.exception("[Updater] Непредвиденная ошибка при обновлении")
        return False, f"Ошибка обновления: {str(e)}"


def schedule_server_restart(delay_seconds: float = 1.5):
    """
    Планирует безопасный перезапуск сервера в фоновом потоке,
    позволяя текущему HTTP-запросу вернуть успешный ответ клиенту.
    """
    def _restart_worker():
        time.sleep(delay_seconds)
        logger.info("[Updater] Инициирован перезапуск процесса сервера...")
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass

        # Если сервер запущен в Docker (restart: unless-stopped) или systemd (Restart=always),
        # завершение процесса приводит к мгновенному автоматическому перезапуску с новым кодом.
        # В автономном режиме Windows/Linux пытаемся перезапустить интерпретатор.
        try:
            if not os.environ.get("DOCKER_CONTAINER"):
                # Попытка перезапуска текущего процесса
                executable = sys.executable
                args = [executable] + sys.argv
                if os.name == "nt":
                    # На Windows запускаем новый процесс и выходим
                    subprocess.Popen(args, cwd=SERVER_ROOT)
                    os._exit(0)
                else:
                    os.execv(executable, args)
        except Exception as e:
            logger.warning(f"[Updater] Не удалось выполнить os.execv: {e}")

        # Гарантированный выход для перезапуска супервизором / Docker
        os._exit(0)

    t = threading.Thread(target=_restart_worker, daemon=True, name="sentinel-updater-restart")
    t.start()
