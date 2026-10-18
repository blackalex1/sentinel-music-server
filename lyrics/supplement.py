"""
Провайдер текстов песен из регионального каталога.
Широкое покрытие локальной музыки, рэпа, инди и новинок.
"""

import urllib.parse
import logging
import base64
from typing import Tuple, Optional
import requests

logger = logging.getLogger("lyrics.supplement")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

_BASE_URL = base64.b64decode("aHR0cHM6Ly9hcGkubXVzaWMueWFuZGV4Lm5ldA==").decode("utf-8")


def fetch_supplement_lyrics(artist: str, title: str) -> Tuple[Optional[str], bool]:
    """
    Выполняет поиск трека в региональном каталоге и извлекает официальный текст из supplement.
    Возвращает (text, is_synced).
    """
    if not artist and not title:
        return None, False

    query = f"{artist} {title}".strip()
    session = requests.Session()
    try:
        q_enc = urllib.parse.quote(query)
        search_url = f"{_BASE_URL}/search?text={q_enc}&type=all&page=0"
        resp = session.get(search_url, headers=HEADERS, timeout=5)
        if resp.status_code != 200:
            return None, False

        data = resp.json()
        tracks = data.get("result", {}).get("tracks", {}).get("results", [])
        if not tracks:
            return None, False

        for trk in tracks[:3]:
            track_id = trk.get("id")
            if not track_id:
                continue

            sup_url = f"{_BASE_URL}/tracks/{track_id}/supplement"
            sup_resp = session.get(sup_url, headers=HEADERS, timeout=4)
            if sup_resp.status_code == 200:
                sup_data = sup_resp.json()
                lyrics_obj = sup_data.get("result", {}).get("lyrics")
                if lyrics_obj:
                    full_text = lyrics_obj.get("fullLyrics") or lyrics_obj.get("lyrics")
                    if full_text and len(full_text.strip()) > 30:
                        raw = full_text.strip()
                        is_synced = "[" in raw[:60] and "]" in raw[:60]
                        logger.info(f"[LyricsSupplement] Официальный текст песни успешно найден для '{query}'")
                        return raw, is_synced
    except Exception as e:
        logger.debug(f"[LyricsSupplement] Ошибка поиска текста: {e}")
    finally:
        session.close()

    return None, False
