"""Enviar mensajes a WhatsApp via WAHA (mismo endpoint que usa n8n)."""
import asyncio

import httpx

from config import WAHA_URL, WAHA_API_KEY, WAHA_SESSION

HEADERS = {"X-Api-Key": WAHA_API_KEY, "Content-Type": "application/json"}


async def enviar_texto(chat_id: str, texto: str) -> None:
    """chat_id es el 'from' original de WhatsApp (ej '549...@c.us')."""
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(
            f"{WAHA_URL}/api/sendText",
            headers=HEADERS,
            json={"session": WAHA_SESSION, "chatId": chat_id, "text": texto},
        )


async def enviar_con_tipeo(chat_id: str, texto: str) -> None:
    """Muestra 'escribiendo...' y espera una pausa proporcional al largo, para
    que parezca humano (no responde instantaneo). Despues envia el texto."""
    demora = min(1.8 + len(texto) / 22, 7.0)  # entre ~2s y 7s segun el largo
    body = {"session": WAHA_SESSION, "chatId": chat_id}
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            await client.post(f"{WAHA_URL}/api/startTyping", headers=HEADERS, json=body)
            await asyncio.sleep(demora)
            await client.post(f"{WAHA_URL}/api/stopTyping", headers=HEADERS, json=body)
        except Exception:
            pass  # si el indicador falla, igual mandamos el mensaje
        await client.post(
            f"{WAHA_URL}/api/sendText",
            headers=HEADERS,
            json={"session": WAHA_SESSION, "chatId": chat_id, "text": texto},
        )
