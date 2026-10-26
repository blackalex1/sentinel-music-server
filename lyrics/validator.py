"""
Модуль валидации и фильтрации релевантности текстов песен.
Защищает от:
1. Подтягивания текстов на неподходящих языках (например, китайский вместо английского/русского).
2. Ложных срабатываний нечеткого поиска, когда возвращается совершенно другой трек.
"""

import re
from typing import Optional

CJK_REGEX = re.compile(r'[\u4e00-\u9fff]')
STOP_WORDS = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with", "by", "и", "в", "на", "с", "по", "к", "о", "об"}


def is_cjk(text: str) -> bool:
    """Проверяет, содержит ли строка иероглифы (китайские/японские)."""
    return bool(CJK_REGEX.search(text))


def normalize_str(s: str) -> str:
    """Упрощает строку для сравнения (нижний регистр, очистка тегов и спецсимволов)."""
    if not s:
        return ""
    s = s.lower()
    # Убираем скобки с feat, remix, edit, prod, official, audio
    s = re.sub(r'[\(\[][^\)\]]*(?:feat|ft|remix|edit|prod|explicit|official|audio|version)[^\)\]]*[\)\]]', '', s)
    # Заменяем пунктуацию на пробелы
    s = re.sub(r'[^\w\s]', ' ', s)
    return ' '.join(s.split())


def get_meaningful_tokens(s: str) -> set:
    """Возвращает множество значимых слов (длиной от 2 символов, исключая предлоги)."""
    norm = normalize_str(s)
    tokens = set()
    for tok in norm.split():
        if len(tok) >= 2 and tok not in STOP_WORDS:
            tokens.add(tok)
    return tokens


def validate_lyrics_match(
    target_artist: str,
    target_title: str,
    cand_artist: Optional[str] = None,
    cand_title: Optional[str] = None,
    lyrics_text: Optional[str] = None
) -> bool:
    """
    Строго проверяет релевантность найденного текста песни.
    Возвращает True только если текст действительно относится к запрашиваемому треку.
    """
    if not lyrics_text or len(lyrics_text.strip()) < 10:
        return False

    # 1. Защита от CJK (китайских иероглифов) для не-азиатских треков
    query_has_cjk = is_cjk(f"{target_artist} {target_title}")
    if not query_has_cjk:
        cjk_chars = len(CJK_REGEX.findall(lyrics_text))
        if cjk_chars > 5:
            # Текст содержит китайские иероглифы, хотя трек не азиатский
            return False

    # 2. Проверка совпадения названия трека
    if cand_title:
        target_tokens = get_meaningful_tokens(target_title)
        cand_tokens = get_meaningful_tokens(cand_title)

        if target_tokens and cand_tokens:
            overlap = target_tokens.intersection(cand_tokens)
            if not overlap:
                # Ни одно значимое слово из названия не совпало
                return False

    # 3. Проверка совпадения исполнителя
    if cand_artist and target_artist:
        target_art_tokens = get_meaningful_tokens(target_artist)
        cand_art_tokens = get_meaningful_tokens(cand_artist)

        if target_art_tokens and cand_art_tokens:
            overlap = target_art_tokens.intersection(cand_art_tokens)
            if not overlap:
                # Если в исполнителе нет общих слов, проверяем, не упомянут ли артист в названии трека
                cand_full = normalize_str(f"{cand_artist} {cand_title or ''}")
                if not any(tok in cand_full for tok in target_art_tokens if len(tok) >= 3):
                    return False

    return True
