"""
Unit tests for the audio trimming helpers in VoiceParsingService.

These tests use synthetic audio generated with pydub (silence + a 440 Hz
sine tone simulating voice) so they do not depend on real recordings or
the OpenAI API.

Skipped automatically if pydub or ffmpeg is not available.
"""
import pytest

pydub = pytest.importorskip("pydub", reason="pydub is required for audio trim tests")
from pydub import AudioSegment
from pydub.generators import Sine
from pydub.utils import which as pydub_which

# ffmpeg is required by pydub for any non-trivial decoding/encoding work.
# detect_leading_silence on raw in-memory AudioSegments does not need ffmpeg,
# but keeping the guard makes failures explicit on misconfigured CI.
_FFMPEG_AVAILABLE = pydub_which("ffmpeg") is not None

from src.domains.health.voice_parsing import VoiceParsingService


def _make_test_audio(silence_ms: int, voice_ms: int) -> AudioSegment:
    """Generate synthetic audio: leading silence followed by a 440 Hz tone."""
    silence = AudioSegment.silent(duration=silence_ms)
    if voice_ms <= 0:
        return silence
    # -10 dBFS tone is well above the default silence threshold (-40 dBFS)
    voice = Sine(440).to_audio_segment(duration=voice_ms).apply_gain(-10)
    return silence + voice


# ---------------------------------------------------------------------------
# _trim_leading_silence
# ---------------------------------------------------------------------------

class TestTrimLeadingSilence:
    def test_removes_long_leading_silence(self):
        audio = _make_test_audio(silence_ms=5000, voice_ms=3000)
        trimmed, removed_ms = VoiceParsingService._trim_leading_silence(
            audio, silence_threshold_dbfs=-40.0
        )
        # At least 4.5s should be removed (5s - 300ms safety margin - tolerance)
        assert removed_ms >= 4500, f"expected >= 4500ms removed, got {removed_ms}"
        # Voice portion preserved (3000ms tone, allowing for small detection slop)
        assert len(trimmed) >= 2500, f"expected >= 2500ms remaining, got {len(trimmed)}"

    def test_no_crash_on_pure_silence(self):
        audio = AudioSegment.silent(duration=10_000)
        trimmed, removed_ms = VoiceParsingService._trim_leading_silence(audio)
        # min_output_duration protection kicks in and returns original
        assert removed_ms == 0
        assert len(trimmed) == len(audio)

    def test_no_cut_when_voice_starts_immediately(self):
        # Only 100ms of silence before voice -> after subtracting 300ms safety
        # margin the start_trim is clamped to 0, so nothing is removed.
        audio = _make_test_audio(silence_ms=100, voice_ms=5000)
        trimmed, removed_ms = VoiceParsingService._trim_leading_silence(
            audio, silence_threshold_dbfs=-40.0
        )
        assert removed_ms == 0
        assert len(trimmed) == len(audio)

    def test_respects_min_output_duration(self):
        # Long silence + very short voice -> trimming would yield only ~500ms,
        # which is below the 1500ms minimum -> return original.
        audio = _make_test_audio(silence_ms=8000, voice_ms=500)
        trimmed, removed_ms = VoiceParsingService._trim_leading_silence(
            audio,
            silence_threshold_dbfs=-40.0,
            min_output_duration_ms=1500,
        )
        assert removed_ms == 0
        assert len(trimmed) == len(audio)


# ---------------------------------------------------------------------------
# _detect_noise_floor
# ---------------------------------------------------------------------------

class TestDetectNoiseFloor:
    def test_pure_silence_returns_sensitive_default(self):
        audio = AudioSegment.silent(duration=2000)
        threshold = VoiceParsingService._detect_noise_floor(audio)
        # Pure silence -> -inf dBFS -> fallback to -50.0
        assert threshold == -50.0

    def test_threshold_is_clamped(self):
        # Loud signal at the start would push threshold above -25 dBFS;
        # the implementation clamps to [-55.0, -25.0].
        loud = Sine(440).to_audio_segment(duration=1000).apply_gain(0)  # ~0 dBFS
        threshold = VoiceParsingService._detect_noise_floor(loud)
        assert -55.0 <= threshold <= -25.0

    def test_threshold_is_above_noise_floor(self):
        # A quiet noise sample around -45 dBFS -> threshold should be ~-39 dBFS
        # (noise_floor + 6 dB), still within the clamp range.
        quiet = Sine(440).to_audio_segment(duration=1000).apply_gain(-45)
        threshold = VoiceParsingService._detect_noise_floor(quiet)
        assert -55.0 <= threshold <= -25.0
        # Should be strictly greater than the underlying noise floor
        assert threshold > quiet.dBFS


# ---------------------------------------------------------------------------
# _export_audio_for_whisper (requires ffmpeg for MP3 encoding)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _FFMPEG_AVAILABLE, reason="ffmpeg not available")
class TestExportForWhisper:
    def test_export_returns_mp3_bytes(self):
        audio = _make_test_audio(silence_ms=100, voice_ms=1000)
        data, filename = VoiceParsingService._export_audio_for_whisper(audio)
        assert isinstance(data, bytes)
        assert len(data) > 0
        assert filename == "audio.mp3"


# ---------------------------------------------------------------------------
# _format_from_content_type
# ---------------------------------------------------------------------------

class TestFormatFromContentType:
    @pytest.mark.parametrize(
        "content_type,filename,expected",
        [
            ("audio/mp4", None, "mp4"),
            ("audio/m4a", None, "mp4"),
            ("audio/3gpp", None, "3gpp"),
            ("audio/mpeg", None, "mp3"),
            (None, "recording.m4a", "mp4"),
            (None, "recording.3gpp", "3gpp"),
            (None, None, "mp4"),  # default fallback
            ("audio/mp4; codecs=mp4a.40.2", None, "mp4"),  # parameterized type
        ],
    )
    def test_format_detection(self, content_type, filename, expected):
        assert (
            VoiceParsingService._format_from_content_type(content_type, filename)
            == expected
        )
