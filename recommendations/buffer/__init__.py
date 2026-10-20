"""
Package recommendations.buffer:
Modular architecture for Discovery / Stream buffer management:
- constants: configuration, paths, retention TTL, safe console output.
- history: disk persistence, atomic writes, legacy migration.
- cleaner: periodic TTL expiration, database sync, backfill likes.
- refiller: background buffer replenishment and HQ lossless upgrades.
- manager: DiscoveryBufferManager coordinator and singleton instance.
"""

from recommendations.buffer.constants import (
    BUFFER_SUBDIR,
    TARGET_BUFFER_SIZE,
    RETENTION_DAYS,
    HISTORY_FILENAME,
    LEGACY_HISTORY_FILENAME,
    SAVED_DISCOVERIES_DIRNAME,
    safe_print,
)
from recommendations.buffer.history import BufferHistory
from recommendations.buffer.cleaner import BufferCleaner
from recommendations.buffer.refiller import BufferRefiller
from recommendations.buffer.manager import DiscoveryBufferManager, discovery_buffer_manager

__all__ = [
    "BUFFER_SUBDIR",
    "TARGET_BUFFER_SIZE",
    "RETENTION_DAYS",
    "HISTORY_FILENAME",
    "LEGACY_HISTORY_FILENAME",
    "SAVED_DISCOVERIES_DIRNAME",
    "safe_print",
    "BufferHistory",
    "BufferCleaner",
    "BufferRefiller",
    "DiscoveryBufferManager",
    "discovery_buffer_manager",
]
