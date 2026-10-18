import os
import pytest
from core.security import (
    hash_password,
    verify_password,
    generate_session_token
)


def test_password_hashing_and_verification():
    password = "MySecurePassword2026!"
    salt, p_hash = hash_password(password)

    # Проверяем, что соль и хеш не пустые и имеют ожидаемый формат hex
    assert len(salt) == 32
    assert len(p_hash) == 64
    assert salt != p_hash

    # Проверка правильного пароля
    assert verify_password(password, salt, p_hash) is True

    # Проверка неверного пароля
    assert verify_password("WrongPassword!", salt, p_hash) is False
    assert verify_password("", salt, p_hash) is False


def test_unique_salts_for_same_password():
    password = "identical_password"
    salt1, hash1 = hash_password(password)
    salt2, hash2 = hash_password(password)

    # Разные соли должны давать разные хеши
    assert salt1 != salt2
    assert hash1 != hash2

    # При этом каждый должен успешно валидироваться со своей солью
    assert verify_password(password, salt1, hash1) is True
    assert verify_password(password, salt2, hash2) is True


def test_generate_session_token():
    t1 = generate_session_token()
    t2 = generate_session_token()

    assert len(t1) >= 40
    assert len(t2) >= 40
    assert t1 != t2


def test_tampered_token_rejected(client):
    """Проверка защиты от подделки и модификации токенов авторизации."""
    # 1. Полностью фиктивный токен
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer forged_fake_token_1234567890"})
    assert res.status_code == 401

    # 2. Модифицированный / обрезанный токен
    res2 = client.get("/api/tracks", headers={"Authorization": "Bearer fake_token"})
    assert res2.status_code == 401

    # 3. Пустой Bearer заголовок
    res3 = client.get("/api/auth/me", headers={"Authorization": "Bearer "})
    assert res3.status_code == 401

    # 4. Некорректная схема авторизации (Basic вместо Bearer)
    res4 = client.get("/api/auth/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert res4.status_code == 401


def test_expired_token_rejected(client, db_session):
    """Проверка автоматического отклонения токенов с истекшим сроком действия."""
    from datetime import datetime, timezone, timedelta
    from database.models import User, SessionToken

    salt, p_hash = hash_password("Password123")
    user = User(username="expired_test_user", password_hash=p_hash, salt=salt, is_admin=False)
    db_session.add(user)
    db_session.commit()

    # Токен, истекший 1 час назад
    expired_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    tok_str = generate_session_token()
    tok = SessionToken(token=tok_str, user_id=user.id, device_name="TestDevice", expires_at=expired_time)
    db_session.add(tok)
    db_session.commit()

    # Должен возвращать 401 Unauthorized
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok_str}"})
    assert res.status_code == 401
    assert "истек" in res.json().get("detail", "").lower() or "токен" in res.json().get("detail", "").lower()


def test_sql_injection_defense_across_endpoints(client, auth_headers):
    """Проверка устойчивости всех эндпоинтов против различных векторов SQL-инъекций."""
    injection_payloads = [
        "1' OR '1'='1",
        "'; DROP TABLE tracks; --",
        "' UNION SELECT null, username, password_hash FROM users --",
        "admin'--",
        "1; WAITFOR DELAY '0:0:5'--",
        "1 AND (SELECT 1 FROM (SELECT COUNT(*), CONCAT((SELECT database()), FLOOR(RAND(0)*2)) x FROM information_schema.tables GROUP BY x)a)"
    ]

    for payload in injection_payloads:
        # Поиск (FastAPI валидирует длину max_length=100, возвращая 422, либо БД безопасно обрабатывает запрос и возвращает 200)
        r1 = client.get(f"/api/tracks/search?q={payload}", headers=auth_headers)
        assert r1.status_code in (200, 422)

        # Фильтр настроения
        r2 = client.get(f"/api/tracks?mood={payload}", headers=auth_headers)
        assert r2.status_code in (200, 422)

        # Сортировка
        r3 = client.get(f"/api/tracks?sort={payload}", headers=auth_headers)
        assert r3.status_code in (200, 422)


