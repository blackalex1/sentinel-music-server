import os
import sys

# Принудительная кодировка UTF-8 для консоли (предотвращает краш cp1251 charmap на Unicode/японских символах в тегах треков)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import settings
from database.db import engine, Base, SessionLocal
from core.bootstrap import bootstrap_admin_user
from plugin_system.manager import plugin_manager
from streaming.watcher import music_watcher
from database.search_index import init_search_index
from api import api_router

# Автоматическое создание схемы БД при старте
try:
    Base.metadata.create_all(bind=engine)
    init_search_index(engine)
except Exception:
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом сервера, плагинов, фонового Watchdog и учетных данных."""
    # Автоматическая миграция колонок нормализации громкости EBU R128
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE tracks ADD COLUMN IF NOT EXISTS loudness_lufs FLOAT, ADD COLUMN IF NOT EXISTS gain_db FLOAT, ADD COLUMN IF NOT EXISTS peak_db FLOAT, ADD COLUMN IF NOT EXISTS is_discovery BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tracks_is_discovery ON tracks (is_discovery);"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_devices (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    device_id VARCHAR NOT NULL,
                    name VARCHAR DEFAULT 'Компьютер',
                    device_type VARCHAR DEFAULT 'player',
                    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.commit()
    except Exception as e:
        pass

    # Автоматическая генерация учетных данных администратора при первом старте (Zero Hardcode)
    if settings.AUTO_GENERATE_ADMIN:
        credentials_file = os.path.join(settings.DATA_DIR, settings.CREDENTIALS_FILE)
        with SessionLocal() as db:
            bootstrap_admin_user(db, credentials_path=credentials_file)

    count = plugin_manager.load_plugins()
    print(f"[Server] Активно расширений и плагинов: {count}")
    await plugin_manager.startup({"engine": engine})

    if settings.WATCHDOG_ENABLED and os.path.exists(settings.MUSIC_DIR):
        music_watcher.start(
            music_dir=settings.MUSIC_DIR,
            debounce_seconds=settings.WATCHDOG_DEBOUNCE_SECONDS
        )

    # Фоновая очистка фантомных записей (файлы которых отсутствуют на диске)
    try:
        from streaming.scanner import cleanup_missing_tracks
        with SessionLocal() as db:
            cleaned = cleanup_missing_tracks(settings.MUSIC_DIR, db)
            if cleaned > 0:
                print(f"[Server Startup] Очищено фантомных треков: {cleaned}")
    except Exception as e:
        print(f"[Server Startup] Очистка отсутствующих треков: {e}")

    # Автоматическое фоновое сканирование новых треков при старте
    import asyncio
    async def run_startup_scan():
        await asyncio.sleep(1)
        try:
            from streaming.scanner import scan_directory
            def do_scan():
                with SessionLocal() as db:
                    return scan_directory(settings.MUSIC_DIR, db)
            added = await asyncio.to_thread(do_scan)
            if added > 0:
                print(f"[Server Startup] Автосканирование завершено: добавлено {added} новых треков")
        except Exception as e:
            print(f"[Server Startup] Ошибка автосканирования: {e}")

    asyncio.create_task(run_startup_scan())

    # Запуск фонового воркера автономного буфера новинок (Discovery Buffer & TTL Retention)
    from recommendations.buffer_manager import discovery_buffer_manager
    discovery_buffer_manager.session_factory = SessionLocal
    discovery_buffer_manager.start_worker()

    try:
        yield
    finally:
        discovery_buffer_manager.stop_worker()
        music_watcher.stop()
        await plugin_manager.shutdown()


app = FastAPI(
    title="Self-Hosted Music Service API",
    version="1.0.0",
    lifespan=lifespan
)

# Безопасная настройка CORS для веб-клиента, локальной сети (LAN), мобильного приложения и Tauri Desktop
allowed_origins_raw = getattr(settings, "ALLOWED_ORIGINS", "") or os.getenv("ALLOWED_ORIGINS", "")
if allowed_origins_raw.strip():
    cors_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
else:
    cors_origins = [
        "http://localhost",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
        "tauri://localhost",
        "https://tauri.localhost"
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Добавляет базовые защитные HTTP-заголовки к ответам сервера и предотвращает устаревание статики."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Для интерфейсных файлов отключаем агрессивный кэш браузера, чтобы обновления применялись сразу
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"

    return response

# Подключение модульного API роутера
app.include_router(api_router, prefix="/api")

# Монтирование модульных интерфейсов плагинов (/plugins/<name>/...)
plugin_manager.mount_plugin_assets(app)

# Динамическое монтирование API роутеров активных плагинов
plugin_manager.mount_plugin_routers(app)

# Подключение фронтенда (Web / Tauri WebView)
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(frontend_dir):
    from fastapi.responses import FileResponse, RedirectResponse

    @app.api_route("/login", methods=["GET", "HEAD"], include_in_schema=False)
    async def login_page():
        login_path = os.path.join(frontend_dir, "login.html")
        if os.path.exists(login_path):
            return FileResponse(login_path)
        return RedirectResponse(url="/")

    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    ssl_cert = os.path.join(settings.DATA_DIR, "cert.pem")
    ssl_key = os.path.join(settings.DATA_DIR, "key.pem")
    ssl_opts = {}
    if os.path.exists(ssl_cert) and os.path.exists(ssl_key):
        print(f"[Server] Обнаружен SSL-сертификат: запуск по HTTPS на порту {settings.PORT}")
        ssl_opts["ssl_certfile"] = ssl_cert
        ssl_opts["ssl_keyfile"] = ssl_key

    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True, **ssl_opts)
