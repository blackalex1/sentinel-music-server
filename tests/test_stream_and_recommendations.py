import pytest
from recommendations.vibe_engine import cosine_similarity, VibeEngine
from database.models import Track, UserReaction


def test_cosine_similarity_math():
    v1 = [1.0, 2.0, 3.0]
    v2 = [1.0, 2.0, 3.0]
    # Одинаковые векторы
    assert pytest.approx(cosine_similarity(v1, v2), 0.001) == 1.0

    # Противоположные / ортогональные
    v_orth = [-3.0, 0.0, 1.0]  # dot = -3 + 3 = 0
    assert pytest.approx(cosine_similarity(v1, v_orth), 0.001) == 0.0

    # Разная длина
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0
    assert cosine_similarity([], []) == 0.0


def test_vibe_engine_dislike_filtering(db_session):
    # Создаем 2 трека
    t1 = Track(title="Good Song", artist="Artist A", duration=180, audio_format="mp3", file_path="t1.mp3")
    t2 = Track(title="Bad Song", artist="Artist B", duration=180, audio_format="mp3", file_path="t2.mp3")
    db_session.add_all([t1, t2])
    db_session.commit()

    # Ставим дизлайк на t2
    reaction = UserReaction(track_id=t2.id, is_disliked=True, is_liked=False)
    db_session.add(reaction)
    db_session.commit()

    engine = VibeEngine(db_session)
    # Запрашиваем трек для Потока: Bad Song никогда не должен быть выбран
    for _ in range(5):
        next_track = engine.get_next_vibe_track(discovery_ratio=0.0)
        assert next_track is not None
        assert next_track.id == t1.id
        assert next_track.title == "Good Song"


def test_vibe_engine_mood_filters(db_session):
    # Создаем треки с разными настроениями, каждый строго попадает только в свою категорию
    fast_energetic = Track(
        title="Banger", artist="DJ Fast", duration=150, audio_format="flac",
        file_path="fast.flac", bpm=140.0, energy=0.95, valence=0.51, danceability=0.5, loudness_lufs=-5.0
    )
    slow_chill = Track(
        title="Ambient Calm", artist="Lofi Chill", duration=200, audio_format="flac",
        file_path="chill.flac", bpm=75.0, energy=0.2, valence=0.51, danceability=0.3, loudness_lufs=-12.0
    )
    bright_happy = Track(
        title="Sunshine", artist="Sunny Band", duration=180, audio_format="flac",
        file_path="sunny.flac", bpm=95.0, energy=0.85, valence=0.85, danceability=0.7, loudness_lufs=-8.0
    )
    dark_sad = Track(
        title="Rainy Tears", artist="Sad Singer", duration=210, audio_format="flac",
        file_path="sad.flac", bpm=100.0, energy=0.75, valence=0.20, danceability=0.4, loudness_lufs=-8.0
    )
    db_session.add_all([fast_energetic, slow_chill, bright_happy, dark_sad])
    db_session.commit()

    engine = VibeEngine(db_session)

    # 1. Запрос бодрого трека
    track_energy = engine.get_next_vibe_track(mood="energy", discovery_ratio=0.0)
    assert track_energy is not None
    assert track_energy.id == fast_energetic.id

    # 2. Запрос спокойного трека
    track_chill = engine.get_next_vibe_track(mood="chill", discovery_ratio=0.0)
    assert track_chill is not None
    assert track_chill.id == slow_chill.id

    # 3. Запрос радостного трека
    track_happy = engine.get_next_vibe_track(mood="happy", discovery_ratio=0.0)
    assert track_happy is not None
    assert track_happy.id == bright_happy.id

    # 4. Запрос грустного трека
    track_sad = engine.get_next_vibe_track(mood="sad", discovery_ratio=0.0)
    assert track_sad is not None
    assert track_sad.id == dark_sad.id


def test_vibe_engine_anti_repeat_recent_ids(db_session):
    t1 = Track(title="Track 1", artist="Artist 1", duration=180, audio_format="mp3", file_path="t1.mp3")
    t2 = Track(title="Track 2", artist="Artist 2", duration=180, audio_format="mp3", file_path="t2.mp3")
    db_session.add_all([t1, t2])
    db_session.commit()

    engine = VibeEngine(db_session)

    # Если t1 уже в recent_track_ids, двигатель обязан выбрать t2
    next_track = engine.get_next_vibe_track(recent_track_ids=[t1.id], discovery_ratio=0.0)
    assert next_track is not None
    assert next_track.id == t2.id


