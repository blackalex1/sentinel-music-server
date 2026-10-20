import os
import sys
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Добавляем корневую директорию сервера в sys.path
SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from database.db import Base, get_db
from database.models import User, SessionToken, Track
from database.search_index import init_search_index
from core.config import settings
from core.security import hash_password, generate_session_token
from main import app

import tempfile

# Для тестов отключаем автогенерацию и фоновые процессы, взаимодействующие с сервером
settings.AUTO_GENERATE_ADMIN = False
settings.WATCHDOG_ENABLED = False
TEST_DATA_DIR = tempfile.mkdtemp(prefix="sentinel_test_data_")
settings.DATA_DIR = TEST_DATA_DIR
TEST_MUSIC_DIR = tempfile.mkdtemp(prefix="sentinel_test_music_")
settings.MUSIC_DIR = TEST_MUSIC_DIR

# Защита от запуска фоновых воркеров во время тестов
from recommendations.buffer_manager import discovery_buffer_manager
discovery_buffer_manager.start_worker = lambda: None

from streaming.watcher import music_watcher
music_watcher.start = lambda *args, **kwargs: False

# Тестовая база данных (изолированная тестовая БД)
_base_db = os.getenv("DATABASE_URL")
if _base_db and "music_db" in _base_db:
    _default_test_url = _base_db.replace("music_db", "music_test_db")
elif _base_db:
    _default_test_url = _base_db
else:
    _default_test_url = "sqlite:///./data/test_music.db"

TEST_DB_URL = os.getenv("TEST_DATABASE_URL", _default_test_url)
test_engine = create_engine(
    TEST_DB_URL,
    pool_pre_ping=True if not TEST_DB_URL.startswith("sqlite") else False
)

@event.listens_for(test_engine, "connect")
def _set_sqlite_unicode_lower(dbapi_connection, connection_record):
    if hasattr(dbapi_connection, "create_function"):
        try:
            dbapi_connection.create_function("lower", 1, lambda s: s.lower() if s is not None else None)
        except Exception:
            pass

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

import database.db as _db_mod
import api.remote as _remote_mod
import api.tracks as _tracks_mod
_db_mod.SessionLocal = TestingSessionLocal
_remote_mod.SessionLocal = TestingSessionLocal
_tracks_mod.SessionLocal = TestingSessionLocal



@pytest.fixture(autouse=True)
def mock_plugin_network_and_ingestion(monkeypatch):
    """
    Глобальная изоляция тестовой среды:
    Предотвращает реальные сетевые запросы и загрузку треков в фонотеку во время тестов.
    """
    from unittest.mock import AsyncMock
    from plugin_system.manager import plugin_manager


    monkeypatch.setattr(plugin_manager, "request_track_import", AsyncMock(return_value=True))
    monkeypatch.setattr(plugin_manager, "download_selected_candidate", AsyncMock(return_value=True))



@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Однократная инициализация схемы и расширений на тестовую сессию."""
    with test_engine.connect() as conn:
        if test_engine.dialect.name == "postgresql":
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector;")
            conn.commit()
    Base.metadata.create_all(bind=test_engine)
    init_search_index(test_engine)
    yield
    try:
        with test_engine.connect() as conn:
            if test_engine.dialect.name == "postgresql":
                conn.exec_driver_sql("""
                    TRUNCATE TABLE play_history, user_reactions, playlist_tracks, playlists, session_tokens, users, tracks CASCADE;
                """)
                conn.commit()
            else:
                for table in reversed(Base.metadata.sorted_tables):
                    conn.execute(table.delete())
                conn.commit()
    except Exception:
        pass


@pytest.fixture(scope="function")
def db_session():
    """Создает изолированную сессию БД на каждый тест и быстро очищает данные."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        with test_engine.connect() as conn:
            if test_engine.dialect.name == "postgresql":
                conn.exec_driver_sql("""
                    TRUNCATE TABLE play_history, user_reactions, playlist_tracks, playlists, session_tokens, users, tracks CASCADE;
                """)
                conn.commit()
            else:
                for table in reversed(Base.metadata.sorted_tables):
                    conn.execute(table.delete())
                conn.commit()


@pytest.fixture(scope="function")
def client(db_session, tmp_path):
    """Тестовый HTTP-клиент FastAPI с подменой зависимости get_db и изоляцией кэша обложек."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        from plugin_system.manager import plugin_manager
        modified_plugins = []
        for plugin in getattr(plugin_manager, "plugins", []):
            if hasattr(plugin, "cache_dir"):
                orig_cache = getattr(plugin, "cache_dir", None)
                test_cache = str(tmp_path / "covers_cache")
                os.makedirs(test_cache, exist_ok=True)
                plugin.cache_dir = test_cache
                modified_plugins.append((plugin, orig_cache))
        try:
            yield test_client
        finally:
            for plugin, orig_cache in modified_plugins:
                if orig_cache is not None:
                    plugin.cache_dir = orig_cache
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_user_and_token(db_session):
    """Создает или использует существующего тестового пользователя и сессионный токен."""
    user = db_session.query(User).filter(User.username == "testuser").first()
    if not user:
        salt, p_hash = hash_password("secret123")
        user = User(username="testuser", password_hash=p_hash, salt=salt, is_admin=True)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

    token = generate_session_token()
    session = SessionToken(token=token, user_id=user.id, device_name="Test Device")
    db_session.add(session)
    db_session.commit()

    return user, token


@pytest.fixture(scope="function")
def auth_headers(auth_user_and_token):
    """Возвращает валидные заголовки авторизации Bearer."""
    _, token = auth_user_and_token
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def sample_track(db_session, tmp_path):
    """Создает тестовый аудиофайл и запись трека в БД."""
    dummy_audio = tmp_path / "test_song.mp3"
    dummy_audio.write_bytes(b"ID3" + b"\x00" * 1024)  # 1 КБ фиктивного аудио

    track = Track(
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        year=2026,
        duration=180.5,
        audio_format="mp3",
        bitrate=320,
        file_size=1027,
        file_path=str(dummy_audio)
    )
    db_session.add(track)
    db_session.commit()
    db_session.refresh(track)
    return track
