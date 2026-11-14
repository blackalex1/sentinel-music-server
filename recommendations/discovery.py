import time
import json
import requests
import urllib.parse
import threading
import base64
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models import Track, UserReaction, PlayHistory
from recommendations.mood import apply_mood_filter
from recommendations.collaborative import collab_graph_client


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

    def get_seed_artists(self, db: Session, limit: int = 5, mood: Optional[str] = None) -> List[str]:
        """Определяет ключевых исполнителей вкусового профиля пользователя с учетом настроения."""
        seeds = []
        active_mood = mood if (mood and mood not in ("default", "all")) else None

        # 1. Сначала проверяем лайки пользователя (с фильтром настроения, если задано)
        if active_mood:
            liked_mood_q = (
                db.query(Track.artist)
                .join(UserReaction, UserReaction.track_id == Track.id)
                .filter(UserReaction.is_liked == True)
            )
            liked_mood_artists = (
                apply_mood_filter(liked_mood_q, active_mood)
                .group_by(Track.artist)
                .order_by(func.count(Track.id).desc())
                .limit(limit)
                .all()
            )
            seeds = [a[0] for a in liked_mood_artists if a[0]]

        if len(seeds) < limit:
            liked_artists = (
                db.query(Track.artist)
                .join(UserReaction, UserReaction.track_id == Track.id)
                .filter(UserReaction.is_liked == True)
                .group_by(Track.artist)
                .order_by(func.count(Track.id).desc())
                .limit(limit)
                .all()
            )
            for a in liked_artists:
                if a[0] and a[0] not in seeds:
                    seeds.append(a[0])

        if len(seeds) >= 3:
            return seeds[:limit]

        # 2. Если лайков мало, проверяем историю прослушиваний
        if active_mood and len(seeds) < limit:
            history_mood_q = (
                db.query(Track.artist)
                .join(PlayHistory, PlayHistory.track_id == Track.id)
            )
            history_mood_artists = (
                apply_mood_filter(history_mood_q, active_mood)
                .group_by(Track.artist)
                .order_by(func.count(PlayHistory.id).desc())
                .limit(limit)
                .all()
            )
            for a in history_mood_artists:
                if a[0] and a[0] not in seeds:
                    seeds.append(a[0])

        if len(seeds) < limit:
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
        if active_mood and len(seeds) < limit:
            top_library_mood_q = apply_mood_filter(db.query(Track.artist), active_mood)
            top_library_mood = (
                top_library_mood_q
                .group_by(Track.artist)
                .order_by(func.count(Track.id).desc())
                .limit(limit)
                .all()
            )
            for a in top_library_mood:
                if a[0] and a[0] not in seeds:
                    seeds.append(a[0])

        if len(seeds) < limit:
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

        if not seeds:
            mood_defaults = {
                "energy": ["The Prodigy", "Metallica", "Skrillex", "AC/DC", "Linkin Park"],
                "chill": ["Bonobo", "Tycho", "Massive Attack", "Norah Jones", "Moby"],
                "happy": ["Pharrell Williams", "Bruno Mars", "Daft Punk", "Earth, Wind & Fire", "Dua Lipa"],
                "sad": ["Radiohead", "Adele", "Lana Del Rey", "Billie Eilish", "Coldplay"],
            }
            seeds = mood_defaults.get(active_mood, ["Queen", "The Weeknd", "Daft Punk", "Nirvana", "Michael Jackson"])

        return seeds[:limit]

    def get_seed_tracks(self, db: Session, limit: int = 5, mood: Optional[str] = None) -> List[Tuple[str, str]]:
        """Определяет ключевые композиции вкусового профиля пользователя (артист, название)."""
        seeds: List[Tuple[str, str]] = []
        active_mood = mood if (mood and mood not in ("default", "all")) else None

        # 1. Лайкнутые треки
        liked_q = (
            db.query(Track.artist, Track.title)
            .join(UserReaction, UserReaction.track_id == Track.id)
            .filter(UserReaction.is_liked == True)
        )
        if active_mood:
            liked_q = apply_mood_filter(liked_q, active_mood)
        liked_tracks = liked_q.limit(limit).all()
        for a, t in liked_tracks:
            if a and t:
                seeds.append((a.strip(), t.strip()))

        if len(seeds) >= limit:
            return seeds[:limit]

        # 2. Часто прослушиваемые треки
        hist_q = (
            db.query(Track.artist, Track.title)
            .join(PlayHistory, PlayHistory.track_id == Track.id)
            .filter(PlayHistory.completed == True)
        )
        if active_mood:
            hist_q = apply_mood_filter(hist_q, active_mood)
        hist_tracks = (
            hist_q
            .group_by(Track.artist, Track.title)
            .order_by(func.count(PlayHistory.id).desc())
            .limit(limit)
            .all()
        )
        for a, t in hist_tracks:
            if a and t:
                pair = (a.strip(), t.strip())
                if pair not in seeds:
                    seeds.append(pair)
                    if len(seeds) >= limit:
                        break

        return seeds[:limit]

    def _fetch_candidates_from_network(
        self,
        seed_artists: List[str],
        db: Session,
        seed_tracks: Optional[List[Tuple[str, str]]] = None
    ) -> List[Dict[str, Any]]:
        """Запрашивает глобальный музыкальный граф и отбирает новые треки, отсутствующие в фонотеке."""
        new_candidates = []
        headers = {"User-Agent": "SentinelMusic/2.0"}
        api_base = base64.b64decode("aHR0cHM6Ly9hcGkuZGVlemVyLmNvbQ==").decode("utf-8")
        seen_keys = set()

        # 1. Сначала опрашиваем коллаборативный граф ассоциаций треков (высокая точность)
        active_seed_tracks = seed_tracks if seed_tracks is not None else self.get_seed_tracks(db, limit=4)
        for seed_art, seed_tit in active_seed_tracks:
            try:
                similars = collab_graph_client.get_similar_tracks(seed_art, seed_tit, limit=6)
                for item in similars:
                    c_art = item.get("artist", "").strip()
                    c_tit = item.get("title", "").strip()
                    c_match = float(item.get("match", 0.5))
                    if not c_art or not c_tit:
                        continue

                    key = f"{c_art.lower()} - {c_tit.lower()}"
                    if key in seen_keys:
                        continue

                    existing = (
                        db.query(Track.id)
                        .filter(
                            Track.artist.ilike(f"%{c_art}%"),
                            Track.title.ilike(f"%{c_tit}%")
                        )
                        .first()
                    )
                    if existing:
                        continue

                    seen_keys.add(key)
                    preview_url = None
                    cover_url = None
                    album_title = "Discovery Single"
                    duration = 30.0

                    try:
                        q_str = urllib.parse.quote(f"{c_art} {c_tit}")
                        s_resp = requests.get(f"{api_base}/search?q={q_str}&limit=1", headers=headers, timeout=3.0)
                        if s_resp.status_code == 200:
                            s_data = s_resp.json().get("data", [])
                            if s_data:
                                top_match = s_data[0]
                                preview_url = top_match.get("preview")
                                cover_url = top_match.get("album", {}).get("cover_medium") or top_match.get("album", {}).get("cover_big")
                                album_title = top_match.get("album", {}).get("title") or album_title
                                duration = float(top_match.get("duration", 30.0))
                    except Exception:
                        pass

                    reason = f"Ассоциация с «{seed_tit}» (схожесть {int(c_match * 100)}%)"
                    candidate = {
                        "id": -(1000 + len(new_candidates) + 1),
                        "title": c_tit,
                        "artist": c_art,
                        "album": album_title,
                        "duration": duration,
                        "audio_format": "mp3",
                        "file_path": preview_url,
                        "preview_url": preview_url,
                        "cover_url": cover_url,
                        "is_discovery": True,
                        "is_preview": True,
                        "discovery_reason": reason,
                        "collab_match": c_match
                    }
                    new_candidates.append(candidate)
                    if len(new_candidates) >= 12:
                        break
            except Exception:
                continue

        # 2. Если кандидатов из коллаборативного графа пока мало — дополняем графом связанных артистов
        if len(new_candidates) < 8:
            for seed in seed_artists:
                try:
                    q = urllib.parse.quote(seed)
                    url = f"{api_base}/search/artist?q={q}"
                    resp = requests.get(url, headers=headers, timeout=4)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    artists = data.get("data", [])
                    if not artists:
                        continue

                    exact_matches = [a for a in artists if a.get("name", "").strip().lower() == seed.strip().lower()]
                    chosen = max(exact_matches, key=lambda a: a.get("nb_fan", 0)) if exact_matches else max(artists, key=lambda a: a.get("nb_fan", 0))

                    artist_id = chosen["id"]
                    seed_name = chosen["name"]

                    rel_url = f"{api_base}/artist/{artist_id}/related"
                    resp_rel = requests.get(rel_url, headers=headers, timeout=4)
                    if resp_rel.status_code != 200:
                        continue
                    rel_data = resp_rel.json()

                    related_artists = rel_data.get("data", [])[:4]
                    target_artists = [{"id": artist_id, "name": seed_name}] + related_artists

                    for rel in target_artists:
                        rel_id = rel.get("id")
                        rel_name = rel.get("name")
                        if not rel_id or not rel_name:
                            continue

                        top_url = f"{api_base}/artist/{rel_id}/top?limit=5"
                        resp_top = requests.get(top_url, headers=headers, timeout=4)
                        if resp_top.status_code != 200:
                            continue
                        top_data = resp_top.json()

                        for item in top_data.get("data", []):
                            track_title = item.get("title", "").strip()
                            preview_url = item.get("preview")
                            if not track_title or not preview_url:
                                continue

                            key = f"{rel_name.lower()} - {track_title.lower()}"
                            if key in seen_keys:
                                continue

                            existing = (
                                db.query(Track.id)
                                .filter(
                                    Track.artist.ilike(f"%{rel_name}%"),
                                    Track.title.ilike(f"%{track_title}%")
                                )
                                .first()
                            )
                            if existing:
                                continue

                            seen_keys.add(key)
                            reason = f"Похоже на {seed_name}" if rel_name != seed_name else f"Открытие от {seed_name}"
                            candidate = {
                                "id": -(1000 + len(new_candidates) + 1),
                                "title": track_title,
                                "artist": rel_name,
                                "album": item.get("album", {}).get("title", "Discovery Single"),
                                "duration": float(item.get("duration", 30.0)),
                                "audio_format": "mp3",
                                "file_path": preview_url,
                                "preview_url": preview_url,
                                "cover_url": item.get("album", {}).get("cover_medium") or item.get("album", {}).get("cover_big"),
                                "is_discovery": True,
                                "is_preview": True,
                                "discovery_reason": reason,
                                "collab_match": 0.5
                            }
                            new_candidates.append(candidate)
                            if len(new_candidates) >= 20:
                                break
                except Exception:
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
                    seed_tracks = self.get_seed_tracks(db, limit=4)
                    try:
                        candidates = self._fetch_candidates_from_network(seeds, db, seed_tracks=seed_tracks)
                    except TypeError:
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

    def get_discovery_candidate(
        self,
        db: Session,
        mood: Optional[str] = "default",
        session_factory=None,
        allow_preview_fallback: bool = True,
        only_network: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Возвращает один трек-открытие:
        1. Сначала отдает треки-кандидаты из внешнего музыкального графа и коллаборативного пула.
        2. При only_network=True гарантирует, что трек НИКОГДА не будет взят из локальной фонотеки.
        3. Если only_network=False и сеть недоступна, может вернуть непрослушанный трек из фонотеки.
        """
        # Проверяем наличие плагинов скачивания
        has_ingestion = True
        try:
            from plugin_system.manager import plugin_manager
            has_ingestion = plugin_manager.has_ingestion_plugins()
        except Exception:
            has_ingestion = True

        now = time.time()
        with self._lock:
            # Если кэш пуст — пытаемся получить кандидатов из сети прямо сейчас
            if not self._cache_candidates:
                seeds = self.get_seed_artists(db, mood=mood)
                seed_tracks = self.get_seed_tracks(db, limit=4, mood=mood)
                try:
                    self._cache_candidates = self._fetch_candidates_from_network(seeds, db, seed_tracks=seed_tracks)
                except TypeError:
                    self._cache_candidates = self._fetch_candidates_from_network(seeds, db)
                self._last_refresh_ts = now
            elif now - self._last_refresh_ts > self._cache_ttl and session_factory:
                self.refresh_cache_in_background(session_factory)

            # 1. Извлекаем кандидата из сети
            while self._cache_candidates:
                cand = dict(self._cache_candidates.pop(0))
                # Проверяем, чтобы трека не было в локальной фонотеке
                existing = (
                    db.query(Track.id)
                    .filter(
                        Track.artist.ilike(f"%{cand.get('artist', '')}%"),
                        Track.title.ilike(f"%{cand.get('title', '')}%")
                    )
                    .first()
                )
                if not existing:
                    cand["is_preview"] = True
                    reason_base = cand.get("discovery_reason", "Новая музыка")
                    if not has_ingestion:
                        cand["discovery_reason"] = f"30с демо (нет плагинов скачивания) • {reason_base}"
                    elif "30с демо" not in reason_base:
                        cand["discovery_reason"] = f"30с демо (пока буфер загружается) • {reason_base}"
                    return cand

        # Если запрошены строго треки из интернета (например, 100% новое) — никогда не берем треки из медиатеки!
        if only_network:
            return None

        # Фоллбэк (только если не строгий режим): выбираем неслушанный трек из локальной фонотеки
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