def test_reaction_endpoint_and_stream_api(client, auth_headers, sample_track):
    # 1. Запрос следующего трека для Потока
    res = client.get("/api/stream/next?mood=default&discovery_ratio=0.0", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["id"] == sample_track.id

    # 2. Установка лайка
    like_res = client.post(f"/api/reaction/{sample_track.id}?is_like=true", headers=auth_headers)
    assert like_res.status_code == 200
    assert like_res.json()["is_liked"] is True
    assert like_res.json()["is_disliked"] is False

    # 3. Смена на дизлайк: лайк должен автоматически сброситься
    dislike_res = client.post(f"/api/reaction/{sample_track.id}?is_like=false", headers=auth_headers)
    assert dislike_res.status_code == 200
    assert dislike_res.json()["is_liked"] is False
    assert dislike_res.json()["is_disliked"] is True


def test_analytics_endpoints(client, auth_headers, sample_track):
    # Статус аналитики
    res = client.get("/api/stream/analytics/status", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "total_tracks" in data
    assert "moods" in data
    assert "progress_percent" in data


def test_discovery_delivers_full_unplayed_tracks(db_session):
    from recommendations.discovery import discovery_engine
    # Создаем трек в библиотеке
    unplayed = Track(
        title="Unexplored Masterpiece",
        artist="Underground Artist",
        duration=240.0,
        audio_format="flac",
        file_path="/music/unexplored.flac",
        bpm=128.0,
        energy=0.8,
        valence=0.7
    )
    db_session.add(unplayed)
    db_session.commit()

    cand = discovery_engine.get_discovery_candidate(db_session, mood="energy")
    assert cand is not None
    assert cand["is_discovery"] is True
    assert cand["id"] == unplayed.id
    assert cand["duration"] == 240.0
    assert cand["audio_format"] == "flac"
    assert cand["discovery_reason"] == "Открытие из вашей коллекции"


def test_discovery_import_endpoint(client, auth_headers, monkeypatch):
    from unittest.mock import AsyncMock
    from plugin_system.manager import plugin_manager
    mock_import = AsyncMock(return_value=True)
    monkeypatch.setattr(plugin_manager, "request_track_import", mock_import)

    # Тест вызова импорта через API
    res = client.post(
        "/api/stream/discovery/import",
        json={"artist": "Test Artist", "title": "Test Title"},
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "queued"
    assert data["artist"] == "Test Artist"
    assert data["title"] == "Test Title"
    mock_import.assert_awaited_once_with("Test Artist", "Test Title")


def test_library_analyzer_worker_progress(db_session):
    from recommendations.analyzer import LibraryAnalyzer
    from database.db import SessionLocal
    # Создаем 3 неразмеченных трека
    track_ids = []
    for i in range(3):
        t = Track(
            title=f"Unanalyzed {i}",
            artist=f"Artist {i}",
            duration=120.0,
            audio_format="mp3",
            file_path=f"/nonexistent/path_{i}.mp3",
            bpm=None,
            energy=None,
            valence=None,
            loudness_lufs=None
        )
        db_session.add(t)
        db_session.flush()
        track_ids.append(t.id)
    db_session.commit()

    analyzer = LibraryAnalyzer(session_factory=SessionLocal)
    for tid in track_ids:
        analyzer._process_single_track(tid)

    with SessionLocal() as verify_db:
        status = analyzer.get_status(verify_db)
        assert status["analyzed_tracks"] >= 3
        for tid in track_ids:
            refreshed = verify_db.query(Track).filter(Track.id == tid).first()
            assert refreshed.bpm is not None
            assert refreshed.energy is not None
            assert refreshed.valence is not None
            assert refreshed.loudness_lufs is not None


def test_stream_capability_and_preview_fallback(client, auth_headers, db_session, monkeypatch):
    """Проверяет эндпоинт /api/stream/capability и отдачу 30с Deezer демо при отсутствии плагинов скачивания."""
    from plugin_system.manager import plugin_manager
    from recommendations.discovery import discovery_engine

    # 1. Проверяем эндпоинт capability
    res = client.get("/api/stream/capability", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "has_ingestion_plugins" in data
    assert "library_tracks_count" in data
    assert data["preview_fallback"] is True

    # 2. Мокаем отсутствие плагинов скачивания
    monkeypatch.setattr(plugin_manager, "has_ingestion_plugins", lambda: False)

    # Заполняем кэш кандидатов Deezer с отрицательными ID
    discovery_engine._cache_candidates = [
        {
            "id": -1001,
            "title": "Deezer Demo Track",
            "artist": "Deezer Artist",
            "duration": 30.0,
            "preview_url": "https://cdns-preview.deezer.com/stream.mp3",
            "file_path": "https://cdns-preview.deezer.com/stream.mp3",
            "is_discovery": True,
            "discovery_reason": "Top Hits"
        }
    ]

    cand = discovery_engine.get_discovery_candidate(db_session, allow_preview_fallback=True)
    assert cand is not None
    assert cand["id"] == -1001
    assert cand["is_preview"] is True
    assert "30с демо" in cand["discovery_reason"]
    assert cand["preview_url"] == "https://cdns-preview.deezer.com/stream.mp3"
