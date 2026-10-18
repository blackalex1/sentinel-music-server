from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.db import get_db
from database.models import Playlist, PlaylistTrack, Track, User
from core.security import get_current_user

router = APIRouter(prefix="/playlists", tags=["Плейлисты"])


class PlaylistCreateRequest(BaseModel):
    title: str
    description: str | None = None


class PlaylistAddTrackRequest(BaseModel):
    track_id: int


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
