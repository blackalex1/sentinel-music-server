import pytest


def test_playlist_crud_lifecycle(client, auth_headers, sample_track):
    # 1. Создание нового плейлиста
    create_res = client.post("/api/playlists", headers=auth_headers, json={
        "title": "Мой Любимый Рок",
        "description": "Лучшие треки для поездок"
    })
    assert create_res.status_code == 200
    data = create_res.json()
    assert data["status"] == "created"
    playlist_id = data["playlist_id"]

    # 2. Получение списка плейлистов
    list_res = client.get("/api/playlists", headers=auth_headers)
    assert list_res.status_code == 200
    playlists = list_res.json()
    assert len(playlists) == 1
    assert playlists[0]["id"] == playlist_id
    assert playlists[0]["track_count"] == 0

    # 3. Добавление трека в плейлист
    add_res = client.post(f"/api/playlists/{playlist_id}/tracks", headers=auth_headers, json={
        "track_id": sample_track.id
    })
    assert add_res.status_code == 200
    assert add_res.json()["status"] == "added"

    # Повторное добавление того же трека не дублирует позицию
    dup_res = client.post(f"/api/playlists/{playlist_id}/tracks", headers=auth_headers, json={
        "track_id": sample_track.id
    })
    assert dup_res.status_code == 200
    assert dup_res.json()["status"] == "already_exists"

    # 4. Просмотр состава плейлиста
    detail_res = client.get(f"/api/playlists/{playlist_id}", headers=auth_headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["track_count"] == 1
    assert len(detail["tracks"]) == 1
    assert detail["tracks"][0]["id"] == sample_track.id
    assert detail["tracks"][0]["title"] == "Test Song"

    # 5. Удаление трека из плейлиста
    del_track_res = client.delete(f"/api/playlists/{playlist_id}/tracks/{sample_track.id}", headers=auth_headers)
    assert del_track_res.status_code == 200
    assert del_track_res.json()["status"] == "removed"

    # Проверка, что трек удален
    check_empty = client.get(f"/api/playlists/{playlist_id}", headers=auth_headers).json()
    assert check_empty["track_count"] == 0

    # 6. Удаление самого плейлиста
    del_pl_res = client.delete(f"/api/playlists/{playlist_id}", headers=auth_headers)
    assert del_pl_res.status_code == 200
    assert del_pl_res.json()["status"] == "deleted"

    # Теперь запрос плейлиста дает 404
    assert client.get(f"/api/playlists/{playlist_id}", headers=auth_headers).status_code == 404


def test_playlist_error_cases(client, auth_headers):
    """Проверяет обработку ошибок 404 для несуществующих плейлистов и треков."""
    assert client.get("/api/playlists/99999", headers=auth_headers).status_code == 404
    assert client.post("/api/playlists/99999/tracks", json={"track_id": 1}, headers=auth_headers).status_code == 404
    assert client.delete("/api/playlists/99999/tracks/1", headers=auth_headers).status_code == 404
    assert client.delete("/api/playlists/99999", headers=auth_headers).status_code == 404


def test_smart_playlists_api(client, auth_headers, db_session):
    """Проверяет работу умных динамических плейлистов (Forgotten Favorites, Heavy Rotation, Radio)."""
    import datetime
    from database.models import Track, PlayHistory, UserReaction, utc_now

    t1 = Track(title="Old Favorite", artist="Classic Band", duration=200, audio_format="flac", file_path="t1.flac", bpm=120.0, energy=0.7)
    t2 = Track(title="Heavy Hit", artist="Modern Star", duration=180, audio_format="mp3", file_path="t2.mp3", bpm=125.0, energy=0.8)
    t3 = Track(title="Radio Neighbor", artist="Classic Band", duration=195, audio_format="flac", file_path="t3.flac", bpm=122.0, energy=0.72)
    db_session.add_all([t1, t2, t3])
    db_session.commit()

    # t1: лайкнут, но не играл > 40 дней
    db_session.add(UserReaction(track_id=t1.id, is_liked=True))
    old_time = utc_now() - datetime.timedelta(days=45)
    db_session.add(PlayHistory(track_id=t1.id, played_at=old_time, listened_duration=200.0, completed=True))

    # t2: многократно играл за последние 5 дней (Heavy Rotation)
    for _ in range(5):
        db_session.add(PlayHistory(track_id=t2.id, played_at=utc_now(), listened_duration=180.0, completed=True))

    db_session.commit()

    # 1. Проверяем Forgotten Favorites
    ff_res = client.get("/api/playlists/smart/forgotten-favorites", headers=auth_headers)
    assert ff_res.status_code == 200
    ff_data = ff_res.json()
    assert ff_data["track_count"] >= 1
    ff_ids = [t["id"] for t in ff_data["tracks"]]
    assert t1.id in ff_ids

    # 2. Проверяем Heavy Rotation
    hr_res = client.get("/api/playlists/smart/heavy-rotation", headers=auth_headers)
    assert hr_res.status_code == 200
    hr_data = hr_res.json()
    assert hr_data["track_count"] >= 1
    assert hr_data["tracks"][0]["id"] == t2.id

    # 3. Проверяем Radio by Track (для t1)
    radio_res = client.get(f"/api/playlists/smart/radio/{t1.id}", headers=auth_headers)
    assert radio_res.status_code == 200
    r_data = radio_res.json()
    assert r_data["track_count"] >= 1
    # Соседний трек той же группы t3 должен быть в топе рекомендаций
    assert r_data["tracks"][0]["id"] == t3.id

