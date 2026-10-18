import os
from typing import Generator
from fastapi import HTTPException
from fastapi.responses import StreamingResponse


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
