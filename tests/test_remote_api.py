import pytest
from api.remote import remote_manager, ConnectedDevice


def test_remote_manager_devices_tracking():
    """Тестирует внутреннюю логику менеджера устройств Sentinel Connect."""
    user_id = 9999
    dev1 = ConnectedDevice(
        websocket=None,
        device_id="dev_pc_1",
        name="Windows PC",
        device_type="player",
        user_id=user_id
    )
    remote_manager._connections[user_id]["dev_pc_1"] = dev1

    devices = remote_manager.get_user_devices(user_id)
    assert len(devices) == 1
    assert devices[0]["id"] == "dev_pc_1"
    assert devices[0]["name"] == "Windows PC"
    assert devices[0]["can_play"] is True
    assert devices[0]["is_playing"] is False

    # Обновление состояния
    dev1.state["is_playing"] = True
    dev1.state["position_ms"] = 15000
    devices2 = remote_manager.get_user_devices(user_id)
    assert devices2[0]["is_playing"] is True
    assert devices2[0]["position_ms"] == 15000

    # Очистка
    if user_id in remote_manager._connections:
        del remote_manager._connections[user_id]


def test_remote_status_endpoint(client, auth_headers):
    """Проверка REST-эндпоинта статуса подключений /api/remote/status."""
    res = client.get("/api/remote/status", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "has_pc" in data
    assert "is_pc_online" in data
    assert "online_devices" in data
    assert "last_playback_session" in data


def test_remote_devices_endpoint(client, auth_headers):
    """Проверка REST-эндпоинта списка устройств /api/remote/devices."""
    res = client.get("/api/remote/devices", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "devices" in data
    assert isinstance(data["devices"], list)


def test_remote_command_routing_and_cross_user_defense(client, db_session):
    """Проверка безопасности отправки команд: запрет отправки команд устройствам других пользователей."""
    from database.models import User, SessionToken
    from core.security import hash_password, generate_session_token

    salt1, h1 = hash_password("Pass1")
    u1 = User(username="remote_u1", password_hash=h1, salt=salt1, is_admin=False)
    salt2, h2 = hash_password("Pass2")
    u2 = User(username="remote_u2", password_hash=h2, salt=salt2, is_admin=False)
    db_session.add_all([u1, u2])
    db_session.commit()

    t1 = generate_session_token()
    t2 = generate_session_token()
    db_session.add_all([
        SessionToken(token=t1, user_id=u1.id, device_name="D1"),
        SessionToken(token=t2, user_id=u2.id, device_name="D2")
    ])
    db_session.commit()

    # Регистрируем устройство для u2
    dev2 = ConnectedDevice(
        websocket=None,
        device_id="dev_victim_pc",
        name="User 2 PC",
        device_type="player",
        user_id=u2.id
    )
    remote_manager._connections[u2.id]["dev_victim_pc"] = dev2

    # Попытка пользователя u1 отправить команду устройству пользователя u2
    res = client.post(
        "/api/remote/command",
        json={"target_device_id": "dev_victim_pc", "command": "PAUSE"},
        headers={"Authorization": f"Bearer {t1}"}
    )
    # Должен вернуть 404 (Устройство не найдено в сети текущего пользователя)
    assert res.status_code == 404

    # Очистка
    if u2.id in remote_manager._connections:
        del remote_manager._connections[u2.id]


def test_remote_playback_session_handoff(client, db_session):
    """Проверка сохранения и отдачи последней сессии воспроизведения (Handoff с телефона/ПК)."""
    from database.models import User, SessionToken
    from core.security import hash_password, generate_session_token

    salt, h = hash_password("PassHandoff")
    u = User(username="handoff_user", password_hash=h, salt=salt, is_admin=False)
    db_session.add(u)
    db_session.commit()

    tok = generate_session_token()
    db_session.add(SessionToken(token=tok, user_id=u.id, device_name="Phone"))
    db_session.commit()

    # Имитируем сохранение сессии сервером
    remote_manager._last_playback_session[u.id] = {
        "current_track": {"id": 101, "title": "Handoff Track", "artist": "Handoff Artist"},
        "position_ms": 42000,
        "duration_ms": 180000,
        "queue": [],
        "device_name": "Смартфон",
        "saved_at": 1729000000.0
    }

    res = client.get("/api/remote/status", headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 200
    session = res.json().get("last_playback_session")
    assert session is not None
    assert session["current_track"]["id"] == 101
    assert session["position_ms"] == 42000
    assert session["device_name"] == "Смартфон"

    # Очистка
    if u.id in remote_manager._last_playback_session:
        del remote_manager._last_playback_session[u.id]


def test_remote_websocket_lifecycle(client, auth_user_and_token):
    """Тестирует полный жизненный цикл WebSocket-соединения Sentinel Connect."""
    user, token = auth_user_and_token
    device_id = "test_pc_ws_1"

    with client.websocket_connect(
        f"/api/remote/ws?token={token}&device_id={device_id}&device_name=MyDesktop&device_type=player"
    ) as ws:
        # 1. Приветственное сообщение
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome"
        assert welcome["device_id"] == device_id
        assert any(d["id"] == device_id for d in welcome["devices"])

        # 2. Пинг / Понг
        ws.send_json({"action": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"
        assert "time" in pong

        # 3. Запрос актуального списка устройств
        ws.send_json({"action": "request_devices"})
        devs_msg = ws.receive_json()
        assert devs_msg["type"] == "devices_update"
        assert len(devs_msg["devices"]) >= 1

        # 4. Обновление состояния воспроизведения
        ws.send_json({
            "action": "state_update",
            "state": {
                "is_playing": True,
                "position_ms": 12345,
                "duration_ms": 200000,
                "current_track": {"id": 10, "title": "Online Track", "artist": "Online Artist"}
            }
        })

        # Проверяем, что менеджер обновил внутреннее состояние
        devs = remote_manager.get_user_devices(user.id)
        current_dev = next(d for d in devs if d["id"] == device_id)
        assert current_dev["is_playing"] is True
        assert current_dev["position_ms"] == 12345

        # Проверяем, что сессия Handoff зафиксировалась
        session = remote_manager.get_last_playback_session(user.id)
        assert session is not None
        assert session["current_track"]["id"] == 10

    # 5. После закрытия сокета устройство должно удалиться из активных
    devs_after = remote_manager.get_user_devices(user.id)
    assert not any(d["id"] == device_id for d in devs_after)


def test_remote_websocket_command_routing_between_clients(client, auth_user_and_token):
    """Тестирует доставку команд между двумя клиентами одного аккаунта через WebSocket."""
    user, token = auth_user_and_token
    dev_pc_id = "ws_player_pc"
    dev_phone_id = "ws_remote_phone"

    with client.websocket_connect(
        f"/api/remote/ws?token={token}&device_id={dev_pc_id}&device_name=LivingRoomPC&device_type=player"
    ) as ws_pc:
        # PC получает welcome
        ws_pc.receive_json()

        with client.websocket_connect(
            f"/api/remote/ws?token={token}&device_id={dev_phone_id}&device_name=MyPhone&device_type=remote"
        ) as ws_phone:
            # Phone получает welcome
            ws_phone.receive_json()
            # PC получает devices_update о подключении телефона
            update_on_pc = ws_pc.receive_json()
            assert update_on_pc["type"] == "devices_update"

            # Телефон шлет команду на ПК
            ws_phone.send_json({
                "action": "command",
                "target_device_id": dev_pc_id,
                "command": "PLAY_TRACK",
                "payload": {"track_id": 777}
            })

            # ПК должен получить команду
            cmd_received = ws_pc.receive_json()
            assert cmd_received["type"] == "command"
            assert cmd_received["from_device_id"] == dev_phone_id
            assert cmd_received["command"] == "PLAY_TRACK"
            assert cmd_received["payload"]["track_id"] == 777


def test_remote_websocket_auth_rejection(client):
    """Проверяет отклонение подключения с недействительным токеном с кодом 1008."""
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect(
        "/api/remote/ws?token=non_existent_fake_token&device_id=fake_dev"
    ) as ws:
        err = ws.receive_json()
        assert err["type"] == "error"
        assert "токен" in err["message"].lower()
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1008

