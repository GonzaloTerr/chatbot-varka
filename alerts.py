"""Alerta interna de Sofia. Si el procesamiento de un mensaje falla (Anthropic
caido, token de WhatsApp vencido, Supabase inaccesible, etc.), avisa por email via
Resend. Es best-effort: nunca lanza excepcion (si el aviso mismo falla, solo loguea)
y tiene un cooldown para no inundar la casilla si el error se repite en cada mensaje."""
import logging
import time
import traceback

import httpx

from config import RESEND_API_KEY, ALERT_EMAIL

log = logging.getLogger("alerts")

_RESEND_URL = "https://api.resend.com/emails"
_COOLDOWN_S = 600  # no reenviar el mismo tipo de error mas de una vez cada 10 min
_ultimo_envio: dict[str, float] = {}  # tipo_de_error -> timestamp del ultimo aviso


async def avisar_error(contexto: str, error: Exception) -> None:
    """Manda un mail de alerta con el contexto y el traceback. Silencioso ante fallos."""
    if not RESEND_API_KEY:
        log.warning("RESEND_API_KEY sin configurar; no se envia alerta por email")
        return

    # Cooldown por tipo de excepcion: evita el flood si TODOS los mensajes fallan.
    clave = type(error).__name__
    ahora = time.time()
    if ahora - _ultimo_envio.get(clave, 0) < _COOLDOWN_S:
        return
    _ultimo_envio[clave] = ahora

    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    html = (
        "<h2>&#128308; Sofia fallo procesando un mensaje</h2>"
        f"<p><b>Contexto:</b> {contexto}</p>"
        f"<p><b>Error:</b> {type(error).__name__}: {error}</p>"
        f"<pre style='background:#f4f4f4;padding:10px;overflow:auto'>{tb}</pre>"
        "<p>Revisar el contenedor de Sofia en EasyPanel "
        "(varka-chatbot-varka.qonisd.easypanel.host).</p>"
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                _RESEND_URL,
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "Varka Alertas <consultas@varka.tech>",
                    "to": [ALERT_EMAIL],
                    "subject": "\U0001f534 Sofia: error procesando un mensaje",
                    "html": html,
                },
            )
            if r.status_code >= 300:
                log.error("Resend rechazo la alerta (HTTP %s): %s", r.status_code, r.text)
    except Exception:
        log.exception("No se pudo enviar la alerta por email")