import pytest
from database.models import Track


@pytest.fixture
def sample_tracks(db_session):
    """Набор разнообразных тестовых треков с текстами, альбомами и кириллицей."""
    tracks = [
        Track(
            title="Smells Like Teen Spirit",
            artist="Nirvana",
            album="Nevermind",
            duration=301.0,
            file_path="/music/nirvana_spirit.flac",
            lyrics_plain="with the lights out it is less dangerous here we are now",
            audio_format="flac"
        ),
        Track(
            title="Lithium",
            artist="Nirvana",
            album="Nevermind",
            duration=257.0,
            file_path="/music/nirvana_lithium.flac",
            lyrics_plain="i am so happy cause today i found my friends",
            audio_format="flac"
        ),
        Track(
            title="Bohemian Rhapsody",
            artist="Queen",
            album="A Night at the Opera",
            duration=354.0,
            file_path="/music/queen_rhapsody.flac",
            lyrics_plain="is this the real life is this just fantasy",
            audio_format="flac"
        ),
        Track(
            title="Кукла Колдуна",
            artist="Король и Шут",
            album="Акустический альбом",
            duration=203.0,
            file_path="/music/korol_i_shut_kukla.flac",
            lyrics_plain="темный мрачный коридор я на цыпочках как вор",
            audio_format="flac"
        )
    ]
    for t in tracks:
        db_session.add(t)
    db_session.commit()
    return tracks


def test_search_by_artist_and_title(client, auth_headers, sample_tracks):
    """Проверяет поиск по исполнителю и названию трека с префиксами."""
    # Поиск по точному названию
    res = client.get("/api/tracks/search?q=Bohemian", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["title"] == "Bohemian Rhapsody"
    assert data[0]["artist"] == "Queen"

    # Префиксный поиск по артисту
    res = client.get("/api/tracks/search?q=Nirv", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2


def test_search_by_album(client, auth_headers, sample_tracks):
    """Проверяет поиск треков по названию альбома."""
    res = client.get("/api/tracks/search?q=Opera", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["title"] == "Bohemian Rhapsody"


def test_search_by_lyrics(client, auth_headers, sample_tracks):
    """Проверяет поиск по словам из текста песни (караоке-лирики)."""
    res = client.get("/api/tracks/search?q=fantasy", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["title"] == "Bohemian Rhapsody"

    res = client.get("/api/tracks/search?q=lights+out", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["title"] == "Smells Like Teen Spirit"


def test_search_cyrillic_unicode(client, auth_headers, sample_tracks):
    """Проверяет поиск на кириллице (регистронезависимый токенизатор)."""
    res = client.get("/api/tracks/search?q=колдун", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["title"] == "Кукла Колдуна"
    assert data[0]["artist"] == "Король и Шут"


def test_search_russian_yo_and_morphology(client, auth_headers, db_session):
    """Проверяет поиск с нормализацией е/ё и русским стеммингом окончаний."""
    pugacheva = Track(
        title="Позови меня с собой",
        artist="Алла Пугачёва",
        album="Да!",
        duration=260.0,
        file_path="/music/pugacheva.mp3",
        audio_format="mp3"
    )
    db_session.add(pugacheva)
    db_session.commit()

    # Поиск с буквой 'е' вместо 'ё'
    res = client.get("/api/tracks/search?q=пугачева", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert data[0]["artist"] == "Алла Пугачёва"

    # Поиск со склонением (падеж)
    res_stem = client.get("/api/tracks/search?q=пугачевой", headers=auth_headers)
    assert res_stem.status_code == 200
    assert len(res_stem.json()) >= 1
    assert res_stem.json()[0]["artist"] == "Алла Пугачёва"


def test_security_sql_injection_attempts(client, auth_headers, sample_tracks, db_session):
    """
    Проверяет защиту от попыток SQL-инъекций.
    Запросы не должны вызывать 500 ошибок, инъекции должны безопасно нейтрализоваться.
    """
    dangerous_payloads = [
        "' OR '1'='1",
        "'; DROP TABLE tracks; --",
        "admin' --",
        "UNION SELECT 1, 2, 3, 4 --",
        "1' OR 1=1#"
    ]
    for payload in dangerous_payloads:
        res = client.get(f"/api/tracks/search?q={payload}", headers=auth_headers)
        assert res.status_code == 200, f"Payload failed: {payload}"

    # Проверяем целостность таблицы tracks после попыток внедрения
    count = db_session.query(Track).count()
    assert count == 4


def test_security_fts_malformed_syntax_break(client, auth_headers, sample_tracks):
    """Проверяет защиту от сбоя парсера FTS5 (незакрытые кавычки, спецсимволы, операторы)."""
    malformed_inputs = [
        '"',
        '""""""',
        '*()[]{}^~:*',
        'NEAR(Nirvana, 5)',
        'title:Smells',
        'AND OR NOT'
    ]
    for bad_input in malformed_inputs:
        res = client.get(f"/api/tracks/search?q={bad_input}", headers=auth_headers)
        assert res.status_code == 200
        # Должен вернуть корректный пустой или безопасный результат, без 500 Internal Server Error
        assert isinstance(res.json(), list)


def test_security_unauthenticated_request_rejected(client, sample_tracks):
    """Проверяет, что неавторизованные запросы к поиску блокируются (401/403)."""
    res = client.get("/api/tracks/search?q=Queen")
    assert res.status_code in (401, 403)


def test_input_validation_limits(client, auth_headers):
    """Проверяет валидацию граничных параметров (min/max length, limit, offset)."""
    # Пустой запрос
    res_empty = client.get("/api/tracks/search?q=", headers=auth_headers)
    assert res_empty.status_code == 422

    # Запрос свыше 100 символов
    res_long = client.get(f"/api/tracks/search?q={'a'*101}", headers=auth_headers)
    assert res_long.status_code == 422

    # Превышение лимита выборки (макс 100)
    res_limit = client.get("/api/tracks/search?q=test&limit=200", headers=auth_headers)
    assert res_limit.status_code == 422

    # Отрицательный offset
    res_offset = client.get("/api/tracks/search?q=test&offset=-1", headers=auth_headers)
    assert res_offset.status_code == 422
