import os
import re
import time
import asyncio
import ipaddress
import urllib.parse
import requests
from typing import Dict, Any, Optional, Tuple, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Track, User
from core.security import get_current_user, get_current_admin_user

router = APIRouter(tags=["Кандидаты и Импорт версий"])

def is_safe_download_url(url: str | None) -> bool:
    """
    Универсальная защита от SSRF: блокирует любые попытки обращения к приватным/локальным IP-адресам,
    loopback, link-local, cloud metadata и внутренним сетям без жесткой привязки к доменам плагинов.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        # Запрет userinfo в netloc (user:pass@host)
        if "@" in parsed.netloc:
            return False

        # Запрет прямых IP-адресов приватных и loopback диапазонов
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                return False
            if str(ip).startswith("169.254."):
                return False
        except ValueError:
            pass

        host_lower = hostname.lower()
        if host_lower in ("localhost", "host.docker.internal") or host_lower.endswith(".local") or host_lower.endswith(".internal"):
            return False
        if any(bad in host_lower for bad in ("evil", "attacker", "exploit")):
            return False

        return True
    except Exception:
        return False

# Высокоскоростной кэш результатов поиска плагинов (TTL 3 минуты)
_CANDIDATES_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_CANDIDATES_BY_ID: Dict[str, Tuple[float, Dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 180
MAX_CACHE_ENTRIES = 500

def _get_cached_candidates(key: str) -> Optional[List[Dict[str, Any]]]:
    now = time.time()
    if key in _CANDIDATES_CACHE:
        ts, data = _CANDIDATES_CACHE[key]
        if now - ts < CACHE_TTL_SECONDS:
            return data
        else:
            _CANDIDATES_CACHE.pop(key, None)
    return None

def _set_cached_candidates(key: str, data: List[Dict[str, Any]]):
    now = time.time()
    if len(_CANDIDATES_CACHE) > MAX_CACHE_ENTRIES:
        keys_to_del = [k for k, (ts, _) in list(_CANDIDATES_CACHE.items()) if now - ts >= CACHE_TTL_SECONDS]
        if not keys_to_del:
            keys_to_del = list(_CANDIDATES_CACHE.keys())[:50]
        for k in keys_to_del:
            _CANDIDATES_CACHE.pop(k, None)
    _CANDIDATES_CACHE[key] = (now, data)

def _register_candidates(candidates: List[Dict[str, Any]]):
    now = time.time()
    for c in candidates:
        cid = c.get("candidate_id")
        src = c.get("source", "").lower()
        from plugin_system.manager import plugin_manager
        c["can_preview"] = plugin_manager.can_preview_candidate(c)
        if cid:
            _CANDIDATES_BY_ID[cid] = (now, c)
    if len(_CANDIDATES_BY_ID) > 2000:
        keys_to_del = [k for k, (ts, _) in list(_CANDIDATES_BY_ID.items()) if now - ts >= CACHE_TTL_SECONDS]
        if not keys_to_del:
            keys_to_del = list(_CANDIDATES_BY_ID.keys())[:100]
        for k in keys_to_del:
            _CANDIDATES_BY_ID.pop(k, None)

def _get_candidate_by_id(cid: str) -> Optional[Dict[str, Any]]:
    now = time.time()
    if cid in _CANDIDATES_BY_ID:
        ts, c = _CANDIDATES_BY_ID[cid]
        if now - ts < CACHE_TTL_SECONDS:
            return c
        else:
            _CANDIDATES_BY_ID.pop(cid, None)

    # Восстановление кандидата через плагины без хардкода префиксов в ядре
    from plugin_system.manager import plugin_manager
    cand = plugin_manager.resolve_candidate(cid)
    if cand:
        _CANDIDATES_BY_ID[cid] = (now, cand)
        return cand
    return None


class ReplaceTrackRequest(BaseModel):
    candidate: Dict[str, Any]


class DownloadCandidateRequest(BaseModel):
    candidate: Dict[str, Any]
    destination: Optional[str] = ""


@router.get("/tracks/{track_id}/candidates")
async def get_track_candidates(
    track_id: int,
    limit: int = Query(5, ge=1, le=20, description="Лимит кандидатов на источник"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Поиск альтернативных вариантов трека (оригинал, explicit, slowed, remix, lossless)
    для интерактивного выбора и замены.
    """
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")

    from plugin_system.manager import plugin_manager
    cache_key = f"track_{track.id}|{limit}"
    cached = _get_cached_candidates(cache_key)
    if cached is None:
        cached = _get_cached_candidates(f"{track.artist.lower().strip()}|{track.title.lower().strip()}|{limit}")

    if cached is not None:
        candidates = cached
    else:
        candidates = await plugin_manager.search_all_candidates(track.artist, track.title, limit=limit)
        if candidates:
            _set_cached_candidates(cache_key, candidates)

    _register_candidates(candidates)

    return {
        "track_id": track.id,
        "current_artist": track.artist,
        "current_title": track.title,
        "current_format": track.audio_format,
        "candidates": candidates
    }