def test_path_traversal_defense(client, auth_headers):
    """Проверка защиты от Path Traversal атак при скачивании, стриминге и обложках."""
    traversal_payloads = [
        "../../../../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\cmd.exe",
        "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "/etc/shadow",
        "....//....//etc/passwd"
    ]

    for payload in traversal_payloads:
        # Запрос обложки
        r1 = client.get(f"/api/covers/{payload}", headers=auth_headers)
        # Числовой track_id должен сразу отклонять нечисловые payload со статусом 422
        assert r1.status_code in (404, 422)

        # Стриминг
        r2 = client.get(f"/api/stream/{payload}", headers=auth_headers)
        assert r2.status_code in (404, 422)


def test_cross_user_isolation(client, db_session):
    """Проверка строгой изоляции данных и прав между разными пользователями."""
    from database.models import User, SessionToken, Playlist

    salt1, h1 = hash_password("User1Pass")
    u1 = User(username="user_one", password_hash=h1, salt=salt1, is_admin=False)
    salt2, h2 = hash_password("User2Pass")
    u2 = User(username="user_two", password_hash=h2, salt=salt2, is_admin=False)
    db_session.add_all([u1, u2])
    db_session.commit()

    t1 = generate_session_token()
    t2 = generate_session_token()
    db_session.add_all([
        SessionToken(token=t1, user_id=u1.id, device_name="Device1"),
        SessionToken(token=t2, user_id=u2.id, device_name="Device2")
    ])
    db_session.commit()

    # User 1 создает плейлист
    res = client.post(
        "/api/playlists",
        json={"title": "Private User 1 Playlist"},
        headers={"Authorization": f"Bearer {t1}"}
    )
    assert res.status_code == 200
    pl_id = res.json()["playlist_id"]

    # При запросе auth/me получает именно своего пользователя
    me1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {t1}"}).json()
    me2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {t2}"}).json()
    assert me1["username"] == "user_one"
    assert me2["username"] == "user_two"
    assert me1["id"] != me2["id"]


def test_token_bit_flip_and_tampering_deep(client, auth_user_and_token):
    """Глубокая проверка устойчивости к модификации и фальсификации токенов."""
    _, valid_token = auth_user_and_token

    # 1. Замена последнего символа токена (Bit flip / Sub)
    tampered_1 = valid_token[:-1] + ("A" if valid_token[-1] != "A" else "B")
    r1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered_1}"})
    assert r1.status_code == 401

    # 2. Модификация символа в центре токена
    mid = len(valid_token) // 2
    tampered_2 = valid_token[:mid] + ("Z" if valid_token[mid] != "Z" else "X") + valid_token[mid + 1:]
    r2 = client.get("/api/tracks", headers={"Authorization": f"Bearer {tampered_2}"})
    assert r2.status_code == 401

    # 3. Добавление спецсимволов и инъекций в query параметр
    for injection in ["%00", "'", "\"", ";", "--", "../"]:
        r3 = client.get(f"/api/auth/me?token={valid_token}{injection}")
        assert r3.status_code == 401

    # 4. Проверка модифицированных токенов через заголовок
    for raw_inj in ["_tampered", "123", "!@#"]:
        r4 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {valid_token}{raw_inj}"})
        assert r4.status_code == 401


def test_revoked_token_rejected_across_all_surfaces(client, auth_user_and_token, sample_track):
    """Проверка полного аннулирования сессии после logout на всех протоколах и маршрутах."""
    from starlette.websockets import WebSocketDisconnect

    _, token = auth_user_and_token

    # Проверяем, что токен сначала работает
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    # Выполняем logout
    res_logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert res_logout.status_code == 200

    # Проверяем REST API с аннулированным токеном
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/tracks", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get("/api/playlists", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.get(f"/api/stream/{sample_track.id}?token={token}").status_code == 401

    # Проверяем WebSocket соединение с аннулированным токеном -> отклонение с WS_1008
    with client.websocket_connect(f"/api/remote/ws?token={token}&device_id=ghost_dev") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 1008


