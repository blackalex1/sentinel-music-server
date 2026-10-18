"""
Модульный пакет унифицированного конвейера импорта треков (Ingestion Pipeline).
Включает:
- models: Единая схема данных кандидата трека (make_candidate, UnifiedCandidate)
- cleaner: Очистка поисковых строк, вариантов запроса и скоринг (clean_query, generate_candidate_queries, score_candidate_match, detect_version_type)
- http: Потокобезопасный HTTP клиент с защитой от флуда (PoliteSession)
- storage: Сохранение аудио, простановка тегов ID3 и аудит (save_audio_file, resolve_target_path, sanitize_filename, apply_id3_tags, log_audit_history)
"""

from plugin_system.base import BasePlugin
from plugin_system.ingestion.models import UnifiedCandidate, make_candidate
from plugin_system.ingestion.cleaner import (
    clean_query,
    normalize_tokens,
    detect_version_type,
    generate_candidate_queries,
    score_candidate_match
)
from plugin_system.ingestion.http import PoliteSession
from plugin_system.ingestion.storage import (
    sanitize_filename,
    resolve_target_path,
    apply_id3_tags,
    save_audio_file,
    log_audit_history
)

__all__ = [
    "BasePlugin",
    "UnifiedCandidate",
    "make_candidate",
    "clean_query",
    "normalize_tokens",
    "detect_version_type",
    "generate_candidate_queries",
    "score_candidate_match",
    "PoliteSession",
    "sanitize_filename",
    "resolve_target_path",
    "apply_id3_tags",
    "save_audio_file",
    "log_audit_history",
]
