"""
Провайдер синхронизированных караоке-текстов NetEase Cloud Music (music.163.com).
Содержит колоссальную мировую базу LRC файлов с миллисекундными таймкодами [00:12.34].
"""

import re
import logging
from typing import Optional
import requests

logger = logging.getLogger("lyrics.netease")

SEARCH_ENDPOINT = "https://music.163.com/api/search/pc"
LYRIC_ENDPOINT = "https://music.163.com/api/song/lyric"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://music.163.com/",
    "Cookie": "NMTID=00OAVK3xqDG726ITU6jopU6jF2yMk0AAAGCO8l1BA; playerid=94262567"
}

IGNORE_PATTERNS = ["作词", "作曲", "编曲", "制作", "监制", "录音", "混音", "母带"]


def _clean_lrc(lrc_text: str) -> str:
    """Удаляет строки метаданных из начала текста."""
    if not lrc_text:
        return ""
    lines = []
    for line in lrc_text.splitlines():
        if any(pat in line for pat in IGNORE_PATTERNS):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def fetch_netease_lyrics(artist: str, title: str) -> Optional[str]:
    """
    Выполняет поиск трека в NetEase и загружает караоке LRC текст.
    Возвращает строку с LRC текстом или None.
    """
    if not artist and not title:
        return None

    query = f"{artist} {title}".strip()
    session = requests.Session()
    try:
        params = {"limit": 5, "type": 1, "offset": 0, "s": query}
        resp = session.get(SEARCH_ENDPOINT, params=params, headers=HEADERS, timeout=5)
        if resp.status_code != 200:
            return None

        data = resp.json()
        songs = data.get("result", {}).get("songs", [])
        if not songs:
            return None

        # Перебираем найденные треки и запрашиваем текст
        for song in songs[:3]:
            song_id = song.get("id")
            if not song_id:
                continue

            lyr_params = {"id": song_id, "lv": 1, "kv": 1, "tv": -1}
            lyr_resp = session.get(LYRIC_ENDPOINT, params=lyr_params, headers=HEADERS, timeout=4)
            if lyr_resp.status_code == 200:
                lyr_data = lyr_resp.json()
                raw_lrc = lyr_data.get("lrc", {}).get("lyric", "")
                if raw_lrc and "[" in raw_lrc[:60]:
                    cleaned = _clean_lrc(raw_lrc)
                    if len(cleaned) > 50:
                        logger.info(f"[NetEase] Синхронизированный караоке текст успешно найден для '{query}'")
                        return cleaned
    except Exception as e:
        logger.debug(f"[NetEase] Ошибка получения текста: {e}")
    finally:
        session.close()

    return None
