"""Webhook que recibe los mensajes de WhatsApp (via WAHA) y dispara al agente.
Maneja texto y voz (Groq), agrupa mensajes rapidos (debounce) y responde con
indicador de 'escribiendo...'."""
from fastapi import FastAPI, Request

import agent
import debounce
import memory
import transcribe
import waha
from config import WAHA_URL

app = FastAPI(title="Chatbot Varka")

WAHA_LOCAL = "http://localhost:3000"
WAHA_PUB = WAHA_URL  # host publico de WAHA (se configura por variable de entorno)


@app.get("/")
async def health():
    return {"status": "ok"}


async def _procesar(frm: str, phone: str, push: str, texto: str) -> None:
    """Se ejecuta UNA vez por bloque de mensajes (despues del debounce)."""
    historial = await memory.cargar_historial(phone)
    respuesta = await agent.responder(historial, texto, push)
    if respuesta:
        await waha.enviar_con_tipeo(frm, respuesta)  # "escribiendo..." + pausa humana
        await memory.guardar(phone, push, texto, respuesta)


@app.post("/webhook")
async def webhook(req: Request):
    body = await req.json()
    payload = body.get("payload") or {}

    # --- Filtros (igual que el nodo n8n 'Filtrar Mensajes') ---
    if body.get("event") != "message":
        return {"ok": True, "skip": "no es message"}
    if payload.get("fromMe"):
        return {"ok": True, "skip": "propio"}
    frm = payload.get("from", "")
    if "@g.us" in frm:
        return {"ok": True, "skip": "grupo"}

    # --- Extraer phone_key canonico (resuelve @lid -> numero real) ---
    jid = frm
    alt = (((payload.get("_data") or {}).get("key") or {}).get("remoteJidAlt")) or ""
    if "@lid" in jid and alt:
        jid = alt
    phone = "".join(ch for ch in jid.split("@")[0] if ch.isdigit())
    if phone.startswith("549"):
        phone = "54" + phone[3:]  # canonico: 54 + area + numero, sin el 9

    push = ((payload.get("_data") or {}).get("notifyName")
            or (payload.get("_data") or {}).get("pushName")
            or "Cliente")

    # --- Texto, o transcripcion si es nota de voz ---
    texto = (payload.get("body") or "").strip()
    if not texto:
        media = payload.get("media") or {}
        mime = media.get("mimetype") or ""
        msg = (payload.get("_data") or {}).get("message") or {}
        es_audio = bool(msg.get("audioMessage")) or mime.startswith("audio")
        if es_audio and media.get("url"):
            audio_url = media["url"].replace(WAHA_LOCAL, WAHA_PUB)
            trans = await transcribe.transcribir_audio(audio_url)
            if trans:
                texto = "[Nota de voz]: " + trans
    if not texto:
        return {"ok": True, "skip": "sin texto"}

    # --- Debounce: agrupa mensajes rapidos y responde una vez ---
    await debounce.encolar(phone, frm, push, texto, _procesar)
    return {"ok": True}
