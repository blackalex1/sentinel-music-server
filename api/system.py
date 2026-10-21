import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.config import settings
from database.db import get_db
from database.models import User, Track
from streaming.scanner import scan_directory
from plugin_system.manager import plugin_manager
from core.security import get_current_user, get_current_user_optional, get_current_admin_user

router = APIRouter(tags=["Система и Индексация"])


DANGEROUS_SYSTEM_PATHS = {
    "/", "/etc", "/root", "/proc", "/sys", "/dev", "/bin", "/sbin", "/lib", "/var", "/run",
    "c:\\", "c:/", "c:", "d:\\", "d:/", "d:", "c:\\windows", "c:\\windows\\system32",
    "c:\\program files", "c:\\program files (x86)"
}


def validate_music_directory(music_path: Optional[str]) -> str:
    """
    Проверяет и гарантирует, что целевой каталог сканирования безопасен.
    Защищает от Path Traversal и сканирования критических системных каталогов ОС.
    """
    if not music_path or not str(music_path).strip():
        return os.path.abspath(settings.MUSIC_DIR)

    raw_path = str(music_path).strip()
    if "\x00" in raw_path or ".." in raw_path:
        raise HTTPException(status_code=400, detail="Недопустимый путь директории (использование '..' запрещено)")

    raw_path_lower = raw_path.lower().replace("/", "\\")
    
    # Запрещаем сканирование корней дисков
    cleaned_drive_root = raw_path.lower().rstrip("/\\")
    if cleaned_drive_root in ("c:", "d:", "e:", "f:", ""):
        raise HTTPException(status_code=400, detail="Сканирование корневого диска запрещено")

    # Запрещаем прямое указание критических системных путей Windows
    windows_system_prefixes = (
        "\\windows", "/windows", "system32", "\\system32", "/system32",
        "c:\\windows", "c:\\program files", "c:\\recovery", "c:\\boot"
    )
    if any(raw_path_lower.startswith(p) for p in windows_system_prefixes):
        raise HTTPException(status_code=400, detail="Сканирование системных каталогов ОС запрещено")

    resolved = os.path.realpath(os.path.abspath(raw_path))
    norm = resolved.lower().replace("/", "\\") if os.name == "nt" else resolved

    clean_resolved = resolved.lower().replace("\\", "/")
    if os.name == "nt" and len(clean_resolved) >= 2 and clean_resolved[1] == ":":
        clean_no_drive = clean_resolved[2:]
    else:
        clean_no_drive = clean_resolved

    if clean_no_drive in ("", "/", "\\"):
        raise HTTPException(status_code=400, detail="Сканирование корневого диска запрещено")

    dangerous_prefixes = [
        "/etc", "/proc", "/sys", "/dev", "/var", "/run", "/bin", "/sbin", "/lib",
        "/windows", "/system32", "/root", "/boot", "/program files", "/program files (x86)",
        "/recovery"
    ]
    if clean_no_drive in dangerous_prefixes or any(clean_no_drive.startswith(d + "/") or clean_no_drive == d for d in dangerous_prefixes):
        raise HTTPException(status_code=400, detail="Сканирование системных каталогов ОС запрещено")

    if norm in DANGEROUS_SYSTEM_PATHS or resolved in DANGEROUS_SYSTEM_PATHS or clean_resolved in DANGEROUS_SYSTEM_PATHS:
        raise HTTPException(status_code=400, detail="Сканирование системных каталогов ОС запрещено")

    return resolved



