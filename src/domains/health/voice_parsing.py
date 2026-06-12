"""
Voice parsing service for blood pressure readings.

Uses OpenAI to extract BP values from natural language transcriptions.
Supports both text transcriptions and audio files (via Whisper STT).
"""
import os
import re
import io
import json
import tempfile
from openai import AsyncOpenAI
from typing import Optional, BinaryIO, Tuple
from src._config.logger import get_logger

logger = get_logger(__name__)

# Optional audio processing dependencies (pydub + ffmpeg).
# If unavailable, the audio trim step is skipped and the original audio
# is forwarded to Whisper unchanged.
try:
    from pydub import AudioSegment
    from pydub.silence import detect_leading_silence
    _PYDUB_AVAILABLE = True
except Exception as _pydub_err:  # pragma: no cover - import-time guard
    AudioSegment = None  # type: ignore
    detect_leading_silence = None  # type: ignore
    _PYDUB_AVAILABLE = False
    logger.warning(f"pydub not available - audio trimming disabled: {_pydub_err}")


# Mapping of HTTP content types to pydub format strings
_CONTENT_TYPE_TO_FORMAT = {
    "audio/mp4": "mp4",
    "audio/m4a": "mp4",   # pydub uses "mp4" container for M4A
    "audio/x-m4a": "mp4",
    "audio/3gpp": "3gpp",
    "audio/aac": "aac",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/webm": "webm",
}

# System prompt for BP extraction
BP_EXTRACTION_PROMPT = """You are a medical assistant that extracts blood pressure readings from patient voice transcriptions.

Your task is to extract:
1. Systolic pressure (the first/higher number)
2. Diastolic pressure (the second/lower number)
3. Pulse/heart rate (if mentioned)
4. Device classification (if the patient mentions the device type)

Spanish number words to parse:
- "ciento veinte" = 120
- "setenta y cinco" = 75
- "ochenta" = 80
- Numbers can be said as "120 sobre 80", "120/80", or "ciento veinte ochenta"

Common phrases:
- "mi presión es...", "mi presión está en..."
- "tengo la presión en..."
- "sobre" = separator between systolic and diastolic
- "con pulso de..." = pulse rate

IMPORTANT RULES:
1. Systolic must be between 60-300 mmHg
2. Diastolic must be between 30-200 mmHg
3. Systolic must be greater than diastolic
4. Pulse must be between 20-300 BPM
5. If values seem implausible, set confidence to "low"

Output JSON format:
{
    "systolic": <int or null>,
    "diastolic": <int or null>,
    "pulse": <int or null>,
    "device_classification": <string or null>,
    "confidence": "high" or "low"
}

Set confidence to "high" only if:
- Both systolic and diastolic are clearly stated
- Values are physiologically plausible
- The transcription clearly references blood pressure

Set confidence to "low" if:
- Only one value is mentioned
- Values are ambiguous or unclear
- The transcription might not be about blood pressure"""


# System prompt for medication-take INTENT extraction (patient confirming pills already taken)
MED_TAKE_INTENT_PROMPT = """You are a medical assistant for an elderly-care app in Spanish.
The patient speaks to CONFIRM they already took their pills. Extract their intent and
which time-of-day group ("franja") they mean.

Time-of-day groups:
- "morning"  = mañana (e.g. "las de la mañana", "las matutinas", "las del desayuno")
- "midday"   = mediodía / media tarde / tarde (e.g. "las del mediodía", "las de la tarde", "las del almuerzo")
- "night"    = noche (e.g. "las de la noche", "las de antes de dormir", "las de la cena")
- "all"      = todas (e.g. "ya me las tomé todas", "todas mis pastillas")

Rules:
1. intent = "confirm_take" ONLY if the patient clearly states (past tense) they already took / are confirming pills.
2. If they speak in future tense ("me las tomo mañana"), ask a question, or it is unclear -> intent = "unknown".
3. franja = null if no clear time-of-day group is stated. If a specific franja is named, prefer it over "all".
4. confidence = "high" only when intent is clearly a past-tense confirmation AND a franja (or "all") is clear; otherwise "low".

Output JSON only:
{ "intent": "confirm_take" | "unknown", "franja": "morning" | "midday" | "night" | "all" | null, "confidence": "high" | "low" }"""

