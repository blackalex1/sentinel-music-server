import os
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from database.models import Track
from lyrics.lrclib import fetch_lyrics
from lyrics.parser import parse_lrc


def get_lrc_file_path(audio_path: str) -> str:
    """Возвращает путь к файлу .lrc рядом с аудиофайлом."""
    base, _ = os.path.splitext(audio_path)
    return base + ".lrc"


def load_lyrics_from_disk(audio_path: str) -> Optional[str]:
    """Проверяет наличие файла .lrc на диске рядом с треком."""
    lrc_path = get_lrc_file_path(audio_path)
    if os.path.exists(lrc_path):
        try:
            with open(lrc_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception as e:
            print(f"[LyricsStorage] Ошибка чтения {lrc_path}: {e}")
    return None


def save_lyrics_to_disk(audio_path: str, lrc_content: str) -> bool:
    """Сохраняет караоке-текст в файл .lrc рядом с треком на диске."""
    if not lrc_content:
        return False
    try:
        lrc_path = get_lrc_file_path(audio_path)
        with open(lrc_path, "w", encoding="utf-8") as f:
            f.write(lrc_content)
        return True
    except Exception as e:
        print(f"[LyricsStorage] Не удалось сохранить {audio_path}.lrc: {e}")
        return False


def get_or_fetch_lyrics(track: Track, db: Session) -> Tuple[bool, list, str]:
    """
    Многоуровневое получение текста без повторных загрузок:
    1. Проверка базы данных (PostgreSQL).
    2. Проверка локального файла .lrc рядом с аудиофайлом на сервере.
    3. Скачивание из сети (LRCLIB) ТОЛЬКО при отсутствии в п.1 и п.2.
    4. Автоматическое сохранение и в БД, и в файл .lrc на диск.
    """
    # Уровень 1: Уже сохранено в базе данных
    if track.lyrics_synced:
        return True, parse_lrc(track.lyrics_synced), track.lyrics_synced
    if track.lyrics_plain:
        return False, [], track.lyrics_plain

    # Уровень 2: Проверка наличия .lrc файла на диске
    disk_lrc = load_lyrics_from_disk(track.file_path)
    if disk_lrc:
        track.lyrics_synced = disk_lrc
        db.commit()
        return True, parse_lrc(disk_lrc), disk_lrc

    # Уровень 3: Загрузка из интернета (один раз через LRCLIB)
    lyrics_data = fetch_lyrics(
        artist=track.artist,
        title=track.title,
        album=track.album,
        duration=track.duration
    )

    if lyrics_data and lyrics_data.get("full"):
        raw_text = lyrics_data["full"]
        is_synced = lyrics_data.get("is_synced", False)

        if is_synced:
            track.lyrics_synced = raw_text
            # Сохраняем .lrc файл рядом с треком
            save_lyrics_to_disk(track.file_path, raw_text)
            db.commit()
            return True, parse_lrc(raw_text), raw_text
        else:
            track.lyrics_plain = raw_text
            db.commit()
            return False, [], raw_text

    return False, [], ""
