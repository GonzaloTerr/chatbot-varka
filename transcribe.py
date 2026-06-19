"""Transcripcion de notas de voz con Groq Whisper (gratis, sin tarjeta).
Descarga el audio de WAHA y lo manda a Groq."""
import httpx

from config import GROQ_API_KEY, WAHA_API_KEY

_GROQ = "https://api.groq.com/openai/v1/audio/transcriptions"


async def transcribir_audio(audio_url: str) -> str:
    if not GROQ_API_KEY:
        return ""
    async with httpx.AsyncClient(timeout=60) as client:
        # 1) bajar el audio de WAHA
        r = await client.get(audio_url, headers={"X-Api-Key": WAHA_API_KEY})
        if r.status_code != 200:
            return ""
        audio = r.content
        # 2) mandarlo a Groq. OJO: el nombre debe terminar en .ogg (Groq rechaza .oga)
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