# Keyword fallback maps, used when the OpenAI client is unavailable. Specific
# franjas are checked before "all" so "todas las de la mañana" -> morning.
_FRANJA_KEYWORDS = {
    "morning": ["mañana", "manana", "matutin", "desayun"],
    "midday": ["mediodía", "mediodia", "medio día", "medio dia", "tarde", "almuerzo", "comida"],
    "night": ["noche", "dormir", "cena", "acostar"],
    "all": ["todas", "todos", "toditas", "completas"],
}
# Past-tense take confirmations. Present/future ("me las tomo mañana") is left out.
_TAKE_KEYWORDS = ["tomé", "tome", "tomado", "tomada", "ya me tom", "me las tomé", "ya las tomé"]


# System prompt for NEW-medication extraction (sub-flow A: register by voice)
MED_EXTRACTION_PROMPT = """You extract a NEW medication that a patient or caregiver is registering by voice (Spanish).

Extract:
- name: the medication name as spoken (brand name or active ingredient), or null if not clearly stated.
- dosage: the dose with its unit if stated (e.g. "50 mg", "10 ml", "1 tableta"), else "".
- frequency_text: the frequency exactly as said (e.g. "cada 12 horas", "una vez al dia en la manana"), else "".
- times: a list of HH:MM (24h) reminder times INFERRED from the frequency:
    "cada 12 horas" -> ["08:00","20:00"];  "cada 8 horas" -> ["08:00","16:00","00:00"];
    "en la manana y en la noche" -> ["08:00","20:00"];  "una vez al dia" / "en la manana" -> ["08:00"].
  Empty list if it cannot be inferred.
- confidence: "high" only if a name is clearly stated AND a dosage or frequency is present; otherwise "low".

NEVER invent or guess a medication name. If unsure, set name to null and confidence to "low".

Output JSON only:
{ "name": <string|null>, "dosage": <string>, "frequency_text": <string>, "times": [<string>], "confidence": "high"|"low" }"""


