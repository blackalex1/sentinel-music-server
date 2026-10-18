import pytest
from api.covers import extract_embedded_cover


def test_folder_cover_art_fallback(tmp_path):
    audio_file = tmp_path / "song.mp3"
    audio_file.write_bytes(b"dummy audio")

    # Сначала обложки нет
    data, mime = extract_embedded_cover(str(audio_file))
    assert data is None
    assert mime is None

    # Создаем cover.jpg в той же папке
    cover_file = tmp_path / "cover.jpg"
    dummy_jpeg = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"\x00" * 64
    cover_file.write_bytes(dummy_jpeg)

    # Теперь обложка должна успешно обнаружиться
    data2, mime2 = extract_embedded_cover(str(audio_file))
    assert data2 == dummy_jpeg
    assert mime2 == "image/jpeg"


def test_covers_api_endpoint(client, sample_track, tmp_path):
    # Добавляем cover.jpg рядом с тестовым треком
    cover_file = tmp_path / "cover.jpg"
    cover_bytes = b"\xFF\xD8\xFF\xE0" + b"\x00" * 32
    cover_file.write_bytes(cover_bytes)

    res = client.get(f"/api/covers/{sample_track.id}")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert res.content == cover_bytes

    # Несуществующий трек -> 404
    bad_res = client.get("/api/covers/8888")
    assert bad_res.status_code == 404


def test_covers_fallback_svg(client, sample_track, monkeypatch):
    """Проверяет отдачу резервного SVG при отсутствии любых обложек."""
    from plugin_system.manager import plugin_manager
    from unittest.mock import AsyncMock

    monkeypatch.setattr(plugin_manager, "get_track_cover", AsyncMock(return_value=(None, None)))

    res = client.get(f"/api/covers/{sample_track.id}")
    assert res.status_code == 200
    assert "image/svg+xml" in res.headers["content-type"]
    assert b"<svg" in res.content


def test_covers_refresh(client, sample_track, auth_headers):
    """Проверяет сброс и обновление обложки трека."""
    # Существующий трек
    res = client.post(f"/api/covers/{sample_track.id}/refresh", headers=auth_headers)
    assert res.status_code == 200
    assert "status" in res.json()

    # Несуществующий трек -> 404
    res_404 = client.post("/api/covers/99999/refresh", headers=auth_headers)
    assert res_404.status_code == 404


def test_covers_backfill(client, auth_headers, monkeypatch):
    """Проверяет вызов пакетного заполнения обложек."""
    import plugins.cover_art.plugin as cap_module
    monkeypatch.setattr(cap_module, "fetch_online_cover", lambda artist, title: (None, None, None))
    res = client.post("/api/covers/backfill?limit=5", headers=auth_headers)
    assert res.status_code in (200, 503)

