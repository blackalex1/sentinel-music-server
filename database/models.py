from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Index, select, func, case
from sqlalchemy.orm import relationship, column_property, validates
from .db import Base


def utc_now():
    return datetime.now(timezone.utc)


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        Index("idx_tracks_artist_title", "artist", "title"),
        Index("idx_tracks_album", "album"),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    artist = Column(String, index=True, nullable=False)
    album = Column(String, nullable=True)
    year = Column(Integer, nullable=True)
    duration = Column(Float, nullable=False)  # В секундах
    file_path = Column(String, unique=True, nullable=False)
    audio_format = Column(String, default="flac")  # flac, mp3
    bitrate = Column(Integer, nullable=True)  # kbps
    file_size = Column(Integer, default=0, nullable=False)  # bytes

    bpm = Column(Float, nullable=True)
    energy = Column(Float, nullable=True)  # 0.0 - 1.0
    valence = Column(Float, nullable=True)  # 0.0 - 1.0 (Мажорность / Позитивность)
    danceability = Column(Float, nullable=True)  # 0.0 - 1.0
    embedding_json = Column(Text, nullable=True)  # Спектральный вектор признаков

    # Текст песни
    lyrics_synced = Column(Text, nullable=True)  # LRC формат
    lyrics_plain = Column(Text, nullable=True)

    # EBU R128 Нормализация громкости (Loudness Normalization)
    loudness_lufs = Column(Float, nullable=True)  # Интегральная громкость LUFS (-14.0 LUFS стандарт)
    gain_db = Column(Float, nullable=True)        # Поправка громкости в дБ
    peak_db = Column(Float, nullable=True)        # True Peak в dBFS

    # Флаг временного буфера Потока (Discovery Buffer)
    is_discovery = Column(Boolean, default=False, index=True)

    @validates("file_path")
    def validate_file_path(self, key, value):
        if value:
            self.is_discovery = "discovery_buffer" in str(value).lower()
        return value

    created_at = Column(DateTime, default=utc_now, index=True)


class PlayHistory(Base):
    __tablename__ = "play_history"
    __table_args__ = (
        Index("idx_play_history_track_id", "track_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    track_id = Column(Integer, ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    played_at = Column(DateTime, default=utc_now)
    listened_duration = Column(Float, default=0.0)
    completed = Column(Boolean, default=False)
    skipped = Column(Boolean, default=False)


class UserReaction(Base):
    __tablename__ = "user_reactions"

    id = Column(Integer, primary_key=True, index=True)
    track_id = Column(Integer, ForeignKey("tracks.id", ondelete="CASCADE"), unique=True, nullable=False)
    is_liked = Column(Boolean, default=False)
    is_disliked = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


# Вычисляемые свойства реакций для треков:
# Треки в основной фонотеке (вне discovery_buffer) считаются лайкнутыми по умолчанию (is_liked=True).
# Временные треки в discovery_buffer по умолчанию не лайкнуты (is_liked=False), пока пользователь не нажмет лайк.
Track.is_liked = column_property(
    func.coalesce(
        select(UserReaction.is_liked).where(UserReaction.track_id == Track.id).correlate_except(UserReaction).scalar_subquery(),
        case((Track.is_discovery == True, False), else_=True)
    )
)

Track.is_disliked = column_property(
    func.coalesce(
        select(UserReaction.is_disliked).where(UserReaction.track_id == Track.id).correlate_except(UserReaction).scalar_subquery(),
        False
    )
)


class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Связь с треками через ассоциативную таблицу
    items = relationship("PlaylistTrack", back_populates="playlist", cascade="all, delete-orphan", order_by="PlaylistTrack.position")


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"
    __table_args__ = (
        Index("idx_playlist_tracks_playlist_id", "playlist_id"),
        Index("idx_playlist_tracks_track_id", "track_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False)
    track_id = Column(Integer, ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, default=0)
    added_at = Column(DateTime, default=utc_now)

    playlist = relationship("Playlist", back_populates="items")
    track = relationship("Track")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    salt = Column(String, nullable=False)
    is_admin = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

    sessions = relationship("SessionToken", back_populates="user", cascade="all, delete-orphan")
    devices = relationship("UserDevice", back_populates="user", cascade="all, delete-orphan")


class SessionToken(Base):
    __tablename__ = "session_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_name = Column(String, default="Unknown Device")
    created_at = Column(DateTime, default=utc_now)
    expires_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="sessions")


class UserDevice(Base):
    __tablename__ = "user_devices"
    __table_args__ = (
        Index("idx_user_devices_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    device_id = Column(String, index=True, nullable=False)
    name = Column(String, default="Компьютер")
    device_type = Column(String, default="player")  # "player", "remote", "hybrid"
    last_seen_at = Column(DateTime, default=utc_now)

    user = relationship("User", back_populates="devices")

