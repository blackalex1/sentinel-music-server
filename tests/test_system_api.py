import pytest
from unittest.mock import AsyncMock, MagicMock


def test_system_plugins_list(client, auth_headers):
    """Проверяет получение списка активных плагинов."""
    res = client.get("/api/plugins", headers=auth_headers)
    assert res.status_code == 200
    plugins = res.json()
    assert isinstance(plugins, list)
    for p in plugins:
        assert "name" in p
        assert "enabled" in p
        assert "priority" in p


def test_system_ingest_request(client, auth_headers, monkeypatch):
    """Проверяет запрос фонового импорта аудиозаписи через систему плагинов."""
    from plugin_system.manager import plugin_manager

    mock_import = AsyncMock(return_value=True)
    monkeypatch.setattr(plugin_manager, "request_track_import", mock_import)

    res = client.post(
        "/api/ingest/request?artist=Queen&title=Radio Ga Ga",
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["artist"] == "Queen"
    assert data["title"] == "Radio Ga Ga"
    assert data["handled"] is True


def test_system_scan(client, auth_headers, tmp_path, monkeypatch):
    """Проверяет ручной запуск индексации директории через /api/scan."""
    import api.system as system_module
    import streaming.scanner as scanner_module

    monkeypatch.setattr(scanner_module, "cleanup_missing_tracks", lambda p, db: 2)
    monkeypatch.setattr(scanner_module, "scan_directory", lambda p, db: 5)
    monkeypatch.setattr(system_module, "scan_directory", lambda p, db: 5)

    res = client.post(f"/api/scan?music_path={tmp_path}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["added_tracks"] == 5
    assert data["deleted_missing_tracks"] == 2


def test_system_watcher_controls(client, auth_headers, monkeypatch):
    """Проверяет получение статуса, запуск и остановку Watchdog сервиса."""
    from streaming.watcher import music_watcher

    # 1. Статус watcher
    res_status = client.get("/api/watcher", headers=auth_headers)
    assert res_status.status_code == 200
    st_data = res_status.json()
    assert "running" in st_data or "is_running" in st_data or "total_tracks" in st_data

    # 2. Запуск watcher (с моком)
    monkeypatch.setattr(music_watcher, "start", lambda *args, **kwargs: True)
    res_start = client.post("/api/watcher/start?music_path=/music", headers=auth_headers)
    assert res_start.status_code == 200
    assert res_start.json()["status"] == "started"

    # 3. Остановка watcher
    monkeypatch.setattr(music_watcher, "stop", lambda: None)
    res_stop = client.post("/api/watcher/stop", headers=auth_headers)
    assert res_stop.status_code == 200
    assert res_stop.json()["status"] == "stopped"
