import requests
from typing import Optional, Dict, Any

from lyrics.validator import validate_lyrics_match

LRCLIB_API_URL = "https://lrclib.net/api"
USER_AGENT = "MusicService/1.0 (Open-Source Lyrics Engine; +https://github.com/blackalex1)"


def fetch_lyrics(artist: str, title: str, album: Optional[str] = None, duration: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """
    Поиск караоке-текста в открытой глобальной базе LRCLIB (без необходимости токенов или авторизации).
    Возвращает dict с полями:
    - 'full': текст (LRC или plain)
    - 'is_synced': bool (наличие синхронизированных таймкодов)
    """
    if not artist or not title:
        return None

    headers = {"User-Agent": USER_AGENT}
    params = {"artist_name": artist, "track_name": title}
    if album:
        params["album_name"] = album
    if duration:
        params["duration"] = int(duration)

    try:
        # 1. Сначала пробуем точный поиск по артисту и треку
        resp = requests.get(f"{LRCLIB_API_URL}/get", params=params, headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            cand_artist = data.get("artistName", "")
            cand_title = data.get("trackName", "")
            synced = data.get("syncedLyrics")
            plain = data.get("plainLyrics")
            full = synced or plain
            if full and validate_lyrics_match(artist, title, cand_artist=cand_artist, cand_title=cand_title, lyrics_text=full):
                return {"full": full, "is_synced": bool(synced)}

        # 2. Если точный поиск не дал результата, пробуем полнотекстовый поиск
        search_resp = requests.get(
            f"{LRCLIB_API_URL}/search",
            params={"q": f"{artist} {title}"},
            headers=headers,
            timeout=6
        )
        if search_resp.status_code == 200:
            results = search_resp.json()
            if results and isinstance(results, list):
                # 1) Ищем среди результатов первый валидный с синхронизированным текстом
                for item in results:
                    synced = item.get("syncedLyrics")
                    if not synced:
                        continue
                    cand_artist = item.get("artistName", "")
                    cand_title = item.get("trackName", "") or item.get("name", "")
                    if validate_lyrics_match(artist, title, cand_artist=cand_artist, cand_title=cand_title, lyrics_text=synced):
                        return {"full": synced, "is_synced": True}
                # 2) Если с таймкодами нет, ищем валидный обычный текст
                for item in results:
                    plain = item.get("plainLyrics")
                    if not plain:
                        continue
                    cand_artist = item.get("artistName", "")
                    cand_title = item.get("trackName", "") or item.get("name", "")
                    if validate_lyrics_match(artist, title, cand_artist=cand_artist, cand_title=cand_title, lyrics_text=plain):
                        return {"full": plain, "is_synced": False}
    except Exception as e:
        print(f"[LRCLIB] Ошибка запроса текста: {e}")

    return None