class VoiceParsingService:
    """Service for parsing BP values from voice transcriptions using OpenAI."""
    
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set - voice parsing will use fallback")
            self.client = None
        else:
            self.client = AsyncOpenAI(api_key=api_key)
    
    async def parse_transcription(self, transcription: str) -> dict:
        """
        Parse a voice transcription to extract BP values.
        
        Args:
            transcription: Raw text from speech recognition
            
        Returns:
            dict with keys: systolic, diastolic, pulse, device_classification, confidence
        """
        # Try regex fallback first for simple patterns
        regex_result = self._try_regex_parse(transcription)
        
        # If we have OpenAI, use it for better parsing
        if self.client:
            try:
                llm_result = await self._parse_with_llm(transcription)
                
                # If LLM found values and regex didn't, use LLM
                # If both found values, prefer LLM for confidence assessment
                if llm_result.get("systolic") or llm_result.get("diastolic"):
                    return llm_result
                    
            except Exception as e:
                logger.error(f"LLM parsing failed, falling back to regex: {e}")
        
        # Fall back to regex result
        return regex_result
    
    def _try_regex_parse(self, text: str) -> dict:
        """
        Simple regex-based parsing for common BP patterns.
        
        Patterns matched:
        - "120/80" or "120 / 80"
        - "120 sobre 80"
        - "120 80" (two numbers in sequence)
        """
        result = {
            "systolic": None,
            "diastolic": None,
            "pulse": None,
            "device_classification": None,
            "confidence": "low"
        }
        
        lower = text.lower()
        
        # Pattern 1: "120/80" or "120 / 80"
        slash_match = re.search(r'(\d{2,3})\s*[/\\]\s*(\d{2,3})', text)
        if slash_match:
            s, d = int(slash_match.group(1)), int(slash_match.group(2))
            if self._is_plausible(s, d):
                result["systolic"] = s
                result["diastolic"] = d
                result["confidence"] = "high"
        
        # Pattern 2: "120 sobre 80"
        if not result["systolic"]:
            sobre_match = re.search(r'(\d{2,3})\s+sobre\s+(\d{2,3})', lower)
            if sobre_match:
                s, d = int(sobre_match.group(1)), int(sobre_match.group(2))
                if self._is_plausible(s, d):
                    result["systolic"] = s
                    result["diastolic"] = d
                    result["confidence"] = "high"
        
        # Pattern 3: "pulso de 75" or "latidos 75"
        pulse_match = re.search(r'(?:pulso|latidos|bpm)\s*(?:de|:)?\s*(\d{2,3})', lower)
        if pulse_match:
            p = int(pulse_match.group(1))
            if 20 <= p <= 300:
                result["pulse"] = p
        
        return result
    
    def _is_plausible(self, systolic: int, diastolic: int) -> bool:
        """Check if BP values are physiologically plausible."""
        if not (60 <= systolic <= 300):
            return False
        if not (30 <= diastolic <= 200):
            return False
        if systolic <= diastolic:
            return False
        return True
    
    async def _parse_with_llm(self, transcription: str) -> dict:
        """Use OpenAI to parse the transcription."""
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": BP_EXTRACTION_PROMPT},
                {"role": "user", "content": f"Parse this voice transcription:\n\n{transcription}"}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        result = json.loads(content)
        
        # Ensure all keys exist
        return {
            "systolic": result.get("systolic"),
            "diastolic": result.get("diastolic"),
            "pulse": result.get("pulse"),
            "device_classification": result.get("device_classification"),
            "confidence": result.get("confidence", "low")
        }
    
    async def transcribe_audio(
        self,
        audio_content: bytes,
        filename: str,
        content_type: Optional[str] = None,
    ) -> Tuple[str, dict]:
        """
        Transcribe audio to text using OpenAI Whisper.

        Applies leading-silence trimming with pydub (if available) before
        sending to Whisper, to reduce API cost and latency. If trimming
        fails for any reason, the original audio is forwarded unchanged.

        Args:
            audio_content: Audio file bytes (M4A, 3GP, MP3, WAV, ...)
            filename: Original filename (used as fallback for format detection)
            content_type: HTTP content type of the upload (preferred for format detection)

        Returns:
            Tuple of (transcription_text, metadata_dict). The metadata dict
            contains the following keys (all ints, all in milliseconds):
              - audio_original_duration_ms
              - audio_trimmed_duration_ms
              - silence_removed_ms
            When trimming is not applied (pydub missing or fallback), the
            three values are equal/zero, but the keys are always present.
        """
        if not self.client:
            raise ValueError("OpenAI client not configured - cannot transcribe audio")

        logger.info(
            f"Transcribing audio file: {filename}, size: {len(audio_content)} bytes, "
            f"content_type={content_type}"
        )

        # Default metadata (used when trim is skipped or fails)
        metadata = {
            "audio_original_duration_ms": 0,
            "audio_trimmed_duration_ms": 0,
            "silence_removed_ms": 0,
        }

        send_bytes = audio_content
        send_filename = filename

        # Best-effort audio trim: load + detect silence + re-export. On any
        # failure, fall back silently to the original audio.
        if _PYDUB_AVAILABLE:
            try:
                audio_segment = self._load_audio_from_bytes(audio_content, content_type, filename)
                original_duration_ms = len(audio_segment)
                metadata["audio_original_duration_ms"] = original_duration_ms

                threshold = self._detect_noise_floor(audio_segment)
                trimmed, removed_ms = self._trim_leading_silence(
                    audio_segment,
                    silence_threshold_dbfs=threshold,
                )

                metadata["audio_trimmed_duration_ms"] = len(trimmed)
                metadata["silence_removed_ms"] = removed_ms

                if removed_ms > 0:
                    logger.info(
                        f"Trim applied: removed {removed_ms}ms of leading silence "
                        f"({original_duration_ms}ms -> {len(trimmed)}ms, "
                        f"threshold={threshold:.1f} dBFS)"
                    )
                    send_bytes, send_filename = self._export_audio_for_whisper(trimmed)
                else:
                    logger.info(
                        f"No silence trim applied (threshold={threshold:.1f} dBFS, "
                        f"duration={original_duration_ms}ms)"
                    )
            except Exception as e:
                logger.warning(
                    f"Audio trim failed, sending original audio to Whisper: {e}"
                )
                # Reset metadata to safe defaults on failure
                metadata = {
                    "audio_original_duration_ms": 0,
                    "audio_trimmed_duration_ms": 0,
                    "silence_removed_ms": 0,
                }
                send_bytes = audio_content
                send_filename = filename

        # Whisper API accepts file tuples; wrap bytes in BytesIO so the
        # OpenAI SDK can stream them with a proper content-length header.
        response = await self.client.audio.transcriptions.create(
            model="whisper-1",
            file=(send_filename, io.BytesIO(send_bytes)),
            language="es",  # Spanish
            response_format="text"
        )

        transcription = response.strip() if isinstance(response, str) else str(response).strip()
        logger.info(f"Transcription result ({len(transcription)} chars): {transcription[:100]}...")
        return transcription, metadata

    # ------------------------------------------------------------------
    # Audio processing helpers (pydub-based)
    # ------------------------------------------------------------------

    @staticmethod
    def _format_from_content_type(content_type: Optional[str], filename: Optional[str]) -> str:
        """Resolve a pydub format string from HTTP content type, with filename fallback."""
        if content_type:
            ct = content_type.split(";")[0].strip().lower()
            fmt = _CONTENT_TYPE_TO_FORMAT.get(ct)
            if fmt:
                return fmt
        if filename:
            ext = os.path.splitext(filename)[1].lower().lstrip(".")
            if ext == "m4a":
                return "mp4"
            if ext in {"mp4", "3gpp", "aac", "mp3", "wav", "webm"}:
                return ext
        # Default: assume M4A container (the Android client default)
        return "mp4"

    def _load_audio_from_bytes(
        self,
        file_bytes: bytes,
        content_type: Optional[str],
        filename: Optional[str] = None,
    ) -> "AudioSegment":
        """
        Load an audio upload (M4A/3GP/MP3/...) into a pydub AudioSegment.

        Writes the bytes to a short-lived temp file because ffmpeg needs a
        seekable input. The temp file is always cleaned up.
        """
        fmt = self._format_from_content_type(content_type, filename)
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            return AudioSegment.from_file(tmp_path, format=fmt)
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _detect_noise_floor(audio: "AudioSegment", sample_ms: int = 500) -> float:
        """
        Estimate background noise level by measuring dBFS of the first
        `sample_ms` of audio (assumed to be silence/noise while the user
        waits for the BP cuff to finish). Returns a dynamic silence
        threshold = noise_floor + 6 dB, clamped to [-55.0, -25.0] dBFS.

        For absolute silence (dBFS == -inf), returns a very sensitive
        default of -50.0 dBFS so that any voice will be detected.
        """
        sample = audio[:sample_ms]
        noise_floor_dbfs = sample.dBFS
        if noise_floor_dbfs == float("-inf"):
            return -50.0
        threshold = noise_floor_dbfs + 6.0
        # Clamp to reasonable speech-detection bounds
        return max(-55.0, min(-25.0, threshold))

    @staticmethod
    def _trim_leading_silence(
        audio: "AudioSegment",
        silence_threshold_dbfs: float = -40.0,
        safety_margin_ms: int = 300,
        min_output_duration_ms: int = 1500,
    ) -> Tuple["AudioSegment", int]:
        """
        Trim leading silence from an AudioSegment.

        Args:
            audio: full audio segment
            silence_threshold_dbfs: dBFS level below which audio is silence.
                More negative = more aggressive (trims more).
            safety_margin_ms: ms preserved before the detected onset, so the
                attack of the first word is not cut.
            min_output_duration_ms: if trimming would yield audio shorter
                than this, return the original instead.

        Returns:
            (trimmed_audio, ms_removed). ms_removed == 0 when no trim was applied.
        """
        if detect_leading_silence is None:
            return audio, 0

        start_trim_ms = detect_leading_silence(
            audio, silence_threshold=silence_threshold_dbfs
        )
        start_trim_ms = max(0, start_trim_ms - safety_margin_ms)
        if start_trim_ms == 0:
            return audio, 0

        trimmed = audio[start_trim_ms:]
        if len(trimmed) < min_output_duration_ms:
            return audio, 0

        return trimmed, start_trim_ms

    @staticmethod
    def _export_audio_for_whisper(audio: "AudioSegment") -> Tuple[bytes, str]:
        """
        Export the (possibly trimmed) AudioSegment to in-memory MP3 bytes.

        MP3 is supported by Whisper, lighter than WAV, and consistently
        smaller than the original M4A when the user had a long silent
        prefix that has now been removed.

        Returns:
            (audio_bytes, filename) where filename carries the .mp3
            extension so Whisper detects the format from the multipart upload.
        """
        buffer = io.BytesIO()
        audio.export(buffer, format="mp3")
        buffer.seek(0)
        return buffer.read(), "audio.mp3"

    async def parse_audio(
        self,
        audio_content: bytes,
        filename: str,
        content_type: Optional[str] = None,
    ) -> dict:
        """
        Transcribe audio and parse BP values in one step.

        Args:
            audio_content: Audio file bytes
            filename: Original filename
            content_type: Optional HTTP content type, used to pick the
                pydub decoder before trimming.

        Returns:
            dict with: systolic, diastolic, pulse, device_classification,
            confidence, transcription, audio_original_duration_ms,
            audio_trimmed_duration_ms, silence_removed_ms
        """
        # Step 1: Transcribe audio to text (with silence trim if available)
        transcription, audio_metadata = await self.transcribe_audio(
            audio_content, filename, content_type=content_type
        )

        if not transcription:
            return {
                "systolic": None,
                "diastolic": None,
                "pulse": None,
                "device_classification": None,
                "confidence": "low",
                "transcription": "",
                **audio_metadata,
            }

        # Step 2: Parse transcription for BP values
        result = await self.parse_transcription(transcription)

        # Include transcription + audio metadata in result
        result["transcription"] = transcription
        result.update(audio_metadata)

        return result

    # ------------------------------------------------------------------
    # Medication-take intent (sub-flow B): "ya me tomé las de la mañana"
    # ------------------------------------------------------------------

    def _try_keyword_take_intent(self, text: str) -> dict:
        """Keyword fallback for take-intent parsing (no OpenAI required)."""
        lower = (text or "").lower()
        intent = "confirm_take" if any(k in lower for k in _TAKE_KEYWORDS) else "unknown"
        franja = None
        for key in ("morning", "midday", "night", "all"):
            if any(k in lower for k in _FRANJA_KEYWORDS[key]):
                franja = key
                break
        confidence = "high" if (intent == "confirm_take" and franja) else "low"
        return {"intent": intent, "franja": franja, "confidence": confidence}

    async def _parse_take_intent_with_llm(self, transcription: str) -> dict:
        """Use OpenAI to parse the medication-take intent."""
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": MED_TAKE_INTENT_PROMPT},
                {"role": "user", "content": f"Parse this patient voice transcription:\n\n{transcription}"},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        intent = result.get("intent")
        franja = result.get("franja")
        if intent not in ("confirm_take", "unknown"):
            intent = "unknown"
        if franja not in ("morning", "midday", "night", "all", None):
            franja = None
        return {
            "intent": intent or "unknown",
            "franja": franja,
            "confidence": result.get("confidence", "low"),
        }

    async def parse_take_intent(self, transcription: str) -> dict:
        """
        Parse a voice transcription to detect a medication-take confirmation
        and its time-of-day group ("franja").

        Returns dict with keys: intent ("confirm_take"|"unknown"), franja
        ("morning"|"midday"|"night"|"all"|None), confidence ("high"|"low").
        Falls back to keyword matching when the OpenAI client is unavailable.
        """
        if self.client:
            try:
                return await self._parse_take_intent_with_llm(transcription)
            except Exception as e:
                logger.error(f"LLM take-intent parsing failed, using keyword fallback: {e}")
        return self._try_keyword_take_intent(transcription)

    async def parse_take_audio(
        self,
        audio_content: bytes,
        filename: str,
        content_type: Optional[str] = None,
    ) -> dict:
        """
        Transcribe audio and parse the medication-take intent in one step.

        Returns dict with: intent, franja, confidence, transcription.
        """
        transcription, _audio_metadata = await self.transcribe_audio(
            audio_content, filename, content_type=content_type
        )
        if not transcription:
            return {"intent": "unknown", "franja": None, "confidence": "low", "transcription": ""}
        result = await self.parse_take_intent(transcription)
        result["transcription"] = transcription
        return result

    # ------------------------------------------------------------------
    # Medication registration (sub-flow A): register a NEW medication by
    # voice. The extracted name is validated against the drug catalog and
    # read back to the patient before anything is saved.
    # ------------------------------------------------------------------

    async def _parse_medication_with_llm(self, transcription: str) -> dict:
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": MED_EXTRACTION_PROMPT},
                {"role": "user", "content": f"Extract the medication from:\n\n{transcription}"},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        times = [t for t in (result.get("times") or []) if isinstance(t, str) and ":" in t]
        return {
            "name": result.get("name") or None,
            "dosage": result.get("dosage") or "",
            "frequency_text": result.get("frequency_text") or "",
            "times": times,
            "confidence": result.get("confidence", "low"),
        }

    async def parse_medication_intent(self, transcription: str) -> dict:
        """
        Extract a new medication's {name, dosage, frequency_text, times,
        confidence} from a transcription. Requires the LLM; without it returns
        an empty/low-confidence result (a drug name cannot be reliably
        extracted by keywords).
        """
        if self.client:
            try:
                return await self._parse_medication_with_llm(transcription)
            except Exception as e:
                logger.error(f"LLM medication extraction failed: {e}")
        return {"name": None, "dosage": "", "frequency_text": "", "times": [], "confidence": "low"}

    async def parse_medication_audio(
        self,
        audio_content: bytes,
        filename: str,
        content_type: Optional[str] = None,
    ) -> dict:
        """Transcribe audio and extract the new medication in one step."""
        transcription, _meta = await self.transcribe_audio(audio_content, filename, content_type=content_type)
        if not transcription:
            return {"name": None, "dosage": "", "frequency_text": "", "times": [], "confidence": "low", "transcription": ""}
        result = await self.parse_medication_intent(transcription)
        result["transcription"] = transcription
        return result


# Singleton instance
_voice_parsing_service: Optional[VoiceParsingService] = None

def get_voice_parsing_service() -> VoiceParsingService:
    """Get or create the voice parsing service singleton."""
    global _voice_parsing_service
    if _voice_parsing_service is None:
        _voice_parsing_service = VoiceParsingService()
    return _voice_parsing_service
