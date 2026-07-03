"""Transcripcion de notas de voz con Groq Whisper (gratis, sin tarjeta).
Recibe los bytes del audio (ya descargado de WhatsApp) y los manda a Groq."""
import httpx

from config import GROQ_API_KEY

_GROQ = "https://api.groq.com/openai/v1/audio/transcriptions"


async def transcribir_bytes(audio: bytes) -> str:
    """`audio` son los bytes crudos del audio (ogg/opus de WhatsApp)."""
    if not GROQ_API_KEY or not audio:
        return ""
    async with httpx.AsyncClient(timeout=60) as client:
        # OJO: el nombre debe terminar en .ogg (Groq rechaza .oga)
        files = {"file": ("audio.ogg", audio, "audio/ogg")}
        data = {"model": "whisper-large-v3", "language": "es"}
        gr = await client.post(
            _GROQ,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files=files,
            data=data,
        )
        if gr.status_code != 200:
            return ""
        return (gr.json().get("text") or "").strip()