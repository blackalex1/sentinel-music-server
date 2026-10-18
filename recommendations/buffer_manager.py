"""
Backwards-compatibility proxy for recommendations.buffer package.
All implementation has been decomposed into modular components under recommendations.buffer:
- recommendations.buffer.constants
- recommendations.buffer.history
- recommendations.buffer.cleaner
- recommendations.buffer.refiller
- recommendations.buffer.manager
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
