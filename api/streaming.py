import os
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Track, User
from streaming.streamer import (
    stream_audio_file,
    mark_track_streaming,
    get_active_stream_path
)
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

    target_path = track.file_path

    # Если это повторный Range-запрос в рамках уже активного стриминга (буферизация/перемотка),
    # проверяем активный файл сессии (защита от сбоя декодера при фоновом авто-апгрейде качества)
    if range is not None:
        active_path = get_active_stream_path(track.id)
        if active_path and os.path.exists(active_path) and os.path.dirname(active_path) == os.path.dirname(target_path or ""):
            target_path = active_path

    # Самодиагностика и самовосстановление путей (например, после перемещения в Saved_Discoveries)
    if not target_path or not os.path.exists(target_path):
        recovered_path = None
        if track.file_path:
            filename = os.path.basename(track.file_path)
            music_dir = os.getenv("MUSIC_DIR") or "/music"
            candidates = [
                os.path.join(music_dir, "Saved_Discoveries", filename),
                os.path.join(music_dir, "discovery_buffer", filename),
                os.path.join(music_dir, filename),
            ]
            for cand in candidates:
                if os.path.exists(cand) and is_safe_track_file_path(cand):
                    recovered_path = cand
                    break

        if recovered_path:
            track.file_path = recovered_path
            try:
                db.commit()
            except Exception:
                db.rollback()
            target_path = recovered_path
        else:
            # Self-healing: если файл окончательно отсутствует на диске и не может быть восстановлен,
            # удаляем фантомную запись из БД
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

    if not is_safe_track_file_path(target_path):
        raise HTTPException(
            status_code=403,
            detail="Доступ к аудиофайлу запрещен (путь находится за пределами фонотеки)"
        )

    # Регистрируем трек как активно воспроизводимый
    mark_track_streaming(track.id, target_path)

    # Определяем MIME-тип по расширению фактического файла
    ext = os.path.splitext(target_path)[1].lower()
    if ext == ".flac":
        mime_type = "audio/flac"
    elif ext == ".ogg":
        mime_type = "audio/ogg"
    elif ext == ".wav":
        mime_type = "audio/wav"
    elif ext == ".m4a":
        mime_type = "audio/mp4"
    else:
        mime_type = "audio/mpeg"

    gain_db = track.gain_db
    loudness_lufs = track.loudness_lufs
    peak_db = track.peak_db

    # Освобождаем сессию БД перед началом длительной отдачи аудио-потока
    db.close()

    extra_headers = {}
    if gain_db is not None:
        extra_headers["X-Audio-Gain-dB"] = str(gain_db)
    if loudness_lufs is not None:
        extra_headers["X-Audio-Loudness-LUFS"] = str(loudness_lufs)
    if peak_db is not None:
        extra_headers["X-Audio-Peak-dB"] = str(peak_db)
    if extra_headers:
        extra_headers["Access-Control-Expose-Headers"] = "X-Audio-Gain-dB, X-Audio-Loudness-LUFS, X-Audio-Peak-dB"

    return stream_audio_file(target_path, range, mime_type=mime_type, extra_headers=extra_headers)
