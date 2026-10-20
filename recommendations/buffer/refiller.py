import time
import asyncio
import threading
from typing import Optional, Callable
from sqlalchemy.orm import Session

from plugin_system.manager import plugin_manager
from recommendations.discovery import discovery_engine
from recommendations.buffer.constants import safe_print
from recommendations.buffer.history import BufferHistory


class BufferRefiller:
    """
    Отвечает за фоновое пополнение буфера и апгрейд качества треков:
    - Пополнение автономного буфера Потока до TARGET_BUFFER_SIZE (2-3 трека).
    - Фоновый поиск и апгрейд качества трека по лайку через доступные модули импорта.
    """

    def __init__(self, lock: Optional[threading.RLock] = None):
        self._lock = lock or threading.RLock()
        self._is_refilling = False

    @property
    def is_refilling(self) -> bool:
        with self._lock:
            return self._is_refilling

    def refill_buffer(
        self,
        db: Session,
        history: BufferHistory,
        buffer_subdir: str,
        target_size: int,
        sync_callback: Optional[Callable[[Session], None]] = None
    ):
        """
        Проверяет наполненность буфера и докачивает до target_size (2-3 трека).
        """
        with self._lock:
            if self._is_refilling:
                return
            self._is_refilling = True

        try:
            if sync_callback:
                sync_callback(db)

            records = history.load_history()
            buffered_count = sum(1 for r in records if r.get("status") == "buffered")
            needed = target_size - buffered_count

            if needed <= 0:
                return

            # Находим похожих артистов через DiscoveryEngine
            seeds = discovery_engine.get_seed_artists(db)
            candidates = discovery_engine._fetch_candidates_from_network(seeds, db)

            # Собираем список всех названий, которые когда-либо были в Потоке
            history_keys = {
                f"{r.get('artist', '').lower()} - {r.get('title', '').lower()}"
                for r in records
            }

            queued = 0
            for cand in candidates:
                if queued >= needed:
                    break

                artist = cand.get("artist")
                title = cand.get("title")
                key = f"{artist.lower()} - {title.lower()}"

                if key in history_keys:
                    continue

                # Отправляем в очередь загрузки без тяжелых P2P источников для экономии места
                success = asyncio.run(
                    plugin_manager.request_track_import(
                        artist,
                        title,
                        destination=buffer_subdir,
                        exclude_sources=["p2p", "slow"]
                    )
                )

                if success:
                    queued += 1
                    safe_print(f"[DiscoveryBuffer] Предзагрузка MP3 поставлена в очередь (экономия места): {artist} - {title}")
                    # Небольшая пауза между постановками
                    time.sleep(2)

        except Exception as e:
            safe_print(f"[DiscoveryBuffer] Ошибка при дозаполнении буфера: {e}")
        finally:
            with self._lock:
                self._is_refilling = False

    def trigger_background_refill(self, session_factory, refill_fn: Callable[[Session], None]):
        """Запускает дозаполнение буфера в отдельном фоновом потоке."""
        if not session_factory:
            return

        def _worker():
            db = session_factory()
            try:
                refill_fn(db)
            finally:
                db.close()

        t = threading.Thread(target=_worker, daemon=True, name="DiscoveryBufferRefiller")
        t.start()

    def trigger_background_upgrade(
        self,
        track_id: int,
        artist: Optional[str],
        title: Optional[str],
        destination: str = "Saved_Discoveries"
    ):
        """
        Фоновый поиск и апгрейд качества трека по лайку:
        Опрашивает зарегистрированные плагины импорта по их приоритетам для поиска наилучшей HQ/Lossless версии в постоянную фонотеку.
        """
        if not artist or not title:
            return

        def _worker():
            try:
                safe_print(f"[DiscoveryBuffer] [❤️ Upgrade] Запуск поиска HQ/Lossless версии для: {artist} - {title}")
                # Вызываем import без исключений: плагины опрашиваются по порядку приоритета
                success = asyncio.run(
                    plugin_manager.request_track_import(
                        artist=artist,
                        title=title,
                        destination=destination,
                        force_replace=True
                    )
                )
                if success:
                    safe_print(f"[DiscoveryBuffer] [❤️ Upgrade] Трек {artist} - {title} успешно поставлен в очередь загрузки HQ версий")
                else:
                    safe_print(f"[DiscoveryBuffer] [❤️ Upgrade] Альтернативных HQ версий для {artist} - {title} не найдено, сохранена текущая версия из буфера.")
            except Exception as e:
                safe_print(f"[DiscoveryBuffer] Ошибка при фоновом апгрейде трека #{track_id}: {e}")

        t = threading.Thread(target=_worker, daemon=True, name=f"TrackUpgrade_{track_id}")
        t.start()
