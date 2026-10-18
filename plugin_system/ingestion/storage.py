"""
Модуль сохранения файлов фонотеки, простановки тегов ID3 и аудита загрузок.
"""

import os
import time
import json
from typing import Optional, Tuple, Dict, Any
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, ID3NoHeaderError


def sanitize_filename(name: str) -> str:
    """Удаляет запрещенные в файловых системах символы."""
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, '_')
    return " ".join(name.split()).strip()


def resolve_target_path(
    artist: str,
    title: str,
    fmt: str = "mp3",
    destination: str = "",
    music_dir: Optional[str] = None
) -> str:
    """
    Вычисляет корректный абсолютный путь для сохранения файла.
    Учитывает destination (может быть конкретным путем к файлу, подпапкой или пустым).
    Гарантирует защиту от Path Traversal и выхода за пределы фонотеки.
    """
    base_music = os.path.realpath(os.path.abspath(music_dir or os.getenv("MUSIC_DIR") or "/music"))
    fmt = fmt.lower().lstrip(".")

    if destination and (destination.endswith(f".{fmt}") or destination.endswith(".flac") or destination.endswith(".mp3")):
        # Передан прямой целевой путь к файлу — проверяем безопасность пути
        cand_path = os.path.realpath(os.path.abspath(destination))
        if cand_path == base_music or cand_path.startswith(base_music + os.sep):
            parent = os.path.dirname(cand_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            return cand_path
        # При попытке выхода за пределы фонотеки принудительно сохраняем имя файла внутри base_music
        safe_fn = sanitize_filename(os.path.basename(destination))
        return os.path.join(base_music, safe_fn)

    if destination:
        # Передана подпапка (например, 'non-flac' или 'artist/album')
        cand_dir = os.path.realpath(os.path.abspath(os.path.join(base_music, destination)))
        if cand_dir == base_music or cand_dir.startswith(base_music + os.sep):
            target_dir = cand_dir
        else:
            target_dir = base_music
    else:
        # По умолчанию: FLAC в корень фонотеки, MP3 в подпапку non-flac
        if fmt == "flac":
            target_dir = base_music
        else:
            non_flac = os.path.join(base_music, "non-flac")
            target_dir = non_flac if os.path.exists(non_flac) else base_music

    os.makedirs(target_dir, exist_ok=True)
    fn = sanitize_filename(f"{artist} - {title}.{fmt}")
    return os.path.join(target_dir, fn)


def apply_id3_tags(
    file_path: str,
    title: str,
    artist: str,
    album: Optional[str] = None,
    cover_bytes: Optional[bytes] = None
) -> None:
    """Проставляет ID3v2.4 теги в MP3 файл."""
    if not file_path.lower().endswith(".mp3"):
        return

    try:
        try:
            audio = ID3(file_path)
        except ID3NoHeaderError:
            audio = ID3()

        audio["TIT2"] = TIT2(encoding=3, text=title)
        audio["TPE1"] = TPE1(encoding=3, text=artist)
        if album:
            audio["TALB"] = TALB(encoding=3, text=album)
        if cover_bytes and len(cover_bytes) > 500:
            audio["APIC"] = APIC(
                encoding=3,
                mime='image/jpeg',
                type=3,
                desc='Cover',
                data=cover_bytes
            )
        audio.save(file_path)
    except Exception as e:
        print(f"[Storage] Предупреждение: не удалось проставить ID3-теги для {file_path}: {e}")


def save_audio_file(
    content: bytes,
    artist: str,
    title: str,
    fmt: str = "mp3",
    destination: str = "",
    force_replace: bool = True,
    cover_bytes: Optional[bytes] = None,
    album: Optional[str] = None,
    music_dir: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Сохраняет бинарный поток аудио в файл с записью ID3 тегов.
    Возвращает: (успех, итоговый_путь_к_файлу)
    """
    if not content or len(content) < 100000:
        return False, ""

    target_path = resolve_target_path(artist, title, fmt=fmt, destination=destination, music_dir=music_dir)
    if os.path.exists(target_path) and not force_replace:
        return True, target_path

    try:
        with open(target_path, "wb") as f_out:
            f_out.write(content)

        apply_id3_tags(target_path, title=title, artist=artist, album=album, cover_bytes=cover_bytes)
        return True, target_path
    except Exception as e:
        print(f"[Storage] Ошибка записи файла {target_path}: {e}")
        return False, ""


def log_audit_history(
    artist: str,
    title: str,
    status: str,
    details: Optional[Dict[str, Any]] = None,
    history_file: Optional[str] = None
) -> None:
    """Ведет постоянный журнал аудита найденных и скачанных треков."""
    h_file = history_file or os.getenv("INGESTION_HISTORY_FILE") or "/app/data/discovered_tracks_history.json"
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "artist": artist,
        "title": title,
        "status": status,
        "details": details or {}
    }
    try:
        os.makedirs(os.path.dirname(h_file), exist_ok=True)
        with open(h_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
