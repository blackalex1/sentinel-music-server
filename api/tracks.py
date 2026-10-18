import os
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.sql import func, text

from database.db import get_db, SessionLocal
from database.models import Track, User, UserReaction, PlayHistory, PlaylistTrack
from database.search_index import search_tracks
from core.security import get_current_user, get_current_admin_user, is_safe_track_file_path
from core.config import settings
from streaming.scanner import scan_single_file
from recommendations.analyzer import library_analyzer

router = APIRouter(tags=["Треки"])


def apply_library_filter(query):
    """Исключает временные треки буфера Потока (discovery_buffer) из медиатеки пользователя."""
    return query.filter(Track.is_discovery == False)


from recommendations.mood import apply_mood_filter


@router.get("/tracks")
def get_tracks(
    q: str | None = None,
    mood: str | None = Query(None, description="Фильтр по настроению: energy, chill, happy, sad"),
    limit: int = Query(50, ge=1, le=50000),
    offset: int = Query(0, ge=0),
    sort: str = Query("recent", description="Сортировка: recent, oldest, title, artist"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Список треков в фонотеке с поддержкой опционального поиска, настроения и сортировки."""
    if q and q.strip():
        return search_tracks(db, q.strip(), limit=limit, offset=offset)

    query = db.query(Track)
    query = apply_library_filter(query)
    query = apply_mood_filter(query, mood)

    if sort == "recent":
        query = query.order_by(Track.created_at.desc(), Track.id.desc())
    elif sort == "oldest":
        query = query.order_by(Track.id.asc())
    elif sort == "title":
        query = query.order_by(Track.title.asc(), Track.id.asc())
    elif sort == "artist":
        query = query.order_by(Track.artist.asc(), Track.id.asc())
    else:
        query = query.order_by(Track.created_at.desc(), Track.id.desc())

    return query.offset(offset).limit(limit).all()


@router.get("/tracks/recent")
def get_recent_tracks(
    mood: str | None = Query(None, description="Фильтр по настроению: energy, chill, happy, sad"),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Возвращает самые недавно добавленные в фонотеку треки с опциональным фильтром настроения и пагинацией."""
    query = db.query(Track)
    query = apply_library_filter(query)
    query = apply_mood_filter(query, mood)

    return (
        query.order_by(Track.created_at.desc(), Track.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/tracks/count")
def get_tracks_count(
    mood: str | None = Query(None, description="Фильтр по настроению: energy, chill, happy, sad"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Возвращает общее количество треков в фонотеке (с учетом опционального фильтра настроения)."""
    query = db.query(Track)
    query = apply_library_filter(query)
    query = apply_mood_filter(query, mood)
    return {"count": query.count()}


@router.get("/tracks/shuffle")
def get_shuffled_tracks(
    mood: str | None = Query(None, description="Фильтр по настроению: energy, chill, happy, sad"),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Серверный случайный микс фонотеки (Server-side Shuffle).
    Быстро выбирает случайные треки на уровне базы данных с исключением дизлайков и учетом настроения.
    """
    disliked_subquery = (
        db.query(UserReaction.track_id)
        .filter(UserReaction.is_disliked.is_(True))
    )

    query = db.query(Track)
    query = apply_library_filter(query)
    query = apply_mood_filter(query, mood)
    query = query.filter(~Track.id.in_(disliked_subquery))

    random_tracks = query.order_by(func.random()).limit(limit).all()
    return random_tracks


def _perform_track_deletion(track: Track, delete_file: bool, db: Session) -> dict:
    """Универсальное удаление трека с очисткой зависимостей и дисковых файлов."""
    t_id = track.id
    f_path = track.file_path
    f_size = track.file_size or 0

    # 1. Удаление зависимых записей из базы данных
    db.query(PlayHistory).filter(PlayHistory.track_id == t_id).delete()
    db.query(UserReaction).filter(UserReaction.track_id == t_id).delete()
    db.query(PlaylistTrack).filter(PlaylistTrack.track_id == t_id).delete()

    # 2. Обновление статуса в буфере открытий (Discovery Buffer)
    try:
        from recommendations.buffer_manager import discovery_buffer_manager
        discovery_buffer_manager.handle_track_deletion(t_id)
    except Exception as e:
        print(f"[DeleteTrack] Предупреждение: ошибка обновления буфера: {e}")

    # 3. Физическое удаление файла с диска
    file_deleted = False
    if delete_file and f_path and is_safe_track_file_path(f_path):
        if os.path.exists(f_path):
            try:
                os.remove(f_path)
                file_deleted = True
            except Exception as e:
                print(f"[DeleteTrack] Предупреждение: не удалось удалить файл {f_path}: {e}")

        # Удаление .lrc файла (субтитры/текст песни) рядом
        lrc_candidate = os.path.splitext(f_path)[0] + ".lrc"
        if os.path.exists(lrc_candidate) and is_safe_track_file_path(lrc_candidate):
            try:
                os.remove(lrc_candidate)
            except Exception:
                pass

    # 4. Удаление трека из базы данных
    db.delete(track)
    return {
        "track_id": t_id,
        "artist": track.artist,
        "title": track.title,
        "file_deleted": file_deleted,
        "freed_bytes": f_size if file_deleted else 0
    }


class DeleteDuplicatesPayload(BaseModel):
    track_ids: List[int]
    delete_files: bool = True


class ResolveDuplicateGroupPayload(BaseModel):
    keep_track_id: int
    delete_track_ids: List[int]
    delete_files: bool = True


@router.get("/tracks/duplicates")
def get_duplicates_report(
    q: Optional[str] = Query(None, description="Фильтр по названию или исполнителю среди дубликатов"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Обнаруживает группы дублированных треков (одинаковый исполнитель и название).
    Оценивает качество аудио каждого дубликата и рекомендует наилучшую версию для сохранения.
    """
    # 1. Быстрый поиск групп дубликатов через SQL CTE
    sql = text("""
        WITH dup_keys AS (
            SELECT LOWER(TRIM(artist)) as norm_artist, LOWER(TRIM(title)) as norm_title, count(*) as cnt
            FROM tracks
            WHERE is_discovery = FALSE
            GROUP BY LOWER(TRIM(artist)), LOWER(TRIM(title))
            HAVING count(*) > 1
        )
        SELECT t.id, t.title, t.artist, t.album, t.year, t.duration, t.audio_format,
               t.bitrate, t.file_size, t.file_path, t.created_at,
               d.cnt as duplicate_count,
               d.norm_artist, d.norm_title
            FROM tracks t
            JOIN dup_keys d ON LOWER(TRIM(t.artist)) = d.norm_artist AND LOWER(TRIM(t.title)) = d.norm_title
            WHERE is_discovery = FALSE
            ORDER BY d.cnt DESC, d.norm_artist, d.norm_title, t.id ASC;
    """)

    rows = db.execute(sql).fetchall()

    # Группируем треки по ключу (norm_artist, norm_title)
    groups_dict = {}
    q_filter = q.strip().lower() if q else ""

    for r in rows:
        key = f"{r.norm_artist} — {r.norm_title}"
        if q_filter and (q_filter not in r.norm_artist and q_filter not in r.norm_title):
            continue

        if key not in groups_dict:
            groups_dict[key] = {
                "group_key": key,
                "artist": r.artist,
                "title": r.title,
                "count": r.duplicate_count,
                "tracks": []
            }

        groups_dict[key]["tracks"].append({
            "id": r.id,
            "title": r.title,
            "artist": r.artist,
            "album": r.album,
            "year": r.year,
            "duration": r.duration or 0.0,
            "audio_format": (r.audio_format or "mp3").lower(),
            "bitrate": r.bitrate or 0,
            "file_size": r.file_size or 0,
            "filename": os.path.basename(r.file_path) if r.file_path else "",
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(r.created_at, "strftime") else (str(r.created_at) if r.created_at else None)
        })

    total_groups = len(groups_dict)
    total_extra_tracks = 0
    total_potential_freed_bytes = 0

    groups_list = []
    for group in groups_dict.values():
        tracks = group["tracks"]
        if len(tracks) < 2:
            continue

        # Функция оценки качества трека для автоматической рекомендации лучшей версии
        def quality_score(t):
            fmt = str(t.get("audio_format", "")).lower()
            bitrate = t.get("bitrate") or 0
            size = t.get("file_size") or 0
            # Lossless форматы получают максимальный приоритет
            is_lossless = 2_000_000 if fmt in ("flac", "wav", "alac") else 0
            bitrate_score = bitrate * 1000
            duration = t.get("duration") or 0.0
            duration_bonus = 50_000 if duration > 45 else 0
            return is_lossless + bitrate_score + duration_bonus + (size // 1024)

        # Находим лучший трек
        best_track = max(tracks, key=quality_score)
        for t in tracks:
            t["is_best"] = (t["id"] == best_track["id"])

        extra_count = len(tracks) - 1
        extra_bytes = sum(t["file_size"] for t in tracks if t["id"] != best_track["id"])

        total_extra_tracks += extra_count
        total_potential_freed_bytes += extra_bytes

        group["extra_count"] = extra_count
        group["extra_bytes"] = extra_bytes
        group["best_track_id"] = best_track["id"]
        # Сортируем: лучший сверху, остальные по убыванию качества
        tracks.sort(key=lambda t: (0 if t["is_best"] else 1, -quality_score(t)))
        groups_list.append(group)

    return {
        "total_groups": len(groups_list),
        "total_extra_tracks": total_extra_tracks,
        "potential_saved_bytes": total_potential_freed_bytes,
        "groups": groups_list
    }


@router.post("/tracks/duplicates/delete")
def delete_duplicate_tracks_batch(
    payload: DeleteDuplicatesPayload,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Пакетное удаление выбранных дубликатов треков (требуются права администратора).
    Очищает связанные записи БД, обновляет Discovery Buffer и удаляет файлы с диска.
    """
    if not payload.track_ids:
        return {"status": "ok", "deleted_count": 0, "freed_bytes": 0}

    deleted_count = 0
    total_freed = 0

    tracks = db.query(Track).filter(Track.id.in_(payload.track_ids)).all()
    for track in tracks:
        res = _perform_track_deletion(track, delete_file=payload.delete_files, db=db)
        deleted_count += 1
        total_freed += res["freed_bytes"]

    db.commit()

    return {
        "status": "success",
        "deleted_count": deleted_count,
        "freed_bytes": total_freed
    }


@router.post("/tracks/duplicates/resolve-group")
def resolve_duplicate_group(
    payload: ResolveDuplicateGroupPayload,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Оставляет один выбранный трек в группе дубликатов, а остальные копии удаляет (требуются права администратора).
    """
    return delete_duplicate_tracks_batch(
        DeleteDuplicatesPayload(track_ids=payload.delete_track_ids, delete_files=payload.delete_files),
        current_user=current_user,
        db=db
    )


@router.get("/tracks/{track_id}")
def get_track(
    track_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Детальная информация о конкретном треке."""
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")
    return track


@router.delete("/tracks/{track_id}")
def delete_track(
    track_id: int,
    delete_file: bool = Query(True, description="Удалить аудиофайл и сопутствующие файлы с диска"),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Полное удаление трека из фонотеки:
    - Очищает связанные данные (историю прослушиваний, реакции, участие в плейлистах).
    - Очищает запись в журнале Discovery Buffer, если трек был там.
    - Удаляет аудиофайл и сопутствующие файлы (.lrc) с диска (если delete_file=True).
    - Удаляет запись о треке из базы данных.
    """
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="Трек не найден")

    res = _perform_track_deletion(track, delete_file=delete_file, db=db)
    db.commit()

    return {
        "status": "deleted",
        "track_id": res["track_id"],
        "artist": res["artist"],
        "title": res["title"],
        "file_deleted": res["file_deleted"]
    }


ALLOWED_AUDIO_EXTENSIONS = {".flac", ".mp3", ".m4a", ".wav", ".ogg"}


def sanitize_upload_filename(filename: str) -> str:
    """Очищает имя загружаемого файла от небезопасных символов и path traversal."""
    base = os.path.basename(filename)
    for ch in r'\/:*?"<>|':
        base = base.replace(ch, '_')
    return " ".join(base.split())


def _async_analyze_track(track_id: int):
    """Фоновый расчет аудио-характеристик и эмбеддинга для загруженного трека."""
    try:
        db = SessionLocal()
        try:
            library_analyzer.analyze_single_track(track_id, db)
        finally:
            db.close()
    except Exception as e:
        print(f"[Upload] Ошибка фонового анализа трека #{track_id}: {e}")


@router.post("/tracks/upload")
async def upload_tracks(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ручная загрузка аудиофайлов в фонотеку (.mp3, .flac, .m4a, .ogg, .wav).
    Сохраняет файлы в каталог фонотеки, извлекает метаданные и регистрирует треки в БД.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Не передано ни одного файла для загрузки")

    music_dir = os.path.abspath(settings.MUSIC_DIR)
    os.makedirs(music_dir, exist_ok=True)
    non_flac_dir = os.path.join(music_dir, "non-flac")

    uploaded_tracks = []
    failed_files = []

    for file in files:
        original_name = file.filename or "unknown_track"
        ext = os.path.splitext(original_name)[1].lower()

        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            failed_files.append({
                "filename": original_name,
                "error": f"Формат {ext} не поддерживается (разрешены: FLAC, MP3, M4A, WAV, OGG)"
            })
            continue

        # Определяем целевую директорию: FLAC в корень, остальные в non-flac
        target_dir = music_dir
        if ext != ".flac":
            os.makedirs(non_flac_dir, exist_ok=True)
            target_dir = non_flac_dir

        safe_name = sanitize_upload_filename(original_name)
        if not safe_name or safe_name == ext:
            safe_name = f"upload_{int(os.times()[4] * 1000)}{ext}"

        dest_path = os.path.join(target_dir, safe_name)

        # Предотвращение коллизий имен файлов
        if os.path.exists(dest_path):
            name_stem = os.path.splitext(safe_name)[0]
            counter = 1
            while os.path.exists(dest_path):
                dest_path = os.path.join(target_dir, f"{name_stem} ({counter}){ext}")
                counter += 1

        try:
            # Потоковая запись файла на диск чанками по 1 МБ с ограничением до 250 МБ (защита от DoS)
            MAX_UPLOAD_SIZE = 250 * 1024 * 1024  # 250 MB
            total_bytes = 0
            file_too_large = False

            with open(dest_path, "wb") as f_out:
                while chunk := await file.read(1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_UPLOAD_SIZE:
                        file_too_large = True
                        break
                    f_out.write(chunk)

            if file_too_large:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                failed_files.append({
                    "filename": original_name,
                    "error": "Размер файла превышает допустимый лимит (максимум 250 МБ)"
                })
                continue

            # Проверяем, что файл записан и не пустой
            if os.path.getsize(dest_path) == 0:
                os.remove(dest_path)
                failed_files.append({
                    "filename": original_name,
                    "error": "Файл пуст (размер 0 байт)"
                })
                continue

            # Сканируем файл и добавляем в базу данных
            track = scan_single_file(dest_path, db)
            if not track:
                if os.path.exists(dest_path):
                    try:
                        os.remove(dest_path)
                    except Exception:
                        pass
                failed_files.append({
                    "filename": original_name,
                    "error": "Не удалось прочитать аудио-метаданные файла"
                })
                continue

            # Запускаем фоновый анализ настроения / эмбеддинга
            background_tasks.add_task(_async_analyze_track, track.id)

            uploaded_tracks.append({
                "id": track.id,
                "title": track.title,
                "artist": track.artist,
                "album": track.album,
                "year": track.year,
                "duration": track.duration,
                "audio_format": track.audio_format,
                "bitrate": track.bitrate,
                "file_size": track.file_size
            })

        except Exception as e:
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
            failed_files.append({
                "filename": original_name,
                "error": f"Ошибка сохранения: {str(e)}"
            })

    return {
        "status": "ok",
        "total_uploaded": len(uploaded_tracks),
        "total_failed": len(failed_files),
        "uploaded": uploaded_tracks,
        "failed": failed_files
    }


@router.post("/tracks/cleanup-missing")
def cleanup_missing_tracks_endpoint(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Проверяет всю фонотеку и автоматически удаляет записи треков,
    файлы которых были удалены с диска (требуются права администратора).
    """
    from streaming.scanner import cleanup_missing_tracks
    deleted = cleanup_missing_tracks(None, db)
    return {
        "status": "success",
        "deleted_count": deleted,
        "message": f"Очищено {deleted} треков, отсутствовавших на диске"
    }



