import os
import json
import pytest
from datetime import datetime, timedelta
from database.models import Track, UserReaction
from recommendations.buffer_manager import DiscoveryBufferManager


def test_buffer_manager_lifecycle(tmp_path, db_session):
    # Тестовый каталог для буфера
    music_dir = str(tmp_path / "music")
    buf_manager = DiscoveryBufferManager(music_dir=music_dir)
    assert os.path.exists(buf_manager.buffer_dir)
    assert os.path.exists(buf_manager.history_json_path)

    # 1. Создаем тестовый трек в буферной папке
    file_path = os.path.join(buf_manager.buffer_dir, "test_song.flac")
    with open(file_path, "wb") as f:
        f.write(b"fLaC dummy audio content")

    track = Track(
        title="Buffer Hit",
        artist="Fresh Artist",
        duration=210.0,
        audio_format="flac",
        file_path=file_path,
        bpm=120.0,
        energy=0.75,
        valence=0.6
    )
    db_session.add(track)
    db_session.commit()

    # 2. Синхронизируем файлы
    buf_manager.sync_buffer_files(db_session)
    history = buf_manager.load_history()
    assert len(history) == 1
    rec = history[0]
    assert rec["track_id"] == track.id
    assert rec["status"] == "buffered"
    assert rec["liked"] is False

    # 3. Выборка для Потока
    cand = buf_manager.get_next_buffered_track(db_session)
    assert cand is not None
    assert cand["id"] == track.id
    assert cand["discovery_reason"] == "🔥 Свежая новинка из сети"

    # Проверяем, что статус стал 'played' и зафиксирован played_in_stream_at
    history = buf_manager.load_history()
    assert history[0]["status"] == "played"
    assert history[0]["played_in_stream_at"] is not None

    # 4. Лайк трека -> закрепление навсегда
    promoted = buf_manager.handle_user_reaction(track.id, is_like=True, db=db_session)
    assert promoted is True
    history = buf_manager.load_history()
    assert history[0]["status"] == "saved_permanent"
    assert history[0]["liked"] is True

    # 5. Проверка очистки истекших (TTL = 3 дня)
    # Создаем второй трек с истекшим сроком
    expired_path = os.path.join(buf_manager.buffer_dir, "expired.flac")
    with open(expired_path, "wb") as f:
        f.write(b"expired flac")

    t_expired = Track(
        title="Unliked Song",
        artist="Old Artist",
        duration=180.0,
        audio_format="flac",
        file_path=expired_path
    )
    db_session.add(t_expired)
    db_session.commit()

    buf_manager.sync_buffer_files(db_session)
    history = buf_manager.load_history()
    assert len(history) == 2

    # Искусственно состариваем запись на 4 дня назад
    for r in history:
        if r["track_id"] == t_expired.id:
            four_days_ago = (datetime.now() - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")
            r["expires_at"] = four_days_ago
    buf_manager.save_history(history)

    # Запускаем очистку
    deleted_count = buf_manager.cleanup_expired_tracks(db_session)
    assert deleted_count == 1
    assert not os.path.exists(expired_path)  # Файл физически удален

    # Запись в stream_history.json ОБЯЗАНА сохраниться
    history = buf_manager.load_history()
    assert len(history) == 2
    deleted_rec = next(r for r in history if r["track_id"] == t_expired.id)
    assert deleted_rec["status"] == "expired_deleted"
    assert deleted_rec["deleted_at"] is not None


def test_backfill_main_folder_likes(tmp_path, db_session):
    music_dir = str(tmp_path / "music_backfill")
    buf_manager = DiscoveryBufferManager(music_dir=music_dir)

    # Создаем трек в основной папке (вне discovery_buffer)
    main_track = Track(
        title="Main Folder Classic",
        artist="Favorite Band",
        duration=200.0,
        audio_format="flac",
        file_path=os.path.join(music_dir, "Rock", "classic.flac")
    )
    db_session.add(main_track)
    db_session.commit()

    # Запускаем бэкфилл
    count = buf_manager.backfill_main_folder_likes(db_session)
    assert count >= 1

    reaction = db_session.query(UserReaction).filter(UserReaction.track_id == main_track.id).first()
    assert reaction is not None
    assert reaction.is_liked is True
    assert reaction.is_disliked is False


def test_buffer_api_endpoints(client, auth_headers):
    # Тест эндпоинта статуса буфера
    res_status = client.get("/api/stream/discovery/buffer/status", headers=auth_headers)
    assert res_status.status_code == 200
    data = res_status.json()
    assert "target_buffer_size" in data
    assert "counts" in data
    assert data["target_buffer_size"] == 10
    assert data["retention_days"] == 3
    assert "stream_history.json" in data["history_file"]

    # Тест эндпоинта истории буфера
    res_history = client.get("/api/stream/discovery/buffer/history", headers=auth_headers)
    assert res_history.status_code == 200
    assert isinstance(res_history.json(), list)


def test_discovery_buffer_tracks_hidden_from_library(client, auth_headers, db_session):
    # 1. Создаем обычный трек и трек в discovery_buffer
    t_normal = Track(
        title="Normal Track",
        artist="Artist A",
        duration=180.0,
        file_path="/music/Rock/normal.flac",
        audio_format="flac"
    )
    t_buffer = Track(
        title="Buffer Track",
        artist="Artist B",
        duration=180.0,
        file_path="/music/discovery_buffer/buffer.mp3",
        audio_format="mp3"
    )
    db_session.add_all([t_normal, t_buffer])
    db_session.commit()

    # Проверяем /api/tracks
    res = client.get("/api/tracks", headers=auth_headers)
    assert res.status_code == 200
    track_ids = [t["id"] for t in res.json()]
    assert t_normal.id in track_ids
    assert t_buffer.id not in track_ids

    # Проверяем /api/tracks/recent
    res_recent = client.get("/api/tracks/recent", headers=auth_headers)
    assert res_recent.status_code == 200
    recent_ids = [t["id"] for t in res_recent.json()]
    assert t_normal.id in recent_ids
    assert t_buffer.id not in recent_ids

    # Проверяем /api/tracks/count
    res_count = client.get("/api/tracks/count", headers=auth_headers)
    assert res_count.status_code == 200
    assert res_count.json()["count"] >= 1


def test_like_triggers_upgrade_and_reveals_in_library(tmp_path, db_session, monkeypatch):
    music_dir = str(tmp_path / "music_upgrade")
    buf_manager = DiscoveryBufferManager(music_dir=music_dir)

    # Создаем буферный трек
    os.makedirs(buf_manager.buffer_dir, exist_ok=True)
    f_path = os.path.join(buf_manager.buffer_dir, "stream_song.mp3")
    with open(f_path, "wb") as f:
        f.write(b"mp3 dummy")

    track = Track(
        title="Song To Upgrade",
        artist="Cool Artist",
        duration=180.0,
        audio_format="mp3",
        file_path=f_path
    )
    db_session.add(track)
    db_session.commit()

    buf_manager.sync_buffer_files(db_session)

    upgraded_called = []
    def mock_trigger(track_id, artist, title):
        upgraded_called.append((track_id, artist, title))

    monkeypatch.setattr(buf_manager, "trigger_background_upgrade", mock_trigger)

    # Лайкаем трек
    promoted = buf_manager.handle_user_reaction(track.id, is_like=True, db=db_session)
    assert promoted is True
    assert len(upgraded_called) == 1
    assert upgraded_called[0] == (track.id, "Cool Artist", "Song To Upgrade")

    # Проверяем, что файл перемещен из discovery_buffer в Saved_Discoveries
    db_session.refresh(track)
    assert "discovery_buffer" not in track.file_path
    assert "Saved_Discoveries" in track.file_path
    assert track.is_discovery is False


def test_unlike_does_not_delete_track(tmp_path, db_session):
    music_dir = str(tmp_path / "music_unlike")
    buf_manager = DiscoveryBufferManager(music_dir=music_dir)
    os.makedirs(buf_manager.buffer_dir, exist_ok=True)
    f_path = os.path.join(buf_manager.buffer_dir, "unlike_song.mp3")
    with open(f_path, "wb") as f:
        f.write(b"mp3 dummy")

    track = Track(
        title="Unlike Song",
        artist="Test Artist",
        duration=180.0,
        audio_format="mp3",
        file_path=f_path
    )
    db_session.add(track)
    db_session.commit()
    buf_manager.sync_buffer_files(db_session)

    # 1. Лайкаем
    buf_manager.handle_user_reaction(track.id, is_like=True, is_disliked=False, db=db_session)
    db_session.refresh(track)
    assert track.is_discovery is False
    assert os.path.exists(track.file_path)

    # 2. Снимаем лайк (is_like=False, is_disliked=False)
    buf_manager.handle_user_reaction(track.id, is_like=False, is_disliked=False, db=db_session)
    # Файл и запись в БД ОБЯЗАНЫ остаться на месте!
    assert os.path.exists(track.file_path)
    existing_track = db_session.query(Track).filter(Track.id == track.id).first()
    assert existing_track is not None


def test_cleanup_expired_with_play_history(tmp_path, db_session):
    from database.models import PlayHistory
    music_dir = str(tmp_path / "music_fk")
    buf_manager = DiscoveryBufferManager(music_dir=music_dir)
    os.makedirs(buf_manager.buffer_dir, exist_ok=True)
    f_path = os.path.join(buf_manager.buffer_dir, "expired_fk.flac")
    with open(f_path, "wb") as f:
        f.write(b"flac dummy")

    t_expired = Track(
        title="Expired Song",
        artist="FK Artist",
        duration=180.0,
        audio_format="flac",
        file_path=f_path
    )
    db_session.add(t_expired)
    db_session.commit()

    # Добавляем историю прослушивания (FK на t_expired.id)
    history_entry = PlayHistory(track_id=t_expired.id, listened_duration=60.0, completed=True)
    db_session.add(history_entry)
    db_session.commit()

    buf_manager.sync_buffer_files(db_session)
    records = buf_manager.load_history()
    for r in records:
        if r["track_id"] == t_expired.id:
            r["expires_at"] = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    buf_manager.save_history(records)

    # Запускаем очистку
    deleted = buf_manager.cleanup_expired_tracks(db_session)
    assert deleted == 1
    assert not os.path.exists(f_path)
    assert db_session.query(Track).filter(Track.id == t_expired.id).first() is None
