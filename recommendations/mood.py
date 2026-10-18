from typing import Optional, List
from sqlalchemy import or_, and_, not_, func
from database.models import Track


def apply_mood_filter(query, mood: Optional[str]):
    """
    Применяет многофакторный фильтр настроения по психоакустической модели Рассела
    (BPM x Danceability x Valence x LUFS Loudness).
    
    Категории:
    - energy (Бодрое): быстрый темп, тяжелый рок/метал саунд или зажигательный ритм
    - happy (Радостное): высокая танцевальность и клубный драйв либо позитивный мажорный лад
    - sad (Грустное): меланхоличные медляки и эмо-лирика (исключая быстрый танцевальный рейв)
    - chill (Спокойное): мягкий мастеринг, ненавязчивый ритм, расслабляющая акустика
    """
    if not mood or mood in ("default", "all"):
        return query

    if mood == "energy":
        return query.filter(
            or_(
                Track.bpm >= 118.0,
                Track.loudness_lufs >= -7.2,
                and_(Track.bpm >= 100.0, Track.danceability >= 0.75)
            )
        )
    elif mood == "chill":
        return query.filter(
            and_(
                func.coalesce(Track.loudness_lufs, -9.0) <= -7.5,
                or_(
                    and_(Track.loudness_lufs <= -10.2, Track.bpm <= 115.0),
                    and_(Track.bpm <= 92.0, Track.danceability <= 0.60),
                    Track.energy <= 0.65
                )
            )
        )
    elif mood == "happy":
        return query.filter(
            or_(
                and_(Track.danceability >= 0.66, Track.bpm >= 100.0),
                and_(Track.valence >= 0.52, Track.bpm >= 80.0)
            )
        )
    elif mood == "sad":
        is_not_rave = not_(and_(Track.bpm >= 125.0, Track.danceability >= 0.70))
        sad_conditions = or_(
            and_(Track.valence <= 0.45, Track.bpm <= 118.0, func.coalesce(Track.loudness_lufs, -9.0) <= -7.0),
            and_(Track.bpm <= 95.0, Track.danceability <= 0.65, Track.valence <= 0.50)
        )
        return query.filter(is_not_rave, sad_conditions)

    return query


def classify_track_moods(track: Track) -> List[str]:
    """Возвращает список подходящих категорий настроений для конкретного трека."""
    bpm = track.bpm or 120.0
    val = track.valence or 0.5
    dance = track.danceability or 0.5
    lufs = track.loudness_lufs if track.loudness_lufs is not None else -9.0
    energy = track.energy or 0.8

    moods = []

    # 1. Бодрое
    if bpm >= 118.0 or lufs >= -7.2 or (bpm >= 100.0 and dance >= 0.75):
        moods.append("energy")

    # 2. Радостное
    if (dance >= 0.66 and bpm >= 100.0) or (val >= 0.52 and bpm >= 80.0):
        moods.append("happy")

    # 3. Грустное
    is_rave = bpm >= 125.0 and dance >= 0.70
    if not is_rave:
        if (val <= 0.45 and bpm <= 118.0 and lufs <= -7.0) or (bpm <= 95.0 and dance <= 0.65 and val <= 0.50):
            moods.append("sad")

    # 4. Спокойное
    if lufs <= -7.5 and ((lufs <= -10.2 and bpm <= 115.0) or (bpm <= 92.0 and dance <= 0.60) or energy <= 0.65):
        moods.append("chill")

    return moods