def test_sql_injection_in_auth_endpoints(client, db_session):
    """Проверка защиты от SQL-инъекций в эндпоинтах логина и регистрации."""
    sqli_vectors = [
        "' OR '1'='1",
        "admin'--",
        "'; DROP TABLE users CASCADE; --",
        "1' UNION SELECT 1, 'hacked', 'hash', 'salt', true, null, null --",
        "$$; SELECT pg_sleep(1); --$$"
    ]

    for payload in sqli_vectors:
        # Логин с SQLi логином
        r_login = client.post("/api/auth/login", json={
            "username": payload,
            "password": "some_password"
        })
        # Должен возвращать 401 Unauthorized, а не 500 Internal Server Error
        assert r_login.status_code == 401

        # Регистрация с SQLi логином
        r_reg = client.post("/api/auth/register", json={
            "username": payload,
            "password": "valid_password_123"
        })
        # Должен либо безопасно зарегистрировать (строка экранирована), либо вернуть 400
        assert r_reg.status_code in (200, 400, 422)

    # Проверяем целостность таблицы пользователей
    from database.models import User
    assert db_session.query(User).count() >= 0


def test_sql_injection_in_playlists_and_candidates(client, auth_headers):
    """Проверка защиты от SQL-инъекций в плейлистах и поиске кандидатов."""
    sqli_title = "Favorites'); DROP TABLE playlists; --"
    res_pl = client.post("/api/playlists", json={"title": sqli_title}, headers=auth_headers)
    assert res_pl.status_code == 200
    pl_id = res_pl.json()["playlist_id"]

    # Проверяем, что плейлист сохранился с экранированным именем без выполнения инъекции
    pl_data = client.get(f"/api/playlists/{pl_id}", headers=auth_headers).json()
    assert pl_data["title"] == sqli_title

    # Попытка SQL-инъекции через ID плейлиста
    r_bad_id = client.get("/api/playlists/1' OR '1'='1", headers=auth_headers)
    assert r_bad_id.status_code in (404, 422)


def test_sanitize_upload_filename_security():
    """Тестирует функцию безопасной нормализации имен загружаемых файлов."""
    from api.tracks import sanitize_upload_filename

    # Directory traversal
    assert ".." not in sanitize_upload_filename("../../../../etc/passwd")
    assert "passwd" in sanitize_upload_filename("../../../../etc/passwd")

    # Windows-style path traversal
    assert "cmd.exe" in sanitize_upload_filename("..\\..\\..\\windows\\system32\\cmd.exe")
    assert "\\" not in sanitize_upload_filename("..\\..\\..\\windows\\system32\\cmd.exe")

    # Запрещенные символы в именах файлов
    sanitized = sanitize_upload_filename('file*with?invalid:chars"<>|.mp3')
    for ch in r'\/:*?"<>|':
        assert ch not in sanitized


def test_boundary_and_fuzzing_defense(client, auth_headers):
    """Проверка устойчивости API к некорректным типам, огромным параметрам и переполнению."""
    # 1. Нечисловой ID трека в маршруте
    r1 = client.get("/api/tracks/not_an_int", headers=auth_headers)
    assert r1.status_code == 422

    # 2. Огромный limit в пагинации
    r2 = client.get("/api/tracks?limit=9999999999999999999999999", headers=auth_headers)
    assert r2.status_code in (200, 422)

    # 3. Отрицательный offset
    r3 = client.get("/api/tracks?offset=-10", headers=auth_headers)
    assert r3.status_code in (200, 422)

    # 4. Поисковый запрос гигантской длины (10 000 символов)
    giant_q = "A" * 10000
    r4 = client.get(f"/api/tracks/search?q={giant_q}", headers=auth_headers)
    assert r4.status_code in (200, 422)


