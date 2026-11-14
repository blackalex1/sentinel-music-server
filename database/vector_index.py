import json
from typing import List, Optional, Set
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy import text, func

from database.models import Track
from recommendations.embeddings import deserialize_vector, cosine_similarity
from recommendations.mood import apply_mood_filter


_HAS_PGVECTOR = False


def init_vector_index(engine: Engine):
    """
    Инициализирует аппаратный векторный поиск PostgreSQL (расширение pgvector):
    - Создает расширение vector (если поддерживается СУБД)
    - Добавляет столбец embedding_vec vector(16)
    - Создает индекс HNSW по косинусному расстоянию (vector_cosine_ops)
    - Синхронизирует существующие спектральные векторы
    """
    global _HAS_PGVECTOR
    if engine.dialect.name != "postgresql":
        _HAS_PGVECTOR = False
        return

    with engine.connect() as conn:
        try:
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector;")
            conn.commit()
            _HAS_PGVECTOR = True
            print("[VectorIndex] PostgreSQL расширение pgvector успешно подключено.")
        except Exception as e:
            _HAS_PGVECTOR = False
            print(f"[VectorIndex] PostgreSQL pgvector расширение недоступно: {e}")
            return

        try:
            conn.exec_driver_sql("ALTER TABLE tracks ADD COLUMN IF NOT EXISTS embedding_vec vector(16);")
            conn.commit()
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS idx_tracks_embedding_hnsw ON tracks "
                "USING hnsw (embedding_vec vector_cosine_ops);"
            )
            conn.commit()
        except Exception as ie:
            print(f"[VectorIndex] Инициализация HNSW индекса: {ie}")

        # Синхронизация треков, у которых есть embedding_json, но не заполнен embedding_vec
        try:
            conn.exec_driver_sql("""
                UPDATE tracks 
                SET embedding_vec = embedding_json::vector 
                WHERE embedding_json IS NOT NULL 
                  AND embedding_vec IS NULL 
                  AND length(embedding_json) > 10;
            """)
            conn.commit()
        except Exception:
            pass


def is_pgvector_active(db: Session) -> bool:
    """Проверяет, доступен ли аппаратный векторный поиск pgvector в текущей сессии БД."""
    global _HAS_PGVECTOR
    try:
        if db.bind and db.bind.dialect.name == "postgresql" and _HAS_PGVECTOR:
            return True
    except Exception:
        pass
    return False


def find_nearest_tracks(
    db: Session,
    target_vector: List[float],
    limit: int = 100,
    mood: Optional[str] = None,
    exclude_ids: Optional[Set[int]] = None
) -> List[Track]:
    """
    Выполняет аппаратный векторный поиск ближайших треков (Nearest Neighbors).
    В PostgreSQL использует оператор косинусного расстояния `<=>` и индекс HNSW.
    В SQLite автоматически переключается на встроенный программный расчет косинуса.
    """
    if not target_vector or len(target_vector) != 16:
        return []

    exclude_set = exclude_ids or set()

    # 1. Аппаратный поиск через pgvector (PostgreSQL)
    if is_pgvector_active(db):
        try:
            vec_str = "[" + ",".join(str(round(x, 4)) for x in target_vector) + "]"
            raw_sql = """
                SELECT id FROM tracks
                WHERE is_discovery = false
                  AND embedding_vec IS NOT NULL
            """
            params = {"vec": vec_str, "lim": max(10, limit * 2)}
            if exclude_set:
                raw_sql += " AND id NOT IN :ex_ids"
                params["ex_ids"] = tuple(exclude_set)

            raw_sql += " ORDER BY embedding_vec <=> :vec::vector LIMIT :lim"

            rows = db.execute(text(raw_sql), params).fetchall()
            found_ids = [r[0] for r in rows]
            if found_ids:
                q = db.query(Track).filter(Track.id.in_(found_ids))
                if mood and mood not in ("default", "all"):
                    q = apply_mood_filter(q, mood)
                tracks = q.all()
                # Сортируем обратно по порядку схожести
                id_map = {t.id: t for t in tracks}
                ordered = [id_map[tid] for tid in found_ids if tid in id_map]
                if ordered:
                    return ordered[:limit]
        except Exception:
            # При любой ошибке в raw SQL бесшовно переходим на программный фоллбэк
            pass

    # 2. Программный фоллбэк (SQLite / fallback)
    query = (
        db.query(Track)
        .filter(Track.is_discovery == False)
        .filter(Track.embedding_json.isnot(None))
    )
    if exclude_set:
        query = query.filter(~Track.id.in_(exclude_set))
    if mood and mood not in ("default", "all"):
        query = apply_mood_filter(query, mood)

    pool = query.limit(200).all()
    if not pool:
        return []

    scored = []
    for t in pool:
        v = deserialize_vector(t.embedding_json)
        if v and len(v) == 16:
            sim = cosine_similarity(target_vector, v)
            scored.append((sim, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:limit]]
