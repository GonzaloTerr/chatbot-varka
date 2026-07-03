"""Enviar/recibir por la WhatsApp Cloud API oficial de Meta (Graph API).
Reemplaza a waha.py. Incluye indicador de 'escribiendo...' y descarga de media
(audios), que en Meta van por media_id y no por URL directa."""
import asyncio
import logging

import httpx

from config import GRAPH_API_VERSION, WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID

log = logging.getLogger("whatsapp")

_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
_MESSAGES = f"{_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
_AUTH = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
_HEADERS = {**_AUTH, "Content-Type": "application/json"}


def _formato_ar_15(to: str) -> str:
    """Formato alternativo SOLO para el numero de prueba de Meta. Su lista de
    destinatarios autorizados guarda los moviles argentinos en el viejo formato
    con '15' (54 + area + 15 + numero), pero el webhook entrega el wa_id canonico
    (549 + area + numero). Si respondemos al canonico, el numero de prueba rechaza
    con 131030. Devuelve el equivalente con '15' para reintentar; '' si no aplica.
    En un numero de PRODUCCION el envio al wa_id canonico sale a la primera y este
    reintento nunca se dispara."""
    if to.startswith("549") and len(to) == 13:   # 549 + area(2, CABA=11) + numero(8)
        return "54" + to[3:5] + "15" + to[5:]
    return ""


async def _post_texto(client: httpx.AsyncClient, to: str, texto: str) -> httpx.Response:
    return await client.post(_MESSAGES, headers=_HEADERS, json={
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": texto},
    })


async def enviar_texto(to: str, texto: str) -> None:
    """`to` es el wa_id del destinatario (ej '5491144049400'), tal como llega en el webhook."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await _post_texto(client, to, texto)
        if r.status_code == 200:
            return
        # Reintento en formato '15' por si es el numero de prueba con un movil AR.
        alt = _formato_ar_15(to)
        if alt:
            r_alt = await _post_texto(client, alt, texto)
            if r_alt.status_code == 200:
                return
            r = r_alt
        # Meta rechazo el envio (401 token, 131030 no autorizado, etc.). Antes esto
        # se tragaba en silencio y quedabamos a ciegas: ahora queda en el log.
        log.error("Fallo el envio a %s (HTTP %s): %s", to, r.status_code, r.text)


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