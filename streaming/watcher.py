"""
Модуль фонового мониторинга файловой системы (Watchdog).
Автоматически обнаруживает новые аудиозаписи при скачивании или перемещении,
дебаунсит процесс записи на диск и индексирует треки в базе данных.
"""

import os
import time
import threading
from typing import Optional, Callable, Dict, Tuple
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from database.db import SessionLocal
from streaming.scanner import scan_single_file

SUPPORTED_AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".wav", ".ogg"}


class MusicEventHandler(FileSystemEventHandler):
    """Слушатель событий файловой системы для фонотеки."""

    def __init__(self, watcher: "MusicLibraryWatcher"):
        super().__init__()
        self.watcher = watcher

    def _is_audio(self, path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in SUPPORTED_AUDIO_EXTS

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory and self._is_audio(event.src_path):
            self.watcher.queue_file(event.src_path)

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory and self._is_audio(event.src_path):
            self.watcher.queue_file(event.src_path)

    def on_deleted(self, event: FileSystemEvent):
        if not event.is_directory and self._is_audio(event.src_path):
            self.watcher.handle_deleted_file(event.src_path)

    def on_moved(self, event: FileSystemEvent):
        dest_path = getattr(event, "dest_path", None)
        if not event.is_directory and self._is_audio(event.src_path) and dest_path and self._is_audio(dest_path):
            self.watcher.handle_moved_file(event.src_path, dest_path)
        else:
            if not event.is_directory and self._is_audio(event.src_path):
                self.watcher.handle_deleted_file(event.src_path)
            if not event.is_directory and dest_path and self._is_audio(dest_path):
                self.watcher.queue_file(dest_path)


class MusicLibraryWatcher:
    """
    Управляет наблюдателем Watchdog и пулом отложенной обработки файлов.
    Предотвращает чтение недокачанных / частично записанных файлов через дебаунсинг.
    """

    def __init__(
        self,
        music_dir: Optional[str] = None,
        debounce_seconds: float = 2.0,
        session_factory=SessionLocal
    ):
        self.music_dir = os.path.abspath(music_dir) if music_dir else None
        self.debounce_seconds = debounce_seconds
        self.session_factory = session_factory

        self._observer: Optional[Observer] = None
        self._pending_files: Dict[str, Tuple[float, int]] = {}  # path -> (last_seen_ts, file_size)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._callbacks = []
        self._last_indexed_at = None
        self._last_indexed_track = None

    def add_callback(self, cb: Callable[[str], None]):
        """Регистрирует callback-функцию при успешном добавлении трека."""
        self._callbacks.append(cb)

    def queue_file(self, file_path: str):
        """Добавляет или обновляет файл в очереди ожидания стабилизации."""
        abs_path = os.path.abspath(file_path)
        try:
            size = os.path.getsize(abs_path) if os.path.exists(abs_path) else 0
        except OSError:
            size = 0

        with self._lock:
            self._pending_files[abs_path] = (time.time(), size)

    def handle_deleted_file(self, file_path: str):
        """Обрабатывает удаление аудиофайла с диска (например, через rm в терминале)."""
        abs_path = os.path.abspath(file_path)
        with self._lock:
            if abs_path in self._pending_files:
                del self._pending_files[abs_path]

        # Если файл всё ещё существует (или был перезаписан/заменен в рамках атомарной перезаписи) — не удаляем
        if os.path.exists(abs_path) or os.path.exists(file_path):
            return

        db = self.session_factory()
        try:
            from database.models import Track, PlayHistory, UserReaction, PlaylistTrack
            from streaming.streamer import is_track_streaming

            track = db.query(Track).filter(
                (Track.file_path == abs_path) | (Track.file_path == file_path)
            ).first()

            if track:
                # Если файл трека уже указывает на другой существующий путь (например, перенесен в Saved_Discoveries или обновлен) — не удаляем!
                if track.file_path != abs_path and track.file_path != file_path and os.path.exists(track.file_path):
                    return

                # Если трек прямо сейчас воспроизводится у пользователя — не удаляем его из базы
                if is_track_streaming(track.id, file_path=abs_path):
                    return

                t_id = track.id
                artist = track.artist
                title = track.title

                db.query(PlayHistory).filter(PlayHistory.track_id == t_id).delete()
                db.query(UserReaction).filter(UserReaction.track_id == t_id).delete()
                db.query(PlaylistTrack).filter(PlaylistTrack.track_id == t_id).delete()

                try:
                    from recommendations.buffer_manager import discovery_buffer_manager
                    discovery_buffer_manager.handle_track_deletion(t_id)
                except Exception:
                    pass

                db.delete(track)
                db.commit()
                print(f"[Watchdog] [🗑️] Аудиофайл удален с диска (rm). Трек исключен из БД: {artist} - {title}")
        except Exception as e:
            db.rollback()
            print(f"[Watchdog] Ошибка удаления трека при удалении файла {file_path}: {e}")
        finally:
            db.close()

    def handle_moved_file(self, src_path: str, dest_path: str):
        """Обрабатывает перемещение или переименование аудиофайла без удаления трека и истории."""
        abs_src = os.path.abspath(src_path)
        abs_dest = os.path.abspath(dest_path)
        with self._lock:
            if abs_src in self._pending_files:
                del self._pending_files[abs_src]

        db = self.session_factory()
        try:
            from database.models import Track
            track = db.query(Track).filter(
                (Track.file_path == abs_src) | (Track.file_path == src_path)
            ).first()

            if track:
                track.file_path = abs_dest
                db.commit()
                print(f"[Watchdog] [Перемещение] Путь к файлу трека #{track.id} ({track.artist} - {track.title}) обновлен: {abs_dest}")
                try:
                    from recommendations.buffer_manager import discovery_buffer_manager
                    discovery_buffer_manager.update_track_path(track.id, abs_dest)
                except Exception:
                    pass
            else:
                self.queue_file(abs_dest)
        except Exception as e:
            db.rollback()
            print(f"[Watchdog] Ошибка обновления пути при перемещении {src_path} -> {dest_path}: {e}")
        finally:
            db.close()

    def process_pending_files(self) -> int:
        """
        Проверяет стабилизировавшиеся файлы и индексирует их в БД.
        Может вызываться вручную или фоновым рабочим циклом.
        """
        now = time.time()
        to_process = []

        with self._lock:
            for path, (last_ts, last_size) in list(self._pending_files.items()):
                if now - last_ts < self.debounce_seconds:
                    continue

                if not os.path.exists(path):
                    del self._pending_files[path]
                    continue

                try:
                    current_size = os.path.getsize(path)
                    # Если размер изменился, файл еще пишется
                    if current_size != last_size or current_size == 0:
                        self._pending_files[path] = (now, current_size)
                        continue

                    # Проверка возможности открыть файл для чтения
                    with open(path, "rb"):
                        pass

                    to_process.append(path)
                    del self._pending_files[path]
                except (OSError, PermissionError):
                    # Файл занят другим процессом (например, идет фоновая запись загрузчика), ждем следующий цикл
                    self._pending_files[path] = (now, last_size)

        indexed_count = 0
        if to_process:
            db = self.session_factory()
            try:
                for path in to_process:
                    track = scan_single_file(path, db)
                    if track:
                        indexed_count += 1
                        with self._lock:
                            self._last_indexed_at = time.time()
                            self._last_indexed_track = {
                                "id": track.id,
                                "artist": track.artist,
                                "title": track.title
                            }
                        print(f"[Watchdog] Новый трек проиндексирован: {track.artist} - {track.title}")

                        # Автоматический психоакустический анализ признаков нового трека
                        try:
                            from recommendations.analyzer import library_analyzer
                            library_analyzer.analyze_single_track(track.id, db)
                        except Exception as ae:
                            print(f"[Watchdog] Не удалось извлечь аудиохарактеристики: {ae}")

                        for cb in self._callbacks:
                            try:
                                cb(path)
                            except Exception as e:
                                print(f"[Watchdog] Ошибка в callback: {e}")
            finally:
                db.close()

        return indexed_count

    def _worker_loop(self):
        """Фоновый цикл обработки стабилизировавшихся файлов."""
        while not self._stop_event.is_set():
            try:
                self.process_pending_files()
            except Exception as e:
                print(f"[Watchdog Worker Error]: {e}")
            time.sleep(1.0)

    def start(self, music_dir: Optional[str] = None, debounce_seconds: Optional[float] = None) -> bool:
        """Запускает фоновое наблюдение за каталогом музыки."""
        if music_dir:
            self.music_dir = os.path.abspath(music_dir)
        if debounce_seconds is not None:
            self.debounce_seconds = debounce_seconds

        if not self.music_dir or not os.path.exists(self.music_dir):
            print(f"[Watchdog] Каталог {self.music_dir} не найден, наблюдение не запущено.")
            return False

        if self.is_running():
            return True

        self._stop_event.clear()
        event_handler = MusicEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(event_handler, self.music_dir, recursive=True)
        self._observer.start()

        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="MusicWatchdogWorker")
        self._worker_thread.start()

        print(f"[Watchdog] Наблюдение за фонотекой активно: {self.music_dir} (дебаунс: {self.debounce_seconds}с)")
        return True

    def stop(self):
        """Останавливает наблюдение."""
        self._stop_event.set()
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:
                pass
            self._observer = None

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
            self._worker_thread = None

        with self._lock:
            self._pending_files.clear()

        print("[Watchdog] Наблюдение остановлено.")

    def is_running(self) -> bool:
        """Возвращает текущий статус активности наблюдателя."""
        return self._observer is not None and self._observer.is_alive()

    def status(self) -> dict:
        """Информация о состоянии сервиса автосканирования."""
        with self._lock:
            pending_count = len(self._pending_files)
            last_at = self._last_indexed_at
            last_track = self._last_indexed_track
        return {
            "running": self.is_running(),
            "music_dir": self.music_dir,
            "debounce_seconds": self.debounce_seconds,
            "pending_files_count": pending_count,
            "last_indexed_at": last_at,
            "last_track": last_track
        }


# Глобальный экземпляр для подключения в lifespan приложения
music_watcher = MusicLibraryWatcher()
