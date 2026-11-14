import math
import random
import datetime
from typing import List, Optional, Union, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from database.models import Track, UserReaction, PlayHistory
from database.vector_index import find_nearest_tracks
from .embeddings import (
    deserialize_vector,
    compute_user_taste_centroid,
    update_session_drift_vector
)
from .discovery import discovery_engine
from .mood import apply_mood_filter


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Вычисляет косинусное сходство между двумя векторами признаков."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0

    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


class VibeEngine:
    """
    Движок умного бесконечного персонального радио («Поток» / Vibe Stream 2.0).
    Психоакустическая модель настроения (Energy x Valence), плавность темпа (DJ Flow),
    персонализация (лайки/дизлайки), сессионный кулдаун и управляемая частота открытий.
    """

    def __init__(self, db: Session, session_factory=None):
        self.db = db
        self.session_factory = session_factory

    def get_next_vibe_track(
        self,
        current_track_id: Optional[int] = None,
        recent_track_ids: Optional[List[int]] = None,
        mood: Optional[str] = "default",
        mood_energy: Optional[float] = None,  # Обратная совместимость
        discovery_ratio: float = 0.2,         # 0.0 - 1.0 (Частота новых треков)
        consecutive_artist: Optional[str] = None,
        consecutive_count: int = 0,
        skipped_artists: Optional[List[str]] = None,
        tz_offset_minutes: int = 0
    ) -> Optional[Union[Track, Dict[str, Any]]]:
        """
        Выбирает следующий трек для потока на основе психоакустических признаков,
        настроения и настраиваемой вероятности внедрения новых треков (Discovery).
        """
        # Определение целевого настроения
        active_mood = mood or "default"
        if active_mood == "default" and mood_energy is not None:
            if mood_energy >= 0.7:
                active_mood = "energy"
            elif mood_energy <= 0.35:
                active_mood = "chill"

        # 1. Проверяем слот для Нового Трека (Discovery)
        # Если discovery_ratio >= 1.0 — это СТРОГИЙ режим: только треки из интернета / буфера открытий!
        if discovery_ratio >= 1.0:
            from .buffer_manager import discovery_buffer_manager
            buffered_track = discovery_buffer_manager.get_next_buffered_track(self.db, mood=active_mood)
            if buffered_track:
                return buffered_track

            cand_discovery = discovery_engine.get_discovery_candidate(
                self.db,
                mood=active_mood,
                session_factory=self.session_factory,
                allow_preview_fallback=True,
                only_network=True
            )
            if self.session_factory:
                discovery_buffer_manager.session_factory = self.session_factory
                discovery_buffer_manager.trigger_background_refill()

            if cand_discovery:
                return cand_discovery

            # В режиме «100% новое» строго запрещено проигрывать локальную медиатеку!
            return None

        # Для промежуточных соотношений (0.0 < discovery_ratio < 1.0)
        should_discover = False
        if discovery_ratio > 0.0 and random.random() < discovery_ratio:
            should_discover = True

        if should_discover:
            from .buffer_manager import discovery_buffer_manager
            buffered_track = discovery_buffer_manager.get_next_buffered_track(self.db, mood=active_mood)
            if buffered_track:
                return buffered_track

            cand_discovery = discovery_engine.get_discovery_candidate(
                self.db,
                mood=active_mood,
                session_factory=self.session_factory,
                allow_preview_fallback=True,
                only_network=False
            )
            if self.session_factory:
                discovery_buffer_manager.session_factory = self.session_factory
                discovery_buffer_manager.trigger_background_refill()

            if cand_discovery:
                return cand_discovery

        # 2. Выборка из локальной фонотеки
        recent_ids = set(recent_track_ids or [])

        # Исключаем дизлайкнутые треки навсегда через подзапрос в БД
        disliked_subquery = self.db.query(UserReaction.track_id).filter(UserReaction.is_disliked == True)
        query = self.db.query(Track).filter(Track.is_discovery == False).filter(~Track.id.in_(disliked_subquery))
        if recent_ids:
            query = query.filter(~Track.id.in_(recent_ids))
        if current_track_id:
            query = query.filter(Track.id != current_track_id)

        # Запрет повторения одного артиста более 2 раз подряд
        if consecutive_artist and consecutive_count >= 2:
            query = query.filter(Track.artist != consecutive_artist)

        # 3. Фильтрация по настроению (Mood Filter)
        active_mood = mood or "default"
        if active_mood == "default" and mood_energy is not None:
            if mood_energy >= 0.7:
                active_mood = "energy"
            elif mood_energy <= 0.35:
                active_mood = "chill"

        # Применяем фильтр настроения к выборке
        mood_filtered_query = apply_mood_filter(query, active_mood)

        current_track = (
            self.db.query(Track).filter(Track.id == current_track_id).first()
            if current_track_id else None
        )
        curr_vec = (
            deserialize_vector(current_track.embedding_json)
            if current_track and current_track.embedding_json else None
        )

        # 4. Вычисление центроида вкуса пользователя и направляющего вектора сессии
        user_taste_vec = compute_user_taste_centroid(self.db, mood=active_mood)
        target_direction_vec = (
            update_session_drift_vector(user_taste_vec, curr_vec, action="complete")
            if curr_vec else user_taste_vec
        )

        # 5. Двухэтапная генерация кандидатов (Nearest Neighbors HNSW + Serendipity Random)
        disliked_ids = {
            r[0] for r in self.db.query(UserReaction.track_id).filter(UserReaction.is_disliked == True).all()
        }
        all_excluded = recent_ids | disliked_ids
        if current_track_id:
            all_excluded.add(current_track_id)

        nearest_candidates = find_nearest_tracks(
            self.db,
            target_vector=target_direction_vec,
            limit=50,
            mood=active_mood,
            exclude_ids=all_excluded
        )
        random_candidates = mood_filtered_query.order_by(func.random()).limit(50).all()

        candidate_map = {c.id: c for c in nearest_candidates if c.id not in disliked_ids}
        for r_cand in random_candidates:
            if r_cand.id not in candidate_map and r_cand.id not in disliked_ids:
                candidate_map[r_cand.id] = r_cand
        candidates = list(candidate_map.values())

        # Если в выбранном настроении кандидаты закончились из-за кулдауна сессии,
        # сбрасываем recent_ids, но СТРОГО сохраняем целевой фильтр настроения!
        if not candidates:
            fb_query = self.db.query(Track).filter(Track.is_discovery == False).filter(~Track.id.in_(disliked_subquery))
            if current_track_id:
                fb_query = fb_query.filter(Track.id != current_track_id)
            mood_fb_query = apply_mood_filter(fb_query, active_mood)
            candidates = mood_fb_query.order_by(func.random()).limit(100).all()

            if not candidates:
                cand_discovery = discovery_engine.get_discovery_candidate(
                    self.db, mood=active_mood, session_factory=self.session_factory, allow_preview_fallback=True
                )
                if cand_discovery:
                    return cand_discovery
                candidates = fb_query.order_by(func.random()).limit(100).all()
                if not candidates:
                    return None

        # Данные персонализации: лайки треков, любимые артисты и история
        candidate_ids = {c.id for c in candidates}
        candidate_artists = {c.artist for c in candidates if c.artist}

        liked_track_ids = set()
        if candidate_ids:
            liked_track_ids = {
                row[0] for row in self.db.query(UserReaction.track_id)
                .filter(UserReaction.is_liked == True, UserReaction.track_id.in_(candidate_ids))
                .all()
            }

        liked_artists = set()
        if candidate_artists:
            liked_artists = {
                row[0] for row in self.db.query(Track.artist)
                .join(UserReaction, UserReaction.track_id == Track.id)
                .filter(UserReaction.is_liked == True, Track.artist.in_(candidate_artists))
                .distinct()
                .all()
            }

        play_counts: Dict[int, int] = {}
        skip_counts: Dict[int, int] = {}
        if candidate_ids:
            play_counts = dict(
                self.db.query(PlayHistory.track_id, func.count(PlayHistory.id))
                .filter(PlayHistory.track_id.in_(candidate_ids))
                .group_by(PlayHistory.track_id)
                .all()
            )
            skip_counts = dict(
                self.db.query(PlayHistory.track_id, func.count(PlayHistory.id))
                .filter(PlayHistory.track_id.in_(candidate_ids), PlayHistory.skipped == True)
                .group_by(PlayHistory.track_id)
                .all()
            )

        # Определение часа суток для Dayparting
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        local_now = now_utc + datetime.timedelta(minutes=tz_offset_minutes)
        current_hour = local_now.hour

        cooled_artists = set(skipped_artists or [])

        scored_candidates = []
        for cand in candidates:
            score = 1.0

            # 1. Соответствие центроиду вкуса пользователя (User Taste Centroid)
            cand_vec = deserialize_vector(cand.embedding_json)
            if cand_vec and user_taste_vec:
                taste_sim = cosine_similarity(user_taste_vec, cand_vec)
                score += taste_sim * 2.0

            # 2. Акустическое сходство с играющим треком (вектор 16D)
            if curr_vec and cand_vec:
                sim = cosine_similarity(curr_vec, cand_vec)
                score += sim * 2.5
            elif current_track and cand.artist == current_track.artist:
                score += 1.2

            # 2. Плавность перехода темпа (DJ Flow: не более 20-30 BPM разницы)
            if current_track and current_track.bpm and cand.bpm:
                bpm_diff = abs(current_track.bpm - cand.bpm)
                score -= min(1.0, bpm_diff / 50.0)

            # 4. Персонализация: Буст любимых треков и артистов
            if cand.id in liked_track_ids:
                score += 5.5  # Максимальный приоритет конкретным лайкнутым трекам
            elif cand.artist in liked_artists:
                score += 1.0  # Умеренный приоритет другим трекам любимого артиста

            # 4. Персонализация: Буст за историю прослушиваний
            pc = play_counts.get(cand.id, 0)
            if pc > 0:
                score += min(1.5, math.log1p(pc) * 0.5)

            # 5. Skip Penalty: Штраф за частые пропуски трека
            sk = skip_counts.get(cand.id, 0)
            if sk > 0:
                score -= min(2.5, sk * 1.4)

            # Охлаждение артистов с повторными скипами
            if cand.artist and cand.artist in cooled_artists:
                score -= 1.8

            # 6. Точность попадания в целевое настроение
            if active_mood == "energy" and cand.energy is not None:
                score += cand.energy * 1.5
            elif active_mood == "chill" and cand.energy is not None:
                score += (1.0 - cand.energy) * 1.5
            elif active_mood == "happy" and cand.valence is not None:
                score += cand.valence * 1.5
            elif active_mood == "sad" and cand.valence is not None:
                score += (1.0 - cand.valence) * 1.5
            elif active_mood == "default":
                # Dayparting: адаптация под биоритмы по времени суток
                if 6 <= current_hour < 11:
                    # Утро: позитив, подъем
                    if cand.valence is not None and cand.valence >= 0.50:
                        score += 0.8 * cand.valence
                    if cand.energy is not None and 0.45 <= cand.energy <= 0.85:
                        score += 0.6
                elif 11 <= current_hour < 18:
                    # День: концентрация, рабочий флоу
                    if cand.energy is not None and 0.40 <= cand.energy <= 0.75:
                        score += 0.6
                elif 18 <= current_hour < 22:
                    # Вечер: расслабленный вечерний вайб
                    if cand.danceability is not None and cand.danceability >= 0.55:
                        score += 0.6
                else:
                    # Ночь (22..05): calm, lofi, chill, мягкий звук
                    if cand.energy is not None and cand.energy <= 0.50:
                        score += 1.2
                    elif cand.energy is not None and cand.energy > 0.75:
                        score -= 1.2
                    if cand.bpm is not None and cand.bpm <= 115.0:
                        score += 0.5

            # 7. Контролируемая энтропия (температура), чтобы избежать зацикливания
            noise = random.uniform(0.85, 1.15)
            final_score = max(0.05, score * noise)
            scored_candidates.append((final_score, cand))

        # Взвешенный вероятностный выбор среди топ-кандидатов с учетом персонализации
        if not scored_candidates:
            return candidates[0]

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored_candidates[:min(5, len(scored_candidates))]
        weights = [max(0.01, score) for score, _ in top_candidates]
        chosen = random.choices([c for _, c in top_candidates], weights=weights, k=1)[0]
        return chosen
