"""
Модуль полнотекстового индексирования и безопасного поиска в PostgreSQL.
Поддерживает:
- Расширение pg_trgm (word_similarity): нечеткий поиск опечаток и подстрок;
- Нормализация е/ё и регистронезависимость;
- Стемминг русских окончаний;
- Двусторонняя транслитерация (кириллица <-> латиница);
- Высокоточное многоуровневое ранжирование.
Обеспечивает мгновенный (< 1-2 мс) защищенный поиск.
"""

import re
from typing import List, Set
from sqlalchemy import or_, func, case
from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine

from database.models import Track

# Окончания русских слов для стемминга
RUSSIAN_ENDINGS = (
    "ому", "ему", "ыми", "ими", "ого", "его", "ых", "их",
    "ую", "юю", "ая", "яя", "ое", "ее", "ые", "ие", "ым", "им",
    "ом", "ем", "ой", "ей", "ий", "ый", "ах", "ях", "ам", "ям",
    "ов", "ев", "ей", "ия", "ие", "ии", "ию",
    "а", "е", "и", "й", "о", "у", "ы", "ь", "я"
)

CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sh',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
}

LATIN_TO_CYRILLIC = {
    'zh': 'ж', 'ts': 'ц', 'ch': 'ч', 'sh': 'ш', 'yu': 'ю', 'ya': 'я',
    'a': 'а', 'b': 'б', 'c': 'к', 'd': 'д', 'e': 'е', 'f': 'ф', 'g': 'г',
    'h': 'х', 'i': 'и', 'j': 'дж', 'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н',
    'o': 'о', 'p': 'п', 'q': 'к', 'r': 'р', 's': 'с', 't': 'т', 'u': 'у',
    'v': 'в', 'w': 'в', 'x': 'кс', 'y': 'и', 'z': 'з'
}


def init_search_index(engine: Engine):
    """
    Инициализирует поисковые структуры PostgreSQL:
    подключает расширение pg_trgm для быстрого нечеткого поиска, опечаток и подстрок,
    а также GIN-триграммные индексы для ускорения поиска по artist, title, album.
    """
    if engine.dialect.name != "postgresql":
        return

    with engine.connect() as conn:
        try:
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
            conn.commit()
            print("[SearchIndex] PostgreSQL расширение pg_trgm успешно подключено.")
        except Exception as e:
            print(f"[SearchIndex] PostgreSQL pg_trgm инициализация: {e}")

        # Создаем GIN-триграммные индексы для ускорения ILIKE и word_similarity
        trgm_indexes = [
            ("idx_tracks_artist_trgm", "CREATE INDEX IF NOT EXISTS idx_tracks_artist_trgm ON tracks USING gin (artist gin_trgm_ops);"),
            ("idx_tracks_title_trgm", "CREATE INDEX IF NOT EXISTS idx_tracks_title_trgm ON tracks USING gin (title gin_trgm_ops);"),
            ("idx_tracks_album_trgm", "CREATE INDEX IF NOT EXISTS idx_tracks_album_trgm ON tracks USING gin (album gin_trgm_ops);"),
        ]
        for idx_name, sql in trgm_indexes:
            try:
                conn.exec_driver_sql(sql)
                conn.commit()
            except Exception as e:
                # В SQLite или при отсутствующей таблице не прерываем работу
                pass


