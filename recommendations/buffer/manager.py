import os
import time
import shutil
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from database.models import Track, UserReaction
from core.config import settings
from recommendations.buffer.constants import (
    BUFFER_SUBDIR,
    TARGET_BUFFER_SIZE,
    RETENTION_DAYS,
    HISTORY_FILENAME,
    SAVED_DISCOVERIES_DIRNAME,
    safe_print
)
from recommendations.buffer.history import BufferHistory
from recommendations.buffer.cleaner import BufferCleaner
from recommendations.buffer.refiller import BufferRefiller


class DiscoveryBufferManager:
    """
    Координатор автономного буфера Потока:
    - В фоне держит 2-3 готовых трека (FLAC/MP3) в буферной папке discovery_buffer.
    - Треки стартуют в Потоке мгновенно и играют на 100% длительности.
    - Ведет на диске постоянный stream_history.json со всей историей треков в потоке.
    - При лайке (❤️) трек переносится в постоянную фонотеку навсегда и ищется HQ/Lossless версия на P2P.
    - Нелайкнутые треки автоматически удаляются с диска и из БД через 3 дня (TTL).
    - Журнал stream_history.json сохраняется навсегда.
    """

    BUFFER_SUBDIR = BUFFER_SUBDIR
    TARGET_BUFFER_SIZE = TARGET_BUFFER_SIZE
    RETENTION_DAYS = RETENTION_DAYS
    HISTORY_FILENAME = HISTORY_FILENAME

    def __init__(self, music_dir: Optional[str] = None, session_factory=None):
        self.music_dir = os.path.abspath(music_dir or settings.MUSIC_DIR)
        self.buffer_dir = os.path.join(self.music_dir, self.BUFFER_SUBDIR)
        self.session_factory = session_factory
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        self.history = BufferHistory(buffer_dir=self.buffer_dir, lock=self._lock)
        self.cleaner = BufferCleaner()
        self.refiller = BufferRefiller(lock=self._lock)

    @property
    def history_json_path(self) -> str:
        return self.history.history_json_path

    @property
    def _is_refilling(self) -> bool:
        return self.refiller.is_refilling

    @_is_refilling.setter
    def _is_refilling(self, val: bool):
        with self._lock:
            self.refiller._is_refilling = val

    def _ensure_dir(self):
        """Создает буферную директорию и при необходимости мигрирует устаревший файл истории."""
        self.history._ensure_dir()

    def load_history(self) -> List[Dict[str, Any]]:
        """Загружает журнал треков Потока из JSON-файла на диске."""
        return self.history.load_history()

    def save_history(self, records: List[Dict[str, Any]]):
        """Атомарно сохраняет журнал треков Потока в JSON на диск."""
        self.history.save_history(records)

    def sync_buffer_files(self, db: Session):
        """
        Сканирует буферную папку и связывает скачанные файлы с базой данных и журналом.
        """
        self.cleaner.sync_buffer_files(
            db=db,
            history=self.history,
            buffer_subdir=self.BUFFER_SUBDIR,
            retention_days=self.RETENTION_DAYS
        )

    def get_next_buffered_track(self, db: Session, mood: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Возвращает следующий готовый к воспроизведению трек из автономного буфера.
        Трек играет мгновенно на 100% длительности без ожидания сети.
        """
        self.sync_buffer_files(db)
        records = self.load_history()

        # Исключаем дизлайкнутые
        disliked_ids = {
            r.track_id for r in db.query(UserReaction.track_id).filter(UserReaction.is_disliked == True).all()
        }

        # Кандидаты со статусом 'buffered' (готовы к воспроизведению)
        candidates = [
            r for r in records
            if r.get("status") == "buffered"
            and r.get("track_id") not in disliked_ids
            and r.get("file_path")
            and os.path.exists(r.get("file_path"))
        ]

        if not candidates:
            return None

        # Выбираем первого кандидата
        chosen_rec = candidates[0]
        track_id = chosen_rec.get("track_id")

        track = db.query(Track).filter(Track.id == track_id).first()
        if not track:
            return None

        # Переводим статус в 'played'
        with self._lock:
            chosen_rec["status"] = "played"
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            chosen_rec["played_in_stream_at"] = now_str
            self.save_history(records)

        # Запускаем фоновую дозагрузку буфера, чтобы в нем всегда было 2-3 трека
        if self.session_factory:
            self.trigger_background_refill()

        return {
            "id": track.id,
            "title": track.title,
            "artist": track.artist,
            "album": track.album,
            "duration": track.duration,
            "audio_format": track.audio_format,
            "file_path": track.file_path,
            "bpm": track.bpm,
            "energy": track.energy,
            "valence": track.valence,
            "is_discovery": True,
            "discovery_reason": "🔥 Свежая новинка из сети",
            "is_buffer_track": True
        }

    def handle_user_reaction(self, track_id: int, is_like: bool = False, is_disliked: bool = False, db: Session = None) -> bool:
        """
        Обрабатывает лайк / дизлайк:
        - При лайке (❤️) трек закрепляется в постоянной коллекции фонотеки навсегда (is_discovery=False).
        - При дизлайке (💔) файл немедленно удаляется из буфера и БД.
        - При снятии лайка/дизлайка файл НЕ удаляется, просто обновляется статус в истории.
        """
        records = self.load_history()
        target_rec = None
        for r in records:
            if r.get("track_id") == track_id:
                target_rec = r
                break

        if not target_rec:
            return False

        with self._lock:
            if is_like:
                target_rec["liked"] = True
                target_rec["liked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                target_rec["status"] = "saved_permanent"

                # Опционально перемещаем файл из discovery_buffer в основную папку фонотеки
                old_path = target_rec.get("file_path")
                if old_path and os.path.exists(old_path) and self.BUFFER_SUBDIR in old_path:
                    try:
                        fav_dir = os.path.join(self.music_dir, SAVED_DISCOVERIES_DIRNAME)
                        os.makedirs(fav_dir, exist_ok=True)
                        filename = os.path.basename(old_path)
                        new_path = os.path.join(fav_dir, filename)
                        shutil.move(old_path, new_path)

                        target_rec["file_path"] = new_path
                        if db:
                            track = db.query(Track).filter(Track.id == track_id).first()
                            if track:
                                track.file_path = new_path
                                track.is_discovery = False
                                db.commit()
                        safe_print(f"[DiscoveryBuffer] [❤️] Трек {target_rec.get('artist')} - {target_rec.get('title')} навсегда перенесен в основную фонотеку: {new_path}")
                    except Exception as me:
                        safe_print(f"[DiscoveryBuffer] Ошибка перемещения файла: {me}")
                elif db:
                    track = db.query(Track).filter(Track.id == track_id).first()
                    if track:
                        track.is_discovery = False
                        db.commit()

                # Закрепляем лайк в таблице UserReaction базы данных
                if db:
                    reaction = db.query(UserReaction).filter(UserReaction.track_id == track_id).first()
                    if not reaction:
                        db.add(UserReaction(track_id=track_id, is_liked=True, is_disliked=False))
                    else:
                        reaction.is_liked = True
                        reaction.is_disliked = False
                    db.commit()

                self.save_history(records)

                # Запускаем фоновый апгрейд качества трека по лайку (в первую очередь P2P P2P)
                self.trigger_background_upgrade(
                    track_id=track_id,
                    artist=target_rec.get("artist"),
                    title=target_rec.get("title")
                )
                return True

            elif is_disliked:
                # При дизлайке удаляем трек немедленно, не дожидаясь 3 дней
                old_path = target_rec.get("file_path")
                if old_path and os.path.exists(old_path):
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass
                if db:
                    track = db.query(Track).filter(Track.id == track_id).first()
                    if track:
                        try:
                            db.delete(track)
                            db.commit()
                        except Exception as de:
                            db.rollback()
                            safe_print(f"[DiscoveryBuffer] Ошибка удаления трека {track_id} из БД: {de}")

                target_rec["status"] = "disliked_deleted"
                target_rec["deleted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.save_history(records)
                safe_print(f"[DiscoveryBuffer] [💔] Трек {target_rec.get('artist')} - {target_rec.get('title')} удален из буфера по дизлайку.")
                return True

            else:
                # Снятие лайка или дизлайка — не удаляем файл и запись
                target_rec["liked"] = False
                self.save_history(records)
                safe_print(f"[DiscoveryBuffer] Реакция снята для трека {target_rec.get('artist')} - {target_rec.get('title')}.")
                return True

    def handle_track_deletion(self, track_id: int):
        """
        Обновляет статус трека в истории потока (stream_history.json) при ручном удалении пользователем.
        """
        self.history.handle_track_deletion(track_id)

    def update_track_path(self, track_id: int, new_path: str):
        """
        Обновляет путь к файлу трека в stream_history.json при его перемещении или апгрейде качества.
        """
        self.history.update_track_path(track_id, new_path)

    def cleanup_expired_tracks(self, db: Session) -> int:
        """
        Проверяет срок жизни нелайкнутых треков (TTL = 3 дня).
        Удаляет файл с диска и запись из БД, но сохраняет метаданные в журнале навсегда.
        """
        return self.cleaner.cleanup_expired_tracks(db, self.history)

    def refill_buffer(self, db: Session):
        """
        Проверяет наполненность буфера и докачивает до TARGET_BUFFER_SIZE (2-3 трека).
        """
        self.refiller.refill_buffer(
            db=db,
            history=self.history,
            buffer_subdir=self.BUFFER_SUBDIR,
            target_size=self.TARGET_BUFFER_SIZE,
            sync_callback=self.sync_buffer_files
        )

    def trigger_background_refill(self):
        """Запускает дозаполнение буфера в отдельном фоновом потоке."""
        self.refiller.trigger_background_refill(
            session_factory=self.session_factory,
            refill_fn=self.refill_buffer
        )

    def trigger_background_upgrade(self, track_id: int, artist: Optional[str], title: Optional[str]):
        """
        Фоновый поиск и апгрейд качества трека по лайку (в первую очередь P2P).
        """
        self.refiller.trigger_background_upgrade(
            track_id=track_id,
            artist=artist,
            title=title,
            destination=SAVED_DISCOVERIES_DIRNAME
        )

    def backfill_main_folder_likes(self, db: Session) -> int:
        """
        Проставляет статус 'лайкнуто' (is_liked=True) по умолчанию для всех треков,
        находящихся в основной папке фонотеки (вне временного discovery_buffer).
        """
        return self.cleaner.backfill_main_folder_likes(db, self.BUFFER_SUBDIR)

    def start_worker(self):
        """Запускает периодический фоновый цикл очистки устаревших треков и синхронизации."""
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()

        def _loop():
            # При запуске сервера единоразово проставляем лайки для всех треков основной папки
            if self.session_factory:
                try:
                    with self.session_factory() as db:
                        self.backfill_main_folder_likes(db)
                except Exception as be:
                    safe_print(f"[DiscoveryBuffer] Ошибка первичного авто-лайка фонотеки: {be}")

            while not self._stop_event.is_set():
                if self.session_factory:
                    try:
                        db = self.session_factory()
                        try:
                            self.cleanup_expired_tracks(db)
                            self.sync_buffer_files(db)
                        finally:
                            db.close()
                    except Exception as e:
                        safe_print(f"[DiscoveryBufferWorker Error]: {e}")

                # Проверка каждые 60 секунд
                for _ in range(60):
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)

        self._worker_thread = threading.Thread(target=_loop, daemon=True, name="DiscoveryBufferJanitor")
        self._worker_thread.start()
        safe_print("[DiscoveryBuffer] Фоновый воркер очистки и синхронизации буфера запущен.")

    def stop_worker(self):
        """Останавливает фоновый воркер."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)


# Глобальный синглтон менеджера буфера открытий
discovery_buffer_manager = DiscoveryBufferManager()
