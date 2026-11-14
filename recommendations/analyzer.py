import os
import time
import threading
import concurrent.futures
from typing import Dict, Any, Optional, Set, List
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, not_, case

from database.models import Track
from database.db import SessionLocal
from recommendations.embeddings import extract_audio_features, serialize_vector
from recommendations.loudness import measure_track_loudness
from recommendations.mood import apply_mood_filter


class LibraryAnalyzer:
    """
    Фоновый воркер для психоакустического анализа фонотеки:
    - Извлекает BPM, Energy, Valence, Danceability для всех треков
    - Выполняет параллельный анализ с контролем пула воркеров (Zero Audio Stutter)
    - Ведет учет статистики, прогресса и распределения по настроениям
    """

    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._failed_track_ids: Set[int] = set()
        self._active_jobs: Dict[int, str] = {}

        self.max_workers = min(4, max(1, (os.cpu_count() or 2) - 1))
        self.is_running = False
        self.total_tracks = 0
        self.analyzed_count = 0
        self.current_track: Optional[str] = None
        self.errors_count = 0
        self.last_started_at: Optional[float] = None
        self.last_completed_at: Optional[float] = None

    def start_analysis(self, batch_size: int = 25, max_workers: Optional[int] = None) -> bool:
        """Запускает фоновый анализ треков, у которых еще не рассчитаны характеристики."""
        with self._lock:
            if self.is_running:
                return False
            self.is_running = True
            self._stop_event.clear()
            self._failed_track_ids.clear()
            self._active_jobs.clear()
            if max_workers is not None and max_workers > 0:
                self.max_workers = max_workers
            else:
                self.max_workers = min(4, max(1, (os.cpu_count() or 2) - 1))
            self.last_started_at = time.time()

        self._thread = threading.Thread(
            target=self._worker_loop,
            args=(batch_size,),
            name="LibraryAnalyzerWorker",
            daemon=True
        )
        self._thread.start()
        print(f"[Analyzer] Фоновый анализ фонотеки запущен (воркеров: {self.max_workers})...")
        return True

    def stop_analysis(self):
        """Останавливает фоновый анализ."""
        self._stop_event.set()
        with self._lock:
            self.is_running = False
            self._active_jobs.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            self._thread = None
        print("[Analyzer] Фоновый анализ остановлен.")

    def _apply_audio_features(self, track: Track):
        """Извлекает аудиохарактеристики и нормализацию громкости, гарантируя валидные значения."""
        file_path = track.file_path
        features = None
        loudness = None

        # 1. Музыкальные и психоакустические характеристики (BPM, Energy, Valence)
        if track.bpm is None or track.energy is None or track.valence is None:
            try:
                if file_path and os.path.exists(file_path):
                    features = extract_audio_features(file_path)
            except Exception as fe:
                print(f"[Analyzer] Ошибка извлечения признаков {file_path}: {fe}")

            if not features:
                features = {
                    "bpm": 120.0,
                    "energy": 0.5,
                    "valence": 0.5,
                    "danceability": 0.5,
                    "vector": [0.667, 0.5, 0.5, 0.5] + [0.0] * 12
                }

            track.bpm = features["bpm"]
            track.energy = features["energy"]
            track.valence = features["valence"]
            track.danceability = features["danceability"]
            track.embedding_json = serialize_vector(features["vector"])

        # 2. Нормализация громкости ITU-R BS.1770 / EBU R128 (LUFS, Gain, True Peak)
        if track.loudness_lufs is None:
            try:
                if file_path and os.path.exists(file_path):
                    loudness = measure_track_loudness(file_path)
            except Exception as le:
                print(f"[Analyzer] Ошибка замера громкости {file_path}: {le}")

            if loudness:
                track.loudness_lufs = loudness["loudness_lufs"]
                track.gain_db = loudness["gain_db"]
                track.peak_db = loudness["peak_db"]
            else:
                track.loudness_lufs = -14.0
                track.gain_db = 0.0
                track.peak_db = -1.0

    def _process_single_track(self, track_id: int):
        """Обрабатывает один трек с немедленной фиксацией в БД (Real-time Progress & Crash Resilience)."""
        if self._stop_event.is_set():
            return

        db: Session = self.session_factory()
        try:
            track = db.query(Track).filter(Track.id == track_id).first()
            if not track:
                return

            label = f"{track.artist} - {track.title}"
            with self._lock:
                self._active_jobs[track_id] = label
                self.current_track = label

            self._apply_audio_features(track)
            db.commit()

            with self._lock:
                self.analyzed_count += 1
                self._active_jobs.pop(track_id, None)
        except Exception as e:
            db.rollback()
            with self._lock:
                self.errors_count += 1
                self._failed_track_ids.add(track_id)
                self._active_jobs.pop(track_id, None)
            print(f"[Analyzer Error]: Не удалось зафиксировать трек #{track_id}: {e}")
        finally:
            db.close()

    def _worker_loop(self, batch_size: int):
        try:
            while not self._stop_event.is_set():
                with self.session_factory() as db:
                    query = db.query(Track.id).filter(or_(
                        Track.bpm.is_(None),
                        Track.energy.is_(None),
                        Track.valence.is_(None),
                        Track.loudness_lufs.is_(None)
                    ))
                    with self._lock:
                        failed = set(self._failed_track_ids)
                    if failed:
                        query = query.filter(~Track.id.in_(failed))

                    track_ids = [row[0] for row in query.order_by(Track.id.asc()).limit(batch_size).all()]

                if not track_ids:
                    with self._lock:
                        self.is_running = False
                        self.last_completed_at = time.time()
                        self.current_track = None
                        self._active_jobs.clear()
                    print("[Analyzer] Все треки в фонотеке успешно проанализированы!")
                    break

                # Параллельная обработка пакета треков
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {executor.submit(self._process_single_track, tid): tid for tid in track_ids}
                    for future in concurrent.futures.as_completed(futures):
                        if self._stop_event.is_set():
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        try:
                            future.result()
                        except Exception as fe:
                            tid = futures[future]
                            print(f"[Analyzer Error]: Непредвиденная ошибка воркера для трека #{tid}: {fe}")

                time.sleep(0.01)

        finally:
            with self._lock:
                self.is_running = False
                self.current_track = None
                self._active_jobs.clear()

    def analyze_single_track(self, track_id: int, db: Session) -> Optional[Track]:
        """Анализирует один трек и сохраняет характеристики и громкость в БД."""
        track = db.query(Track).filter(Track.id == track_id).first()
        if not track:
            return None

        try:
            self._apply_audio_features(track)
            db.commit()
            db.refresh(track)
            return track
        except Exception as e:
            db.rollback()
            print(f"[Analyzer] Ошибка при анализе трека #{track_id}: {e}")
            return None

    def get_status(self, db: Session) -> Dict[str, Any]:
        """Возвращает актуальный статус анализа и распределение фонотеки по настроениям."""
        energy_cond = or_(
            Track.bpm >= 118.0,
            Track.loudness_lufs >= -7.2,
            and_(Track.bpm >= 100.0, Track.danceability >= 0.75)
        )
        chill_cond = and_(
            func.coalesce(Track.loudness_lufs, -9.0) <= -7.5,
            or_(
                and_(Track.loudness_lufs <= -10.2, Track.bpm <= 115.0),
                and_(Track.bpm <= 92.0, Track.danceability <= 0.60),
                Track.energy <= 0.65
            )
        )
        happy_cond = or_(
            and_(Track.danceability >= 0.66, Track.bpm >= 100.0),
            and_(Track.valence >= 0.52, Track.bpm >= 80.0)
        )
        sad_cond = and_(
            not_(and_(Track.bpm >= 125.0, Track.danceability >= 0.70)),
            or_(
                and_(Track.valence <= 0.45, Track.bpm <= 118.0, func.coalesce(Track.loudness_lufs, -9.0) <= -7.0),
                and_(Track.bpm <= 95.0, Track.danceability <= 0.65, Track.valence <= 0.50)
            )
        )

        row = (
            db.query(
                func.count(Track.id).label("total"),
                func.count(case(((Track.bpm.is_not(None)) & (Track.energy.is_not(None)) & (Track.loudness_lufs.is_not(None)), Track.id))).label("analyzed"),
                func.count(case((energy_cond, Track.id))).label("energy"),
                func.count(case((chill_cond, Track.id))).label("chill"),
                func.count(case((happy_cond, Track.id))).label("happy"),
                func.count(case((sad_cond, Track.id))).label("sad")
            )
            .filter(Track.is_discovery == False)
            .first()
        )

        total = row.total if row else 0
        analyzed = row.analyzed if row else 0
        unanalyzed = max(0, total - analyzed)
        energy_count = row.energy if row else 0
        chill_count = row.chill if row else 0
        happy_count = row.happy if row else 0
        sad_count = row.sad if row else 0

        with self._lock:
            running = self.is_running
            current = self.current_track
            active_jobs = list(self._active_jobs.values())
            errors = self.errors_count
            workers = self.max_workers if running else 0

        progress_pct = round((analyzed / total * 100.0), 1) if total > 0 else 100.0

        return {
            "is_running": running,
            "total_tracks": total,
            "analyzed_tracks": analyzed,
            "unanalyzed_tracks": unanalyzed,
            "progress_percent": progress_pct,
            "current_track": current,
            "current_tracks": active_jobs,
            "active_workers": workers,
            "errors_count": errors,
            "moods": {
                "energy": energy_count,
                "chill": chill_count,
                "happy": happy_count,
                "sad": sad_count
            }
        }


# Глобальный инстанс анализатора
library_analyzer = LibraryAnalyzer()
