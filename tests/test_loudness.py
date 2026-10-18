import pytest
from unittest.mock import patch, MagicMock
from recommendations.loudness import measure_track_loudness
from database.models import Track


def test_measure_track_loudness_nonexistent():
    assert measure_track_loudness("/non/existent/file.mp3") is None


def test_measure_track_loudness_parsing():
    dummy_stderr = """
[Parsed_ebur128_0 @ 0x123] Summary:

  Integrated loudness:
    I:         -16.5 LUFS
    Threshold: -26.8 LUFS

  Loudness range:
    LRA:         7.2 LU
    Threshold: -36.8 LUFS
    LRA low:   -21.0 LUFS
    LRA high:  -13.8 LUFS

  True peak:
    Peak:       -4.0 dBFS
"""
    with patch("os.path.exists", return_value=True):
        with patch("subprocess.Popen") as mock_popen:
            process_mock = MagicMock()
            process_mock.communicate.return_value = ("", dummy_stderr)
            mock_popen.return_value = process_mock

            res = measure_track_loudness("/fake/song.flac", target_lufs=-14.0)
            assert res is not None
            assert res["loudness_lufs"] == -16.5
            assert res["peak_db"] == -4.0
            assert res["lra"] == 7.2
            # target (-14.0) - measured (-16.5) = +2.5 dB
            # peak (-4.0) + gain (+2.5) = -1.5 dBFS <= -1.0 dBFS (no peak clamping needed)
            assert res["gain_db"] == 2.5


def test_measure_track_loudness_true_peak_clamping():
    # If track is quiet (-20 LUFS) but has high true peak (-0.5 dBFS)
    # normal gain = -14.0 - (-20.0) = +6.0 dB
    # with gain, peak would be -0.5 + 6.0 = +5.5 dBFS (huge clipping!)
    # True Peak protection must cap gain at: -1.0 - (-0.5) = -0.5 dB
    dummy_stderr = """
  Integrated loudness:
    I:         -20.0 LUFS

  True peak:
    Peak:       -0.5 dBFS

  Loudness range:
    LRA:         4.0 LU
"""
    with patch("os.path.exists", return_value=True):
        with patch("subprocess.Popen") as mock_popen:
            process_mock = MagicMock()
            process_mock.communicate.return_value = ("", dummy_stderr)
            mock_popen.return_value = process_mock

            res = measure_track_loudness("/fake/quiet_peaky.flac", target_lufs=-14.0)
            assert res is not None
            assert res["loudness_lufs"] == -20.0
            assert res["peak_db"] == -0.5
            assert res["gain_db"] == -0.5  # Clamped to prevent peak above -1.0 dBFS!


def test_streaming_endpoint_loudness_headers(client, auth_headers, db_session, tmp_path):
    # Создаем тестовый аудиофайл
    audio_file = tmp_path / "normalized_track.mp3"
    audio_file.write_bytes(b"dummy mp3 data for streaming headers test")

    t = Track(
        title="Loud Track",
        artist="Test Artist",
        duration=180,
        audio_format="mp3",
        file_path=str(audio_file),
        file_size=len(audio_file.read_bytes()),
        loudness_lufs=-11.4,
        gain_db=-2.6,
        peak_db=-0.2
    )
    db_session.add(t)
    db_session.commit()

    headers = dict(auth_headers)
    headers["Range"] = "bytes=0-10"
    res = client.get(f"/api/stream/{t.id}", headers=headers)
    assert res.status_code == 206
    assert res.headers.get("X-Audio-Gain-dB") == "-2.6"
    assert res.headers.get("X-Audio-Loudness-LUFS") == "-11.4"
    assert res.headers.get("X-Audio-Peak-dB") == "-0.2"
