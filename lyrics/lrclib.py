import requests
from typing import Optional, Dict, Any

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
            if data.get("syncedLyrics"):
                return {"full": data["syncedLyrics"], "is_synced": True}
            elif data.get("plainLyrics"):
                return {"full": data["plainLyrics"], "is_synced": False}

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
                # Ищем среди результатов первый с синхронизированным текстом
                for item in results:
                    if item.get("syncedLyrics"):
                        return {"full": item["syncedLyrics"], "is_synced": True}
                # Если с таймкодами нет, отдаем обычный текст
                if results[0].get("plainLyrics"):
                    return {"full": results[0]["plainLyrics"], "is_synced": False}
    except Exception as e:
        print(f"[LRCLIB] Ошибка запроса текста: {e}")

    return None
