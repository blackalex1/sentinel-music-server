import os
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.db import get_db, SessionLocal
from database.models import User, UserReaction
from recommendations.vibe_engine import VibeEngine
from recommendations.analyzer import library_analyzer
from recommendations.discovery import discovery_engine
from plugin_system.manager import plugin_manager
from core.security import get_current_user, get_current_admin_user

router = APIRouter(tags=["Поток и Реакции"])


@router.get("/stream/next")
def get_next_stream_track(
    current_track_id: Optional[int] = None,
    mood: Optional[str] = Query("default", description="Настроение: default, energy, chill, happy, sad"),
    mood_energy: Optional[float] = Query(None, description="Обратная совместимость: 0.0 - 1.0"),
    recent_ids: Optional[str] = Query(None, description="Список недавних ID через запятую: 1,2,3"),
    discovery_ratio: float = Query(0.2, ge=0.0, le=1.0, description="Частота новых треков: 0.0 - 1.0"),
    consecutive_artist: Optional[str] = Query(None, description="Имя артиста текущего трека"),
    consecutive_count: int = Query(0, ge=0, description="Сколько раз подряд играл этот артист"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Возвращает следующий трек для бесконечного умного потока «Поток».
    Поддерживает ранжирование по настроению, темпу, исключение повторов и управляемую частоту открытий.
    """
    parsed_recent_ids: List[int] = []
    if recent_ids:
        try:
            parsed_recent_ids = [int(i.strip()) for i in recent_ids.split(",") if i.strip().isdigit()]
        except Exception:
            parsed_recent_ids = []

    engine = VibeEngine(db, session_factory=SessionLocal)
    next_track = engine.get_next_vibe_track(
        current_track_id=current_track_id,
        recent_track_ids=parsed_recent_ids,
        mood=mood,
        mood_energy=mood_energy,
        discovery_ratio=discovery_ratio,
        consecutive_artist=consecutive_artist,
        consecutive_count=consecutive_count
    )

    if not next_track:
        raise HTTPException(status_code=404, detail="Нет доступных треков для Потока")

    return next_track


@router.get("/stream/analytics/status")
def get_analytics_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Возвращает текущий прогресс психоакустического анализа фонотеки и распределение настроений."""
    return library_analyzer.get_status(db)


@router.post("/stream/analytics/start")
def start_analytics(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Запускает фоновый расчет характеристик (BPM, Energy, Valence) для всех неразмеченных треков (требуются права администратора)."""
    started = library_analyzer.start_analysis()
    return {
        "status": "ok" if started else "already_running",
        "details": library_analyzer.get_status(db)
    }


@router.post("/stream/analytics/stop")
def stop_analytics(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Останавливает фоновый анализ (требуются права администратора)."""
    library_analyzer.stop_analysis()
    return {"status": "stopped", "details": library_analyzer.get_status(db)}


from pydantic import BaseModel


class TrackImportRequest(BaseModel):
    artist: str
    title: str


@router.get("/stream/discovery/candidates")
def get_discovery_candidates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Возвращает список актуальных рекомендаций и открытий из музыкального графа."""
    seeds = discovery_engine.get_seed_artists(db)
    return {
        "seed_artists": seeds,
        "cached_candidates_count": len(discovery_engine._cache_candidates),
        "candidates": discovery_engine._cache_candidates[:15]
    }


@router.post("/stream/discovery/import")
async def import_discovery_track(
    payload: TrackImportRequest,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Запускает поиск и фоновую загрузку трека в фонотеку через активные модули импорта (требуются права администратора).
    """
    success = await plugin_manager.request_track_import(payload.artist, payload.title)
    return {
        "status": "queued" if success else "not_found",
        "artist": payload.artist,
        "title": payload.title,
        "message": "Трек найден и поставлен в очередь фоновой загрузки" if success else "Трек не найден у доступных источников импорта"
    }


@router.post("/reaction/{track_id}")
async def set_reaction(
    track_id: int,
    is_like: bool,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Установка лайка/дизлайка для трека.
    Обучает персональный профиль рекомендаций и оповещает подключенные плагины.
    """
    reaction = db.query(UserReaction).filter(UserReaction.track_id == track_id).first()
    if not reaction:
        reaction = UserReaction(track_id=track_id)
        db.add(reaction)

    if is_like:
        reaction.is_liked = not reaction.is_liked
        reaction.is_disliked = False
    else:
        reaction.is_disliked = not reaction.is_disliked
        reaction.is_liked = False

    db.commit()

    # Оповещаем все зарегистрированные плагины
    await plugin_manager.notify_reaction(track_id, reaction.is_liked, reaction.is_disliked)

    # Если это трек из буфера Потока, закрепляем в фонотеке при лайке или удаляем при дизлайке
    from recommendations.buffer_manager import discovery_buffer_manager
    saved_permanent = discovery_buffer_manager.handle_user_reaction(
        track_id,
        is_like=reaction.is_liked,
        is_disliked=reaction.is_disliked,
        db=db
    )

    return {
        "status": "ok",
        "is_liked": reaction.is_liked,
        "is_disliked": reaction.is_disliked,
        "saved_permanent": saved_permanent
    }


@router.get("/stream/discovery/buffer/history")
def get_stream_buffer_history(
    current_user: User = Depends(get_current_user)
):
    """
    Возвращает постоянный JSON-журнал всех треков, которые когда-либо были в Потоке.
    """
    from recommendations.buffer_manager import discovery_buffer_manager
    return discovery_buffer_manager.load_history()


@router.get("/stream/discovery/buffer/status")
def get_stream_buffer_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Возвращает статус автономного буфера предзагрузки: сколько готово, сколько сыграло, сколько сохранено.
    """
    from recommendations.buffer_manager import discovery_buffer_manager
    discovery_buffer_manager.sync_buffer_files(db)
    records = discovery_buffer_manager.load_history()

    buffered = sum(1 for r in records if r.get("status") == "buffered")
    played = sum(1 for r in records if r.get("status") == "played")
    saved = sum(1 for r in records if r.get("status") == "saved_permanent" or r.get("liked") is True)
    expired = sum(1 for r in records if r.get("status") == "expired_deleted")

    return {
        "target_buffer_size": discovery_buffer_manager.TARGET_BUFFER_SIZE,
        "retention_days": discovery_buffer_manager.RETENTION_DAYS,
        "counts": {
            "buffered_ready": buffered,
            "played": played,
            "saved_permanent": saved,
            "expired_deleted": expired,
            "total_history": len(records)
        },
        "history_file": os.path.basename(discovery_buffer_manager.history_json_path)
    }