@router.post("/scan")
def trigger_scan(
    music_path: Optional[str] = Query(None, description="Целевая директория фонотеки"),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Запускает сканирование директории с музыкой на сервере (требуются права администратора):
    регистрирует новые треки и автоматически удаляет из базы отсутствующие файлы.
    """
    safe_path = validate_music_directory(music_path)
    from streaming.scanner import cleanup_missing_tracks
    deleted = cleanup_missing_tracks(safe_path, db)
    added = scan_directory(safe_path, db)
    return {"status": "success", "added_tracks": added, "deleted_missing_tracks": deleted}


@router.get("/plugins")
def list_plugins(current_user: Optional[User] = Depends(get_current_user_optional)):
    """Возвращает список активных подключенных плагинов расширения."""
    return [
        {
            "name": p.name,
            "version": getattr(p, "version", "1.0.0"),
            "description": getattr(p, "description", ""),
            "priority": getattr(p, "priority", 100),
            "enabled": p.enabled,
            "has_ui": getattr(p, "has_ui", False),
            "ui_entry": getattr(p, "ui_entry", None),
            "ui_styles": getattr(p, "ui_styles", None),
        }
        for p in plugin_manager.plugins
        if p.enabled
    ]


@router.post("/ingest/request")
async def request_external_import(
    artist: str,
    title: str,
    current_user: User = Depends(get_current_admin_user)
):
    """
    Запрос на фоновый импорт аудиозаписи (требуются права администратора).
    Делегируется активным плагинам расширения (если подключены).
    """
    handled = await plugin_manager.request_track_import(artist, title)
    return {"artist": artist, "title": title, "handled": handled}


@router.get("/watcher")
def get_watcher_status(
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Возвращает текущее состояние фонового сервиса Watchdog автосканирования."""
    from streaming.watcher import music_watcher
    st = music_watcher.status()
    st["total_tracks"] = db.query(Track).filter(Track.is_discovery == False).count()
    return st


@router.post("/watcher/start")
def start_watcher(
    music_path: Optional[str] = Query(None, description="Целевая директория фонотеки"),
    current_user: User = Depends(get_current_admin_user)
):
    """Запускает или перезапускает фоновый Watchdog для указанного пути (требуются права администратора)."""
    safe_path = validate_music_directory(music_path) if music_path else None
    from streaming.watcher import music_watcher
    started = music_watcher.start(music_dir=safe_path)
    return {"status": "started" if started else "failed", "details": music_watcher.status()}


@router.post("/watcher/stop")
def stop_watcher(
    current_user: User = Depends(get_current_admin_user)
):
    """Останавливает фоновый Watchdog (требуются права администратора)."""
    from streaming.watcher import music_watcher
    music_watcher.stop()
    return {"status": "stopped", "details": music_watcher.status()}


class SslGenerateRequest:
    pass

from pydantic import BaseModel

class SslRequest(BaseModel):
    domain: str
    email: Optional[str] = ""
    is_self_signed: bool = False


@router.get("/ssl/status")
@router.get("/system/ssl/status")
def get_ssl_certificate_status(
    current_user: User = Depends(get_current_admin_user)
):
    """Возвращает информацию о текущем SSL-сертификате сервера."""
    from core.ssl import get_ssl_status
    return get_ssl_status()


@router.post("/ssl/generate")
@router.post("/system/ssl/generate")
async def generate_ssl_certificate(
    payload: SslRequest,
    current_user: User = Depends(get_current_admin_user)
):
    """
    Выпуск SSL-сертификата (требуются права администратора):
    - При is_self_signed=True: мгновенная генерация самоподписанного сертификата для домена / IP.
    - При is_self_signed=False: автоматический выпуск доверенного сертификата Let's Encrypt через ACME HTTP-01.
    """
    import re
    import ipaddress
    domain = payload.domain.strip()
    email = (payload.email or "").strip()

    if not domain:
        raise HTTPException(status_code=400, detail="Укажите доменное имя")

    is_valid_domain = bool(re.match(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$", domain)) or domain == "localhost"
    is_valid_ip = False
    try:
        ipaddress.ip_address(domain)
        is_valid_ip = True
    except ValueError:
        pass

    if payload.is_self_signed:
        if not (is_valid_domain or is_valid_ip or re.match(r"^[a-zA-Z0-9_\-\.]{1,100}$", domain)):
            raise HTTPException(status_code=400, detail="Некорректное доменное имя или IP-адрес для самоподписанного сертификата")
    else:
        if not is_valid_domain:
            raise HTTPException(status_code=400, detail="Некорректный формат доменного имени (например, music.mydomain.com)")
        if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise HTTPException(status_code=400, detail="Некорректный адрес электронной почты")

    import asyncio
    from core.ssl import request_ssl_cert, generate_self_signed_cert, get_ssl_status

    if payload.is_self_signed:
        success, msg = await asyncio.to_thread(generate_self_signed_cert, domain)
    else:
        success, msg = await asyncio.to_thread(request_ssl_cert, domain, email)

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    return {
        "status": "success",
        "message": msg,
        "ssl_details": get_ssl_status()
    }


@router.get("/version")
@router.get("/system/version")
def get_system_version_info(
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Возвращает информацию о версии сервера и поддержке автоматического обновления."""
    from core.updater import get_version_info
    return get_version_info()


@router.post("/update")
@router.post("/system/update")
async def trigger_system_update(
    current_user: User = Depends(get_current_admin_user)
):
    """
    Запускает автоматическое обновление сервера (1-Click Update):
    - Скачивает последние изменения из репозитория GitHub
    - Применяет обновления (git reset --hard)
    - Инициирует безопасный перезапуск сервера
    Требуются права администратора.
    """
    import asyncio
    from core.updater import perform_server_update, schedule_server_restart

    success, msg = await asyncio.to_thread(perform_server_update, "main")
    if not success:
        raise HTTPException(status_code=500, detail=msg)

    # Запускаем отложенный перезапуск (1.5 сек), чтобы успеть вернуть ответ клиенту
    schedule_server_restart(delay_seconds=1.5)

    return {
        "status": "success",
        "message": msg,
        "restarting": True
    }



