import datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, desc

from database.db import get_db
from database.models import Playlist, PlaylistTrack, Track, User, PlayHistory, UserReaction, utc_now
from recommendations.embeddings import deserialize_vector, cosine_similarity
from core.security import get_current_user

router = APIRouter(prefix="/playlists", tags=["Плейлисты"])


def _format_track_item(t: Track, position: int = 0) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "artist": t.artist,
        "album": t.album,
        "duration": t.duration,
        "audio_format": t.audio_format,
        "is_liked": bool(t.is_liked),
        "position": position
    }


class PlaylistCreateRequest(BaseModel):
    title: str
    description: str | None = None


class PlaylistAddTrackRequest(BaseModel):
    track_id: int


@router.get("/smart/forgotten-favorites")
def get_smart_forgotten_favorites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Умный плейлист «Забытые фавориты»:
    Любимые или часто прослушиваемые треки, которые не звучали последние 30 дней.
    """
    threshold_date = utc_now() - datetime.timedelta(days=30)

    # Ищем треки с лайками или высокой историей, у которых последнее воспроизведение старше 30 дней
    last_played_sub = (
        db.query(PlayHistory.track_id, func.max(PlayHistory.played_at).label("last_played"))
        .group_by(PlayHistory.track_id)
        .subquery()
    )

    liked_sub = (
        db.query(UserReaction.track_id)
        .filter(UserReaction.is_liked == True)
        .scalar_subquery()
    )

    tracks = (
        db.query(Track)
        .outerjoin(last_played_sub, Track.id == last_played_sub.c.track_id)
        .filter(Track.is_discovery == False)
        .filter(Track.id.in_(liked_sub))
        .filter(or_(last_played_sub.c.last_played == None, last_played_sub.c.last_played < threshold_date))
        .order_by(func.coalesce(last_played_sub.c.last_played, Track.created_at).asc())
        .limit(50)
        .all()
    )

    formatted = [_format_track_item(t, idx) for idx, t in enumerate(tracks)]
    return {
        "id": "smart_forgotten_favorites",
        "title": "Забытые фавориты",
        "description": "Ваши любимые треки, которые давно не звучали",
        "track_count": len(formatted),
        "tracks": formatted
    }


@router.get("/smart/heavy-rotation")
def get_smart_heavy_rotation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Умный плейлист «Heavy Rotation»:
    Топ треков по числу прослушиваний за последние 30 дней.
    """
    threshold_date = utc_now() - datetime.timedelta(days=30)

    top_ids = (
        db.query(PlayHistory.track_id, func.count(PlayHistory.id).label("cnt"))
        .filter(PlayHistory.played_at >= threshold_date)
        .group_by(PlayHistory.track_id)
        .order_by(desc("cnt"))
        .limit(30)
        .all()
    )

    id_order = {row[0]: idx for idx, row in enumerate(top_ids)}
    tracks = (
        db.query(Track)
        .filter(Track.id.in_(id_order.keys()), Track.is_discovery == False)
        .all()
    )
    tracks.sort(key=lambda t: id_order.get(t.id, 999))

    formatted = [_format_track_item(t, idx) for idx, t in enumerate(tracks)]
    return {
        "id": "smart_heavy_rotation",
        "title": "Heavy Rotation",
        "description": "Самые часто воспроизводимые треки за последний месяц",
        "track_count": len(formatted),
        "tracks": formatted
    }


