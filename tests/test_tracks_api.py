import pytest
from database.models import Track


def test_get_tracks_pagination(client, auth_headers, sample_track):
    # Доступ без авторизации -> 401
    assert client.get("/api/tracks").status_code == 401

    # Запрос с валидным токеном
    res = client.get("/api/tracks?limit=10&offset=0", headers=auth_headers)
    assert res.status_code == 200
    tracks = res.json()
    assert len(tracks) == 1
    assert tracks[0]["title"] == "Test Song"
    assert tracks[0]["artist"] == "Test Artist"


def test_get_track_by_id(client, auth_headers, sample_track):
    # Существующий трек
    res = client.get(f"/api/tracks/{sample_track.id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["title"] == "Test Song"

    # Несуществующий трек -> 404
    bad_res = client.get("/api/tracks/99999", headers=auth_headers)
    assert bad_res.status_code == 404


def test_audio_streaming_range_request(client, auth_user_and_token, sample_track):
    _, token = auth_user_and_token

    # 1. Потоковый запрос с Range заголовком (HTTP 206 Partial Content)
    headers = {
        "Authorization": f"Bearer {token}",
        "Range": "bytes=0-511"
    }
    res = client.get(f"/api/stream/{sample_track.id}", headers=headers)
    assert res.status_code == 206
    assert res.headers.get("Accept-Ranges") == "bytes"
    assert res.headers.get("Content-Range") == f"bytes 0-511/{sample_track.file_size}"
    assert len(res.content) == 512

    # 2. Потоковый запрос через query-параметр ?token= (как в <audio> плеере)
    res_query = client.get(
        f"/api/stream/{sample_track.id}?token={token}",
        headers={"Range": "bytes=512-1026"}
    )
    assert res_query.status_code == 206
    assert len(res_query.content) == 515


def test_streaming_missing_file_404(client, auth_headers, db_session):
    from database.models import Track

    # Трек, файл которого отсутствует на диске
    ghost_track = Track(
        title="Ghost Track",
        artist="Ghost Artist",
        duration=120.0,
        audio_format="mp3",
        file_path="C:/non_existent_path/fake_audio.mp3"
    )
    db_session.add(ghost_track)
    db_session.commit()
    db_session.refresh(ghost_track)

    res = client.get(f"/api/stream/{ghost_track.id}", headers=auth_headers)
    assert res.status_code == 404


def test_get_shuffled_tracks(client, auth_headers, sample_track):
    # Тест серверного шаффла
    res = client.get("/api/tracks/shuffle?limit=10", headers=auth_headers)
    assert res.status_code == 200
    tracks = res.json()
    assert isinstance(tracks, list)
    assert len(tracks) >= 1
    assert tracks[0]["title"] == sample_track.title


def test_get_recent_tracks(client, auth_headers, sample_track, db_session):
    from database.models import Track
    import datetime

    # Добавляем второй трек с более новой датой создания
    newer_track = Track(
        title="Newer Track",
        artist="Newer Artist",
        duration=180.0,
        audio_format="mp3",
        file_path="/music/newer.mp3",
        created_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=10)
    )
    db_session.add(newer_track)
    db_session.commit()

    # Запрос недавних треков
    res = client.get("/api/tracks/recent?limit=10", headers=auth_headers)
    assert res.status_code == 200
    recent = res.json()
    assert len(recent) == 2
    # Самый новый трек должен идти первым
    assert recent[0]["title"] == "Newer Track"
    assert recent[1]["title"] == sample_track.title

    # Проверяем сортировку sort=oldest в /api/tracks
    res_old = client.get("/api/tracks?sort=oldest", headers=auth_headers)
    assert res_old.status_code == 200
    tracks_old = res_old.json()
    assert tracks_old[0]["title"] == sample_track.title


