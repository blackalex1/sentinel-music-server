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

