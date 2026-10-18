"""
Модуль нормализации запросов, генерации поисковых вариантов и скоринга кандидатов.
Единый алгоритм очистки и валидации для всех 5 источников.
"""

import re
import difflib
from typing import List, Tuple


def clean_query(text: str) -> str:
    """Очищает строку от фитов, продюсеров и мусора в скобках."""
    if not text:
        return ""
    # Удаляем feat/ft/prod конструкции
    text = re.sub(r'\(.*?\b(?:feat|ft|prod|prod\sby|bonus)\b.*?\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?\b(?:feat|ft|prod|prod\sby|bonus)\b.*?\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(?:feat|ft|prod|prod\sby)\b.*', '', text, flags=re.IGNORECASE)
    # Удаляем пустые скобки
    text = re.sub(r'\(\s*\)|\[\s*\]', '', text)
    # Удаляем спецсимволы
    text = re.sub(r'[^\w\s\-\.,]', ' ', text, flags=re.UNICODE)
    return " ".join(text.split()).strip()


def normalize_tokens(text: str) -> List[str]:
    """Разбивает строку на нормализованные токены без пунктуации."""
    clean = re.sub(r'[^\w\s]', ' ', text.lower(), flags=re.UNICODE)
    return [w for w in clean.split() if len(w) >= 2]


def detect_version_type(title: str) -> Tuple[str, str]:
    """
    Определяет тип и отображаемый лейбл версии по названию трека.
    Возвращает: (version_type, version_label)
    """
    t_lower = title.lower()
    if "slowed" in t_lower:
        return "slowed", "Slowed"
    elif "speed up" in t_lower or "sped up" in t_lower:
        return "speed_up", "Speed Up"
    elif "remix" in t_lower or "mix" in t_lower:
        return "remix", "Remix"
    elif "acoustic" in t_lower:
        return "acoustic", "Acoustic"
    elif "live" in t_lower:
        return "live", "Live"
    elif "instrumental" in t_lower or "минус" in t_lower:
        return "instrumental", "Instrumental"
    elif "explicit" in t_lower:
        return "original_explicit", "Original (Explicit)"
    elif "radio edit" in t_lower:
        return "radio_edit", "Radio Edit"
    return "original", "Original"


def generate_candidate_queries(artist: str, title: str) -> List[str]:
    """
    Генерирует поисковые варианты запросов:
    1. Исходный 'Артист Название'
    2. Очищенный 'Артист Название'
    3. Разделенные по отдельным артистам (если несколько через запятую)
    4. Чистое название трека (если достаточно длинное)
    """
    queries = []
    raw = f"{artist} {title}".strip()
    if raw:
        queries.append(raw)

    c_art = clean_query(artist)
    c_tit = clean_query(title)
    if f"{c_art} {c_tit}" not in queries and (c_art != artist or c_tit != title):
        queries.append(f"{c_art} {c_tit}")

    # Если несколько артистов через запятую или &
    if ',' in artist or '&' in artist:
        parts = [a.strip() for a in re.split(r'[,&]', artist) if a.strip()]
        for single_art in parts:
            cand = f"{single_art} {title}"
            if cand not in queries:
                queries.append(cand)
            c_single = clean_query(single_art)
            if f"{c_single} {c_tit}" not in queries:
                queries.append(f"{c_single} {c_tit}")

    # Чистое название трека как крайний fallback
    if c_tit and c_tit not in queries and len(c_tit.split()) >= 3:
        queries.append(c_tit)

    return queries


def score_candidate_match(
    q_art: str,
    q_tit: str,
    c_art: str,
    c_tit: str,
    c_path: str = ""
) -> int:
    """
    Оценивает релевантность кандидата запросу.
    Возвращает отрицательное число (< 0), если трек не подходит (штраф за нежелательные модификации,
    несовпадение артиста или названия). При совпадении возвращает положительный score (0..100).
    """
    c_tit_l = c_tit.lower()
    q_tit_l = q_tit.lower()
    c_art_l = c_art.lower()
    q_art_l = q_art.lower()
    comb_text = f"{c_art_l} {c_tit_l} {c_path.lower()}".strip()
    q_comb = f"{q_art_l} {q_tit_l}".strip()

    # 1. Запрещенные модификации, если их не было в исходном запросе
    unwanted = [
        "slowed", "slow", "speed up", "sped up", "speedup", "nightcore", "daycore",
        "bass boosted", "bassboost", "reverb", "mashup", "cover", "кавер",
        "karaoke", "караоке", "tribute", "instrumental", "минус", "минусовка"
    ]
    for mod in unwanted:
        if mod in comb_text and mod not in q_comb:
            return -1

    if "remix" in comb_text and "remix" not in q_comb:
        return -1

    # 2. Проверка схожести названия
    clean_q_tit = re.sub(r'[^\w\s]', '', re.sub(r'\(.*?\)|\[.*?\]', '', q_tit_l)).strip()
    clean_c_tit = re.sub(r'[^\w\s]', '', re.sub(r'\(.*?\)|\[.*?\]', '', c_tit_l)).strip()
    sim = difflib.SequenceMatcher(None, clean_q_tit, clean_c_tit).ratio()
    is_sub = (clean_q_tit in clean_c_tit or clean_c_tit in clean_q_tit) and len(clean_q_tit) >= 3

    q_tit_tokens = [w for w in normalize_tokens(clean_q_tit) if len(w) >= 2]
    matched_tit_tokens = sum(1 for t in q_tit_tokens if t in comb_text)
    token_ok = (matched_tit_tokens == len(q_tit_tokens)) if len(q_tit_tokens) <= 2 else (matched_tit_tokens >= max(2, int(len(q_tit_tokens) * 0.7)))

    if sim < 0.65 and not is_sub and not token_ok:
        return -1

    # 3. Строгая проверка артиста (если артист был задан в запросе)
    if q_art_l.strip():
        raw_arts = [a.strip() for a in re.split(r'[,&]|\bfeat\b|\bft\b', q_art_l) if a.strip()]
        art_matched = False
        for a in raw_arts:
            toks = [w for w in normalize_tokens(a) if w not in ["feat", "ft", "prod"]]
            if not toks:
                continue
            if len(toks) == 1:
                if toks[0] in comb_text:
                    art_matched = True
                    break
            else:
                if sum(1 for t in toks if t in comb_text) >= len(toks):
                    art_matched = True
                    break
        if not art_matched:
            return -1

    # Базовый score от схожести названия
    score = int(sim * 50) + (25 if is_sub else 0) + (25 if token_ok else 0)
    return score
