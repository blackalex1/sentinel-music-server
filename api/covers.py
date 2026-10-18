import os
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Track, User
from core.security import get_current_user, get_current_admin_user, get_current_user_optional, is_safe_track_file_path
from plugin_system.manager import plugin_manager

router = APIRouter(prefix="/covers", tags=["Обложки"])


def extract_embedded_cover(file_path: str):
    """
    Резервный метод извлечения встроенной обложки альбома (на случай отсутствия плагина).
    """
    try:
        from mutagen import File as MutagenFile
        from mutagen.id3 import APIC

        audio = MutagenFile(file_path)
        if audio is None:
            return None, None

        if hasattr(audio, "pictures") and audio.pictures:
            pic = audio.pictures[0]
            return pic.data, pic.mime

        if audio.tags:
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    return tag.data, tag.mime
    except Exception:
        pass

    parent_dir = os.path.dirname(file_path)
    for name in ["cover.jpg", "cover.png", "folder.jpg", "folder.png", "album.jpg"]:
        candidate = os.path.join(parent_dir, name)
        if os.path.exists(candidate):
            try:
                mime = "image/png" if name.endswith(".png") else "image/jpeg"
                with open(candidate, "rb") as f:
                    return f.read(), mime
            except Exception:
                pass

    return None, None


DEFAULT_COVER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300">'
    '<rect width="100%" height="100%" fill="#202020"/>'
    '<circle cx="150" cy="150" r="70" fill="#282828"/>'
    '<path d="M130 185 A 18 14 0 1 1 112 171 A 18 14 0 1 1 130 185 Z M130 185 L130 115 L180 102 L180 170 A 18 14 0 1 1 162 156 A 18 14 0 1 1 180 170 Z M130 115 L180 102" fill="#555" stroke="#ffcc00" stroke-width="4" stroke-linejoin="round"/>'
    '</svg>'
).encode("utf-8")


@router.get("/{track_id}")
async def get_track_cover(
    track_id: int,
    db: Session = Depends(get_db)
):
    """
    Возвращает изображение обложки альбома через модульную систему плагинов.
    Если обложка отсутствует в файле, плагин автоматически подтянет её онлайн
    через внешние каталоги и закеширует на диске.
    """
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")

    # 1. Запрашиваем обложку через систему плагинов (CoverPlugin)
    data, mime = await plugin_manager.get_track_cover(track)

    # 2. Резервный поиск, если плагины отключены или не вернули результат
    if not data or not mime:
        if track.file_path and os.path.exists(track.file_path) and is_safe_track_file_path(track.file_path):
            data, mime = await asyncio.to_thread(extract_embedded_cover, track.file_path)

    # 3. Fallback SVG, если обложку найти не удалось
    if not data or not mime:
        return Response(
            content=DEFAULT_COVER_SVG,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=600"}
        )

    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "public, max-age=86400"}
    )


@router.post("/backfill")
async def backfill_covers(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Запускает фоновое/пакетное заполнение обложек для треков фонотеки,
    у которых они пока отсутствуют (требуются права администратора).
    """
    cover_plugin = plugin_manager.get_plugin("CoverPlugin")
    if not cover_plugin or not hasattr(cover_plugin, "backfill_covers"):
        raise HTTPException(status_code=503, detail="Плагин CoverPlugin не активен")

    result = await cover_plugin.backfill_covers(db, limit=limit)
    return result


@router.post("/{track_id}/refresh")
async def refresh_track_cover(
    track_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Сбрасывает кэш обложки для указанного трека и выполняет повторный поиск.
    """
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")

    cover_plugin = plugin_manager.get_plugin("CoverPlugin")
    if cover_plugin and hasattr(cover_plugin, "cache_dir"):
        for ext in [".jpg", ".jpeg", ".png", ".webp", ".none"]:
            cand = os.path.join(cover_plugin.cache_dir, f"{track_id}{ext}")
            if os.path.exists(cand):
                try:
                    os.remove(cand)
                except Exception:
                    pass

    data, mime = await plugin_manager.get_track_cover(track)
    if data and mime:
        return {"status": "ok", "message": "Обложка успешно обновлена", "mime": mime}

    return {"status": "not_found", "message": "Обложка не найдена"}
