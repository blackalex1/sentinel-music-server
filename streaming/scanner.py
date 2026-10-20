import os
from pathlib import Path
from typing import Optional
from mutagen import File as MutagenFile
from sqlalchemy.orm import Session

from database.models import Track
from core.security import is_safe_track_file_path


def sanitize_str(val: Optional[str]) -> Optional[str]:
    """Удаляет NUL (0x00) байты, несовместимые с PostgreSQL."""
    if val is None:
        return None
    cleaned = str(val).replace("\x00", "").strip()
    return cleaned if cleaned else None


def extract_metadata(file_path: str) -> dict:
    """Извлекает аудио-метаданные и теги через Mutagen с надежным фоллбэком."""
    audio = None
    try:
        audio = MutagenFile(file_path)
    except Exception:
        pass

    filename_base = os.path.splitext(os.path.basename(file_path))[0]
    title = filename_base
    artist = "Unknown Artist"
    if " - " in filename_base:
        parts = filename_base.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()

    album = None
    year = None

    # Попытка извлечь теги из VorbisComment (FLAC) или ID3 (MP3)
    if audio and audio.tags:
        tags = audio.tags
        if hasattr(tags, "get"):
            t = tags.get("title") or tags.get("TITLE") or tags.get("TIT2")
            if t:
                title = str(t[0]) if isinstance(t, list) else str(t)
            a = tags.get("artist") or tags.get("ARTIST") or tags.get("TPE1")
            if a:
                artist = str(a[0]) if isinstance(a, list) else str(a)
            alb = tags.get("album") or tags.get("ALBUM") or tags.get("TALB")
            if alb:
                album = str(alb[0]) if isinstance(alb, list) else str(alb)
            date = tags.get("date") or tags.get("DATE") or tags.get("TDRC")
            if date:
                try:
                    year = int(str(date[0])[:4])
                except (ValueError, TypeError):
                    pass

    duration = getattr(audio.info, "length", 0.0) if (audio and hasattr(audio, "info")) else 0.0
    bitrate = getattr(audio.info, "bitrate", None) if (audio and hasattr(audio, "info")) else None
    if bitrate:
        bitrate = int(bitrate / 1000)

    ext = Path(file_path).suffix.lstrip(".").lower()

    # Проверка наличия уже сохраненного .lrc файла рядом с музыкой
    lyrics_synced = None
    lrc_candidate = os.path.splitext(file_path)[0] + ".lrc"
    if os.path.exists(lrc_candidate):
        try:
            with open(lrc_candidate, "r", encoding="utf-8") as lf:
                lyrics_synced = lf.read().strip()
        except Exception:
            pass

    return {
        "title": sanitize_str(title) or "Unknown Title",
        "artist": sanitize_str(artist) or "Unknown Artist",
        "album": sanitize_str(album),
        "year": year,
        "duration": duration,
        "audio_format": ext,
        "bitrate": bitrate,
        "file_size": os.path.getsize(file_path),
        "file_path": file_path,
        "lyrics_synced": sanitize_str(lyrics_synced),
    }


