import os
import pytest
from streaming.scanner import scan_directory
from database.models import Track


def test_scan_directory_and_avoid_duplicates(tmp_path, db_session):
    # Создаем фиктивные файлы в тестовой директории
    song1 = tmp_path / "artist1 - song1.mp3"
    song1.write_bytes(b"ID3" + b"\x00" * 512)

    song2 = tmp_path / "artist2 - song2.flac"
    song2.write_bytes(b"fLaC" + b"\x00" * 512)

    # Неподдерживаемый файл (должен игнорироваться)
    ignore_file = tmp_path / "readme.txt"
    ignore_file.write_text("Hello world", encoding="utf-8")

    # 1. Первое сканирование: должно найти 2 трека
    added = scan_directory(str(tmp_path), db_session)
    assert added == 2
    assert db_session.query(Track).count() == 2

    # 2. Повторное сканирование той же папки: должно вернуть 0 (дубликаты не создаются)
    added_again = scan_directory(str(tmp_path), db_session)
    assert added_again == 0
    assert db_session.query(Track).count() == 2


def test_scan_single_file_upgrades_existing_track_and_removes_old_file(tmp_path, db_session, monkeypatch):
    """
    Проверяет сценарий лайка из потока:
    1. Трек добавлен как MP3 в Saved_Discoveries (ID 1).
    2. Позже скачивается FLAC версия того же трека.
    3. Сканер обновляет существующий трек до FLAC, не создает дубликат и удаляет старый MP3.
    """
    from streaming.scanner import scan_single_file
    from database.models import UserReaction

    saved_dir = tmp_path / "Saved_Discoveries"
    saved_dir.mkdir(parents=True, exist_ok=True)

    old_mp3 = saved_dir / "T-Fest - Song.mp3"
    old_mp3.write_bytes(b"dummy mp3 content")

    track = Track(
        title="Song",
        artist="T-Fest",
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

    # Скачивается FLAC файл с другим именем (например, с префиксом треклиста из P2P)
    new_flac = saved_dir / "02. T-Fest - Song.flac"
    new_flac.write_bytes(b"dummy flac content")

    # Мокаем extract_metadata для new_flac
    def mock_extract(path):
        if "flac" in path:
            return {
                "title": "Song",
                "artist": "T-Fest",
                "album": "Madonnina",
                "year": 2024,
                "duration": 182.0,
                "audio_format": "flac",
                "bitrate": 930,
                "file_size": 25_000_000,
                "file_path": str(new_flac),
                "lyrics_synced": None
            }
        return None

    monkeypatch.setattr("streaming.scanner.extract_metadata", mock_extract)

    # Сканируем новый FLAC файл
    result_track = scan_single_file(str(new_flac), db_session)

    assert result_track is not None
    # ID трека сохранился (тот же самый трек, не дубликат!)
    assert result_track.id == track.id
    assert db_session.query(Track).count() == 1

    # Метаданные обновлены до FLAC
    assert result_track.audio_format == "flac"
    assert result_track.bitrate == 930
    assert result_track.album == "Madonnina"
    assert result_track.file_path == str(new_flac)

    # Старый MP3 файл был удален с диска
    assert not os.path.exists(str(old_mp3))
    # Новый FLAC файл существует
    assert os.path.exists(str(new_flac))

    # Лайк сохранился
    rx = db_session.query(UserReaction).filter(UserReaction.track_id == track.id).first()
    assert rx is not None
    assert rx.is_liked is True

