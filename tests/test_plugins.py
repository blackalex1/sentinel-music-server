import pytest
from plugin_system.base import BasePlugin
from plugin_system.manager import PluginManager


class MockPlugin(BasePlugin):
    name = "mock_test_plugin"
    version = "1.0.0"

    def __init__(self):
        self.started = False
        self.reactions = []
        self.import_requests = []

    async def on_startup(self, context: dict):
        self.started = True

    async def on_shutdown(self):
        self.started = False

    async def on_user_reaction(self, track_id: int, is_like: bool, is_dislike: bool):
        self.reactions.append((track_id, is_like, is_dislike))

    async def on_track_import_request(self, artist: str, title: str) -> bool:
        self.import_requests.append((artist, title))
        return True


@pytest.mark.asyncio
async def test_plugin_lifecycle_and_hooks():
    manager = PluginManager()
    plugin = MockPlugin()
    manager.plugins = [plugin]

    # Startup hook
    await manager.startup({})
    assert plugin.started is True

    # Reaction hook
    await manager.notify_reaction(101, True, False)
    assert len(plugin.reactions) == 1
    assert plugin.reactions[0] == (101, True, False)

    # Ingestion request hook
    handled = await manager.request_track_import("Daft Punk", "Get Lucky")
    assert handled is True
    assert len(plugin.import_requests) == 1
    assert plugin.import_requests[0] == ("Daft Punk", "Get Lucky")

    # Shutdown hook
    await manager.shutdown()
    assert plugin.started is False


