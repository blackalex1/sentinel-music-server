import os
from core.config import Settings


def test_default_config_safe_values():
    """Проверяет безопасность и корректность конфигурации по умолчанию."""
    settings = Settings()
    assert settings.PORT == 8000
    assert settings.HOST == "0.0.0.0"
    assert settings.WATCHDOG_ENABLED is True
    assert settings.WATCHDOG_DEBOUNCE_SECONDS == 2.0
    # Проверка, что нет утечек приватных IP в значениях по умолчанию
    assert "192.168." not in settings.EXT_P2P_API_URL
    assert "10.0." not in settings.EXT_P2P_API_URL


def test_custom_env_override(monkeypatch):
    """Проверяет переопределение конфигурации через переменные окружения."""
    monkeypatch.setenv("MUSIC_DIR", "/custom/music/path")
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("WATCHDOG_DEBOUNCE_SECONDS", "5.5")
    monkeypatch.setenv("DATABASE_URL", "postgresql://custom_user:pass@localhost:5432/custom_db")

    custom_settings = Settings()
    assert custom_settings.MUSIC_DIR == "/custom/music/path"
    assert custom_settings.PORT == 9999
    assert custom_settings.WATCHDOG_DEBOUNCE_SECONDS == 5.5
    assert custom_settings.DATABASE_URL == "postgresql://custom_user:pass@localhost:5432/custom_db"