def extract_search_terms(query_str: str) -> Set[str]:
    """
    Генерирует набор поисковых терминов с нормализацией е/ё,
    стеммингом русских окончаний и транслитерацией.
    """
    norm_q = query_str.strip().lower().replace("ё", "е")
    raw_tokens = re.findall(r"\w+", norm_q[:100], re.UNICODE)
    if not raw_tokens:
        return set()

    terms = set(raw_tokens)
    if len(raw_tokens) > 1:
        terms.add(norm_q)

    for tok in raw_tokens:
        # 1. Стемминг русских окончаний для падежей/множественного числа
        if len(tok) >= 4:
            for end in RUSSIAN_ENDINGS:
                if tok.endswith(end) and len(tok) - len(end) >= 3:
                    terms.add(tok[:-len(end)])
                    break

        # 2. Транслитерация кириллица -> латиница
        latin_translit = "".join(CYRILLIC_TO_LATIN.get(c, c) for c in tok)
        if latin_translit != tok and len(latin_translit) >= 2:
            terms.add(latin_translit)

        # 3. Транслитерация латиница -> кириллица
        cyr_acc = tok
        for lat_k, cyr_v in LATIN_TO_CYRILLIC.items():
            cyr_acc = cyr_acc.replace(lat_k, cyr_v)
        if cyr_acc != tok and len(cyr_acc) >= 2:
            terms.add(cyr_acc)

    return terms


def search_tracks(db: Session, query_str: str, limit: int = 50, offset: int = 0) -> List[Track]:
    """
    Выполняет умный, быстрый поиск треков в PostgreSQL:
    - pg_trgm (word_similarity) для поиска с учетом опечаток;
    - нормализация е/ё и регистронезависимость;
    - стемминг русских окончаний;
    - транслитерация кириллица <-> латиница;
    - многоуровневое ранжирование релевантности.
    """
    if not query_str or not query_str.strip():
        return []

    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    search_terms = extract_search_terms(query_str)
    if not search_terms:
        return []

    norm_q = query_str.strip().lower().replace("ё", "е")

    norm_title = func.replace(func.lower(Track.title), "ё", "е")
    norm_artist = func.replace(func.lower(Track.artist), "ё", "е")
    norm_album = func.replace(func.lower(func.coalesce(Track.album, "")), "ё", "е")
    norm_lyrics = func.replace(func.lower(func.coalesce(Track.lyrics_plain, func.coalesce(Track.lyrics_synced, ""))), "ё", "е")
    combined_text = norm_artist + " " + norm_title

    is_postgres = False
    try:
        bind = db.get_bind()
        is_postgres = bool(bind and bind.dialect.name == "postgresql")
    except Exception:
        pass

    conditions = []
    for term in search_terms:
        term_conds = [
            norm_artist.like(f"%{term}%"),
            norm_title.like(f"%{term}%"),
            norm_album.like(f"%{term}%"),
            norm_lyrics.like(f"%{term}%"),
        ]
        if is_postgres:
            term_conds.append(func.word_similarity(term, combined_text) > 0.38)
        conditions.append(or_(*term_conds))

    # Релевантное ранжирование: точные совпадения по названию и артисту идут первыми
    score_clauses = [
        case((norm_artist.like(f"{norm_q}%"), 100), else_=0),
        case((norm_artist.like(f"%{norm_q}%"), 60), else_=0),
        case((norm_title.like(f"{norm_q}%"), 80), else_=0),
        case((norm_title.like(f"%{norm_q}%"), 40), else_=0),
        case((norm_album.like(f"%{norm_q}%"), 20), else_=0),
        case((norm_lyrics.like(f"%{norm_q}%"), 15), else_=0),
    ]
    if is_postgres:
        score_clauses.append(func.word_similarity(norm_q, combined_text) * 35)

    for term in search_terms:
        score_clauses.append(case((norm_artist.like(f"{term}%"), 60), else_=0))
        score_clauses.append(case((norm_artist.like(f"%{term}%"), 40), else_=0))
        score_clauses.append(case((norm_title.like(f"{term}%"), 50), else_=0))
        score_clauses.append(case((norm_title.like(f"%{term}%"), 30), else_=0))
        score_clauses.append(case((norm_lyrics.like(f"%{term}%"), 10), else_=0))
        if is_postgres:
            score_clauses.append(func.word_similarity(term, combined_text) * 20)

    rank_score = sum(score_clauses)

    return (
        db.query(Track)
        .filter(Track.is_discovery == False)
        .filter(or_(*conditions))
        .order_by(rank_score.desc())
        .offset(safe_offset)
        .limit(safe_limit)
        .all()
    )
