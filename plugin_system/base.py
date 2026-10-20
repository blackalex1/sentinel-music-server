from abc import ABC
from typing import Dict, Any, Optional, Tuple, List


class BasePlugin(ABC):
    """
    Базовый класс для всех подключаемых плагинов сервера.
    Позволяет расширять возможности сервера без изменения основного кода.
    """
    name: str = "BasePlugin"
    version: str = "1.0.0"
    description: str = "Базовый плагин"
    enabled: bool = True
    priority: int = 100  # Порядок выполнения в цепочке (меньшее число = выше приоритет)

    # Интеграция с веб-интерфейсом (Self-Contained Plugin)
    has_ui: bool = False
    ui_entry: Optional[str] = None   # Относительный URL JS-модуля (/plugins/<name>/index.js)
    ui_styles: Optional[str] = None  # Относительный URL таблицы стилей (/plugins/<name>/styles.css)

    async def on_startup(self, context: Dict[str, Any]) -> None:
        """Вызывается при запуске сервера."""
        pass

    async def on_shutdown(self) -> None:
        """Вызывается при остановке сервера."""
        pass

    async def on_track_import_request(
        self,
        artist: str,
        title: str,
        destination: str = "",
        force_replace: bool = False,
        exclude_sources: Optional[list] = None
    ) -> bool:
        """
        Хук запроса на импорт/загрузку внешнего трека.
        Если плагин умеет находить и импортировать трек — возвращает True.
        Поддерживает принудительную замену (force_replace) и исключение источников (exclude_sources).
        """
        return False

    async def search_candidates(self, artist: str, title: str, limit: int = 5) -> list:
        """
        Ищет доступные варианты трека (оригинал, slowed, remix, разные форматы/битрейты).
        Возвращает список словарей с описанием вариантов для выбора пользователем.
        """
        return []

    async def download_candidate(self, candidate: Dict[str, Any], destination: str = "", force_replace: bool = True) -> bool:
        """
        Скачивает конкретный вариант трека, выбранный пользователем.
        """
        return False

    async def get_candidate_preview_url(self, candidate: Dict[str, Any]) -> Optional[str]:
        """
        Возвращает прямую ссылку на аудиопоток для предпрослушивания (если поддерживается).
        """
        return None

    async def on_user_reaction(self, track_id: int, is_like: bool, is_dislike: bool) -> None:
        """Вызывается при установке лайка или дизлайка."""
        pass

    async def on_track_played(self, track_id: int) -> None:
        """Вызывается после прослушивания трека."""
        pass

    async def get_cover_for_track(self, track: Any) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Хук получения обложки альбома (встроенной, локальной или онлайн).
        Возвращает (image_bytes, mime_type) или (None, None).
        """
        return None, None

    async def get_lyrics_for_track(self, track: Any) -> Tuple[bool, List[dict], str]:
        """
        Хук получения текста песни (синхронизированного караоке или обычного).
        Возвращает (is_synced: bool, lines: list, raw_text: str).
        """
        return False, [], ""

    # ==========================================
    # Коннекторы API и расширений функционала
    # ==========================================

    def get_router(self) -> Optional[Any]:
        """
        Возвращает FastAPI APIRouter плагина (если плагин предоставляет собственные эндпоинты API).
        Роутер автоматически подключается ядром через PluginManager.
        """
        return None

    def can_handle_candidate(self, candidate_id: str) -> bool:
        """
        Проверяет, относится ли данный ID кандидата к этому плагину.
        """
        return False

    def resolve_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        """
        Восстанавливает структуру кандидата по ID (при устаревании кэша в оперативной памяти).
        """
        return None

    def can_preview_candidate(self, candidate: Dict[str, Any]) -> bool:
        """
        Определяет, поддерживает ли данный кандидат предпрослушивание аудио.
        """
        return True

    def get_preview_headers(self, candidate: Dict[str, Any]) -> Dict[str, str]:
        """
        Возвращает HTTP заголовки для обхода анти-хотлинка при предпрослушивании (Referer, Cookie и др.).
        """
        return {}

    async def get_preview_stream(self, candidate: Dict[str, Any], range_header: Optional[str] = None) -> Optional[Any]:
        """
        Возвращает StreamingResponse или генератор байт для предпрослушивания аудиопотока.
        Плагин сам инкапсулирует обход анти-хотлинка (Referer, Cookie, User-Agent) без хардкода в ядре.
        """
        return None

    async def backfill_covers(self, db: Any, limit: int = 50) -> Dict[str, Any]:
        """
        Пакетное фоновое заполнение обложек треков (если поддерживается плагином).
        """
        return {"supported": False}

    def clear_cover_cache(self, track_id: int) -> bool:
        """
        Сброс кэша обложки для указанного трека.
        """
        return False

