"""Herramientas (tools) que puede usar Sofia: ver agenda, reservar en Cal.com, calificar leads.
Cada tool tiene: (1) un schema para Claude y (2) una funcion async que la ejecuta."""
from datetime import datetime, timedelta, timezone

import httpx

from config import CAL_API_KEY, CAL_EVENT_TYPE_ID, TIMEZONE, CAL_LINK

_CAL = "https://api.cal.com/v2"
_DIAS_ES = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]


# ---------- Schemas que ve Claude ----------
SCHEMAS = [
    {
        "name": "consultar_disponibilidad",
        "description": (
            "Devuelve los proximos turnos libres para el diagnostico gratuito. "
            "Usala cuando la persona quiere agendar, para ofrecerle horarios REALES. "
            "Nunca inventes horarios: ofrece solo los que devuelve esta herramienta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {"type": "integer", "description": "Cuantos dias hacia adelante mirar (default 7)"}
            },
        },
    },
    {
        "name": "agendar_diagnostico",
        "description": (
            "Reserva el turno del diagnostico gratuito en el calendario. "
            "SOLO usala cuando ya tenes el NOMBRE, el EMAIL y el horario elegido. "
            "El parametro 'inicio' debe ser EXACTAMENTE el valor 'inicio' de un turno que "
            "devolvio consultar_disponibilidad. Si te falta el email, pedilo ANTES de reservar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre de la persona"},
                "email": {"type": "string", "description": "Email para la confirmacion"},
                "inicio": {"type": "string", "description": "El 'inicio' exacto (ISO UTC) del turno elegido"},
                "notas": {"type": "string", "description": "Resumen para el equipo: empresa, rubro, que necesita y como lo maneja hoy"},
            },
            "required": ["nombre", "email", "inicio"],
        },
    },
    {
        "name": "calificar_lead",
        "description": (
            "Evalua que tan caliente es el prospecto segun rubro, presupuesto mensual aprox "
            "en USD y urgencia. Usala cuando tengas esos datos, para priorizar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rubro": {"type": "string"},
                "presupuesto_usd": {"type": "integer"},
                "urgencia": {"type": "string", "enum": ["alta", "media", "baja"]},
            },
            "required": ["rubro", "presupuesto_usd", "urgencia"],
        },
    },
]


# ---------- Implementaciones ----------
async def consultar_disponibilidad(dias: int = 7) -> str:
    hoy = datetime.now(timezone.utc).date()
    params = {
        "eventTypeId": CAL_EVENT_TYPE_ID,
        "start": hoy.isoformat(),
        "end": (hoy + timedelta(days=dias or 7)).isoformat(),
        "timeZone": TIMEZONE,
    }
    headers = {"Authorization": f"Bearer {CAL_API_KEY}", "cal-api-version": "2024-09-04"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{_CAL}/slots", headers=headers, params=params)
    if r.status_code != 200:
        return f"No pude consultar la agenda (error {r.status_code}). Pasale el link: {CAL_LINK}"

    data = r.json().get("data", {}) or {}
    lineas = []
    for fecha in sorted(data.keys()):
        for slot in data[fecha][:2]:  # max 2 por dia para no abrumar
            local = datetime.fromisoformat(slot["start"])
            utc = local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            etiqueta = f"{_DIAS_ES[local.weekday()]} {local.strftime('%d/%m')} a las {local.strftime('%H:%M')}"
            lineas.append(f"- {etiqueta}  (inicio: {utc})")
        if len(lineas) >= 6:
            break
    if not lineas:
        return f"No hay turnos libres en los proximos {dias or 7} dias. Pasale el link: {CAL_LINK}"
    return ("Turnos libres (ofrecele el dia/hora; para reservar usa el campo 'inicio' tal cual):\n"
            + "\n".join(lineas))


async def agendar_diagnostico(nombre: str, email: str, inicio: str, notas: str = "") -> str:
    body = {
        "start": inicio,
        "eventTypeId": int(CAL_EVENT_TYPE_ID),
        "attendee": {"name": nombre, "email": email, "timeZone": TIMEZONE},
    }
    if notas:
        # Queda en la nota de la reserva -> el equipo llega con contexto a la charla.
        body["bookingFieldsResponses"] = {"notes": notas}
    headers = {
        "Authorization": f"Bearer {CAL_API_KEY}",
        "cal-api-version": "2026-02-25",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{_CAL}/bookings", headers=headers, json=body)
    if r.status_code in (200, 201):
        d = r.json().get("data", {})
        ini = d.get("start", inicio)
        try:
            local = datetime.fromisoformat(ini.replace("Z", "+00:00")).astimezone()
            cuando = f"{_DIAS_ES[local.weekday()]} {local.strftime('%d/%m a las %H:%M')}"
        except Exception:
            cuando = ini
        return f"RESERVA CONFIRMADA para {nombre} el {cuando}. Le llega la confirmacion al mail {email}."
    return (f"No se pudo reservar (error {r.status_code}: {r.text[:200]}). "
            f"Quiza el horario ya se ocupo; ofrecele otro o pasale el link: {CAL_LINK}")


async def calificar_lead(rubro: str, presupuesto_usd: int, urgencia: str) -> str:
    puntaje = 0
    if presupuesto_usd >= 300:
        puntaje += 40
    elif presupuesto_usd >= 100:
        puntaje += 20
    if urgencia.lower() in ("alta", "urgente"):
        puntaje += 40
    elif urgencia.lower() == "media":
        puntaje += 20
    if rubro:
        puntaje += 20
    categoria = "caliente" if puntaje >= 70 else "templado" if puntaje >= 40 else "frio"
    return f"Lead {categoria} (puntaje {puntaje}/100). Rubro: {rubro}, presupuesto: {presupuesto_usd} USD, urgencia: {urgencia}."


# Mapa nombre -> funcion, para el loop del agente
EJECUTORES = {
    "consultar_disponibilidad": consultar_disponibilidad,
    "agendar_diagnostico": agendar_diagnostico,
    "calificar_lead": calificar_lead,
}


async def ejecutar(nombre: str, args: dict) -> str:
    fn = EJECUTORES.get(nombre)
    if not fn:
        return f"Herramienta desconocida: {nombre}"
    try:
        return await fn(**args)
    except Exception as e:
        return f"Error ejecutando {nombre}: {e}"