import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Централизованная конфигурация сервера.
    Все параметры конфигурируются через переменные окружения или .env файл.
    Никакие IP-адреса и учетные данные не хардкодятся.
    """
    # База данных (по умолчанию локальная SQLite, в продакшене переопределяется через .env на PostgreSQL)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/music_library.db")

    # Каталог фонотеки для стриминга и автосканирования
    MUSIC_DIR: str = os.getenv("MUSIC_DIR", "./music")

    # Сетевые настройки и CORS
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    SERVER_LAN_IP: str | None = os.getenv("SERVER_LAN_IP", None)
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "")

    # Фоновый Watchdog автообнаружения файлов
    WATCHDOG_ENABLED: bool = True
    WATCHDOG_DEBOUNCE_SECONDS: float = 2.0

    # Каталог данных и автогенерация администратора
    DATA_DIR: str = os.getenv("DATA_DIR", "./data")
    AUTO_GENERATE_ADMIN: bool = True
    CREDENTIALS_FILE: str = os.getenv("CREDENTIALS_FILE", "credentials.txt")

    # Автономный буфер Потока (Discovery Buffer)
    STREAM_BUFFER_SIZE: int = int(os.getenv("STREAM_BUFFER_SIZE", "10"))

    # Настройки интеграций (опционально для плагинов)
    EXT_P2P_API_URL: str = os.getenv("EXT_P2P_API_URL", "http://localhost:5030/api/v0")
    EXT_P2P_API_KEY: str = os.getenv("EXT_P2P_API_KEY", "")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