def test_tracks_mood_filtering(client, auth_headers, db_session):
    t_energy = Track(title="Fast Jam", artist="DJ Energetic", duration=120, audio_format="mp3", file_path="/fast.mp3", bpm=130.0, energy=0.85)
    t_chill = Track(title="Chill Jam", artist="DJ Calm", duration=120, audio_format="mp3", file_path="/chill.mp3", bpm=80.0, energy=0.2)
    db_session.add_all([t_energy, t_chill])
    db_session.commit()

    # Фильтр по бодрому
    res_energy = client.get("/api/tracks/recent?mood=energy", headers=auth_headers)
    assert res_energy.status_code == 200
    tracks_energy = res_energy.json()
    assert any(t["title"] == "Fast Jam" for t in tracks_energy)
    assert not any(t["title"] == "Chill Jam" for t in tracks_energy)

    # Фильтр по спокойному
    res_chill = client.get("/api/tracks/recent?mood=chill", headers=auth_headers)
    assert res_chill.status_code == 200
    tracks_chill = res_chill.json()
    assert any(t["title"] == "Chill Jam" for t in tracks_chill)
    assert not any(t["title"] == "Fast Jam" for t in tracks_chill)

    # Проверка подсчета треков по настроению (/api/tracks/count?mood=...)
    res_count_energy = client.get("/api/tracks/count?mood=energy", headers=auth_headers)
    assert res_count_energy.status_code == 200
    assert res_count_energy.json()["count"] >= 1

    res_count_chill = client.get("/api/tracks/count?mood=chill", headers=auth_headers)
    assert res_count_chill.status_code == 200
    assert res_count_chill.json()["count"] >= 1

    # Пагинация recent с offset и limit
    res_page = client.get("/api/tracks/recent?mood=energy&limit=1&offset=0", headers=auth_headers)
    assert res_page.status_code == 200
    assert len(res_page.json()) == 1

    # Shuffle с настроением
    res_shuffle = client.get("/api/tracks/shuffle?mood=energy&limit=5", headers=auth_headers)
    assert res_shuffle.status_code == 200
    assert all(t["title"] == "Fast Jam" for t in res_shuffle.json())


def test_delete_track_lifecycle(client, auth_headers, db_session, tmp_path):
    import os
    from database.models import Track, PlayHistory, UserReaction, Playlist, PlaylistTrack

    # Создаем временный файл трека и файл субтитров (.lrc)
    audio_file = tmp_path / "song_to_delete.mp3"
    audio_file.write_bytes(b"dummy mp3 data")
    lrc_file = tmp_path / "song_to_delete.lrc"
    lrc_file.write_text("[00:01.00] Test line", encoding="utf-8")

    # Создаем трек в БД
    track = Track(
        title="Track to Delete",
        artist="Delete Artist",
        duration=180.0,
        audio_format="mp3",
        file_path=str(audio_file),
        file_size=len(b"dummy mp3 data")
    )
    db_session.add(track)
    db_session.commit()
    db_session.refresh(track)
    track_id = track.id

    # Создаем зависимые записи: историю, реакцию, участие в плейлисте
    pl = Playlist(title="Test Pl")
    db_session.add(pl)
    db_session.commit()
    db_session.refresh(pl)

    history = PlayHistory(track_id=track_id, listened_duration=60.0)
    reaction = UserReaction(track_id=track_id, is_liked=True)
    pl_track = PlaylistTrack(playlist_id=pl.id, track_id=track_id)
    db_session.add_all([history, reaction, pl_track])
    db_session.commit()

    # 1. Попытка удаления без авторизации -> 401
    unauth_res = client.delete(f"/api/tracks/{track_id}")
    assert unauth_res.status_code == 401

    # 2. Успешное удаление с авторизацией
    del_res = client.delete(f"/api/tracks/{track_id}?delete_file=true", headers=auth_headers)
    assert del_res.status_code == 200
    data = del_res.json()
    assert data["status"] == "deleted"
    assert data["track_id"] == track_id
    assert data["title"] == "Track to Delete"
    assert data["file_deleted"] is True

    # 3. Файлы на диске удалены
    assert not os.path.exists(str(audio_file))
    assert not os.path.exists(str(lrc_file))

    # 4. Трек больше не находится в БД
    get_res = client.get(f"/api/tracks/{track_id}", headers=auth_headers)
    assert get_res.status_code == 404

    # 5. Зависимые записи в БД очищены
    assert db_session.query(PlayHistory).filter(PlayHistory.track_id == track_id).count() == 0
    assert db_session.query(UserReaction).filter(UserReaction.track_id == track_id).count() == 0
    assert db_session.query(PlaylistTrack).filter(PlaylistTrack.track_id == track_id).count() == 0

    # 6. Повторное удаление того же трека -> 404
    del_404_res = client.delete(f"/api/tracks/{track_id}", headers=auth_headers)
    assert del_404_res.status_code == 404


