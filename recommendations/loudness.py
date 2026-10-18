"""
Модуль измерения громкости аудиофайлов по стандарту ITU-R BS.1770 / EBU R128.
Рассчитывает интегральную громкость (Integrated Loudness, LUFS),
динамический диапазон (LRA) и пиковый уровень (True Peak, dBFS),
а также расчетную поправку (gain_db) относительно целевого уровня.
"""

import os
import re
import subprocess
from typing import Dict, Any, Optional

DEFAULT_TARGET_LUFS = -14.0  # Целевой уровень современных стриминговых сервисов
MAX_TRUE_PEAK_DB = -1.0     # Запас по True Peak для предотвращения интерсэмплового клиппинга


def measure_track_loudness(
    file_path: str,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    timeout_seconds: float = 60.0
) -> Optional[Dict[str, float]]:
    """
    Измеряет громкость аудиофайла через ffmpeg с фильтром ebur128.
    Возвращает словарь:
    {
        "loudness_lufs": float,  # например -15.4
        "gain_db": float,        # например +1.4
        "peak_db": float,        # например -6.1
        "lra": float             # например 8.8
    }
    или None при ошибке.
    """
    if not file_path or not os.path.exists(file_path):
        return None

    cmd = [
        "ffmpeg",
        "-nostats",
        "-i", file_path,
        "-filter_complex", "ebur128=peak=true",
        "-f", "null",
        "-"
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        try:
            _, stderr_text = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.communicate(timeout=2.0)
            except Exception:
                pass
            return None

        if "Summary:" not in stderr_text and "Integrated loudness:" not in stderr_text:
            return None

        # Парсим сводку в конце вывода
        i_match = re.search(r"Integrated loudness:\s+I:\s+([-\d.]+)\s+LUFS", stderr_text)
        tp_match = re.search(r"True peak:\s+Peak:\s+([-\d.]+)\s+dBFS", stderr_text)
        lra_match = re.search(r"Loudness range:\s+LRA:\s+([-\d.]+)\s+LU", stderr_text)

        if not i_match:
            return None

        import math
        try:
            raw_lufs = float(i_match.group(1))
            loudness_lufs = raw_lufs if math.isfinite(raw_lufs) else -14.0
        except Exception:
            loudness_lufs = -14.0
        loudness_lufs = max(-70.0, min(0.0, loudness_lufs))

        try:
            raw_peak = float(tp_match.group(1)) if tp_match else -1.0
            peak_db = raw_peak if math.isfinite(raw_peak) else -1.0
        except Exception:
            peak_db = -1.0
        peak_db = max(-70.0, min(0.0, peak_db))

        try:
            raw_lra = float(lra_match.group(1)) if lra_match else 0.0
            lra = raw_lra if math.isfinite(raw_lra) else 0.0
        except Exception:
            lra = 0.0
        lra = max(0.0, min(50.0, lra))

        # Расчет поправки: target - measured
        gain_db = target_lufs - loudness_lufs

        # Защита от интерсэмплового клиппинга (True Peak Protection):
        # Если при добавлении усиления пик превысит MAX_TRUE_PEAK_DB (-1.0 dBFS),
        # то ограничиваем усиление
        if peak_db + gain_db > MAX_TRUE_PEAK_DB:
            gain_db = MAX_TRUE_PEAK_DB - peak_db

        # Разумные границы безопасности поправки: от -20 dB до +15 dB
        gain_db = max(-20.0, min(15.0, gain_db))
        if not math.isfinite(gain_db):
            gain_db = 0.0

        return {
            "loudness_lufs": round(loudness_lufs, 2),
            "gain_db": round(gain_db, 2),
            "peak_db": round(peak_db, 2),
            "lra": round(lra, 2)
        }
    except Exception as e:
        print(f"[Loudness] Ошибка замера громкости для {file_path}: {e}")
        return None
