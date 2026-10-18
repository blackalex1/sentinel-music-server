import re
from typing import List, Dict

LRC_PATTERN = re.compile(r'\[(\d+):(\d+)(?:\.(\d+))?\](.*)')


def parse_lrc(lrc_text: str) -> List[Dict[str, any]]:
    """
    Парсит LRC разметку в список миллисекундных таймкодов.
    Совместимо с Android SyncLyricsUseCase O(log N).
    Возвращает:
    [
        {"time_ms": 12340, "time_sec": 12.34, "text": "Текст строки"},
        ...
    ]
    """
    if not lrc_text:
        return []

    lines = []
    for line in lrc_text.splitlines():
        line = line.strip()
        match = LRC_PATTERN.search(line)
        if match:
            m, s, ms, text = match.groups()
            ms_val = int(ms) if ms else 0
            if len(str(ms_val)) == 2:
                ms_val *= 10  # 2 знака -> миллисекунды (напр. .45 -> 450ms)
            elif len(str(ms_val)) == 1:
                ms_val *= 100

            total_ms = (int(m) * 60 + int(s)) * 1000 + ms_val
            text_clean = text.strip()

            lines.append({
                "time_ms": total_ms,
                "time_sec": round(total_ms / 1000.0, 2),
                "text": text_clean
            })

    lines.sort(key=lambda x: x["time_ms"])
    return lines
