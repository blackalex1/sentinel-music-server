import os
import sys
import inspect
import importlib.util
import asyncio
from typing import List, Dict, Any, Optional, Tuple

from plugin_system.base import BasePlugin


class PluginManager:
    """
    Менеджер динамической загрузки плагинов из папки plugins/.
    Изолирует сторонний и пользовательский функционал от ядра системы.
    """

    def __init__(self, plugins_dir: Optional[str] = None):
        if plugins_dir is None:
            # По умолчанию server/plugins
            plugins_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "plugins"))
        self.plugins_dir = plugins_dir
        self.plugins: List[BasePlugin] = []

    def load_plugins(self) -> int:
        """Сканирует папку plugins/ и загружает все найденные модули и пакеты."""
        self.plugins.clear()
        if not os.path.exists(self.plugins_dir):
            return 0

        if self.plugins_dir not in sys.path:
            sys.path.insert(0, self.plugins_dir)

        loaded_count = 0
        seen_names = set()

        for item in sorted(os.listdir(self.plugins_dir)):
            if item.startswith("_") or item.startswith(".") or item.endswith(".example"):
                continue

            item_path = os.path.join(self.plugins_dir, item)
            file_path = None
            module_name = None
            search_locations = None

            pkg_name = None
            file_path = None
            search_locations = None

            if os.path.isdir(item_path):
                init_file = os.path.join(item_path, "__init__.py")
                if os.path.exists(init_file):
                    file_path = init_file
                    pkg_name = f"plugins.{item}"
                    search_locations = [item_path]
            elif item.endswith(".py"):
                file_path = item_path
                pkg_name = f"plugins.{os.path.splitext(item)[0]}"

            if not pkg_name:
                continue

            try:
                try:
                    module = importlib.import_module(pkg_name)
                except Exception:
                    if search_locations:
                        spec = importlib.util.spec_from_file_location(
                            pkg_name,
                            file_path,
                            submodule_search_locations=search_locations
                        )
                    else:
                        spec = importlib.util.spec_from_file_location(pkg_name, file_path)

                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[pkg_name] = module
                        spec.loader.exec_module(module)
                    else:
                        continue

                # Алиас для обратной совместимости
                sys.modules[f"server_plugin_{item}"] = module

                # Ищем все классы, наследующие BasePlugin (кроме самого BasePlugin)
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                        if getattr(obj, "name", None) in seen_names:
                            continue
                        plugin_instance = obj()
                        if plugin_instance.enabled:
                            # Автоматическое обнаружение статических UI компонентов плагина
                            if os.path.isdir(item_path):
                                ui_dir = os.path.join(item_path, "ui")
                                if os.path.isdir(ui_dir):
                                    plugin_instance.has_ui = True
                                    if not getattr(plugin_instance, "ui_entry", None) and os.path.exists(os.path.join(ui_dir, "index.js")):
                                        plugin_instance.ui_entry = f"/plugins/{item}/index.js"
                                    if not getattr(plugin_instance, "ui_styles", None) and os.path.exists(os.path.join(ui_dir, "styles.css")):
                                        plugin_instance.ui_styles = f"/plugins/{item}/styles.css"

                            self.plugins.append(plugin_instance)
                            if getattr(obj, "name", None):
                                seen_names.add(obj.name)
                            ui_info = f" [UI: {plugin_instance.ui_entry}]" if getattr(plugin_instance, "has_ui", False) else ""
                            print(f"[PluginManager] Загружен плагин: {plugin_instance.name} v{plugin_instance.version} (priority: {getattr(plugin_instance, 'priority', 100)}){ui_info}")
                            loaded_count += 1
            except Exception as e:
                print(f"[PluginManager] Ошибка загрузки плагина {item}: {e}")

        # Сортируем плагины по приоритету (меньшее число выполняется раньше)
        self.plugins.sort(key=lambda p: getattr(p, "priority", 100))
        return loaded_count

    def mount_plugin_assets(self, app) -> None:
        """
        Монтирует изолированные статические директории интерфейса плагинов (ui/)
        в FastAPI приложение по маршруту /plugins/<plugin_name>/.
        Исходные файлы Python (.py) никогда не отдаются наружу.
        """
        from fastapi.staticfiles import StaticFiles
        if not os.path.exists(self.plugins_dir):
            return

        for item in sorted(os.listdir(self.plugins_dir)):
            if item.startswith("_") or item.startswith("."):
                continue
            item_path = os.path.join(self.plugins_dir, item)
            if os.path.isdir(item_path):
                ui_dir = os.path.join(item_path, "ui")
                if os.path.isdir(ui_dir):
                    mount_path = f"/plugins/{item}"
                    app.mount(mount_path, StaticFiles(directory=ui_dir), name=f"plugin_ui_{item}")
                    print(f"[PluginManager] Смонтирован UI плагина: {item} -> {mount_path}")

    def mount_plugin_routers(self, app) -> int:
        """
        Автоматически монтирует API роутеры всех активных плагинов в приложение FastAPI.
        Позволяет плагинам предоставлять собственные HTTP эндпоинты без изменения ядра.
        """
        mounted = 0
        for p in self.plugins:
            if p.enabled and hasattr(p, "get_router"):
                try:
                    router = p.get_router()
                    if router:
                        app.include_router(router)
                        mounted += 1
                        print(f"[PluginManager] Смонтирован API роутер плагина: {p.name}")
                except Exception as e:
                    print(f"[PluginManager] Ошибка монтирования роутера плагина {p.name}: {e}")
        return mounted

    async def startup(self, context: Dict[str, Any]) -> None:
        """Оповещает все плагины о запуске сервера."""
        for p in self.plugins:
            try:
                await p.on_startup(context)
            except Exception as e:
                print(f"[PluginManager] Ошибка в on_startup плагина {p.name}: {e}")

    async def shutdown(self) -> None:
        """Оповещает все плагины об остановке."""
        for p in self.plugins:
            try:
                await p.on_shutdown()
            except Exception as e:
                print(f"[PluginManager] Ошибка в on_shutdown плагина {p.name}: {e}")

    async def request_track_import(
        self,
        artist: str,
        title: str,
        destination: str = "",
        force_replace: bool = False,
        exclude_sources: Optional[List[str]] = None
    ) -> bool:
        """
        Опрашивает плагины на предмет импорта трека.
        Если хоть один плагин взял задачу в работу — возвращает True.
        Поддерживает исключение определенных источников (exclude_sources)
        и режим принудительной замены файла (force_replace).
        """
        excluded = [s.lower().strip() for s in (exclude_sources or []) if s]
        for p in self.plugins:
            p_name = p.name.lower()
            if any(exc in p_name for exc in excluded):
                print(f"[PluginManager] Пропуск плагина {p.name} (в списке исключений: {excluded})")
                continue

            try:
                try:
                    handled = await p.on_track_import_request(
                        artist,
                        title,
                        destination=destination,
                        force_replace=force_replace,
                        exclude_sources=exclude_sources
                    )
                except TypeError:
                    try:
                        handled = await p.on_track_import_request(artist, title, destination=destination)
                    except TypeError:
                        handled = await p.on_track_import_request(artist, title)

                if handled:
                    return True
            except Exception as e:
                print(f"[PluginManager] Ошибка в on_track_import_request плагина {p.name}: {e}")
        return False

    async def search_all_candidates(self, artist: str, title: str, limit_per_source: int = 5, limit: int = None) -> List[Dict[str, Any]]:
        """
        Параллельно опрашивает все активные плагины через asyncio.gather
        с индивидуальным таймаутом на каждый плагин, чтобы ни один медленный источник не блокировал остальные.
        """
        effective_limit = limit if limit is not None else limit_per_source

        async def _query_plugin(p: BasePlugin) -> List[Dict[str, Any]]:
            try:
                # Ограничиваем время ожидания одного плагина до 7.5 сек (дает внешним источникам и P2P сетям время ответить)
                res = await asyncio.wait_for(p.search_candidates(artist, title, limit=effective_limit), timeout=7.5)
                if res and isinstance(res, list):
                    for r in res:
                        if "plugin_name" not in r:
                            r["plugin_name"] = p.name
                    return res
            except asyncio.TimeoutError:
                print(f"[PluginManager] Таймаут поиска (7.5s) в плагине {p.name}")
            except Exception as e:
                print(f"[PluginManager] Ошибка в search_candidates плагина {p.name}: {e}")
            return []

        tasks = [_query_plugin(p) for p in self.plugins]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        all_candidates = []
        for batch in gathered:
            if isinstance(batch, list):
                all_candidates.extend(batch)

        return all_candidates

    async def download_selected_candidate(
        self,
        candidate: Dict[str, Any],
        destination: str = "",
        force_replace: bool = True
    ) -> bool:
        """
        Делегирует скачивание конкретного кандидата соответствующему плагину.
        """
        target_plugin = candidate.get("plugin_name", "")
        target_source = candidate.get("source", "").lower()

        for p in self.plugins:
            # Находим нужный плагин по имени или source
            if p.name == target_plugin or (target_source and target_source in p.name.lower()):
                try:
                    return await p.download_candidate(
                        candidate,
                        destination=destination,
                        force_replace=force_replace
                    )
                except Exception as e:
                    print(f"[PluginManager] Ошибка в download_candidate плагина {p.name}: {e}")
                    return False

        print(f"[PluginManager] Не найден плагин для источника/плагина: {target_plugin or target_source}")
        return False

    async def get_candidate_preview_url(self, candidate: Dict[str, Any]) -> Optional[str]:
        """
        Запрашивает у соответствующего плагина прямую ссылку на аудиопоток для предпрослушивания.
        """
        target_plugin = candidate.get("plugin_name", "")
        target_source = candidate.get("source", "").lower()

        for p in self.plugins:
            if p.name == target_plugin or (target_source and target_source in p.name.lower()):
                try:
                    if hasattr(p, "get_candidate_preview_url"):
                        return await p.get_candidate_preview_url(candidate)
                except Exception as e:
                    print(f"[PluginManager] Ошибка в get_candidate_preview_url плагина {p.name}: {e}")
                    return None

        return None

    async def notify_reaction(self, track_id: int, is_like: bool, is_dislike: bool) -> None:
        """Оповещает плагины о реакции пользователя."""
        for p in self.plugins:
            try:
                await p.on_user_reaction(track_id, is_like, is_dislike)
            except Exception as e:
                print(f"[PluginManager] Ошибка в on_user_reaction плагина {p.name}: {e}")

    async def get_track_cover(self, track: Any) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Опрашивает плагины для получения обложки трека.
        Первый плагин, вернувший (data, mime), выигрывает.
        """
        for p in self.plugins:
            try:
                if hasattr(p, "get_cover_for_track"):
                    data, mime = await p.get_cover_for_track(track)
                    if data and mime:
                        return data, mime
            except Exception as e:
                print(f"[PluginManager] Ошибка в get_cover_for_track плагина {p.name}: {e}")
        return None, None

    async def get_track_lyrics(self, track: Any) -> Tuple[bool, List[dict], str]:
        """
        Опрашивает плагины для получения текста песни (синхронизированного караоке или обычного).
        Первый плагин, вернувший непустой текст, выигрывает.
        """
        for p in self.plugins:
            try:
                if hasattr(p, "get_lyrics_for_track"):
                    is_synced, lines, raw = await p.get_lyrics_for_track(track)
                    if raw:
                        return is_synced, lines, raw
            except Exception as e:
                print(f"[PluginManager] Ошибка в get_lyrics_for_track плагина {p.name}: {e}")
        return False, [], ""

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """Возвращает экземпляр зарегистрированного плагина по его имени."""
        for p in self.plugins:
            if p.name.lower() == name.lower():
                return p
        return None

    def resolve_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        """
        Восстанавливает информацию о кандидате через плагины, если запись устарела в кэше.
        Устраняет необходимость жесткого кодирования префиксов ID в ядре.
        """
        for p in self.plugins:
            if p.enabled and hasattr(p, "can_handle_candidate"):
                try:
                    if p.can_handle_candidate(candidate_id):
                        cand = p.resolve_candidate(candidate_id)
                        if cand:
                            if "plugin_name" not in cand:
                                cand["plugin_name"] = p.name
                            return cand
                except Exception as e:
                    print(f"[PluginManager] Ошибка в resolve_candidate плагина {p.name}: {e}")
        return None

    def can_preview_candidate(self, candidate: Dict[str, Any]) -> bool:
        """
        Проверяет, поддерживает ли плагин кандидата предпрослушивание аудио.
        """
        target_plugin = candidate.get("plugin_name", "")
        target_source = candidate.get("source", "").lower()

        for p in self.plugins:
            if p.name == target_plugin or (target_source and target_source in p.name.lower()):
                if hasattr(p, "can_preview_candidate"):
                    try:
                        return p.can_preview_candidate(candidate)
                    except Exception as e:
                        print(f"[PluginManager] Ошибка в can_preview_candidate плагина {p.name}: {e}")
        return candidate.get("can_preview", True)

    def get_candidate_preview_headers(self, candidate: Dict[str, Any]) -> Dict[str, str]:
        """
        Запрашивает у плагина заголовки запроса для обхода анти-хотлинка при предпрослушивании.
        """
        target_plugin = candidate.get("plugin_name", "")
        target_source = candidate.get("source", "").lower()

        for p in self.plugins:
            if p.name == target_plugin or (target_source and target_source in p.name.lower()):
                if hasattr(p, "get_preview_headers"):
                    try:
                        return p.get_preview_headers(candidate)
                    except Exception as e:
                        print(f"[PluginManager] Ошибка в get_preview_headers плагина {p.name}: {e}")
        return {}

    async def get_candidate_preview_stream(self, candidate: Dict[str, Any], range_header: Optional[str] = None) -> Optional[Any]:
        """
        Запрашивает у плагина потоковое воспроизведение для предпрослушивания.
        Плагин сам инкапсулирует анти-хотлинк и сетевые заголовки.
        """
        target_plugin = candidate.get("plugin_name", "")
        target_source = candidate.get("source", "").lower()

        for p in self.plugins:
            if p.name == target_plugin or (target_source and target_source in p.name.lower()):
                if hasattr(p, "get_preview_stream"):
                    try:
                        stream = await p.get_preview_stream(candidate, range_header=range_header)
                        if stream is not None:
                            return stream
                    except Exception as e:
                        print(f"[PluginManager] Ошибка в get_preview_stream плагина {p.name}: {e}")
        return None

    async def backfill_covers(self, db: Any, limit: int = 50) -> Dict[str, Any]:
        """
        Делегирует пакетное заполнение обложек плагину обложек без привязки к его конкретному имени.
        """
        for p in self.plugins:
            if p.enabled and hasattr(p, "backfill_covers"):
                try:
                    res = await p.backfill_covers(db, limit=limit)
                    if res and not res.get("supported") is False:
                        return res
                except Exception as e:
                    print(f"[PluginManager] Ошибка в backfill_covers плагина {p.name}: {e}")
        return {"status": "no_provider", "message": "Плагин автоматического заполнения обложек не активен"}

    def clear_cover_cache(self, track_id: int) -> bool:
        """
        Очищает дисковый кэш обложки трека через плагины обложек.
        """
        cleared = False
        for p in self.plugins:
            if p.enabled and hasattr(p, "clear_cover_cache"):
                try:
                    if p.clear_cover_cache(track_id):
                        cleared = True
                except Exception as e:
                    print(f"[PluginManager] Ошибка в clear_cover_cache плагина {p.name}: {e}")
        return cleared


# Глобальный синглтон менеджера плагинов
plugin_manager = PluginManager()
