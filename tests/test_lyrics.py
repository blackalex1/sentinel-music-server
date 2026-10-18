import os
import pytest
from lyrics.parser import parse_lrc
from lyrics.storage import get_or_fetch_lyrics


def test_parse_lrc_accuracy():
    lrc_content = """
    [ar:Queen]
    [ti:Bohemian Rhapsody]
    [00:05.50]Is this the real life?
    [00:09.80]Is this just fantasy?
    [01:15.250]Caught in a landslide
    Invalid line without brackets
    [99:99.99]No escape from reality
    """

    lines = parse_lrc(lrc_content)
    assert len(lines) == 4

    # Проверка миллисекунд и секунд
    assert lines[0]["text"] == "Is this the real life?"
    assert lines[0]["time_ms"] == 5500
    assert lines[0]["time_sec"] == 5.5

    assert lines[1]["text"] == "Is this just fantasy?"
    assert lines[1]["time_ms"] == 9800

    assert lines[2]["text"] == "Caught in a landslide"
    assert lines[2]["time_ms"] == 75250


def test_lyrics_storage_cache_layers(sample_track, db_session, tmp_path):
    # 1. Если текст уже сохранен в БД
    sample_track.lyrics_synced = "[00:01.00]Cached in database"
    db_session.commit()

    is_synced, lines, raw = get_or_fetch_lyrics(sample_track, db_session)
    assert is_synced is True
    assert len(lines) == 1
    assert lines[0]["text"] == "Cached in database"

    # 2. Если текста нет в БД, но есть файл .lrc рядом на диске
    sample_track.lyrics_synced = None
    db_session.commit()

    lrc_file = tmp_path / "test_song.lrc"
    lrc_file.write_text("[00:02.50]Cached in local file", encoding="utf-8")

    is_synced2, lines2, raw2 = get_or_fetch_lyrics(sample_track, db_session)
    assert is_synced2 is True
    assert lines2[0]["text"] == "Cached in local file"
    # Должно было автоматически сохраниться в БД
    assert sample_track.lyrics_synced is not None


def test_lyrics_api_endpoint(client, auth_headers, sample_track):
    sample_track.lyrics_synced = "[00:03.00]API Test Lyrics"

    res = client.get(f"/api/lyrics/{sample_track.id}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["synced"] is True
    assert len(data["lines"]) == 1
    assert data["lines"][0]["text"] == "API Test Lyrics"

    # Несуществующий трек
    bad_res = client.get("/api/lyrics/9999", headers=auth_headers)
    assert bad_res.status_code == 404


def test_lyrics_refresh_endpoint(client, auth_headers, sample_track, tmp_path, db_session, monkeypatch):
    """Проверяет сброс кэша и повторный поиск текста песни через /api/lyrics/{id}/refresh."""
    from plugin_system.manager import plugin_manager
    from unittest.mock import AsyncMock
    import lyrics.storage as storage_module
    import api.lyrics as lyrics_api_mod

    monkeypatch.setattr(plugin_manager, "get_track_lyrics", AsyncMock(return_value=(False, [], None)))
    monkeypatch.setattr(storage_module, "get_or_fetch_lyrics", lambda t, db: (False, [], None))
    monkeypatch.setattr(lyrics_api_mod, "get_or_fetch_lyrics", lambda t, db: (False, [], None))

    # Записываем старый текст в БД и локальный .lrc файл
    sample_track.lyrics_synced = "[00:01.00]Old Text"
    db_session.commit()

    base, _ = os.path.splitext(sample_track.file_path)
    lrc_path = base + ".lrc"
    with open(lrc_path, "w", encoding="utf-8") as f:
        f.write("[00:01.00]Old File Text")
    assert os.path.exists(lrc_path)

    # Вызываем refresh
    res = client.post(f"/api/lyrics/{sample_track.id}/refresh", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "synced" in data

    # Локальный файл должен быть удален
    assert not os.path.exists(lrc_path)

    # Несуществующий трек -> 404
    bad_res = client.post("/api/lyrics/99999/refresh", headers=auth_headers)
    assert bad_res.status_code == 404


