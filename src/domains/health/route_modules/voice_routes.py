"""
Voice and Audio Parsing Routes.

Handles:
- Voice transcription parsing for BP extraction
- Audio file upload and STT (Speech-to-Text) processing
- BP value extraction using LLM with regex fallback

Uses OpenAI Whisper for transcription and GPT for extraction.
Following Single Responsibility Principle (SRP).
"""
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from src.domains.health.schemas import VoiceParseRequest, VoiceParseResult, AudioParseResult
from src.domains.health.voice_parsing import get_voice_parsing_service
from src.domains.events.services import BiometricEventService
from src.domains.events.schemas import BiometricEventType
from src.domains.auth.routes import verify_token_jwt
from src._config.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/parse-bp-voice", response_model=VoiceParseResult)
async def parse_bp_voice(
    request: VoiceParseRequest,
    user_id: str = Depends(verify_token_jwt)
):
    """
    Parse a voice transcription to extract blood pressure values.

    Uses LLM (OpenAI) to extract BP values from natural language,
    with regex fallback for common patterns like "120/80".

    Returns extracted values with a confidence level:
    - "high": Both systolic and diastolic clearly detected
    - "low": Ambiguous or incomplete values
    """
    try:
        logger.info(f"Parsing BP voice transcription for user {user_id}: {request.transcription[:100]}...")

        service = get_voice_parsing_service()
        result = await service.parse_transcription(request.transcription)

        logger.info(f"Parse result: S={result.get('systolic')} D={result.get('diastolic')} conf={result.get('confidence')}")

        return VoiceParseResult(
            systolic=result.get("systolic"),
            diastolic=result.get("diastolic"),
            pulse=result.get("pulse"),
            device_classification=result.get("device_classification"),
            confidence=result.get("confidence", "low")
        )

    except Exception as e:
        logger.error(f"Error parsing BP voice: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse-bp-audio", response_model=AudioParseResult)
async def parse_bp_audio(
    audio: UploadFile = File(...),
    user_id: str = Depends(verify_token_jwt)
):
    """
    Parse an audio recording to extract blood pressure values.

    Flow:
    1. Accepts audio file (3GP, AAC, M4A, MP3, WAV, WEBM)
    2. Transcribes using OpenAI Whisper (Spanish)
    3. Extracts BP values using LLM
    4. Returns values + transcription for confirmation

    File limits:
    - Max size: 10MB
    - Max duration: ~30 seconds recommended
    """
    try:
        logger.info(f"Received audio upload from user {user_id}: {audio.filename}, type: {audio.content_type}")

        # Read audio content
        audio_content = await audio.read()

        # Validate file size
        if len(audio_content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=413, detail="Audio file too large (max 10MB)")

        if len(audio_content) < 1000:  # Minimum ~1KB
            raise HTTPException(status_code=400, detail="Audio file too small or empty")

        logger.info(f"Audio file size: {len(audio_content)} bytes")

        # Parse audio (transcribe + extract BP)
        service = get_voice_parsing_service()
        result = await service.parse_audio(audio_content, audio.filename or "recording.3gp")

        logger.info(
            f"Audio parse result: S={result.get('systolic')} D={result.get('diastolic')} "
            f"P={result.get('pulse')} conf={result.get('confidence')}"
        )

        # Register voice measurement event for notifications
        try:
            from src.core.database import db as db_instance
            database = db_instance.get_db()
            event_service = BiometricEventService(database)
            await event_service.register_biometric_event(
                patient_id=user_id,
                event_type=BiometricEventType.VOICE_MEASUREMENT.value,
                payload={
                    "transcription": result.get("transcription", ""),
                    "systolic": result.get("systolic"),
                    "diastolic": result.get("diastolic"),
                    "pulse": result.get("pulse"),
                    "confidence": result.get("confidence", "low")
                }
            )
        except Exception as e:
            logger.warning(f"Failed to register voice measurement event: {e}")

        return AudioParseResult(
            systolic=result.get("systolic"),
            diastolic=result.get("diastolic"),
            pulse=result.get("pulse"),
            device_classification=result.get("device_classification"),
            confidence=result.get("confidence", "low"),
            transcription=result.get("transcription", "")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error parsing BP audio: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
