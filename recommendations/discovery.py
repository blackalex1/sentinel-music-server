import time
import json
import urllib.request
import urllib.parse
import threading
import base64
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models import Track, UserReaction, PlayHistory
from recommendations.mood import apply_mood_filter


class DiscoveryEngine:
    """
    Движок умных открытий («Новая музыка»):
    - Анализирует музыкальное ядро пользователя (лайки, история, топовые исполнители фонотеки)
    - Находит похожих артистов и их главные хиты через глобальный музыкальный граф
    - Исключает треки, которые уже скачаны в локальную библиотеку
    - Предоставляет поток новых треков с настраиваемой частотой
    """

    def __init__(self):
        self._cache_candidates: List[Dict[str, Any]] = []
        self._last_refresh_ts = 0.0
        self._cache_ttl = 1800  # 30 минут
        self._lock = threading.RLock()
        self._is_refreshing = False

    def get_seed_artists(self, db: Session, limit: int = 5) -> List[str]:
        """Определяет ключевых исполнителей вкусового профиля пользователя."""
        # 1. Сначала проверяем лайки пользователя
        liked_artists = (
            db.query(Track.artist)
            .join(UserReaction, UserReaction.track_id == Track.id)
            .filter(UserReaction.is_liked == True)
            .group_by(Track.artist)
            .order_by(func.count(Track.id).desc())
            .limit(limit)
            .all()
        )
        seeds = [a[0] for a in liked_artists if a[0]]
        if len(seeds) >= 3:
            return seeds[:limit]

        # 2. Если лайков мало, проверяем историю прослушиваний
        history_artists = (
            db.query(Track.artist)
            .join(PlayHistory, PlayHistory.track_id == Track.id)
            .group_by(Track.artist)
            .order_by(func.count(PlayHistory.id).desc())
            .limit(limit)
            .all()
        )
        for a in history_artists:
            if a[0] and a[0] not in seeds:
                seeds.append(a[0])
        if len(seeds) >= 3:
            return seeds[:limit]

        # 3. Базовый фоллбэк: артисты с наибольшим числом треков в библиотеке
        top_library = (
            db.query(Track.artist)
            .group_by(Track.artist)
            .order_by(func.count(Track.id).desc())
            .limit(limit)
            .all()
        )
        for a in top_library:
            if a[0] and a[0] not in seeds:
                seeds.append(a[0])

        return seeds[:limit]

    def _fetch_candidates_from_network(self, seed_artists: List[str], db: Session) -> List[Dict[str, Any]]:
        """Запрашивает граф музыки и отбирает новые треки, отсутствующие в фонотеке."""
        new_candidates = []
        headers = {"User-Agent": "SentinelMusic/1.0"}

        api_base = base64.b64decode("aHR0cHM6Ly9hcGkuZGVlemVyLmNvbQ==").decode("utf-8")

        for seed in seed_artists:
            try:
                # 1. Поиск ID исполнителя
                q = urllib.parse.quote(seed)
                url = f"{api_base}/search/artist?q={q}"
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=4) as resp:
                    data = json.loads(resp.read().decode())
                
                if not data.get("data"):
                    continue

                artist_id = data["data"][0]["id"]
                seed_name = data["data"][0]["name"]

                # 2. Получение связанных исполнителей
                rel_url = f"{api_base}/artist/{artist_id}/related"
                req_rel = urllib.request.Request(rel_url, headers=headers)
                with urllib.request.urlopen(req_rel, timeout=4) as resp_rel:
                    rel_data = json.loads(resp_rel.read().decode())

                related_artists = rel_data.get("data", [])[:3]

                # 3. Топ-хиты найденных артистов
                for rel in related_artists:
                    rel_id = rel.get("id")
                    rel_name = rel.get("name")
                    if not rel_id or not rel_name:
                        continue

                    top_url = f"{api_base}/artist/{rel_id}/top?limit=3"
                    req_top = urllib.request.Request(top_url, headers=headers)
                    with urllib.request.urlopen(req_top, timeout=4) as resp_top:
                        top_data = json.loads(resp_top.read().decode())

                    for item in top_data.get("data", []):
                        track_title = item.get("title", "").strip()
                        preview_url = item.get("preview")
                        if not track_title or not preview_url:
                            continue

                        # 4. Проверяем наличие трека в локальной фонотеке
                        existing = (
                            db.query(Track.id)
                            .filter(
                                Track.artist.ilike(f"%{rel_name}%"),
                                Track.title.ilike(f"%{track_title}%")
                            )
                            .first()
                        )
                        if existing:
                            continue  # Уже есть у пользователя

                        candidate = {
                            "id": -(1000 + len(new_candidates) + 1),  # Отрицательный виртуальный ID
                            "title": track_title,
                            "artist": rel_name,
                            "album": item.get("album", {}).get("title", "Discovery Single"),
                            "duration": float(item.get("duration", 30.0)),
                            "audio_format": "mp3",
                            "file_path": preview_url,
                            "preview_url": preview_url,
                            "cover_url": item.get("album", {}).get("cover_medium") or item.get("album", {}).get("cover_big"),
                            "is_discovery": True,
                            "discovery_reason": f"Похоже на {seed_name}"
                        }
                        new_candidates.append(candidate)

            except Exception as e:
                # Тихо переходим к следующему сид-артисту при сетевой ошибке
                continue

        return new_candidates

    def refresh_cache_in_background(self, db_factory):
        """Фоновое обновление пула открытий без блокировки воспроизведения."""
        with self._lock:
            if self._is_refreshing:
                return
            self._is_refreshing = True

        def _run():
            try:
                db = db_factory()
                try:
                    seeds = self.get_seed_artists(db)
                    candidates = self._fetch_candidates_from_network(seeds, db)
                    with self._lock:
                        if candidates:
                            self._cache_candidates = candidates
                            self._last_refresh_ts = time.time()
                finally:
                    db.close()
            except Exception as e:
                print(f"[Discovery] Ошибка обновления пула: {e}")
            finally:
                with self._lock:
                    self._is_refreshing = False

        t = threading.Thread(target=_run, daemon=True, name="DiscoveryRefresher")
        t.start()

    def get_discovery_candidate(self, db: Session, mood: Optional[str] = "default", session_factory=None) -> Optional[Dict[str, Any]]:
        """
        Возвращает один трек-открытие:
        В режиме «Поток» ВСЕГДА отдаются полные треки (full lossless/audio) без обрывов на 30-секундных превью.
        Выбирает трек из локальной фонотеки, который пользователь еще ни разу не слушал
        (0 записей в PlayHistory), соответствующий выбранному настроению.
        Внешние новинки кэшируются в _cache_candidates для витрины рекомендаций и фонового импорта через P2P.
        """
        now = time.time()
        with self._lock:
            # Фоновое обновление внешнего графа для радара рекомендаций
            if (not self._cache_candidates or now - self._last_refresh_ts > self._cache_ttl) and session_factory:
                self.refresh_cache_in_background(session_factory)

        # Выбираем неслушанный трек из локальной фонотеки
        query = (
            db.query(Track)
            .outerjoin(PlayHistory, PlayHistory.track_id == Track.id)
            .filter(PlayHistory.id.is_(None), Track.is_discovery == False)
        )

        query = apply_mood_filter(query, mood)

        unplayed_local = query.order_by(func.random()).first()

        # Фоллбэк: любой неслушанный трек без фильтра настроения
        if not unplayed_local:
            unplayed_local = (
                db.query(Track)
                .outerjoin(PlayHistory, PlayHistory.track_id == Track.id)
                .filter(PlayHistory.id.is_(None), Track.is_discovery == False)
                .order_by(func.random())
                .first()
            )

        if unplayed_local:
            return {
                "id": unplayed_local.id,
                "title": unplayed_local.title,
                "artist": unplayed_local.artist,
                "album": unplayed_local.album,
                "duration": unplayed_local.duration,
                "audio_format": unplayed_local.audio_format,
                "file_path": unplayed_local.file_path,
                "bpm": unplayed_local.bpm,
                "energy": unplayed_local.energy,
                "valence": unplayed_local.valence,
                "is_discovery": True,
                "discovery_reason": "Открытие из вашей коллекции"
            }

        return None


# Глобальный синглтон движка открытий
discovery_engine = DiscoveryEngine()
