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

