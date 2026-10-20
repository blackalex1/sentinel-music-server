import math
import random
from typing import List, Optional, Union, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from database.models import Track, UserReaction
from .embeddings import deserialize_vector
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
        consecutive_count: int = 0
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
        # Если discovery_ratio > 0 и сработала вероятность (или ratio >= 1.0)
        should_discover = False
        if discovery_ratio >= 1.0:
            should_discover = True
        elif discovery_ratio > 0.0 and random.random() < discovery_ratio:
            should_discover = True

        if should_discover:
            # Сначала проверяем, есть ли готовый предзагруженный трек из сети в буфере
            from .buffer_manager import discovery_buffer_manager
            buffered_track = discovery_buffer_manager.get_next_buffered_track(self.db, mood=active_mood)
            if buffered_track:
                return buffered_track

            # Фоллбэк: если буфер еще пуст или докачивается, берем неслушанный трек из фонотеки
            cand_discovery = discovery_engine.get_discovery_candidate(self.db, mood=active_mood, session_factory=self.session_factory)
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

        # Выбираем случайный пул из 100 подходящих кандидатов по всей библиотеке
        candidates = mood_filtered_query.order_by(func.random()).limit(100).all()

        # Если в выбранном настроении кандидаты закончились из-за кулдауна сессии,
        # сбрасываем recent_ids (но оставляем бан дизлайков и текущий трек)
        if not candidates:
            fb_query = self.db.query(Track).filter(Track.is_discovery == False).filter(~Track.id.in_(disliked_subquery))
            if current_track_id:
                fb_query = fb_query.filter(Track.id != current_track_id)
            candidates = fb_query.order_by(func.random()).limit(100).all()
            if not candidates:
                cand_discovery = discovery_engine.get_discovery_candidate(
                    self.db, mood=active_mood, session_factory=self.session_factory, allow_preview_fallback=True
                )
                if cand_discovery:
                    return cand_discovery
                return None

        current_track = (
            self.db.query(Track).filter(Track.id == current_track_id).first()
            if current_track_id else None
        )
        curr_vec = (
            deserialize_vector(current_track.embedding_json)
            if current_track and current_track.embedding_json else None
        )

        # Список любимых артистов кандидатов (лайки) через точечный JOIN
        candidate_artists = {c.artist for c in candidates if c.artist}
        liked_artists = set()
        if candidate_artists:
            liked_artists = {
                row[0] for row in self.db.query(Track.artist)
                .join(UserReaction, UserReaction.track_id == Track.id)
                .filter(UserReaction.is_liked == True, Track.artist.in_(candidate_artists))
                .distinct()
                .all()
            }

        scored_candidates = []
        for cand in candidates:
            score = 1.0

            # 1. Акустическое сходство (вектор 16D)
            cand_vec = deserialize_vector(cand.embedding_json)
            if curr_vec and cand_vec:
                sim = cosine_similarity(curr_vec, cand_vec)
                score += sim * 2.5
            elif current_track and cand.artist == current_track.artist:
                score += 1.2

            # 2. Плавность перехода темпа (DJ Flow: не более 20-30 BPM разницы)
            if current_track and current_track.bpm and cand.bpm:
                bpm_diff = abs(current_track.bpm - cand.bpm)
                score -= min(1.0, bpm_diff / 50.0)

            # 3. Буст любимых артистов
            if cand.artist in liked_artists:
                score += 1.3

            # 4. Точность попадания в целевое настроение
            if active_mood == "energy" and cand.energy is not None:
                score += cand.energy * 1.5
            elif active_mood == "chill" and cand.energy is not None:
                score += (1.0 - cand.energy) * 1.5
            elif active_mood == "happy" and cand.valence is not None:
                score += cand.valence * 1.5
            elif active_mood == "sad" and cand.valence is not None:
                score += (1.0 - cand.valence) * 1.5

            # 5. Контролируемая энтропия (температура), чтобы избежать зацикливания
            noise = random.uniform(0.85, 1.15)
            final_score = max(0.1, score * noise)
            scored_candidates.append((final_score, cand))

        # Выбираем лучший трек из топ-3 кандидатов для разнообразия
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored_candidates[:3]

        return random.choice(top_candidates)[1] if top_candidates else candidates[0]
