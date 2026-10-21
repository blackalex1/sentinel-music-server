import os
import io
import pytest
from unittest.mock import AsyncMock, MagicMock
from api.candidates import _CANDIDATES_BY_ID, _CANDIDATES_CACHE


@pytest.fixture(autouse=True)
def clear_candidates_cache():
    """Очищает кэши кандидатов перед каждым тестом."""
    _CANDIDATES_CACHE.clear()
    _CANDIDATES_BY_ID.clear()
    yield
    _CANDIDATES_CACHE.clear()
    _CANDIDATES_BY_ID.clear()


def test_get_track_candidates_success(client, auth_headers, sample_track, monkeypatch):
    from plugin_system.manager import plugin_manager

    mock_candidates = [
        {
            "candidate_id": "mock_cand_web_12345",
            "source": "provider_web",
            "title": "Test Song (Remix)",
            "artist": "Test Artist",
            "duration": 190,
            "bitrate": 320,
            "format": "mp3"
        },
        {
            "candidate_id": "mock_cand_p2p_file",
            "source": "provider_p2p",
            "title": "Test Song (Lossless)",
            "artist": "Test Artist",
            "format": "flac"
        }
    ]

    monkeypatch.setattr(
        plugin_manager,
        "search_all_candidates",
        AsyncMock(return_value=mock_candidates)
    )

    res = client.get(f"/api/tracks/{sample_track.id}/candidates?limit=5", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["track_id"] == sample_track.id
    assert data["current_artist"] == sample_track.artist
    assert len(data["candidates"]) == 2

    # Проверяем, что can_preview проставлен: True для потоковых источников, False для фоновых
    c1 = next(c for c in data["candidates"] if c["candidate_id"] == "mock_cand_web_12345")
    c2 = next(c for c in data["candidates"] if c["candidate_id"] == "mock_cand_p2p_file")
    assert c1["can_preview"] is True
    assert c2["can_preview"] is False


def test_get_track_candidates_not_found(client, auth_headers):
    res = client.get("/api/tracks/99999/candidates", headers=auth_headers)
    assert res.status_code == 404
    assert "не найден" in res.json().get("detail", "").lower()


def test_search_candidates_query_variations(client, auth_headers, monkeypatch):
    from plugin_system.manager import plugin_manager

    mock_search = AsyncMock(return_value=[
        {"candidate_id": "c_mock_1", "source": "provider_b", "title": "Track", "artist": "Artist"}
    ])
    monkeypatch.setattr(plugin_manager, "search_all_candidates", mock_search)

    # 1. Запрос с раздельными artist и title
    r1 = client.get("/api/tracks/candidates/search?artist=Queen&title=Bohemian", headers=auth_headers)
    assert r1.status_code == 200
    assert len(r1.json()["candidates"]) == 1
    mock_search.assert_awaited_with("Queen", "Bohemian", limit=5)

    # 2. Единый запрос "Artist - Title"
    r2 = client.get("/api/tracks/candidates/search?q=Nirvana - In Bloom", headers=auth_headers)
    assert r2.status_code == 200
    mock_search.assert_awaited_with("Nirvana", "In Bloom", limit=5)

    # 3. Единый запрос из одного слова (только title)
    r3 = client.get("/api/tracks/candidates/search?q=Yesterday", headers=auth_headers)
    assert r3.status_code == 200
    mock_search.assert_awaited_with("", "Yesterday", limit=5)


def test_search_candidates_validation_and_caching(client, auth_headers, monkeypatch):
    from plugin_system.manager import plugin_manager

    mock_search = AsyncMock(return_value=[
        {"candidate_id": "cached_cand_1", "source": "provider_c", "title": "Song", "artist": "Band"}
    ])
    monkeypatch.setattr(plugin_manager, "search_all_candidates", mock_search)

    # 1. Пустой запрос -> 400
    r_empty = client.get("/api/tracks/candidates/search", headers=auth_headers)
    assert r_empty.status_code == 400

    # 2. Слишком короткий запрос (<2 символов) -> 200 с пустым списком
    r_short = client.get("/api/tracks/candidates/search?q=x", headers=auth_headers)
    assert r_short.status_code == 200
    assert r_short.json()["candidates"] == []
    assert "короткий" in r_short.json()["message"].lower()

    # 3. Нормальный запрос -> кэшируется
    r_normal1 = client.get("/api/tracks/candidates/search?q=Linkin Park - Numb", headers=auth_headers)
    assert r_normal1.status_code == 200
    assert r_normal1.json()["cached"] is False

    # Повторный идентичный запрос -> cached: True без повторного вызова плагинов
    mock_search.reset_mock()
    r_normal2 = client.get("/api/tracks/candidates/search?q=Linkin Park - Numb", headers=auth_headers)
    assert r_normal2.status_code == 200
    assert r_normal2.json()["cached"] is True
    mock_search.assert_not_called()


def test_replace_track_success(client, auth_headers, sample_track, tmp_path, monkeypatch):
    from plugin_system.manager import plugin_manager
    import api.candidates as candidates_module

    # Имитируем скачивание нового аудиофайла
    async def mock_download(candidate, destination, force_replace=True):
        with open(destination, "wb") as f:
            f.write(b"NEW_AUDIO_FLAC_CONTENT_DATA")
        return True

    import streaming.scanner as scanner_module

    monkeypatch.setattr(plugin_manager, "download_selected_candidate", mock_download)
    monkeypatch.setattr(scanner_module, "extract_metadata", lambda p: {
        "title": "Upgraded Title",
        "artist": "Upgraded Artist",
        "album": "Upgraded Album",
        "duration": 240.0,
        "audio_format": "flac",
        "bitrate": 950
    })

    candidate_payload = {
        "candidate_id": "mock_cand_flac_9988",
        "source": "provider_d",
        "title": "Upgraded Title",
        "artist": "Upgraded Artist",
        "format": "flac"
    }

    res = client.post(
        f"/api/tracks/{sample_track.id}/replace",
        json={"candidate": candidate_payload},
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["track"]["title"] == "Upgraded Title"
    assert data["track"]["artist"] == "Upgraded Artist"
    assert data["track"]["audio_format"] == "flac"


def test_replace_track_errors(client, auth_headers, sample_track, monkeypatch):
    from plugin_system.manager import plugin_manager

    # 1. Трек не найден
    r_404 = client.post(
        "/api/tracks/88888/replace",
        json={"candidate": {"title": "A", "artist": "B"}},
        headers=auth_headers
    )
    assert r_404.status_code == 404

    # 2. Кандидат пуст
    r_400 = client.post(
        f"/api/tracks/{sample_track.id}/replace",
        json={"candidate": {}},
        headers=auth_headers
    )
    assert r_400.status_code == 400

    # 3. Ошибка загрузки плагином
    monkeypatch.setattr(
        plugin_manager,
        "download_selected_candidate",
        AsyncMock(return_value=False)
    )
    r_500 = client.post(
        f"/api/tracks/{sample_track.id}/replace",
        json={"candidate": {"title": "Fail", "artist": "Fail", "format": "mp3"}},
        headers=auth_headers
    )
    assert r_500.status_code == 500


def test_download_candidate_queued(client, auth_headers, monkeypatch):
    from plugin_system.manager import plugin_manager

    monkeypatch.setattr(
        plugin_manager,
        "download_selected_candidate",
        AsyncMock(return_value=True)
    )

    candidate_queued = {
        "candidate_id": "queued_123",
        "source": "provider_p2p",
        "title": "Queued Song",
        "artist": "Queued Artist",
        "format": "flac"
    }

    res = client.post(
        "/api/tracks/candidates/download",
        json={"candidate": candidate_queued},
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "queued"
    assert data["source"] == "provider_p2p"


def test_download_candidate_web(client, auth_headers, tmp_path, monkeypatch):
    from plugin_system.manager import plugin_manager
    import api.candidates as candidates_module

    async def mock_download(candidate, destination, force_replace=True):
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as f:
            f.write(b"AUDIO_DATA_BYTES")
        return True

    import streaming.scanner as scanner_module

    monkeypatch.setattr(plugin_manager, "download_selected_candidate", mock_download)
    monkeypatch.setattr(scanner_module, "extract_metadata", lambda p: {
        "title": "Web Song",
        "artist": "Web Artist",
        "album": "Web Album",
        "duration": 180.0,
        "audio_format": "mp3",
        "bitrate": 320
    })

    candidate_web = {
        "candidate_id": "web_777",
        "source": "provider_web",
        "title": "Web Song",
        "artist": "Web Artist",
        "format": "mp3"
    }

    res = client.post(
        "/api/tracks/candidates/download",
        json={"candidate": candidate_web},
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["track"]["title"] == "Web Song"
    assert data["track"]["artist"] == "Web Artist"


def test_preview_candidate_stream(client, auth_headers, monkeypatch):
    import requests
    from plugin_system.manager import plugin_manager
    from api.candidates import _register_candidates

    # 1. Несуществующий кандидат -> 404
    r_404 = client.get("/api/tracks/candidates/preview?candidate_id=non_existent_999", headers=auth_headers)
    assert r_404.status_code == 404

    # 2. Кандидат без поддержки превью -> 400
    _register_candidates([{
        "candidate_id": "no_preview_cid",
        "source": "provider_p2p",
        "title": "Song",
        "artist": "Artist"
    }])
    r_nopreview = client.get("/api/tracks/candidates/preview?candidate_id=no_preview_cid", headers=auth_headers)
    assert r_nopreview.status_code == 400

    # 3. Валидный веб-кандидат с потоковой отдачей
    _register_candidates([{
        "candidate_id": "valid_preview_cid",
        "source": "provider_web",
        "title": "Valid Stream",
        "artist": "Streamer"
    }])

    monkeypatch.setattr(
        plugin_manager,
        "get_candidate_preview_url",
        AsyncMock(return_value="https://example.com/preview_audio.mp3")
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 206
    mock_resp.headers = {
        "Content-Type": "audio/mpeg",
        "Content-Range": "bytes 0-1023/2048",
        "Content-Length": "1024"
    }
    mock_resp.iter_content = MagicMock(return_value=[b"MOCK_STREAM_CHUNK_1", b"MOCK_STREAM_CHUNK_2"])
    monkeypatch.setattr(requests, "get", MagicMock(return_value=mock_resp))

    res = client.get(
        "/api/tracks/candidates/preview?candidate_id=valid_preview_cid",
        headers={**auth_headers, "Range": "bytes=0-1023"}
    )
    assert res.status_code == 206
    assert res.headers["content-type"] == "audio/mpeg"
    assert res.content == b"MOCK_STREAM_CHUNK_1MOCK_STREAM_CHUNK_2"
