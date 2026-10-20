import os
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Track, User
from core.security import get_current_user, is_safe_track_file_path
from plugin_system.manager import plugin_manager
from lyrics.storage import get_or_fetch_lyrics

router = APIRouter(prefix="/lyrics", tags=["Тексты песен"])


@router.get("/{track_id}")
async def get_track_lyrics(
    track_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Получает синхронизированный караоке-текст песни через систему плагинов .
    Каскадный поиск: БД -> .lrc файл -> Встроенные теги -> LRCLIB -> NetEase -> Региональный каталог -> Genius.
    """
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")

    # 1. Запрос через плагины
    is_synced, lines, raw_text = await plugin_manager.get_track_lyrics(track)

    # 2. Резервный поиск через стандартный модуль если плагин отключен
    if not raw_text:
        is_synced, lines, raw_text = await asyncio.to_thread(get_or_fetch_lyrics, track, db)

    return {
        "synced": is_synced,
        "lines": lines,
        "raw": raw_text
    }


@router.post("/{track_id}/refresh")
async def refresh_track_lyrics(
    track_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Сбрасывает сохраненный текст в БД и удаляет файл .lrc, запуская повторный поиск по всем источникам.
    """
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")

    # Сбрасываем поля в БД
    track.lyrics_synced = None
    track.lyrics_plain = None
    db.commit()

    # Удаляем локальный .lrc файл
    if track.file_path:
        base, _ = os.path.splitext(track.file_path)
        lrc_path = base + ".lrc"
        if os.path.exists(lrc_path) and is_safe_track_file_path(lrc_path):
            try:
                os.remove(lrc_path)
            except Exception:
                pass

    # Выполняем повторный поиск
    is_synced, lines, raw_text = await plugin_manager.get_track_lyrics(track)
    if not raw_text:
        is_synced, lines, raw_text = await asyncio.to_thread(get_or_fetch_lyrics, track, db)

    return {
        "status": "ok",
        "synced": is_synced,
        "lines": lines,
        "raw": raw_text
    }
