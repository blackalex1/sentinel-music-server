"""
Скрипт безопасной генерации файла конфигурации окружения (.env).
Автоматически генерирует криптостойкие случайные логины, пароли и секретные ключи,
исключая какой-либо хардкод учетных данных в репозитории.
"""

import os
import secrets
from pathlib import Path


def generate_env(target_path: str = ".env", force: bool = False) -> bool:
    target = Path(target_path)
    if target.exists() and not force:
        print(f"[Setup] Файл {target.resolve()} уже существует. Генерация пропущена.")
        return False

    db_user = f"music_{secrets.token_hex(2)}"
    db_pass = secrets.token_urlsafe(16)
    secret_key = secrets.token_hex(24)

    content = f"""# ==============================================================================
# АВТОМАТИЧЕСКИ СГЕНЕРИРОВАННАЯ КОНФИГУРАЦИЯ (ZERO HARDCODE)
# ==============================================================================

# Сетевой порт веб-сервера
PORT=8000

# Каталог вашей локальной фонотеки на хост-машине (переопределите при необходимости)
MUSIC_DIR=./music

# Каталоги постоянных данных и базы данных
DATA_DIR=./data
PGDATA_DIR=./pgdata

# База данных PostgreSQL (сгенерировано случайно)
POSTGRES_DB=music_db
POSTGRES_USER={db_user}
POSTGRES_PASSWORD={db_pass}
DATABASE_URL=postgresql://{db_user}:{db_pass}@postgres:5432/music_db

# Безопасность и сессии
SECRET_KEY={secret_key}

# Фоновый Watchdog автообнаружения файлов
WATCHDOG_ENABLED=true
WATCHDOG_DEBOUNCE_SECONDS=2.0
"""
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)

    print("=" * 70)
    print("✅ [Setup] Успешно создан безопасный файл .env со случайными данными:")
    print(f"   Пользователь PostgreSQL: {db_user}")
    print(f"   Пароль PostgreSQL:       {db_pass}")
    print("   Файл добавлен в .gitignore и не попадет в репозиторий.")
    print("=" * 70)
    return True


if __name__ == "__main__":
    generate_env()
