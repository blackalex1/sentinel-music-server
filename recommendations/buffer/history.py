import os
import json
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

from recommendations.buffer.constants import (
    HISTORY_FILENAME,
    LEGACY_HISTORY_FILENAME,
    safe_print
)


class BufferHistory:
    """
    Управление файлом истории буфера (stream_history.json):
    - Загрузка и потокобезопасная атомарная запись на диск.
    - Автоматическая миграция со старого имени файла.
    - Отслеживание изменений путей и статусов удаления треков.
    """

    def __init__(
        self,
        buffer_dir: str,
        history_filename: str = HISTORY_FILENAME,
        legacy_filename: str = LEGACY_HISTORY_FILENAME,
        lock: Optional[threading.RLock] = None
    ):
        self.buffer_dir = buffer_dir
        self.history_json_path = os.path.join(self.buffer_dir, history_filename)
        self.legacy_json_path = os.path.join(self.buffer_dir, legacy_filename)
        self._lock = lock or threading.RLock()
        self._cached_records = None
        self._cached_mtime = 0.0

        self._ensure_dir()

    def _ensure_dir(self):
        """Создает буферную директорию и при необходимости мигрирует устаревший файл истории."""
        try:
            os.makedirs(self.buffer_dir, exist_ok=True)
            # Миграция: если существует старый файл, переименовываем в stream_history.json
            if os.path.exists(self.legacy_json_path) and not os.path.exists(self.history_json_path):
                try:
                    os.replace(self.legacy_json_path, self.history_json_path)
                    safe_print("[DiscoveryBuffer] Миграция: файл истории обновлен на stream_history.json")
                except Exception as me:
                    safe_print(f"[DiscoveryBuffer] Не удалось переименовать legacy файл: {me}")

            if not os.path.exists(self.history_json_path):
                with open(self.history_json_path, "w", encoding="utf-8") as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
        except Exception as e:
            safe_print(f"[DiscoveryBuffer] Ошибка создания директории буфера: {e}")

    def load_history(self) -> List[Dict[str, Any]]:
        """Загружает журнал треков Потока с кэшированием в памяти по mtime."""
        with self._lock:
            if not os.path.exists(self.history_json_path):
                return []
            try:
                mtime = os.path.getmtime(self.history_json_path)
                if self._cached_records is not None and mtime == self._cached_mtime:
                    return [r.copy() for r in self._cached_records]

                with open(self.history_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._cached_records = data
                    self._cached_mtime = mtime
                    return [r.copy() for r in data]
            except Exception as e:
                safe_print(f"[DiscoveryBuffer] Ошибка чтения {self.history_json_path}: {e}")
                return []

    def save_history(self, records: List[Dict[str, Any]]):
        """Атомарно сохраняет журнал треков Потока в JSON на диск с обновлением кэша."""
        with self._lock:
            tmp_path = f"{self.history_json_path}.tmp"
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.history_json_path)
                self._cached_records = [r.copy() for r in records]
                self._cached_mtime = os.path.getmtime(self.history_json_path)
            except Exception as e:
                safe_print(f"[DiscoveryBuffer] Ошибка записи журнала: {e}")
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

    def handle_track_deletion(self, track_id: int):
        """
        Обновляет статус трека в истории потока (stream_history.json) при ручном удалении пользователем.
        """
        records = self.load_history()
        updated = False
        with self._lock:
            for r in records:
                if r.get("track_id") == track_id and r.get("status") not in (
                    "disliked_deleted", "expired_deleted", "manually_deleted"
                ):
                    r["status"] = "manually_deleted"
                    r["deleted_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    updated = True
            if updated:
                self.save_history(records)

    def update_track_path(self, track_id: int, new_path: str):
        """
        Обновляет путь к файлу трека в stream_history.json при его перемещении или апгрейде качества.
        """
        records = self.load_history()
        updated = False
        with self._lock:
            for r in records:
                if r.get("track_id") == track_id:
                    r["file_path"] = new_path
                    updated = True
            if updated:
                self.save_history(records)
