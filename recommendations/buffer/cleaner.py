import os
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from database.models import Track, UserReaction
from recommendations.buffer.constants import safe_print
from recommendations.buffer.history import BufferHistory


class BufferCleaner:
    """
    Отвечает за очистку и синхронизацию буфера:
    - Регистрация новых скачанных файлов из буферной папки в истории.
    - TTL-очистка (удаление файлов и записей БД через 3 дня для нелайкнутых треков).
    - Автоматическая расстановка лайков для основной папки фонотеки.
    """

    @staticmethod
    def sync_buffer_files(
        db: Session,
        history: BufferHistory,
        buffer_subdir: str,
        retention_days: int = 3
    ):
        """
        Сканирует буферную папку и связывает скачанные файлы с базой данных и журналом.
        """
        records = history.load_history()
        known_paths = {r.get("file_path") for r in records if r.get("file_path")}
        known_ids = {r.get("track_id") for r in records if r.get("track_id")}

        # Ищем в БД все треки, путь которых лежит внутри буферной папки
        buffer_tracks = (
            db.query(Track)
            .filter(Track.file_path.ilike(f"%{buffer_subdir}%"))
            .all()
        )

        now_dt = datetime.now()
        updated = False

        for t in buffer_tracks:
            if t.id in known_ids or t.file_path in known_paths:
                continue

            entry = {
                "id": t.id,
                "track_id": t.id,
                "artist": t.artist,
                "title": t.title,
                "album": t.album,
                "duration": t.duration,
                "audio_format": t.audio_format,
                "file_path": t.file_path,
                "downloaded_at": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "played_in_stream_at": None,
                "liked": False,
                "liked_at": None,
                "status": "buffered",  # buffered -> played -> saved_permanent | expired_deleted
                "expires_at": (now_dt + timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S"),
                "deleted_at": None
            }
            records.append(entry)
            known_ids.add(t.id)
            known_paths.add(t.file_path)
            updated = True
            safe_print(f"[DiscoveryBuffer] Новый буферизованный трек зарегистрирован в журнале: {t.artist} - {t.title}")

        if updated:
            history.save_history(records)

    @staticmethod
    def cleanup_expired_tracks(db: Session, history: BufferHistory) -> int:
        """
        Проверяет срок жизни нелайкнутых треков (TTL = 3 дня).
        Удаляет файл с диска и запись из БД, но сохраняет метаданные в журнале навсегда.
        """
        records = history.load_history()
        now_dt = datetime.now()
        deleted_count = 0
        updated = False

        for r in records:
            if r.get("liked") is True or r.get("status") not in ("buffered", "played"):
                continue

            exp_str = r.get("expires_at")
            if not exp_str:
                continue

            try:
                exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

            if now_dt >= exp_dt:
                # Срок истек (3 дня без лайка)
                file_path = r.get("file_path")
                track_id = r.get("track_id")

                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        safe_print(f"[DiscoveryBuffer] Ошибка удаления файла {file_path}: {e}")

                if track_id:
                    track = db.query(Track).filter(Track.id == track_id).first()
                    if track:
                        try:
                            db.delete(track)
                            db.commit()
                        except Exception as de:
                            db.rollback()
                            safe_print(f"[DiscoveryBuffer] Ошибка удаления трека {track_id} из БД: {de}")

                r["status"] = "expired_deleted"
                r["deleted_at"] = now_dt.strftime("%Y-%m-%d %H:%M:%S")
                deleted_count += 1
                updated = True
                safe_print(f"[DiscoveryBuffer] [TTL] Трек {r.get('artist')} - {r.get('title')} удален (прошло 3 дня без лайка).")

        if updated:
            history.save_history(records)

        return deleted_count

    @staticmethod
    def backfill_main_folder_likes(db: Session, buffer_subdir: str) -> int:
        """
        Проставляет статус 'лайкнуто' (is_liked=True) по умолчанию для всех треков,
        находящихся в основной папке фонотеки (вне временного discovery_buffer).
        Оптимизировано: устраняет N+1 одиночных запросов через set-based outerjoin.
        """
        # 1. Находим треки без записей в UserReaction
        unreacted_track_ids = [
            row[0] for row in (
                db.query(Track.id)
                .outerjoin(UserReaction, UserReaction.track_id == Track.id)
                .filter(Track.is_discovery == False)
                .filter(UserReaction.id.is_(None))
                .all()
            )
        ]

        count = 0
        if unreacted_track_ids:
            batch_size = 500
            for i in range(0, len(unreacted_track_ids), batch_size):
                chunk = unreacted_track_ids[i:i + batch_size]
                reactions = [
                    UserReaction(track_id=tid, is_liked=True, is_disliked=False)
                    for tid in chunk
                ]
                db.bulk_save_objects(reactions)
                db.commit()
                count += len(chunk)

        # 2. Обновляем существующие реакции без явного предпочтения (is_liked=False, is_disliked=False)
        updated_reactions = (
            db.query(UserReaction)
            .join(Track, Track.id == UserReaction.track_id)
            .filter(Track.is_discovery == False)
            .filter(UserReaction.is_liked == False, UserReaction.is_disliked == False)
            .all()
        )
        if updated_reactions:
            for r in updated_reactions:
                r.is_liked = True
            db.commit()
            count += len(updated_reactions)

        if count > 0:
            safe_print(f"[DiscoveryBuffer] Проставлен статус 'Мне нравится' по умолчанию для {count} треков основной фонотеки.")
        return count
