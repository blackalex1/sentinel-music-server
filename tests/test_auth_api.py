import pytest


def test_auth_status_flow(client):
    # При пустой БД статус initialized: False
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert res.json() == {"initialized": False}

    # Регистрируем первого пользователя
    reg_res = client.post("/api/auth/register", json={
        "username": "admin_user",
        "password": "strong_password_123"
    })
    assert reg_res.status_code == 200
    data = reg_res.json()
    assert data["status"] == "ok"
    assert data["username"] == "admin_user"
    assert data["is_admin"] is True
    assert "token" in data

    # Теперь статус initialized: True
    res2 = client.get("/api/auth/status")
    assert res2.status_code == 200
    assert res2.json() == {"initialized": True}


def test_register_validation_and_duplicate(client):
    # Слишком короткий логин/пароль
    res = client.post("/api/auth/register", json={"username": "ab", "password": "12"})
    assert res.status_code == 400

    # Успешная регистрация
    res1 = client.post("/api/auth/register", json={"username": "alice", "password": "password123"})
    assert res1.status_code == 200

    # Попытка дублирования логина
    res2 = client.post("/api/auth/register", json={"username": "alice", "password": "another_password"})
    assert res2.status_code == 400
    assert "уже существует" in res2.json()["detail"]


def test_login_success_and_failure(client):
    # Регистрация
    client.post("/api/auth/register", json={"username": "bob_marley", "password": "reggae_password"})

    # Успешный логин
    res = client.post("/api/auth/login", json={
        "username": "bob_marley",
        "password": "reggae_password",
        "device_name": "Test Runner"
    })
    assert res.status_code == 200
    token = res.json()["token"]
    assert token is not None

    # Неверный пароль
    bad_res = client.post("/api/auth/login", json={
        "username": "bob_marley",
        "password": "wrong_password"
    })
    assert bad_res.status_code == 401

    # Несуществующий пользователь
    missing_res = client.post("/api/auth/login", json={
        "username": "non_existent",
        "password": "any_password"
    })
    assert missing_res.status_code == 401


def test_me_and_logout_flow(client):
    # Регистрируем пользователя
    reg = client.post("/api/auth/register", json={"username": "carol", "password": "carol_pass"})
    token = reg.json()["token"]

    # Доступ без токена -> 401
    assert client.get("/api/auth/me").status_code == 401

    # Доступ через заголовок Bearer -> 200
    res_header = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_header.status_code == 200
    assert res_header.json()["username"] == "carol"

    # Доступ через query параметр ?token= -> 200 (для стриминга)
    res_query = client.get(f"/api/auth/me?token={token}")
    assert res_query.status_code == 200
    assert res_query.json()["username"] == "carol"

    # Выход из системы
    logout_res = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_res.status_code == 200

    # После выхода токен больше не действует -> 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_qr_hosts_and_code(client):
    # Hosts доступен даже без авторизации
    res_hosts = client.get("/api/auth/qr/hosts")
    assert res_hosts.status_code == 200
    hosts_data = res_hosts.json()
    assert "lan_url" in hosts_data
    assert "emulator_url" not in hosts_data
    assert "localhost_url" not in hosts_data

    # Генерация QR без токена -> 401
    assert client.get("/api/auth/qr/code").status_code == 401

    # Регистрируем пользователя
    reg = client.post("/api/auth/register", json={"username": "qr_tester", "password": "secure_qr_pass"})
    token = reg.json()["token"]

    # Генерация QR с авторизацией
    res_qr = client.get("/api/auth/qr/code", headers={"Authorization": f"Bearer {token}"})
    assert res_qr.status_code == 200
    qr_data = res_qr.json()
    assert qr_data["status"] == "ok"
    assert qr_data["username"] == "qr_tester"
    assert "payload" in qr_data
    assert "payload_json" in qr_data
    assert qr_data["payload"]["url"].startswith("http")
    assert qr_data["qr_image"].startswith("data:image/png;base64,")

    # Генерация с кастомным host (например для эмулятора)
    res_custom = client.get(
        "/api/auth/qr/code?host=http://10.0.2.2:8000",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_custom.status_code == 200
    assert res_custom.json()["server_url"] == "http://10.0.2.2:8000"
    assert res_custom.json()["payload"]["url"] == "http://10.0.2.2:8000"


def test_qr_image_endpoint(client):
    # Прямой запрос изображения с данными data=...
    res_raw = client.get("/api/auth/qr/image?data=hello_sentinel")
    assert res_raw.status_code == 200
    assert res_raw.headers["content-type"] == "image/png"
    assert res_raw.content.startswith(b"\x89PNG")

    # Без параметров -> 400
    assert client.get("/api/auth/qr/image").status_code == 400

    # С токеном
    reg = client.post("/api/auth/register", json={"username": "img_tester", "password": "secure_pass_img"})
    token = reg.json()["token"]

    res_token_img = client.get(f"/api/auth/qr/image?token={token}")
    assert res_token_img.status_code == 200
    assert res_token_img.headers["content-type"] == "image/png"
    assert res_token_img.content.startswith(b"\x89PNG")

    # С токеном через Authorization header
    res_header_img = client.get("/api/auth/qr/image", headers={"Authorization": f"Bearer {token}"})
    assert res_header_img.status_code == 200
    assert res_header_img.content.startswith(b"\x89PNG")

    # С недействительным токеном -> 401
    res_bad_img = client.get("/api/auth/qr/image?token=invalid_token_xyz")
    assert res_bad_img.status_code == 401


def test_auth_ip_utilities():
    """Тестирует функции распознавания IP-адресов и LAN-окружения."""
    from api.auth import is_docker_or_loopback_ip

    assert is_docker_or_loopback_ip(None) is True
    assert is_docker_or_loopback_ip("") is True
    assert is_docker_or_loopback_ip("127.0.0.1") is True
    assert is_docker_or_loopback_ip("localhost") is True
    assert is_docker_or_loopback_ip("172.17.0.2") is True
    assert is_docker_or_loopback_ip("172.31.255.1") is True
    assert is_docker_or_loopback_ip("192.168.1.100") is False
    assert is_docker_or_loopback_ip("10.0.0.5") is False
    assert is_docker_or_loopback_ip("not_an_ip") is False


def test_logout_with_query_token_and_qr_existing_session(client):
    """Тестирует логаут через query-параметр и генерацию QR с существующей сессией."""
    reg = client.post("/api/auth/register", json={"username": "sess_user", "password": "sess_password123"})
    token = reg.json()["token"]

    # QR с reuse existing session (create_new_session=False)
    res_qr = client.get(
        "/api/auth/qr/code?create_new_session=false",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_qr.status_code == 200
    assert res_qr.json()["token"] == token

    # Выход через query token ?token=
    res_out = client.post(f"/api/auth/logout?token={token}")
    assert res_out.status_code == 200

    # Проверяем недействительность токена
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401