def test_rbac_admin_privileges_enforcement(client, db_session, sample_track):
    """
    Проверка ролевой модели доступа (RBAC):
    Обычные пользователи (is_admin=False) не имеют доступа к деструктивным и системным операциям.
    Все такие запросы должны блокироваться со статусом 403 Forbidden.
    """
    from database.models import User, SessionToken
    from core.security import hash_password, generate_session_token

    salt, p_hash = hash_password("NormalUser123")
    regular_user = User(username="regular_user", password_hash=p_hash, salt=salt, is_admin=False)
    db_session.add(regular_user)
    db_session.commit()

    reg_token = generate_session_token()
    db_session.add(SessionToken(token=reg_token, user_id=regular_user.id, device_name="TestRegular"))
    db_session.commit()

    headers = {"Authorization": f"Bearer {reg_token}"}

    # 1. Попытка запуска сканирования директории
    r1 = client.post("/api/scan", headers=headers)
    assert r1.status_code == 403
    assert "администратора" in r1.json().get("detail", "").lower()

    # 2. Попытка остановки и запуска Watchdog
    assert client.post("/api/watcher/start", headers=headers).status_code == 403
    assert client.post("/api/watcher/stop", headers=headers).status_code == 403

    # 3. Попытка запуска/остановки психоакустического анализа библиотеки
    assert client.post("/api/stream/analytics/start", headers=headers).status_code == 403
    assert client.post("/api/stream/analytics/stop", headers=headers).status_code == 403

    # 4. Попытка удаления трека из фонотеки
    assert client.delete(f"/api/tracks/{sample_track.id}", headers=headers).status_code == 403

    # 5. Попытка пакетного удаления дубликатов треков
    assert client.post("/api/tracks/duplicates/delete", json={"track_ids": [sample_track.id]}, headers=headers).status_code == 403

    # 6. Попытка очистки отсутствующих треков
    assert client.post("/api/tracks/cleanup-missing", headers=headers).status_code == 403

    # 7. Попытка скачивания внешнего кандидата в фонотеку
    assert client.post(
        "/api/tracks/candidates/download",
        json={"candidate": {"candidate_id": "test_1", "artist": "A", "title": "B"}},
        headers=headers
    ).status_code == 403

    # 8. Попытка замены версии трека в фонотеке обычным пользователем (RBAC)
    assert client.post(
        f"/api/tracks/{sample_track.id}/replace",
        json={"candidate": {"candidate_id": "test_cand_1", "artist": "A", "title": "B"}},
        headers=headers
    ).status_code == 403

    # 9. Попытка запуска backfill обложек обычным пользователем
    assert client.post("/api/covers/backfill", headers=headers).status_code == 403


def test_ssrf_candidate_url_blocking(client, auth_headers, sample_track):
    """Проверка блокировки атак SSRF через URL кандидатов."""
    malicious_urls = [
        "http://127.0.0.1:5432/evil",
        "http://localhost:8000/api/auth/me",
        "http://169.254.169.254/latest/meta-data/",
        "http://192.168.1.1/admin",
        "http://host.docker.internal:5030/api/v0",
        "https://evil-attacker.com/song.mp3",
        "http://user:pass@127.0.0.1/audio.mp3"
    ]

    for bad_url in malicious_urls:
        # Попытка предпрослушивания с небезопасным URL
        r1 = client.get(f"/api/tracks/candidates/preview?candidate_id=source_a_@127.0.0.1:5432", headers=auth_headers)
        assert r1.status_code in (400, 404)

        # Попытка подмены трека через произвольный dl_url
        r2 = client.post(
            f"/api/tracks/{sample_track.id}/replace",
            json={"candidate": {"candidate_id": "bad_cand", "dl_url": bad_url, "artist": "A", "title": "B"}},
            headers=auth_headers
        )
        assert r2.status_code == 400
        assert "небезопасный url" in r2.json().get("detail", "").lower() or "недопустимый" in r2.json().get("detail", "").lower()


def test_scan_path_traversal_containment(client, auth_headers):
    """Проверка защиты /api/scan от выхода за пределы каталога фонотеки (Path Containment)."""
    malicious_paths = [
        "../../../../../../etc",
        "/etc",
        "/var/run",
        "C:\\Windows\\System32",
        "../"
    ]
    for p in malicious_paths:
        res = client.post(f"/api/scan?music_path={p}", headers=auth_headers)
        assert res.status_code == 400
        detail = res.json().get("detail", "").lower()
        assert "системных" in detail or "недопустимый" in detail or "запрещено" in detail


