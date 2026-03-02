import base64
import io
import logging

from openai import OpenAI

logger = logging.getLogger(__name__)

_client = OpenAI()


def transcribe_audio(audio_base64: str) -> str:
    """Transcreve áudio base64 para texto usando OpenAI Whisper."""
    audio_bytes = base64.b64decode(audio_base64)
    buf = io.BytesIO(audio_bytes)
    buf.name = "audio.ogg"

    logger.info("Transcrevendo áudio (%d bytes)...", len(audio_bytes))
    transcript = _client.audio.transcriptions.create(
        model="whisper-1",
        file=buf,
        language="pt",
    )
    logger.info("Transcrição concluída: %.100s", transcript.text)
    return transcript.text
