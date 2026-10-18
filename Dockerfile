# Multi-stage / lightweight Python build for Music Server
FROM python:3.12-slim

# Установка системных утилит и аудио-библиотек для декодирования и тегов
RUN apt-get update && apt-get install -y --no-install-recommends \
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

# Создание каталогов для данных и монтирования музыки
RUN mkdir -p /app/data /music

# Переменные окружения по умолчанию (переопределяются через docker-compose / .env)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MUSIC_DIR=/music \
    DATABASE_URL=sqlite:////app/data/music_library.db \
    HOST=0.0.0.0 \
    PORT=8000 \
    WATCHDOG_ENABLED=true \
    WATCHDOG_DEBOUNCE_SECONDS=2.0

EXPOSE 8000

# Проверка здоровья контейнера
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/auth/status || exit 1

# Запуск приложения через uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
