import os
import time
import threading
from typing import Generator, Dict, Any
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

# Реестр активных сессий потокового воспроизведения треков:
# track_id -> {"file_path": str, "last_active": float}
_ACTIVE_STREAMS: Dict[int, Dict[str, Any]] = {}
_ACTIVE_STREAMS_LOCK = threading.Lock()


def mark_track_streaming(track_id: int, file_path: str):
    """Регистрирует активность воспроизведения/стриминга трека."""
    with _ACTIVE_STREAMS_LOCK:
        _ACTIVE_STREAMS[track_id] = {
            "file_path": os.path.abspath(file_path),
            "last_active": time.time()
        }


def is_track_streaming(track_id: int, file_path: str | None = None, ttl_seconds: float = 60.0) -> bool:
    """
    Проверяет, стримится ли трек в данный момент (активность за последние ttl_seconds).
    Если передан file_path — проверяет, что стримится именно этот конкретный файл.
    """
    with _ACTIVE_STREAMS_LOCK:
        info = _ACTIVE_STREAMS.get(track_id)
        if not info:
            return False
        if time.time() - info["last_active"] >= ttl_seconds:
            _ACTIVE_STREAMS.pop(track_id, None)
            return False
        if file_path is not None:
            return os.path.abspath(file_path) == os.path.abspath(info["file_path"])
        return True


def get_active_stream_path(track_id: int, ttl_seconds: float = 60.0) -> str | None:
    """
    Возвращает путь к файлу текущей активной сессии воспроизведения трека.
    Используется для поддержания непрерывности Range-запросов даже в случае фонового авто-апгрейда.
    """
    with _ACTIVE_STREAMS_LOCK:
        info = _ACTIVE_STREAMS.get(track_id)
        if not info:
            return None
        if time.time() - info["last_active"] < ttl_seconds:
            path = info["file_path"]
            if os.path.exists(path):
                return path
        return None


def clear_active_streams():
    """Очищает реестр активных стримов (для изоляции тестов и сброса состояния)."""
    with _ACTIVE_STREAMS_LOCK:
        _ACTIVE_STREAMS.clear()


def schedule_delayed_removal(path: str, delay_seconds: float = 180.0):
    """
    Безопасно удаляет устаревший файл после истечения таймера (когда клиент завершит стриминг).
    Исключает сбои воспроизведения на Windows (WinError 32) и разрывы HTTP Range.
    """
    def _delayed():
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"[DelayedRemoval] Отложенный аудиофайл успешно удален: {path}")
        except Exception as e:
            print(f"[DelayedRemoval] Ошибка отложенного удаления {path}: {e}")

    t = threading.Timer(delay_seconds, _delayed)
    t.daemon = True
    t.start()


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int]:
    """Разбирает HTTP заголовок Range (RFC 7233) с поддержкой суффиксов и защитой от переполнения."""
    try:
        unit, ranges = range_header.split("=", 1)
        if unit.strip() != "bytes":
            raise ValueError("Invalid unit")

        ranges = ranges.strip()
        if ranges.count("-") != 1:
            raise ValueError("Malformed range")

        start_str, end_str = ranges.split("-")
        if not start_str and not end_str:
            raise ValueError("Empty range")

        if start_str and not start_str.isdigit():
            raise ValueError("Non-digit start")

        if end_str and not end_str.isdigit():
            raise ValueError("Non-digit end")

        if start_str and end_str:
            start = int(start_str)
            end = int(end_str)
        elif start_str:
            start = int(start_str)
            end = file_size - 1
        else:
            suffix_len = int(end_str)
            if suffix_len <= 0:
                raise ValueError("Invalid suffix length")
            start = max(0, file_size - suffix_len)
            end = file_size - 1

        if start < 0 or end < 0 or start >= file_size or end >= file_size or start > end:
            raise ValueError("Range out of bounds")

        return start, end
    except Exception:
        raise HTTPException(status_code=416, detail="Requested Range Not Satisfiable")


def file_chunk_generator(path: str, start: int, chunk_len: int, chunk_size: int = 512 * 1024) -> Generator[bytes, None, None]:
    """Потоково отдает байты файла порциями по 512KB без загрузки файла целиком в RAM."""
    try:
        with open(path, "rb") as f:
            f.seek(start)
            bytes_left = chunk_len
            while bytes_left > 0:
                read_bytes = min(chunk_size, bytes_left)
                data = f.read(read_bytes)
                if not data:
                    break
                bytes_left -= len(data)
                yield data
    except (GeneratorExit, ConnectionResetError, BrokenPipeError):
        # Штатное закрытие соединения браузером / веб-плеером
        return
    except Exception as e:
        print(f"[Streamer] Исключение при передаче аудиоданных {path}: {e}")
        return


def stream_audio_file(
    file_path: str,
    range_header: str | None,
    mime_type: str = "audio/flac",
    extra_headers: dict | None = None
) -> StreamingResponse:
    """Обеспечивает HTTP 206 Partial Content для плавной перемотки в веб-плеере."""
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")

    file_size = os.path.getsize(file_path)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": mime_type,
    }
    if extra_headers:
        headers.update(extra_headers)

    if range_header:
        start, end = parse_range_header(range_header, file_size)
        content_length = (end - start) + 1
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        headers["Content-Length"] = str(content_length)
        return StreamingResponse(
            file_chunk_generator(file_path, start, content_length),
            status_code=206,
            headers=headers
        )
    else:
        headers["Content-Length"] = str(file_size)
        return StreamingResponse(
            file_chunk_generator(file_path, 0, file_size),
            status_code=200,
            headers=headers
        )