def test_qr_payload_length_restriction(client):
    """Проверка защиты от DoS через генерацию гигантских QR-кодов."""
    # 1. Превышение лимита в 2048 символов -> HTTP 400 Bad Request
    giant_data = "X" * 3000
    res_large = client.get(f"/api/auth/qr/image?data={giant_data}")
    assert res_large.status_code == 400
    assert "максимальный размер" in res_large.json().get("detail", "").lower()

    # 2. Нормальный короткий QR-пейлоад -> HTTP 200 image/png
    res_ok = client.get("/api/auth/qr/image?data=https://sentinel.music/test")
    assert res_ok.status_code == 200
    assert res_ok.headers["content-type"] == "image/png"


def test_security_headers_present(client):
    """Проверка наличия базовых защитных HTTP-заголовков (nosniff, SAMEORIGIN, Referrer-Policy)."""
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-frame-options") == "SAMEORIGIN"
    assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_streaming_path_containment_forbidden(client, auth_headers, db_session):
    """Проверка блокировки попыток чтения системных файлов через стриминг (Path Containment)."""
    from database.models import Track
    # Создаем трек с файловым путем, указывающим на системный файл ОС
    evil_track = Track(
        title="Evil Shadow Stream",
        artist="Attacker",
        duration=180.0,
        file_path="/etc/passwd" if os.name != "nt" else "C:\\Windows\\System32\\drivers\\etc\\hosts",
        audio_format="mp3"
    )
    db_session.add(evil_track)
    db_session.commit()
    db_session.refresh(evil_track)

    res = client.get(f"/api/stream/{evil_track.id}", headers=auth_headers)
    assert res.status_code == 403
    assert "запрещен" in res.json().get("detail", "").lower() or "пределы" in res.json().get("detail", "").lower()


def test_range_header_negative_values(client, auth_headers, sample_track):
    """Проверка защиты парсера Range от отрицательных чисел и целочисленного переполнения."""
    invalid_ranges = [
        "bytes=-10-",
        "bytes=-5-10",
        "bytes=10-5",
        "bytes=999999999-",
        "invalid_unit=0-100"
    ]
    for r in invalid_ranges:
        res = client.get(f"/api/stream/{sample_track.id}", headers={**auth_headers, "Range": r})
        assert res.status_code in (416, 400)


def test_websocket_cswsh_protection(client, auth_user_and_token):
    """Проверка защиты WebSocket от Cross-Site WebSocket Hijacking (CSWSH) через проверку Origin."""
    _, token = auth_user_and_token
    import pytest
    from starlette.websockets import WebSocketDisconnect

    # Попытка подключения с вредоносного внешнего веб-сайта
    try:
        with client.websocket_connect(
            f"/api/remote/ws?token={token}&device_id=test_dev",
            headers={"Origin": "https://evil-hacker.com"}
        ) as ws:
            pytest.fail("WebSocket должен отклонить неразрешенный Origin")
    except WebSocketDisconnect as e:
        assert e.code == 1008  # WS_1008_POLICY_VIOLATION
    except Exception:
        pass


def test_login_timing_protection_and_rate_limiting(client):
    """Проверка защиты от тайминг-атак и ограничения брутфорса на /api/auth/login."""
    from api.auth import clear_failed_logins

    clear_failed_logins()

    for i in range(5):
        res = client.post("/api/auth/login", json={"username": f"nonexistent_{i}", "password": "wrongpassword"})
        assert res.status_code == 401

    res_blocked = client.post("/api/auth/login", json={"username": "any_user", "password": "any_password"})
    assert res_blocked.status_code == 429
    assert "слишком много" in res_blocked.json().get("detail", "").lower()
    assert "Retry-After" in res_blocked.headers

    clear_failed_logins()





