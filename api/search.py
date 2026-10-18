from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import User
from database.search_index import search_tracks
from core.security import get_current_user

router = APIRouter(tags=["Поиск треков"])


@router.get("/tracks/search")
def search_tracks_endpoint(
    q: str = Query(..., min_length=1, max_length=100, description="Поисковый запрос"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Быстрый полнотекстовый поиск по названию, артисту, альбому и текстам песен.
    Включает поддержку русской морфологии (е/ё, окончания, опечатки) и транслитерации.
    """
    return search_tracks(db, q, limit=limit, offset=offset)
