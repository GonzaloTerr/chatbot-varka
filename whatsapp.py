"""Enviar/recibir por la WhatsApp Cloud API oficial de Meta (Graph API).
Reemplaza a waha.py. Incluye indicador de 'escribiendo...' y descarga de media
(audios), que en Meta van por media_id y no por URL directa."""
import asyncio

import httpx

from config import GRAPH_API_VERSION, WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID

_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
_MESSAGES = f"{_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
_AUTH = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
_HEADERS = {**_AUTH, "Content-Type": "application/json"}


async def enviar_texto(to: str, texto: str) -> None:
    """`to` es el wa_id del destinatario (ej '5491144049400'), tal como llega en el webhook."""
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(_MESSAGES, headers=_HEADERS, json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": texto},
        })


async def _marcar_leido_y_tipeando(message_id: str) -> None:
    """Marca el mensaje entrante como leido y muestra 'escribiendo...'. Best-effort:
    si falla, no interrumpe el envio. Meta lo apaga solo al llegar la respuesta."""
    if not message_id:
        return
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            await client.post(_MESSAGES, headers=_HEADERS, json={
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
                "typing_indicator": {"type": "text"},
            })
        except Exception:
            pass


async def enviar_con_tipeo(to: str, texto: str, message_id: str = "") -> None:
    """Muestra 'escribiendo...' y espera una pausa proporcional al largo, para que
    parezca humano (no responde instantaneo). Despues envia el texto."""
    demora = min(1.2 + len(texto) / 26, 5.0)  # entre ~1s y 5s segun el largo
    await _marcar_leido_y_tipeando(message_id)
    await asyncio.sleep(demora)
    await enviar_texto(to, texto)


async def descargar_media(media_id: str) -> bytes:
    """Baja un archivo de media de WhatsApp en dos pasos (ambos con el token):
    1) GET /{media_id} -> devuelve una URL temporal; 2) GET esa URL -> los bytes.
    Devuelve b'' si algo falla."""
    if not media_id:
        return b""
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"{_BASE}/{media_id}", headers=_AUTH)
        if r.status_code != 200:
            return b""
        url = r.json().get("url")
        if not url:
            return b""
        d = await client.get(url, headers=_AUTH)  # la descarga tambien requiere auth
        return d.content if d.status_code == 200 else b""