def test_system_ingest_request_endpoint(client, auth_headers, monkeypatch):
    from unittest.mock import AsyncMock
    from plugin_system.manager import plugin_manager
    mock_import = AsyncMock(return_value=True)
    monkeypatch.setattr(plugin_manager, "request_track_import", mock_import)

    res = client.post(
        "/api/ingest/request?artist=Nirvana&title=Smells+Like+Teen+Spirit",
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["artist"] == "Nirvana"
    assert data["title"] == "Smells Like Teen Spirit"
    assert data["handled"] is True
    mock_import.assert_awaited_once_with("Nirvana", "Smells Like Teen Spirit")


def test_list_plugins_endpoint(client, auth_headers):
    res = client.get("/api/plugins", headers=auth_headers)
    assert res.status_code == 200
    plugins = res.json()
    assert isinstance(plugins, list)
    if len(plugins) > 0:
        # Проверяем контракт полей плагина
        assert "name" in plugins[0]
        assert "version" in plugins[0]
        assert "enabled" in plugins[0]
        assert "has_ui" in plugins[0]

        # Проверяем контракт полей у плагинов с UI (при их наличии)
        ui_plugins = [p for p in plugins if p.get("has_ui")]
        for p in ui_plugins:
            assert "ui_entry" in p
            assert p["ui_entry"].startswith("/plugins/")


def test_plugin_ui_assets_mounting(client, tmp_path):
    """Проверяет корректность раздачи изолированных статических ассетов плагина через HTTP."""
    from fastapi.staticfiles import StaticFiles
    from starlette.routing import Mount
    from main import app

    plugin_dir = tmp_path / "mock_plugin"
    ui_dir = plugin_dir / "ui"
    ui_dir.mkdir(parents=True)
    (ui_dir / "index.js").write_text("export function init() {}", encoding="utf-8")
    (ui_dir / "styles.css").write_text(".mock-tab {}", encoding="utf-8")
    (plugin_dir / "plugin.py").write_text("# private code", encoding="utf-8")

    # Монтируем изолированную папку UI аналогично PluginManager
    mount = Mount("/plugins/test_mock_ui", StaticFiles(directory=str(ui_dir)), name="plugin_ui_test_mock")
    app.router.routes.insert(0, mount)

    try:
        res_js = client.get("/plugins/test_mock_ui/index.js")
        assert res_js.status_code == 200
        assert "init" in res_js.text

        res_css = client.get("/plugins/test_mock_ui/styles.css")
        assert res_css.status_code == 200

        # Проверяем, что исходный код Python (.py) изолирован и недоступен
        res_py = client.get("/plugins/test_mock_ui/plugin.py")
        assert res_py.status_code == 404
    finally:
        if mount in app.router.routes:
            app.router.routes.remove(mount)


@pytest.mark.asyncio
async def test_candidate_preview_url_delegation():
    class PreviewPlugin(BasePlugin):
        name = "test_preview_plugin"

        async def get_candidate_preview_url(self, candidate: dict):
            return "https://mock-stream.example.com/audio.mp3"

    manager = PluginManager()
    manager.plugins = [PreviewPlugin()]

    cand = {"source": "test_preview", "plugin_name": "test_preview_plugin", "candidate_id": "test_1"}
    url = await manager.get_candidate_preview_url(cand)
    assert url == "https://mock-stream.example.com/audio.mp3"


def test_candidate_preview_endpoint_rejects_unsupported(client, auth_headers):
    from api.candidates import _register_candidates
    _register_candidates([{
        "candidate_id": "unsupported_song.mp3",
        "source": "mock_no_preview",
        "can_preview": False,
        "title": "Test No Preview",
        "artist": "Test Artist"
    }])

    res = client.get("/api/tracks/candidates/preview?candidate_id=unsupported_song.mp3", headers=auth_headers)
    assert res.status_code == 400
    assert "не поддерживается" in res.json()["detail"]


def test_candidate_preview_endpoint_streaming(client, auth_headers, monkeypatch):
    from unittest.mock import MagicMock
    from api.candidates import _register_candidates

    _register_candidates([{
        "candidate_id": "mock_preview_99999",
        "source": "mock_provider",
        "plugin_name": "MockProviderPlugin",
        "title": "Mock Track",
        "artist": "Mock Artist",
        "dl_url": "https://example.com/download/99999"
    }])

    # Mock requests.get to return a dummy streaming response
    mock_resp = MagicMock()
    mock_resp.status_code = 206
    mock_resp.headers = {
        "Content-Type": "audio/mpeg",
        "Content-Range": "bytes 0-1023/1024",
        "Content-Length": "1024"
    }
    mock_resp.iter_content.return_value = [b"MPEG_AUDIO_CHUNK_DATA"]

    import requests
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: mock_resp)

    res = client.get(
        "/api/tracks/candidates/preview?candidate_id=mock_preview_99999",
        headers={**auth_headers, "Range": "bytes=0-1023"}
    )
    assert res.status_code == 206
    assert res.headers["Content-Type"] == "audio/mpeg"
    assert res.content == b"MPEG_AUDIO_CHUNK_DATA"


@pytest.mark.asyncio
async def test_zero_plugins_graceful_handling():
    """Проверяет стабильность системы, если в plugins/ нет ни одного плагина."""
    from plugin_system.manager import PluginManager
    empty_manager = PluginManager(plugins_dir="non_existent_empty_dir")
    assert empty_manager.load_plugins() == 0

    # Startup & shutdown работают без ошибок
    await empty_manager.startup({})
    await empty_manager.shutdown()

    # Поиск кандидатов возвращает пустой список без исключений
    candidates = await empty_manager.search_all_candidates("Artist", "Title")
    assert candidates == []

    # Запрос импорта возвращает False без исключений
    handled = await empty_manager.request_track_import("Artist", "Title")
    assert handled is False

    # Скачивание неизвестного кандидата возвращает False
    downloaded = await empty_manager.download_selected_candidate({"plugin_name": "unknown"})
    assert downloaded is False


def test_search_candidates_short_query_protection(client, auth_headers):
    """Проверяет, что при слишком коротком поисковом запросе внешние сервисы не опрашиваются."""
    res = client.get("/api/tracks/candidates/search?q=a", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["candidates"] == []
    assert "короткий" in data.get("message", "")



