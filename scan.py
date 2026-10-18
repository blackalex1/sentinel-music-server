import os
import sys
from database.db import SessionLocal
from streaming.scanner import scan_directory

music_dir = sys.argv[1] if len(sys.argv) > 1 else "/music"
print(f"[Scanner] Сканирование директории {music_dir}...")
db = SessionLocal()
count = scan_directory(music_dir, db)
print(f"[Scanner] Сканирование завершено. Добавлено новых треков: {count}")
db.close()