def scan_single_file(file_path: str, db: Session) -> Optional[Track]:
    """
    Сканирует один аудиофайл и регистрирует его в базе данных,
    либо обновляет существующий трек при апгрейде качества / обнаружении дубликата.
    """
    supported_exts = {".flac", ".mp3", ".m4a", ".wav", ".ogg"}
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in supported_exts:
        return None

    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return None

    full_path = os.path.abspath(file_path)
    existing = db.query(Track).filter(Track.file_path == full_path).first()
    if existing:
        return existing

    meta = extract_metadata(full_path)
    if not meta:
        return None

    artist = (meta.get("artist") or "").strip()
    title = (meta.get("title") or "").strip()

    if artist and title:
        from sqlalchemy import func
        # Ищем существующие треки с совпадающим исполнителем и названием
        existing_candidates = db.query(Track).filter(
            func.lower(func.trim(Track.artist)) == func.lower(func.trim(artist)),
            func.lower(func.trim(Track.title)) == func.lower(func.trim(title))
        ).all()

        if existing_candidates:
            def quality_score(fmt, bitrate, fsize):
                fmt_str = (fmt or "").lower()
                is_lossless = 2_000_000 if fmt_str in ("flac", "wav", "alac") else 0
                return is_lossless + (bitrate or 0) * 1000 + (fsize or 0)

            new_score = quality_score(meta.get("audio_format"), meta.get("bitrate"), meta.get("file_size"))
            is_new_buffer = "discovery_buffer" in full_path.lower() or "saved_discoveries" in full_path.lower()

            # 1. Проверяем кандидатов: если существующий трек в Saved_Discoveries или discovery_buffer —
            # обновляем его при лучшем качестве нового файла или замене на библиотечный
            for cand in existing_candidates:
                cand_score = quality_score(cand.audio_format, cand.bitrate, cand.file_size)
                is_cand_saved = "saved_discoveries" in (cand.file_path or "").lower()
                is_cand_buffer = "discovery_buffer" in (cand.file_path or "").lower() or cand.is_discovery

                if is_cand_saved or is_cand_buffer:
                    if new_score > cand_score or not is_new_buffer:
                        old_path = cand.file_path
                        cand.file_path = full_path
                        cand.audio_format = meta.get("audio_format") or cand.audio_format
                        cand.bitrate = meta.get("bitrate") or cand.bitrate
                        cand.duration = meta.get("duration") or cand.duration
                        cand.file_size = meta.get("file_size") or cand.file_size
                        cand.is_discovery = "discovery_buffer" in full_path.lower()
                        if meta.get("album"):
                            cand.album = meta["album"]
                        if meta.get("year"):
                            cand.year = meta["year"]
                        if meta.get("lyrics_synced"):
                            cand.lyrics_synced = meta["lyrics_synced"]

                        db.commit()
                        db.refresh(cand)

                        # Удаляем старый файл буфера более низкого качества
                        if old_path and os.path.exists(old_path) and os.path.abspath(old_path) != full_path and is_safe_track_file_path(old_path):
                            try:
                                os.remove(old_path)
                                print(f"[Scanner] [🗑️] Устаревший аудиофайл буфера удален при авто-апгрейде: {old_path}")
                            except Exception as e:
                                print(f"[Scanner] Ошибка удаления устаревшего файла {old_path}: {e}")

                            old_lrc = os.path.splitext(old_path)[0] + ".lrc"
                            if os.path.exists(old_lrc) and is_safe_track_file_path(old_lrc):
                                try:
                                    os.remove(old_lrc)
                                except Exception:
                                    pass

                        try:
                            from recommendations.buffer_manager import discovery_buffer_manager
                            discovery_buffer_manager.update_track_path(cand.id, full_path)
                        except Exception:
                            pass

                        print(f"[Scanner] [❤️ Upgrade] Трек #{cand.id} '{cand.artist} - {cand.title}' успешно обновлен до {cand.audio_format.upper()} ({cand.bitrate} kbps).")
                        return cand

            # 2. Если новый файл — из буфера (discovery), а в фонотеке уже есть постоянный трек:
            if is_new_buffer:
                try:
                    os.remove(full_path)
                    print(f"[Scanner] [Дубликат] Удален избыточный трек из буфера рекомендаций: {full_path}")
                except Exception:
                    pass
                return existing_candidates[0]

            # 3. Если и существующий трек, и новый файл — постоянные библиотечные файлы фонотеки (например, MP3 и FLAC):
            # Мы НЕ удаляем старый файл! Мы регистрируем новый файл в БД как отдельный Track,
            # чтобы оба файла отобразились в разделе «Дубликаты» (/tracks/duplicates),
            # где пользователь сможет визуально сравнить спектры/битрейты и выбрать, какую версию сохранить.
            print(f"[Scanner] [Дубликат] Обнаружена новая версия трека '{artist} - {title}' ({meta.get('audio_format')}, {meta.get('bitrate')} kbps). Добавлен в фонотеку для выбора в «Дубликаты».")

    meta["is_discovery"] = "discovery_buffer" in full_path.lower()
    track = Track(**meta)
    db.add(track)
    db.commit()
    db.refresh(track)

    # Треки в основной папке фонотеки считаются лайкнутыми по умолчанию
    if not track.is_discovery:
        from database.models import UserReaction
        existing_reaction = db.query(UserReaction).filter(UserReaction.track_id == track.id).first()
        if not existing_reaction:
            db.add(UserReaction(track_id=track.id, is_liked=True, is_disliked=False))
            db.commit()

    return track


def scan_directory(music_dir: str, db: Session, batch_size: int = 50) -> int:
    """Рекурсивно сканирует директорию с музыкой и добавляет новые треки в БД с дедупликацией."""
    supported_exts = {".flac", ".mp3", ".m4a", ".wav", ".ogg"}
    added_count = 0

    if not os.path.exists(music_dir):
        return 0

    # Предзагружаем все пути из БД в один set в памяти, устраняя N+1 round-trips
    existing_paths = {p[0] for p in db.query(Track.file_path).all()}

    for root, _, files in os.walk(music_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in supported_exts:
                full_path = os.path.abspath(os.path.join(root, f))
                if full_path in existing_paths:
                    continue
                try:
                    track = scan_single_file(full_path, db)
                    if track:
                        existing_paths.add(full_path)
                        added_count += 1
                        if added_count % batch_size == 0:
                            print(f"[Scanner] Проиндексировано: {added_count} треков...", flush=True)
                except Exception as e:
                    db.rollback()
                    print(f"[Scanner] Пропуск файла {f} из-за ошибки: {e}", flush=True)

    # Удаляем из БД записи треков, файлы которых были физически удалены с диска
    cleanup_missing_tracks(music_dir, db)

    return added_count


def cleanup_missing_tracks(music_dir: Optional[str] = None, db: Session = None) -> int:
    """
    Сканирует треки в базе данных и удаляет те, чьи физические файлы отсутствуют на диске.
    Если music_dir передан — ограничивает проверку указанным каталогом.
    Если music_dir=None — проверяет всю базу данных.
    Пакетно удаляет зависимые записи в 4 запросах вместо N*4 одиночных запросов.
    """
    from database.models import PlayHistory, UserReaction, PlaylistTrack

    query = db.query(Track)
    if music_dir:
        abs_music = os.path.abspath(music_dir)
        query = query.filter(Track.file_path.ilike(f"%{music_dir}%") | Track.file_path.ilike(f"%{abs_music}%"))

    tracks = query.all()
    missing_tracks = []
    missing_ids = []

    for t in tracks:
        if not t.file_path or not os.path.exists(t.file_path):
            missing_tracks.append(t)
            missing_ids.append(t.id)
            print(f"[Scanner] Очищен отсутствующий на диске трек #{t.id}: {t.artist} - {t.title}")
            try:
                from recommendations.buffer_manager import discovery_buffer_manager
                discovery_buffer_manager.handle_track_deletion(t.id)
            except Exception:
                pass

    if missing_ids:
        db.query(PlayHistory).filter(PlayHistory.track_id.in_(missing_ids)).delete(synchronize_session=False)
        db.query(UserReaction).filter(UserReaction.track_id.in_(missing_ids)).delete(synchronize_session=False)
        db.query(PlaylistTrack).filter(PlaylistTrack.track_id.in_(missing_ids)).delete(synchronize_session=False)
        for t in missing_tracks:
            db.delete(t)
        db.commit()

    return len(missing_ids)
