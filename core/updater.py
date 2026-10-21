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
CURRENT_VERSION = "0.0.2"

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


def get_version_info() -> Dict[str, Any]:
    """Возвращает информацию о текущей версии сервера и поддержке обновления."""
    git_repo = is_git_repository()
    commit = get_current_git_commit() if git_repo else None
    return {
        "version": CURRENT_VERSION,
        "is_git": git_repo,
        "commit": commit,
        "can_auto_update": git_repo,
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


def perform_server_update(branch: str = "main") -> Tuple[bool, str]:
    """
    Загружает актуальный код из GitHub и применяет изменения (git fetch & git reset --hard).
    """
    if not is_git_repository():
        return False, "Сервер запущен не из git-репозитория. Автообновление доступно при клонировании через git или в Docker Compose."

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
