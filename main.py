"""Webhook que recibe los mensajes de WhatsApp (Cloud API de Meta) y dispara al
agente. Maneja texto y voz (Groq), agrupa mensajes rapidos (debounce) y responde
con indicador de 'escribiendo...'."""
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

import agent
import debounce
import memory
import transcribe
import whatsapp
from config import WHATSAPP_VERIFY_TOKEN

app = FastAPI(title="Chatbot Varka")


@app.get("/")
async def health():
    return {"status": "ok"}


@app.get("/webhook")
async def verificar(request: Request):
    """Verificacion que exige Meta al configurar el webhook: si el token coincide,
    hay que devolver el hub.challenge tal cual, como texto plano."""
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(p.get("hub.challenge", ""))
    return Response(status_code=403)


async def _procesar(to: str, phone: str, push: str, texto: str, msg_id: str) -> None:
    """Se ejecuta UNA vez por bloque de mensajes (despues del debounce).
    `to` es el wa_id al que se responde; `phone` es la clave canonica de memoria."""
    historial = await memory.cargar_historial(phone)
    respuesta = await agent.responder(historial, texto, push)
    if respuesta:
        await whatsapp.enviar_con_tipeo(to, respuesta, msg_id)  # "escribiendo..." + pausa humana
        await memory.guardar(phone, push, texto, respuesta)


@app.post("/webhook")
async def webhook(req: Request):
    body = await req.json()

    # Estructura de Meta: entry[].changes[].value  (puede traer messages y/o statuses)
    try:
        value = body["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return {"ok": True, "skip": "sin value"}

    mensajes = value.get("messages")
    if not mensajes:
        return {"ok": True, "skip": "no es entrante"}  # ignora statuses (sent/delivered/read)

    # Nombre del contacto (viene aparte de los mensajes)
    contactos = value.get("contacts") or []
    push = "Cliente"
    if contactos:
        push = ((contactos[0].get("profile") or {}).get("name")) or "Cliente"

    for msg in mensajes:
        wa_id = msg.get("from", "")   # ej '5491144049400' -> a este wa_id se le responde
        msg_id = msg.get("id", "")
        tipo = msg.get("type")

        # phone_key canonico (54 + area + numero, SIN el 9) para la memoria
        # compartida con los flujos n8n (match por remote_jid).
        phone = "".join(ch for ch in wa_id if ch.isdigit())
        if phone.startswith("549"):
            phone = "54" + phone[3:]

        # --- Texto, o transcripcion si es nota de voz ---
        texto = ""
        if tipo == "text":
            texto = ((msg.get("text") or {}).get("body") or "").strip()
        elif tipo == "audio":
            media_id = (msg.get("audio") or {}).get("id")
            audio = await whatsapp.descargar_media(media_id)
            trans = await transcribe.transcribir_bytes(audio)
            if trans:
                texto = "[Nota de voz]: " + trans
        if not texto:
            continue  # ignora tipos no soportados (imagenes, stickers, ubicacion, etc.)

        # --- Debounce: agrupa mensajes rapidos y responde una vez ---
        await debounce.encolar(phone, wa_id, push, texto, _procesar, msg_id)

    return {"ok": True}