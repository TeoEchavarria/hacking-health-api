"""
Voice parsing service for blood pressure readings.

Uses OpenAI to extract BP values from natural language transcriptions.
Supports both text transcriptions and audio files (via Whisper STT).
"""
import os
import re
import json
from openai import AsyncOpenAI
from typing import Optional, BinaryIO
from src._config.logger import get_logger

logger = get_logger(__name__)

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
    
    async def transcribe_audio(self, audio_content: bytes, filename: str) -> str:
        """
        Transcribe audio to text using OpenAI Whisper.
        
        Args:
            audio_content: Audio file bytes
            filename: Original filename (for format detection)
            
        Returns:
            Transcribed text in Spanish
        """
        if not self.client:
            raise ValueError("OpenAI client not configured - cannot transcribe audio")
        
        logger.info(f"Transcribing audio file: {filename}, size: {len(audio_content)} bytes")
        
        # Whisper API accepts file tuples
        response = await self.client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, audio_content),
            language="es",  # Spanish
            response_format="text"
        )
        
        transcription = response.strip() if isinstance(response, str) else str(response).strip()
        logger.info(f"Transcription result ({len(transcription)} chars): {transcription[:100]}...")
        return transcription
    
    async def parse_audio(self, audio_content: bytes, filename: str) -> dict:
        """
        Transcribe audio and parse BP values in one step.
        
        Args:
            audio_content: Audio file bytes
            filename: Original filename
            
        Returns:
            dict with: systolic, diastolic, pulse, device_classification, confidence, transcription
        """
        # Step 1: Transcribe audio to text
        transcription = await self.transcribe_audio(audio_content, filename)
        
        if not transcription:
            return {
                "systolic": None,
                "diastolic": None,
                "pulse": None,
                "device_classification": None,
                "confidence": "low",
                "transcription": ""
            }
        
        # Step 2: Parse transcription for BP values
        result = await self.parse_transcription(transcription)
        
        # Include transcription in result for display/verification
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
