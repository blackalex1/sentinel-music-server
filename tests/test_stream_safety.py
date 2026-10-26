import os
import time
from database.models import Track, UserReaction
from streaming.streamer import (
    mark_track_streaming,
    is_track_streaming,
    get_active_stream_path,
    clear_active_streams
)
from streaming.scanner import scan_single_file
from streaming.watcher import MusicLibraryWatcher


def test_active_stream_tracking(tmp_path):
    clear_active_streams()
    fake_path = str(tmp_path / "song.flac")

    assert is_track_streaming(100) is False
    assert get_active_stream_path(100) is None

    mark_track_streaming(100, fake_path)

    assert is_track_streaming(100) is True
    assert is_track_streaming(100, file_path=fake_path) is True
    assert is_track_streaming(100, file_path="other.flac") is False

    # С малым TTL активность истекает после небольшой паузы
    time.sleep(0.02)
    assert is_track_streaming(100, ttl_seconds=0.01) is False


def test_stream_path_auto_recovery_on_move(client, auth_headers, db_session, tmp_path, monkeypatch):
    """
    Проверяет самовосстановление пути в /api/stream/{track_id},
    когда файл переместился в Saved_Discoveries (например, после нажатия «Мне нравится»).
    """
    clear_active_streams()
    monkeypatch.setenv("MUSIC_DIR", str(tmp_path))

    buffer_dir = tmp_path / "discovery_buffer"
    buffer_dir.mkdir(parents=True, exist_ok=True)
    saved_dir = tmp_path / "Saved_Discoveries"
    saved_dir.mkdir(parents=True, exist_ok=True)

    filename = "Artist - Discovery Song.mp3"
    old_path = buffer_dir / filename
    new_path = saved_dir / filename

    # Файл переместился в Saved_Discoveries
    new_path.write_bytes(b"ID3" + b"\x00" * 1024)

    # В базе данных старый путь еще указывает на discovery_buffer
    track = Track(
        title="Discovery Song",
        artist="Artist",
        duration=180.0,
        audio_format="mp3",
        bitrate=320,
        file_size=1027,
        file_path=str(old_path)
    )
    db_session.add(track)
    db_session.commit()
    t_id = track.id

    # GET /api/stream/{track.id} должен автоматически обнаружить файл в Saved_Discoveries
    res = client.get(f"/api/stream/{t_id}", headers=auth_headers)
    assert res.status_code == 200

    # Путь в БД должен быть автоматически обновлен
    updated_track = db_session.query(Track).filter(Track.id == t_id).first()
    assert updated_track is not None
    assert updated_track.file_path == str(new_path)


def test_watcher_protects_actively_streaming_track(tmp_path, db_session):
    """
    Проверяет, что Watchdog не удаляет трек из БД при событии on_deleted,
    если этот файл в данный момент активно воспроизводится.
    """
    clear_active_streams()
    audio_file = tmp_path / "stream_protect.flac"
    # Файл физически отсутствует (удален)
    fake_path = str(audio_file)

    track = Track(
        title="Protected Track",
        artist="DJ Safe",
        duration=210.0,
        audio_format="flac",
        file_path=fake_path
    )
    db_session.add(track)
    db_session.commit()
    db_session.refresh(track)

    # Регистрируем трек как активно играющий
    mark_track_streaming(track.id, fake_path)

    watcher = MusicLibraryWatcher(session_factory=lambda: db_session)
    watcher.handle_deleted_file(fake_path)

    # Трек НЕ должен быть удален из БД, так как стриминг активен
    found = db_session.query(Track).filter(Track.id == track.id).first()
    assert found is not None
    assert found.title == "Protected Track"


def test_scanner_delays_removal_for_streaming_track(tmp_path, db_session, monkeypatch):
    """
    Проверяет, что при обновлении качества трека сканером, старый файл
    не удаляется немедленно, если он прямо сейчас воспроизводится пользователем.
    """
    clear_active_streams()
    saved_dir = tmp_path / "Saved_Discoveries"
    saved_dir.mkdir(parents=True, exist_ok=True)

    old_mp3 = saved_dir / "Upgraded - Song.mp3"
    old_mp3.write_bytes(b"dummy mp3 content")

    track = Track(
        title="Song",
        artist="Upgraded",
        duration=180.0,
        audio_format="mp3",
        bitrate=320,
        file_size=5_000_000,
        file_path=str(old_mp3)
    )
    db_session.add(track)
    db_session.commit()

    reaction = UserReaction(track_id=track.id, is_liked=True, is_disliked=False)
    db_session.add(reaction)
    db_session.commit()

    # Помечаем old_mp3 как активно играющий
    mark_track_streaming(track.id, str(old_mp3))

    new_flac = saved_dir / "Upgraded - Song.flac"
    new_flac.write_bytes(b"dummy flac content")

    def mock_extract(path):
        if "flac" in path:
            return {
                "title": "Song",
                "artist": "Upgraded",
                "album": "HQ Album",
                "year": 2026,
                "duration": 180.0,
                "audio_format": "flac",
                "bitrate": 900,
                "file_size": 20_000_000,
                "file_path": str(new_flac),
                "lyrics_synced": None
            }
        return None

    monkeypatch.setattr("streaming.scanner.extract_metadata", mock_extract)

    scan_single_file(str(new_flac), db_session)

    # Старый файл не должен быть удален немедленно, так как стриминг активен
    assert os.path.exists(old_mp3)