def test_upload_tracks_lifecycle(client, auth_headers, tmp_path, monkeypatch, db_session):
    import io
    from core.config import settings

    # Направляем загрузку во временную папку тестов
    test_music_dir = tmp_path / "test_music"
    test_music_dir.mkdir()
    monkeypatch.setattr(settings, "MUSIC_DIR", str(test_music_dir))

    # 1. Загрузка без авторизации -> 401
    unauth_res = client.post("/api/tracks/upload", files=[("files", ("song.mp3", b"audio data", "audio/mpeg"))])
    assert unauth_res.status_code == 401

    # 2. Загрузка неподдерживаемого формата
    unsupported_res = client.post(
        "/api/tracks/upload",
        headers=auth_headers,
        files=[("files", ("document.pdf", b"pdf data", "application/pdf"))]
    )
    assert unsupported_res.status_code == 200
    unsup_data = unsupported_res.json()
    assert unsup_data["total_uploaded"] == 0
    assert unsup_data["total_failed"] == 1
    assert "не поддерживается" in unsup_data["failed"][0]["error"]

    # 3. Загрузка валидного аудиофайла (создаем MP3 через сэмпл или байты с ID3)
    sample_mp3_content = b"ID3\x04\x00\x00\x00\x00\x00#TIT2\x00\x00\x00\x0b\x00\x00\x03Uploaded" + (b"\xff\xfb\x90d" * 500)
    upload_res = client.post(
        "/api/tracks/upload",
        headers=auth_headers,
        files=[("files", ("My Artist - Uploaded Hit.mp3", sample_mp3_content, "audio/mpeg"))]
    )
    assert upload_res.status_code == 200
    up_data = upload_res.json()
    assert up_data["total_uploaded"] == 1
    assert up_data["total_failed"] == 0
    uploaded_track = up_data["uploaded"][0]
    assert uploaded_track["id"] is not None
    assert uploaded_track["title"] == "Uploaded" or uploaded_track["title"] == "Uploaded Hit"
    assert uploaded_track["audio_format"] == "mp3"

    # 4. Проверяем наличие трека в БД через API
    get_res = client.get(f"/api/tracks/{uploaded_track['id']}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == uploaded_track["id"]


def test_get_duplicates_report(client, auth_headers, db_session, tmp_path):
    # 1. Без авторизации -> 401
    assert client.get("/api/tracks/duplicates").status_code == 401

    # 2. Создаем группу дубликатов: MP3 и FLAC
    track_mp3 = Track(
        title="Breathe",
        artist="The Prodigy",
        duration=240.0,
        audio_format="mp3",
        bitrate=128,
        file_size=3_000_000,
        file_path=str(tmp_path / "breathe.mp3")
    )
    track_flac = Track(
        title="breathe ",  # проверяем нечувствительность к пробелам и регистру
        artist="  the prodigy",
        duration=241.0,
        audio_format="flac",
        bitrate=1000,
        file_size=25_000_000,
        file_path=str(tmp_path / "breathe.flac")
    )
    # Одиночный трек (не должен попасть в отчет)
    track_single = Track(
        title="Firestarter",
        artist="The Prodigy",
        duration=220.0,
        audio_format="mp3",
        bitrate=320,
        file_size=8_000_000,
        file_path=str(tmp_path / "firestarter.mp3")
    )
    db_session.add_all([track_mp3, track_flac, track_single])
    db_session.commit()

    # 3. Запрос отчета
    res = client.get("/api/tracks/duplicates", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["total_groups"] == 1
    assert data["total_extra_tracks"] == 1
    assert data["potential_saved_bytes"] == 3_000_000
    group = data["groups"][0]
    assert group["count"] == 2
    assert len(group["tracks"]) == 2

    # Лучший трек должен быть FLAC
    best = group["tracks"][0]
    worst = group["tracks"][1]
    assert best["id"] == track_flac.id
    assert best["is_best"] is True
    assert best["audio_format"] == "flac"
    assert worst["id"] == track_mp3.id
    assert worst["is_best"] is False

    # 4. Проверка фильтра ?q=
    res_q_found = client.get("/api/tracks/duplicates?q=prodigy", headers=auth_headers)
    assert res_q_found.status_code == 200
    assert res_q_found.json()["total_groups"] == 1

    res_q_empty = client.get("/api/tracks/duplicates?q=nonexistent", headers=auth_headers)
    assert res_q_empty.status_code == 200
    assert res_q_empty.json()["total_groups"] == 0


def test_delete_duplicates_batch(client, auth_headers, db_session, tmp_path):
    file_mp3 = tmp_path / "dup1.mp3"
    file_mp3.write_bytes(b"dummy mp3 data")
    file_flac = tmp_path / "dup2.flac"
    file_flac.write_bytes(b"dummy flac data")

    t1 = Track(
        title="Duplicate Song",
        artist="Duplicate Artist",
        duration=180.0,
        audio_format="mp3",
        file_size=file_mp3.stat().st_size,
        file_path=str(file_mp3)
    )
    t2 = Track(
        title="Duplicate Song",
        artist="Duplicate Artist",
        duration=180.0,
        audio_format="flac",
        file_size=file_flac.stat().st_size,
        file_path=str(file_flac)
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    expected_freed = file_mp3.stat().st_size

    # Удаляем дубликат t1 с физическим файлом
    payload = {
        "track_ids": [t1.id],
        "delete_files": True
    }
    del_res = client.post("/api/tracks/duplicates/delete", json=payload, headers=auth_headers)
    assert del_res.status_code == 200
    resp_data = del_res.json()
    assert resp_data["status"] == "success"
    assert resp_data["deleted_count"] == 1
    assert resp_data["freed_bytes"] == expected_freed

    # Проверяем, что t1 удален из БД и с диска
    assert not file_mp3.exists()
    assert db_session.query(Track).filter(Track.id == t1.id).first() is None

    # t2 остался нетронутым
    assert file_flac.exists()
    assert db_session.query(Track).filter(Track.id == t2.id).first() is not None


def test_resolve_duplicate_group(client, auth_headers, db_session, tmp_path):
    f_keep = tmp_path / "keep.flac"
    f_keep.write_bytes(b"keep this file")
    f_del1 = tmp_path / "del1.mp3"
    f_del1.write_bytes(b"delete 1")
    f_del2 = tmp_path / "del2.mp3"
    f_del2.write_bytes(b"delete 2")

    t_keep = Track(title="Same", artist="Artist", duration=200.0, audio_format="flac", file_size=14, file_path=str(f_keep))
    t_del1 = Track(title="Same", artist="Artist", duration=200.0, audio_format="mp3", file_size=8, file_path=str(f_del1))
    t_del2 = Track(title="Same", artist="Artist", duration=200.0, audio_format="mp3", file_size=8, file_path=str(f_del2))
    db_session.add_all([t_keep, t_del1, t_del2])
    db_session.commit()

    payload = {
        "keep_track_id": t_keep.id,
        "delete_track_ids": [t_del1.id, t_del2.id],
        "delete_files": True
    }
    res = client.post("/api/tracks/duplicates/resolve-group", json=payload, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["deleted_count"] == 2

    # Проверяем файлы и БД
    assert f_keep.exists()
    assert not f_del1.exists()
    assert not f_del2.exists()
    assert db_session.query(Track).filter(Track.id == t_keep.id).first() is not None
    assert db_session.query(Track).filter(Track.id == t_del1.id).first() is None
    assert db_session.query(Track).filter(Track.id == t_del2.id).first() is None


def test_delete_track_not_found(client, auth_headers):
    """Удаление несуществующего трека должно возвращать 404."""
    res = client.delete("/api/tracks/99999", headers=auth_headers)
    assert res.status_code == 404


def test_cleanup_missing_tracks_endpoint(client, auth_headers, db_session, tmp_path):
    """Тест эндпоинта /api/tracks/cleanup-missing."""
    # Создаем трек с несуществующим файлом
    ghost = Track(
        title="Ghost Song",
        artist="Ghost Artist",
        duration=100.0,
        audio_format="mp3",
        file_path=str(tmp_path / "deleted_file.mp3")
    )
    db_session.add(ghost)
    db_session.commit()

    res = client.post("/api/tracks/cleanup-missing", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["deleted_count"] >= 1
    assert db_session.query(Track).filter(Track.id == ghost.id).first() is None


def test_upload_tracks_empty_file_and_empty_list(client, auth_headers):
    """Проверка загрузки пустого файла (0 байт) и пустого списка."""
    # Загрузка файла 0 байт
    res = client.post(
        "/api/tracks/upload",
        files=[("files", ("empty.mp3", b"", "audio/mpeg"))],
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_uploaded"] == 0
    assert data["total_failed"] == 1
    assert "0 байт" in data["failed"][0]["error"]





