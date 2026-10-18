"""
Модуль извлечения текстов песен из встроенных метаданных аудиофайлов.
Поддерживает:
- MP3: ID3 USLT (обычный текст) и SYLT (синхронизированный караоке)
- FLAC: Vorbis комментарии LYRICS / UNSYNCEDLYRICS
- MP4 / M4A: атом ©lyr
- OGG / Opus: теги LYRICS
"""

import os
import re
import logging
from typing import Tuple, Optional

logger = logging.getLogger("lyrics.embedded")


def is_lrc_synced(text: str) -> bool:
    """Проверяет, содержит ли текст временные метки вида [01:23.45]."""
    if not text:
        return False
    return bool(re.search(r'\[\d{2}:\d{2}(?:\.\d{2,3})?\]', text[:200]))


def _sylt_to_lrc(sylt_tag) -> Optional[str]:
    """Конвертирует структуру ID3 SYLT в стандартный LRC текст."""
    try:
        entries = getattr(sylt_tag, "text", [])
        if not entries:
            return None
        lines = []
        for text_part, ms in entries:
            text_clean = str(text_part).strip()
            if not text_clean:
                continue
            total_seconds = ms / 1000.0
            m = int(total_seconds // 60)
            s = int(total_seconds % 60)
            cs = int((total_seconds - int(total_seconds)) * 100)
            lines.append(f"[{m:02d}:{s:02d}.{cs:02d}]{text_clean}")
        if lines:
            return "\n".join(lines)
    except Exception as e:
        logger.debug(f"Ошибка конвертации SYLT в LRC: {e}")
    return None


def extract_embedded_lyrics(file_path: str) -> Tuple[Optional[str], bool]:
    """
    Извлекает встроенный текст из тегов аудиофайла.
    Возвращает (raw_text, is_synced).
    """
    if not file_path or not os.path.exists(file_path):
        return None, False

    ext = os.path.splitext(file_path)[1].lower()

    # 1. MP3 ID3 теги
    if ext == ".mp3":
        try:
            from mutagen.id3 import ID3, USLT, SYLT
            id3 = ID3(file_path)

            # Проверяем синхронизированный SYLT
            for tag in id3.values():
                if isinstance(tag, SYLT):
                    lrc = _sylt_to_lrc(tag)
                    if lrc:
                        return lrc, True

            # Проверяем обычный USLT
            for tag in id3.values():
                if isinstance(tag, USLT) and tag.text and tag.text.strip():
                    raw = tag.text.strip()
                    synced = is_lrc_synced(raw)
                    return raw, synced
        except Exception:
            pass

    # 2. FLAC Vorbis комментарии
    elif ext == ".flac":
        try:
            from mutagen.flac import FLAC
            audio = FLAC(file_path)
            if audio.tags:
                for key in ["lyrics", "unsyncedlyrics", "unsynced lyrics", "unsynced_lyrics"]:
                    val = audio.tags.get(key)
                    if val:
                        text = val[0] if isinstance(val, list) else str(val)
                        if text and text.strip():
                            raw = text.strip()
                            return raw, is_lrc_synced(raw)
        except Exception:
            pass

    # 3. MP4 / M4A контейнеры
    elif ext in [".m4a", ".mp4", ".aac"]:
        try:
            from mutagen.mp4 import MP4
            audio = MP4(file_path)
            if audio.tags and "©lyr" in audio.tags:
                val = audio.tags["©lyr"]
                text = val[0] if isinstance(val, list) else str(val)
                if text and text.strip():
                    raw = text.strip()
                    return raw, is_lrc_synced(raw)
        except Exception:
            pass

    # 4. OGG / Opus
    elif ext in [".ogg", ".opus"]:
        try:
            from mutagen.oggvorbis import OggVorbis
            audio = OggVorbis(file_path)
            if audio.tags:
                for key in ["lyrics", "unsyncedlyrics"]:
                    val = audio.tags.get(key)
                    if val:
                        text = val[0] if isinstance(val, list) else str(val)
                        if text and text.strip():
                            raw = text.strip()
                            return raw, is_lrc_synced(raw)
        except Exception:
            pass

    return None, False
