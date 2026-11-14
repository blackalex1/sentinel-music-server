import os
import json
import subprocess
from typing import Dict, Any, List, Optional


def extract_audio_features(file_path: str, offset_seconds: float = 30.0, duration_seconds: float = 30.0) -> Dict[str, Any]:
    """
    Извлекает музыкальные и психоакустические характеристики трека:
    - bpm (Float): темп по автокорреляции огибающей темпа
    - energy (Float, 0.05 - 0.99): плотность и среднеквадратичная громкость (RMS)
    - valence (Float, 0.05 - 0.95): позитивность/мажорность по профилям Крумхансла-Шмуклера
    - danceability (Float, 0.05 - 0.95): танцевальность по регулярности и темпу
    - vector (List[float]): 16-мерный вектор признаков для косинусного сравнения
    """
    try:
        import numpy as np
        from scipy.signal import correlate

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        # 1. Читаем фрагмент в raw float32 PCM через ffmpeg (mono, 22050 Hz)
        cmd = [
            "ffmpeg",
            "-ss", str(offset_seconds),
            "-t", str(duration_seconds),
            "-i", file_path,
            "-f", "f32le",
            "-ac", "1",
            "-ar", "22050",
            "-loglevel", "quiet",
            "-"
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            raw_bytes, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            raw_bytes, _ = proc.communicate()

        if not raw_bytes or len(raw_bytes) < 44100:
            # Если трек короче 30 секунд или смещение слишком велико, пробуем с 0 секунды
            cmd[2] = "0"
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                raw_bytes, _ = proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                raw_bytes, _ = proc.communicate()

        y = np.frombuffer(raw_bytes, dtype=np.float32)
        if len(y) < 44100:
            raise ValueError("Недостаточно аудиоданных для анализа")

        sr = 22050

        # 2. Энергия (Root Mean Square Loudness)
        rms = float(np.sqrt(np.mean(y ** 2)))
        energy = float(np.clip((rms - 0.03) / 0.28, 0.05, 0.99))

        # 3. Темп (BPM) через автокорреляцию огибающей
        hop = 512
        frames = [y[i:i + hop] for i in range(0, len(y) - hop, hop)]
        env = np.array([np.sqrt(np.mean(f ** 2)) for f in frames])
        diff_env = np.maximum(0, np.diff(env))
        if len(diff_env) > 1:
            diff_env = diff_env - np.mean(diff_env)
            autocorr = correlate(diff_env, diff_env, mode="full")
            autocorr = autocorr[len(autocorr) // 2:]

            fps = sr / hop
            min_lag = int(fps * 60 / 180)  # max 180 BPM
            max_lag = int(fps * 60 / 65)   # min 65 BPM
            lags = autocorr[min_lag:max_lag]
            if len(lags) > 0 and np.max(lags) > 0:
                best_lag = min_lag + int(np.argmax(lags))
                bpm = round(float((fps * 60) / best_lag), 1)
            else:
                bpm = 120.0
        else:
            bpm = 120.0

        # 4. Тональность и Valence (Мажорность / Позитивность)
        # Спектральная хромограмма 12 полутонов
        freqs = np.fft.rfftfreq(len(y), 1 / sr)
        fft_mag = np.abs(np.fft.rfft(y))

        chroma = np.zeros(12, dtype=np.float64)
        for p in range(48, 84):  # MIDI ноты C3..B5 (130 - 1000 Hz)
            f0 = 440.0 * (2.0 ** ((p - 69) / 12.0))
            band_mask = (freqs >= f0 * 0.975) & (freqs <= f0 * 1.025)
            if np.any(band_mask):
                chroma[p % 12] += np.sum(fft_mag[band_mask])

        chroma_sum = np.sum(chroma)
        if chroma_sum > 0:
            chroma /= chroma_sum

        # Профили тональностей Крумхансла-Шмуклера
        major_prof = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        minor_prof = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

        if chroma_sum > 0 and np.std(chroma) > 1e-5:
            major_corr = max(
                float(np.corrcoef(np.roll(chroma, -i), major_prof)[0, 1])
                for i in range(12)
            )
            minor_corr = max(
                float(np.corrcoef(np.roll(chroma, -i), minor_prof)[0, 1])
                for i in range(12)
            )
            harmonic_valence = float(np.clip(0.5 + (major_corr - minor_corr) * 1.2, 0.1, 0.9))
        else:
            harmonic_valence = 0.5

        # Спектральная яркость (Spectral Centroid / Тональный баланс высоких частот)
        centroid = float(np.sum(freqs * fft_mag) / (np.sum(fft_mag) + 1e-9))
        brightness = float(np.clip((centroid - 1200.0) / 2400.0, 0.1, 0.9))

        # 5. Танцевальность (Danceability)
        tempo_factor = max(0.0, 1.0 - abs(bpm - 122.5) / 55.0)
        danceability = float(np.clip(0.35 * energy + 0.65 * tempo_factor, 0.05, 0.95))

        # Интегральный Valence (35% гармонический лад, 35% яркость спектра, 30% танцевальный кач)
        valence = float(np.clip(0.35 * harmonic_valence + 0.35 * brightness + 0.30 * danceability, 0.05, 0.95))

        import math
        bpm = bpm if math.isfinite(bpm) and bpm > 0 else 120.0
        energy = energy if math.isfinite(energy) else 0.5
        valence = valence if math.isfinite(valence) else 0.5
        danceability = danceability if math.isfinite(danceability) else 0.5

        # 6. Вектор признаков (16D)
        vector = [
            round(bpm / 180.0, 3),
            round(energy, 3),
            round(valence, 3),
            round(danceability, 3)
        ] + [round(float(c), 3) if math.isfinite(float(c)) else 0.0 for c in chroma[:12]]

        return {
            "bpm": round(bpm, 1),
            "energy": round(energy, 3),
            "valence": round(valence, 3),
            "danceability": round(danceability, 2),
            "vector": vector
        }

    except Exception:
        # Надежный фоллбэк при отсутствии ffmpeg, numpy/scipy или битом файле
        return {
            "bpm": 120.0,
            "energy": 0.5,
            "valence": 0.5,
            "danceability": 0.5,
            "vector": [0.667, 0.5, 0.5, 0.5] + [0.0] * 12
        }


def serialize_vector(vector: List[float]) -> str:
    return json.dumps(vector)


def deserialize_vector(json_str: Optional[str]) -> List[float]:
    if not json_str:
        return []
    try:
        return json.loads(json_str)
    except Exception:
        return []


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Вычисляет косинусное сходство между двумя векторами признаков."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0

    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = sum(a * a for a in v1) ** 0.5
    norm_b = sum(b * b for b in v2) ** 0.5

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / (norm_a * norm_b)


def normalize_vector(v: List[float]) -> List[float]:
    """Нормализует вектор признаков до единичной сферы (L2 норма)."""
    if not v:
        return []
    norm = sum(x * x for x in v) ** 0.5
    if norm == 0.0:
        return [0.0] * len(v)
    return [round(x / norm, 4) for x in v]


def compute_user_taste_centroid(db, mood: Optional[str] = None) -> List[float]:
    """
    Вычисляет математический центроид вкуса пользователя (User Taste Centroid)
    по всей коллекции треков с учетом лайков, истории прослушиваний и настроения.
    """
    import math
    from database.models import Track, UserReaction, PlayHistory
    from recommendations.mood import apply_mood_filter

    liked_ids = {
        r[0] for r in db.query(UserReaction.track_id).filter(UserReaction.is_liked == True).all()
    }
    disliked_ids = {
        r[0] for r in db.query(UserReaction.track_id).filter(UserReaction.is_disliked == True).all()
    }

    # Статистика дослушиваний и скипов
    play_rows = (
        db.query(
            PlayHistory.track_id,
            PlayHistory.completed,
            PlayHistory.skipped
        )
        .all()
    )
    completes: Dict[int, int] = {}
    skips: Dict[int, int] = {}
    for tid, is_comp, is_skip in play_rows:
        if not tid:
            continue
        if is_comp:
            completes[tid] = completes.get(tid, 0) + 1
        if is_skip:
            skips[tid] = skips.get(tid, 0) + 1

    query = (
        db.query(Track)
        .filter(Track.is_discovery == False)
        .filter(Track.embedding_json.isnot(None))
    )
    if mood and mood not in ("default", "all"):
        query = apply_mood_filter(query, mood)

    tracks = query.all()
    if not tracks:
        default_v = [0.667, 0.5, 0.5, 0.5] + [0.0] * 12
        return normalize_vector(default_v)

    accumulated = [0.0] * 16
    total_weight = 0.0

    for t in tracks:
        if t.id in disliked_ids:
            continue
        vec = deserialize_vector(t.embedding_json)
        if not vec or len(vec) != 16:
            continue

        w = 1.0
        if t.id in liked_ids:
            w += 3.5

        c_cnt = completes.get(t.id, 0)
        if c_cnt > 0:
            w += math.log1p(c_cnt) * 1.2

        s_cnt = skips.get(t.id, 0)
        if s_cnt > 0:
            w -= min(2.0, s_cnt * 1.4)

        if w < 0.1:
            w = 0.1

        for i in range(16):
            accumulated[i] += vec[i] * w
        total_weight += w

    if total_weight <= 0.0:
        default_v = [0.667, 0.5, 0.5, 0.5] + [0.0] * 12
        return normalize_vector(default_v)

    mean_vec = [accumulated[i] / total_weight for i in range(16)]
    return normalize_vector(mean_vec)


def update_session_drift_vector(
    current_session_vector: List[float],
    track_vector: List[float],
    action: str = "complete"
) -> List[float]:
    """
    Вычисляет динамический дрейф сессионного вектора предпочтений в реальном времени.
    - like: сильное притяжение к акустическому профилю трека (+0.8)
    - complete: умеренное плавное смещение вектора (+0.35)
    - skip: отталкивание от звучания пропущенного трека (-0.6)
    """
    if not current_session_vector or len(current_session_vector) != 16:
        return track_vector if (track_vector and len(track_vector) == 16) else [0.0] * 16
    if not track_vector or len(track_vector) != 16:
        return current_session_vector

    alpha = 0.35
    if action == "like":
        alpha = 0.80
    elif action == "skip":
        alpha = -0.60

    drifted = [
        c + alpha * t
        for c, t in zip(current_session_vector, track_vector)
    ]
    return normalize_vector(drifted)