@router.get("/smart/radio/{track_id}")
def get_smart_track_radio(
    track_id: int,
    limit: int = 25,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Умный плейлист «Радио по треку»:
    Подборка наиболее близких треков из фонотеки по психоакустическому векторному сходству.
    """
    ref_track = db.query(Track).filter(Track.id == track_id).first()
    if not ref_track:
        raise HTTPException(status_code=404, detail="Исходный трек не найден")

    ref_vec = deserialize_vector(ref_track.embedding_json)
    if not ref_vec:
        ref_vec = [
            (ref_track.bpm or 120.0) / 180.0,
            ref_track.energy or 0.5,
            ref_track.valence or 0.5,
            ref_track.danceability or 0.5
        ]

    candidates = (
        db.query(Track)
        .filter(Track.id != track_id, Track.is_discovery == False)
        .all()
    )

    scored = []
    for cand in candidates:
        c_vec = deserialize_vector(cand.embedding_json)
        if not c_vec:
            c_vec = [
                (cand.bpm or 120.0) / 180.0,
                cand.energy or 0.5,
                cand.valence or 0.5,
                cand.danceability or 0.5
            ]

        sim = cosine_similarity(ref_vec, c_vec)
        if cand.artist == ref_track.artist:
            sim += 0.25
        scored.append((sim, cand))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_tracks = [t for _, t in scored[:limit]]

    formatted = [_format_track_item(t, idx) for idx, t in enumerate(top_tracks)]
    return {
        "id": f"smart_radio_{track_id}",
        "title": f"Радио по треку: {ref_track.artist} - {ref_track.title}",
        "description": f"Похожие композиции на основе темпа, настроения и акустических признаков",
        "reference_track": _format_track_item(ref_track),
        "track_count": len(formatted),
        "tracks": formatted
    }


@router.get("")
def get_playlists(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Список всех плейлистов с числом треков (исключая служебные потоки и буфер)."""
    # Агрегация количества треков одним быстрым SQL-запросом без загрузки объектов Track в память
    counts = dict(
        db.query(PlaylistTrack.playlist_id, func.count(PlaylistTrack.id))
        .join(Track, (PlaylistTrack.track_id == Track.id) & (Track.is_discovery == False))
        .group_by(PlaylistTrack.playlist_id)
        .all()
    )
    playlists = db.query(Playlist).order_by(Playlist.updated_at.desc()).all()
    result = []
    for p in playlists:
        if p.title and p.title.strip().lower() in ("поток", "stream", "discovery_buffer"):
            continue
        result.append({
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "track_count": counts.get(p.id, 0),
            "created_at": p.created_at,
            "updated_at": p.updated_at,
        })
    return result


@router.post("")
def create_playlist(
    payload: PlaylistCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Создание нового плейлиста."""
    playlist = Playlist(title=payload.title.strip(), description=payload.description)
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return {"status": "created", "playlist_id": playlist.id, "title": playlist.title}


@router.get("/{playlist_id}")
def get_playlist_details(
    playlist_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Получение плейлиста и упорядоченного списка его треков (без треков буфера Потока)."""
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Плейлист не найден")

    items = (
        db.query(PlaylistTrack, Track)
        .join(Track, (PlaylistTrack.track_id == Track.id) & (Track.is_discovery == False))
        .filter(PlaylistTrack.playlist_id == playlist_id)
        .order_by(PlaylistTrack.position.asc())
        .all()
    )

    tracks_data = []
    for item, t in items:
        tracks_data.append({
            "id": t.id,
            "title": t.title,
            "artist": t.artist,
            "album": t.album,
            "duration": t.duration,
            "audio_format": t.audio_format,
            "is_liked": bool(t.is_liked),
            "position": item.position,
            "added_at": item.added_at
        })

    return {
        "id": playlist.id,
        "title": playlist.title,
        "description": playlist.description,
        "track_count": len(tracks_data),
        "tracks": tracks_data
    }


@router.post("/{playlist_id}/tracks")
def add_track_to_playlist(
    playlist_id: int,
    payload: PlaylistAddTrackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Добавление трека в плейлист."""
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Плейлист не найден")

    track = db.query(Track).filter((Track.id == payload.track_id) & (Track.is_discovery == False)).first()
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден или находится в буфере потока")

    existing = db.query(PlaylistTrack).filter(
        PlaylistTrack.playlist_id == playlist_id,
        PlaylistTrack.track_id == payload.track_id
    ).first()
    if existing:
        return {"status": "already_exists", "playlist_id": playlist_id, "track_id": payload.track_id}

    max_pos = db.query(PlaylistTrack).filter(PlaylistTrack.playlist_id == playlist_id).count()
    new_item = PlaylistTrack(playlist_id=playlist_id, track_id=payload.track_id, position=max_pos)
    db.add(new_item)
    db.commit()
    return {"status": "added", "playlist_id": playlist_id, "track_id": payload.track_id, "position": max_pos}


@router.delete("/{playlist_id}/tracks/{track_id}")
def remove_track_from_playlist(
    playlist_id: int,
    track_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Удаление трека из плейлиста."""
    item = db.query(PlaylistTrack).filter(
        PlaylistTrack.playlist_id == playlist_id,
        PlaylistTrack.track_id == track_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Трек отсутствует в данном плейлисте")

    db.delete(item)
    db.commit()
    return {"status": "removed", "playlist_id": playlist_id, "track_id": track_id}


@router.delete("/{playlist_id}")
def delete_playlist(
    playlist_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Удаление плейлиста."""
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=404, detail="Плейлист не найден")

    db.delete(playlist)
    db.commit()
    return {"status": "deleted", "playlist_id": playlist_id}