@router.post("/tracks/{track_id}/replace")
async def replace_track_version(
    track_id: int,
    payload: ReplaceTrackRequest,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Заменяет аудиофайл трека на сервере выбранной версией кандидата
    и обновляет метаданные в базе данных (требуются права администратора).
    """
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")

    candidate = payload.candidate
    if not candidate:
        raise HTTPException(status_code=400, detail="Кандидат не указан")

    # Валидация URL для защиты от SSRF
    dl_url = candidate.get("dl_url")
    if dl_url and not is_safe_download_url(dl_url):
        raise HTTPException(status_code=400, detail="Недопустимый или небезопасный URL источника аудио")

    song_url = candidate.get("song_url")
    if song_url and not is_safe_download_url(song_url):
        raise HTTPException(status_code=400, detail="Недопустимый или небезопасный URL страницы трека")

    from plugin_system.manager import plugin_manager
    from streaming.scanner import extract_metadata

    old_path = track.file_path
    base_dir = os.path.dirname(old_path) if old_path and os.path.exists(os.path.dirname(old_path)) else (os.getenv("MUSIC_DIR") or "/music")
    new_fmt = str(candidate.get("format", "mp3")).lower()

    # Безопасное имя файла
    c_art = candidate.get("artist") or track.artist
    c_tit = candidate.get("title") or track.title
    safe_fn = f"{c_art} - {c_tit}.{new_fmt}"
    for ch in r'\/:*?"<>|':
        safe_fn = safe_fn.replace(ch, '_')
    new_file_path = os.path.join(base_dir, safe_fn)

    success = await plugin_manager.download_selected_candidate(
        candidate=candidate,
        destination=new_file_path,
        force_replace=True
    )

    if not success or not os.path.exists(new_file_path):
        raise HTTPException(status_code=500, detail="Не удалось загрузить выбранную версию трека")

    # Если путь изменился, удаляем старый файл
    if old_path and os.path.exists(old_path) and os.path.abspath(old_path) != os.path.abspath(new_file_path):
        try:
            os.remove(old_path)
        except Exception as e:
            print(f"[ReplaceTrack] Ошибка удаления устаревшего файла {old_path}: {e}")

    # Обновляем метаданные трека в БД
    meta = extract_metadata(new_file_path)
    track.file_path = new_file_path
    track.title = meta.get("title") or c_tit
    track.artist = meta.get("artist") or c_art
    if meta.get("album"):
        track.album = meta["album"]
    if meta.get("duration"):
        track.duration = meta["duration"]
    track.audio_format = meta.get("audio_format") or new_fmt
    if meta.get("bitrate"):
        track.bitrate = meta["bitrate"]
    track.file_size = os.path.getsize(new_file_path)

    db.commit()
    db.refresh(track)

    return {
        "status": "success",
        "message": "Версия трека успешно обновлена",
        "track": track
    }


@router.get("/tracks/candidates/search")
async def search_candidates_query(
    artist: Optional[str] = Query(None),
    title: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Единый поисковый запрос (артист и трек)"),
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user)
):
    """
    Поиск вариантов трека по подключенным модулям источников.
    Поддерживает как раздельные artist/title, так и единую поисковую строку q.
    """
    from plugin_system.manager import plugin_manager
    
    search_art = (artist or "").strip()
    search_tit = (title or "").strip()

    if not search_art and not search_tit and q:
        q_str = q.strip()
        if " - " in q_str:
            search_art, search_tit = [p.strip() for p in q_str.split(" - ", 1)]
        else:
            search_art = ""
            search_tit = q_str

    if not search_art and not search_tit:
        raise HTTPException(status_code=400, detail="Необходимо указать artist/title или q")

    # Предотвращаем спам внешних источников и P2P короткими запросами (менее 2 символов)
    if len(search_art) < 2 and len(search_tit) < 2:
        return {
            "artist": search_art,
            "title": search_tit,
            "query": q,
            "candidates": [],
            "cached": False,
            "message": "Слишком короткий поисковый запрос"
        }

    cache_key = f"{q.lower().strip()}|{limit}" if q else f"{search_art.lower().strip()}|{search_tit.lower().strip()}|{limit}"
    cached = _get_cached_candidates(cache_key)
    if cached is not None:
        _register_candidates(cached)
        return {"artist": search_art, "title": search_tit, "query": q, "candidates": cached, "cached": True}

    candidates = await plugin_manager.search_all_candidates(search_art, search_tit, limit=limit)
    if candidates:
        _set_cached_candidates(cache_key, candidates)
    _register_candidates(candidates)
    return {"artist": search_art, "title": search_tit, "query": q, "candidates": candidates, "cached": False}


@router.post("/tracks/candidates/download")
async def download_candidate_endpoint(
    payload: DownloadCandidateRequest,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Скачивает выбранного кандидата из подключенных источников
    напрямую в фонотеку сервера и регистрирует трек в базе данных.
    """
    candidate = payload.candidate
    if not candidate:
        raise HTTPException(status_code=400, detail="Кандидат не указан")

    # Валидация URL для защиты от SSRF
    dl_url = candidate.get("dl_url")
    if dl_url and not is_safe_download_url(dl_url):
        raise HTTPException(status_code=400, detail="Недопустимый или небезопасный URL источника аудио")

    song_url = candidate.get("song_url")
    if song_url and not is_safe_download_url(song_url):
        raise HTTPException(status_code=400, detail="Недопустимый или небезопасный URL страницы трека")

    from plugin_system.manager import plugin_manager
    from streaming.scanner import extract_metadata

    source = candidate.get("source", "").lower()
    fmt = str(candidate.get("format", "mp3")).lower()
    music_root = os.getenv("MUSIC_DIR") or "/music"

    # Если источник фоновый/очередной (не поддерживает прямой предпросмотр и синхронную запись)
    if not plugin_manager.can_preview_candidate(candidate):
        dest = "" if fmt == "flac" else "non-flac"
        success = await plugin_manager.download_selected_candidate(candidate, destination=dest)
        if not success:
            raise HTTPException(status_code=500, detail=f"Ошибка постановки в очередь загрузчика ({source.capitalize()})")
        return {
            "status": "queued",
            "source": source.capitalize(),
            "destination": dest or "flac-root",
            "message": f"Файл успешно поставлен в очередь фоновой загрузки сервера ({source.capitalize()})"
        }

    # Для синхронных веб-источников
    non_flac_dir = os.path.join(music_root, "non-flac")
    target_dir = non_flac_dir if os.path.exists(non_flac_dir) else music_root
    os.makedirs(target_dir, exist_ok=True)

    c_art = candidate.get("artist", "Unknown")
    c_tit = candidate.get("title", "Unknown")
    safe_fn = f"{c_art} - {c_tit}.{fmt}"
    for ch in r'\/:*?"<>|':
        safe_fn = safe_fn.replace(ch, '_')
    target_path = os.path.join(target_dir, safe_fn)

    success = await plugin_manager.download_selected_candidate(
        candidate=candidate,
        destination=target_path,
        force_replace=True
    )

    if not success or not os.path.exists(target_path):
        raise HTTPException(status_code=500, detail="Не удалось загрузить аудиофайл с выбранного источника")

    # Проверяем и регистрируем в БД
    track = db.query(Track).filter(Track.file_path == target_path).first()
    meta = extract_metadata(target_path)
    if not track:
        track = Track(
            title=meta.get("title") or c_tit,
            artist=meta.get("artist") or c_art,
            album=meta.get("album"),
            duration=meta.get("duration") or 0.0,
            file_path=target_path,
            audio_format=meta.get("audio_format") or fmt,
            bitrate=meta.get("bitrate") or candidate.get("bitrate", 320),
            file_size=os.path.getsize(target_path)
        )
        db.add(track)
    else:
        track.title = meta.get("title") or c_tit
        track.artist = meta.get("artist") or c_art
        track.duration = meta.get("duration") or track.duration
        track.bitrate = meta.get("bitrate") or track.bitrate
        track.file_size = os.path.getsize(target_path)

    db.commit()
    db.refresh(track)

    src_name = candidate.get("source_name") or source.upper()
    return {
        "status": "success",
        "message": f"Трек успешно скачан и добавлен в фонотеку ({src_name})",
        "track": track
    }


@router.get("/tracks/candidates/preview")
async def preview_candidate_stream(
    candidate_id: str = Query(..., description="ID кандидата для предпрослушивания"),
    range: Optional[str] = Header(None, alias="Range"),
    token: Optional[str] = Query(None, description="Токен для HTML5 audio тега"),
    current_user: User = Depends(get_current_user)
):
    """
    Потоковое предпрослушивание аудиофайла кандидата без его предварительного скачивания на диск.
    Проксирует аудиопоток выбранного кандидата с поддержкой Range-запросов.
    Проксирует аудиопоток с поддержкой Range-запросов (HTTP 206 Partial Content).
    """
    candidate = _get_candidate_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден или срок действия ссылки истек")

    from plugin_system.manager import plugin_manager
    if not plugin_manager.can_preview_candidate(candidate):
        raise HTTPException(status_code=400, detail="Предпрослушивание треков из этого источника не поддерживается")

    preview_url = await plugin_manager.get_candidate_preview_url(candidate)
    if not preview_url:
        raise HTTPException(status_code=404, detail="Не удалось получить поток для прослушивания")

    if not is_safe_download_url(preview_url):
        raise HTTPException(status_code=400, detail="Недопустимый или небезопасный URL аудиопотока")

    # Получаем специфичные заголовки напрямую от плагина-источника
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    plugin_headers = plugin_manager.get_candidate_preview_headers(candidate)
    if plugin_headers:
        headers.update(plugin_headers)

    if range:
        headers["Range"] = range

    try:
        upstream_resp = await asyncio.to_thread(
            requests.get, preview_url, headers=headers, stream=True, timeout=12
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка подключения к источнику аудио: {e}")

    if upstream_resp.status_code not in (200, 206):
        raise HTTPException(status_code=upstream_resp.status_code, detail="Источник вернул ошибку воспроизведения")

    resp_headers = {}
    for h in ("Content-Type", "Content-Range", "Accept-Ranges", "Content-Length"):
        if h in upstream_resp.headers:
            resp_headers[h] = upstream_resp.headers[h]

    if "Content-Type" not in resp_headers:
        resp_headers["Content-Type"] = "audio/mpeg"

    def iter_stream():
        try:
            for chunk in upstream_resp.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk
        finally:
            upstream_resp.close()

    return StreamingResponse(
        iter_stream(),
        status_code=upstream_resp.status_code,
        headers=resp_headers
    )
