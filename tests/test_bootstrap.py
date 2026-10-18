import os
from core.bootstrap import generate_secure_credentials, bootstrap_admin_user
from core.security import verify_password
from database.models import User


def test_generate_secure_credentials():
    """Проверяет генерацию случайных уникальных логинов и стойких паролей."""
    u1, p1 = generate_secure_credentials()
    u2, p2 = generate_secure_credentials()

    assert u1.startswith("admin_")
    assert u2.startswith("admin_")
    assert u1 != u2
    assert p1 != p2
    assert len(p1) >= 12
    assert len(p2) >= 12


def test_bootstrap_admin_user_on_empty_db(db_session, tmp_path, client):
    """
    Проверяет успешное создание первого администратора при пустой БД,
    сохранение файла учетных данных и возможность реального входа через API.
    """
    cred_file = str(tmp_path / "credentials.txt")

    # 1. Первый старт на чистой БД
    res = bootstrap_admin_user(db_session, credentials_path=cred_file)
    assert res is not None
    username = res["username"]
    password = res["password"]

    # 2. Проверяем запись в БД
    admin_in_db = db_session.query(User).filter(User.username == username).first()
    assert admin_in_db is not None
    assert admin_in_db.is_admin is True
    assert verify_password(password, admin_in_db.salt, admin_in_db.password_hash) is True

    # 3. Проверяем созданный защищенный файл
    assert os.path.exists(cred_file)
    with open(cred_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert f"LOGIN={username}" in content
    assert f"PASSWORD={password}" in content

    # 4. Проверяем вход через HTTP API с сгенерированными данными
    login_res = client.post("/api/auth/login", json={
        "username": username,
        "password": password
    })
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "token" in login_data
    assert login_data["username"] == username
    assert login_data["is_admin"] is True


def test_bootstrap_idempotent_on_existing_users(db_session, tmp_path):
    """Проверяет, что bootstrap ничего не перезаписывает, если пользователь уже есть."""
    cred_file = str(tmp_path / "credentials.txt")

    # Создаем первого администратора
    first_res = bootstrap_admin_user(db_session, credentials_path=cred_file)
    assert first_res is not None

    # Повторный запуск (например, при перезагрузке сервера)
    second_res = bootstrap_admin_user(db_session, credentials_path=cred_file)
    assert second_res is None

    # Количество пользователей не изменилось
    assert db_session.query(User).count() == 1
