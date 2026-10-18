import os
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Track, User
from streaming.streamer import stream_audio_file
from core.security import get_current_user, is_safe_track_file_path

router = APIRouter(tags=["Аудиостриминг"])


@router.get("/stream/{track_id}")
def stream_track(
    track_id: int,
    range: str | None = Header(None),
    token: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Потоковый стриминг аудиофайла (FLAC / MP3) с поддержкой перемотки (HTTP 206)."""
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден в фонотеке")

    if not track.file_path or not os.path.exists(track.file_path):
        # Self-healing: файл был удален с диска в обход системы (например, через rm).
        # Автоматически очищаем фантомный трек из базы данных.
        try:
            from database.models import PlayHistory, UserReaction, PlaylistTrack
            db.query(PlayHistory).filter(PlayHistory.track_id == track.id).delete()
            db.query(UserReaction).filter(UserReaction.track_id == track.id).delete()
            db.query(PlaylistTrack).filter(PlaylistTrack.track_id == track.id).delete()
            try:
                from recommendations.buffer_manager import discovery_buffer_manager
                discovery_buffer_manager.handle_track_deletion(track.id)
            except Exception:
                pass
            db.delete(track)
            db.commit()
            print(f"[Stream Self-Healing] Файл трека #{track_id} ({track.artist} - {track.title}) отсутствовал на диске и был удален из фонотеки.")
        except Exception as e:
            db.rollback()
            print(f"[Stream Self-Healing] Ошибка удаления отсутствующего трека: {e}")

        raise HTTPException(
            status_code=404,
            detail="Аудиофайл трека отсутствует на диске. Запись была автоматически удалена из фонотеки."
        )

    if not is_safe_track_file_path(track.file_path):
        raise HTTPException(
            status_code=403,
            detail="Доступ к аудиофайлу запрещен (путь находится за пределами фонотеки)"
        )

    file_path = track.file_path
    audio_format = track.audio_format
    gain_db = track.gain_db
    loudness_lufs = track.loudness_lufs
    peak_db = track.peak_db

    # Освобождаем сессию PostgreSQL прямо сейчас, чтобы не держать соединение из пула
    # на протяжении всех 3-5 минут потокового воспроизведения трека
    db.close()

    mime_type = "audio/flac" if audio_format == "flac" else "audio/mpeg"
    extra_headers = {}
    if gain_db is not None:
        extra_headers["X-Audio-Gain-dB"] = str(gain_db)
    if loudness_lufs is not None:
        extra_headers["X-Audio-Loudness-LUFS"] = str(loudness_lufs)
    if peak_db is not None:
        extra_headers["X-Audio-Peak-dB"] = str(peak_db)
    if extra_headers:
        extra_headers["Access-Control-Expose-Headers"] = "X-Audio-Gain-dB, X-Audio-Loudness-LUFS, X-Audio-Peak-dB"

    return stream_audio_file(file_path, range, mime_type=mime_type, extra_headers=extra_headers)
