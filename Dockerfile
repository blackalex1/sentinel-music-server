# Multi-stage / lightweight Python build for Music Server
FROM python:3.12-slim

# Обновление пакетов ОС и установка аудио-библиотек для декодирования и тегов
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка зависимостей Python с кэшированием слоев
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода сервера
COPY . .

# Создание непривилегированного пользователя и необходимых каталогов
RUN useradd -u 1000 -m appuser \
    && mkdir -p /app/data /music \
    && chown -R appuser:appuser /app /music

# Переменные окружения по умолчанию (переопределяются через docker-compose / .env)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MUSIC_DIR=/music \
    DATABASE_URL=sqlite:////app/data/music_library.db \
    HOST=0.0.0.0 \
    PORT=8000 \
    WATCHDOG_ENABLED=true \
    WATCHDOG_DEBOUNCE_SECONDS=2.0

EXPOSE 8000 80

# Проверка здоровья контейнера (поддержка HTTP и HTTPS)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/auth/status || curl -f -k https://localhost:8000/api/auth/status || exit 1

USER appuser

# Запуск приложения через main.py с автоматической поддержкой SSL
CMD ["python", "main.py"]
