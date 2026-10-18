import os
import time
from streaming.watcher import MusicLibraryWatcher, MusicEventHandler
from database.models import Track


def test_audio_extension_filter():
    """Проверяет фильтрацию только поддерживаемых аудио-расширений."""
    watcher = MusicLibraryWatcher()
    handler = MusicEventHandler(watcher)

    assert handler._is_audio("song.flac") is True
    assert handler._is_audio("track.mp3") is True
    assert handler._is_audio("audio.wav") is True
    assert handler._is_audio("sound.m4a") is True
    assert handler._is_audio("music.ogg") is True

    assert handler._is_audio("playlist.txt") is False
    assert handler._is_audio("song.flac.tmp") is False
    assert handler._is_audio("download.crdownload") is False
    assert handler._is_audio("album.zip") is False


def test_watcher_debounce_and_processing(tmp_path, db_session):
    """
    Проверяет, что Watchdog корректно выдерживает дебаунс-интервал
    и успешно индексирует трек в базе данных после стабилизации файла.
    """
    music_file = tmp_path / "Artist Test - Debounce Track.mp3"
    music_file.write_bytes(b"ID3" + b"\x00" * 200)

    # Фабрика сессий, возвращающая текущую тестовую in-memory сессию
    watcher = MusicLibraryWatcher(
        music_dir=str(tmp_path),
        debounce_seconds=0.1,  # минимальный интервал для быстрого теста
        session_factory=lambda: db_session
    )

    # 1. Добавляем в очередь
    watcher.queue_file(str(music_file))
    assert watcher.status()["pending_files_count"] == 1

    # 2. Немедленная попытка обработки (дебаунс еще не истек)
    processed_immediate = watcher.process_pending_files()
    assert processed_immediate == 0
    assert watcher.status()["pending_files_count"] == 1

    # 3. Выжидаем дебаунс-интервал
    time.sleep(0.15)

    callback_called = []
    watcher.add_callback(lambda p: callback_called.append(p))

    processed_after = watcher.process_pending_files()
    assert processed_after == 1
    assert watcher.status()["pending_files_count"] == 0
    assert len(callback_called) == 1

    # Проверяем, что трек появился в БД
    saved_track = db_session.query(Track).filter(Track.title == "Debounce Track").first()
    assert saved_track is not None
    assert saved_track.artist == "Artist Test"


def test_watcher_api_endpoints(client, auth_headers):
    """Проверяет эндпоинты статуса и управления Watchdog через API."""
    # Получение статуса
    resp = client.get("/api/watcher", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "running" in data
    assert "pending_files_count" in data

    # Остановка
    stop_resp = client.post("/api/watcher/stop", headers=auth_headers)
    assert stop_resp.status_code == 200
    assert stop_resp.json()["status"] == "stopped"


def test_watcher_handles_file_deletion(tmp_path, db_session):
    """Проверяет удаление трека из БД при удалении файла с диска (Watchdog on_deleted)."""
    fake_path = str(tmp_path / "deleted_song.flac")
    track = Track(
        title="Deleted Song",
        artist="Ghost Artist",
        duration=190.0,
        audio_format="flac",
        file_path=fake_path
    )
    db_session.add(track)
    db_session.commit()

    watcher = MusicLibraryWatcher(session_factory=lambda: db_session)
    watcher.handle_deleted_file(fake_path)

    # Проверяем, что трек удален из базы данных
    found = db_session.query(Track).filter(Track.id == track.id).first()
    assert found is None


def test_stream_self_healing_on_missing_file(client, auth_headers, db_session):
    """Проверяет Self-Healing: при попытке стриминга удаленного файла он удаляется из базы."""
    track = Track(
        title="Vanished Song",
        artist="Vanished Artist",
        duration=200.0,
        audio_format="mp3",
        file_path="/non/existent/path/song.mp3"
    )
    db_session.add(track)
    db_session.commit()

    t_id = track.id
    # Запрос стриминга
    resp = client.get(f"/api/stream/{t_id}", headers=auth_headers)
    assert resp.status_code == 404
    assert "автоматически удалена" in resp.json()["detail"] or "отсутствует" in resp.json()["detail"]

    # Проверяем, что трек автоматически удален из базы
    db_session.expire_all()
    found = db_session.query(Track).filter(Track.id == t_id).first()
    assert found is None


def test_cleanup_missing_tracks_endpoint(client, auth_headers, db_session, tmp_path):
    """Проверяет пакетную очистку отсутствующих на диске файлов через /api/tracks/cleanup-missing."""
    real_file = tmp_path / "real.flac"
    real_file.write_bytes(b"real content")

    t_real = Track(
        title="Real Song",
        artist="Real Artist",
        duration=120.0,
        audio_format="flac",
        file_path=str(real_file)
    )
    t_fake = Track(
        title="Fake Song",
        artist="Fake Artist",
        duration=120.0,
        audio_format="flac",
        file_path="/tmp/definitely_not_here.flac"
    )
    db_session.add_all([t_real, t_fake])
    db_session.commit()

    resp = client.post("/api/tracks/cleanup-missing", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert resp.json()["deleted_count"] >= 1

    db_session.expire_all()
    assert db_session.query(Track).filter(Track.id == t_real.id).first() is not None
    assert db_session.query(Track).filter(Track.id == t_fake.id).first() is None


def test_watcher_handles_file_move_without_deleting_history(tmp_path, db_session):
    """
    Проверяет, что при перемещении файла (например, из discovery_buffer в Saved_Discoveries)
    Watchdog обновляет file_path, а не удаляет трек из базы вместе с лайком.
    """
    from database.models import UserReaction

    src_file = tmp_path / "stream_song.mp3"
    src_file.write_bytes(b"content")

    dest_file = tmp_path / "saved_song.mp3"
    dest_file.write_bytes(b"content")

    track = Track(
        title="Moving Song",
        artist="Moving Artist",
        duration=150.0,
        audio_format="mp3",
        file_path=str(src_file)
    )
    db_session.add(track)
    db_session.commit()

    reaction = UserReaction(track_id=track.id, is_liked=True, is_disliked=False)
    db_session.add(reaction)
    db_session.commit()

    watcher = MusicLibraryWatcher(session_factory=lambda: db_session)
    watcher.handle_moved_file(str(src_file), str(dest_file))

    # Проверяем, что трек не был удален
    db_session.expire_all()
    found_track = db_session.query(Track).filter(Track.id == track.id).first()
    assert found_track is not None
    assert found_track.file_path == str(dest_file)

    # Проверяем, что лайк сохранился
    found_rx = db_session.query(UserReaction).filter(UserReaction.track_id == track.id).first()
    assert found_rx is not None
    assert found_rx.is_liked is True


