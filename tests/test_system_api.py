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


def test_ssl_status(client, auth_headers):
    """Проверяет получение статуса SSL-сертификата администратором."""
    res = client.get("/api/ssl/status", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "installed" in data
    assert "cert_path" in data
    assert "key_path" in data

    # Проверка алиаса /api/system/ssl/status
    res_alias = client.get("/api/system/ssl/status", headers=auth_headers)
    assert res_alias.status_code == 200
    assert res_alias.json()["installed"] == data["installed"]


def test_ssl_generate_self_signed(client, auth_headers, tmp_path, monkeypatch):
    """Проверяет генерацию самоподписанного сертификата для домена и IP."""
    import core.ssl.utils as ssl_utils
    monkeypatch.setattr(ssl_utils, "SSL_CERT_PATH", tmp_path / "cert.pem")
    monkeypatch.setattr(ssl_utils, "SSL_KEY_PATH", tmp_path / "key.pem")

    res = client.post(
        "/api/system/ssl/generate",
        json={"is_self_signed": True, "domain": "192.168.1.100"},
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert (tmp_path / "cert.pem").exists()
    assert (tmp_path / "key.pem").exists()


def test_system_version_endpoint(client):
    """Проверяет получение версии и метаданных системы без обязательной авторизации."""
    res = client.get("/api/system/version")
    assert res.status_code == 200
    data = res.json()
    assert "version" in data
    assert "is_git" in data
    assert "can_auto_update" in data


def test_system_update_success(client, auth_headers, monkeypatch):
    """Проверяет успешный вызов 1-Click Update администратором."""
    import core.updater as updater_module

    restart_called = []
    monkeypatch.setattr(updater_module, "perform_server_update", lambda branch="main": (True, "Обновление успешно загружено. Коммит: abc1234"))
    monkeypatch.setattr(updater_module, "schedule_server_restart", lambda delay_seconds=1.5: restart_called.append(delay_seconds))

    res = client.post("/api/system/update", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["restarting"] is True
    assert "Обновление успешно загружено" in data["message"]
    assert len(restart_called) == 1
    assert restart_called[0] == 1.5


def test_system_update_failure(client, auth_headers, monkeypatch):
    """Проверяет корректную обработку ошибки при сбое обновления git."""
    import core.updater as updater_module

    monkeypatch.setattr(updater_module, "perform_server_update", lambda branch="main": (False, "Сетевая ошибка: GitHub недоступен"))

    res = client.post("/api/system/update", headers=auth_headers)
    assert res.status_code == 500
    assert "GitHub недоступен" in res.json()["detail"]


def test_system_update_permissions(client, db_session):
    """Проверяет, что не-администратор не имеет права запускать обновление системы (403/401)."""
    # 1. Анонимный запрос
    res_anon = client.post("/api/system/update")
    assert res_anon.status_code in (401, 403)

    # 2. Обычный пользователь (не админ)
    from database.models import User, SessionToken
    from core.security import hash_password, generate_session_token

    salt, p_hash = hash_password("secret123")
    regular_user = User(username="regular_user", password_hash=p_hash, salt=salt, is_admin=False)
    db_session.add(regular_user)
    db_session.commit()
    db_session.refresh(regular_user)

    token = generate_session_token()
    db_session.add(SessionToken(token=token, user_id=regular_user.id, device_name="Device"))
    db_session.commit()

    res_user = client.post("/api/system/update", headers={"Authorization": f"Bearer {token}"})
    assert res_user.status_code == 403





