"""Herramientas (tools) que puede usar Sofia: ver agenda, reservar en Cal.com, calificar leads.
Cada tool tiene: (1) un schema para Claude y (2) una funcion async que la ejecuta."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from config import CAL_API_KEY, CAL_EVENT_TYPE_ID, TIMEZONE, CAL_LINK

_CAL = "https://api.cal.com/v2"
_DIAS_ES = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]


# ---------- Schemas que ve Claude ----------
SCHEMAS = [
    {
        "name": "consultar_disponibilidad",
        "description": (
            "Devuelve 2 turnos libres para el diagnostico gratuito. "
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
            "No hace falta volver a consultar la agenda: esta herramienta verifica sola que el "
            "turno siga libre. Si te falta el email, pedilo ANTES de reservar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre de la persona"},
                "email": {"type": "string", "description": "Email para la confirmacion"},
                "inicio": {"type": "string", "description": "Fecha y hora del turno elegido, hora de Argentina, formato AAAA-MM-DDTHH:MM (ej: 2026-10-22T09:00)"},
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
def _etiqueta(local: datetime) -> str:
    return f"{_DIAS_ES[local.weekday()]} {local.strftime('%d/%m')} a las {local.strftime('%H:%M')}"


def _inicio(local: datetime) -> str:
    """El 'inicio' que ve el modelo: hora de Argentina, sin zona ni segundos."""
    return local.strftime("%Y-%m-%dT%H:%M")


def _a_local(inicio: str) -> datetime:
    """Acepta '2026-10-22T09:00' (hora local) o un ISO con zona ('...Z'), y lo devuelve
    en TIMEZONE al minuto."""
    dt = datetime.fromisoformat(inicio.strip().replace("Z", "+00:00"))
    tz = ZoneInfo(TIMEZONE)
    dt = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
    return dt.replace(second=0, microsecond=0)


def _dos_turnos(turnos: list[datetime]) -> list[datetime]:
    """El primer turno de cada uno de los dos primeros dias con lugar. Que ofrezca
    exactamente 2 lo garantiza esto y no el prompt: Haiku ofrecia los 4 (21/10)."""
    elegidos, dias = [], set()
    for t in turnos:
        if t.date() not in dias:
            dias.add(t.date())
            elegidos.append(t)
        if len(elegidos) == 2:
            break
    return elegidos


async def _turnos_libres(dias: int = 7) -> list[datetime] | None:
    """Todos los turnos libres de los proximos 'dias', en TIMEZONE. None si Cal.com falla."""
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
        return None
    data = r.json().get("data", {}) or {}
    tz = ZoneInfo(TIMEZONE)
    return sorted(datetime.fromisoformat(s["start"]).astimezone(tz)
                  for fecha in data for s in data[fecha])


def _lista(turnos: list[datetime]) -> str:
    return "\n".join(f"- {_etiqueta(t)}  (inicio: {_inicio(t)})" for t in turnos)


async def consultar_disponibilidad(dias: int = 7) -> str:
    turnos = await _turnos_libres(dias)
    if turnos is None:
        return f"No pude consultar la agenda. Pasale el link: {CAL_LINK}"
    if not turnos:
        return f"No hay turnos libres en los proximos {dias or 7} dias. Pasale el link: {CAL_LINK}"
    return ("Turnos libres. Ofrecele EXACTAMENTE estos 2, no otros. Para reservar, usa "
            "agendar_diagnostico con el 'inicio' del que elija:\n" + _lista(_dos_turnos(turnos)))


async def agendar_diagnostico(nombre: str, email: str, inicio: str, notas: str = "") -> str:
    # El modelo no ve los resultados de herramientas de mensajes anteriores, y antes se le
    # pedia volver a consultar la agenda para copiar el 'inicio' exacto. Haiku consultaba
    # y cortaba ahi, sin reservar, y volvia a pedir el email (21/10). Ahora el turno se
    # busca aca: el modelo solo pasa la fecha y hora que eligio la persona.
    try:
        pedido = _a_local(inicio)
    except ValueError:
        return (f"No entendi el horario '{inicio}'. Usa el formato AAAA-MM-DDTHH:MM "
                "(ej: 2026-10-22T09:00), en hora de Argentina.")
    dias = min(max(7, (pedido.date() - datetime.now(timezone.utc).date()).days + 2), 30)
    turnos = await _turnos_libres(dias)
    if turnos is None:
        return f"No pude consultar la agenda para reservar. Pasale el link: {CAL_LINK}"
    turno = next((t for t in turnos if t.replace(second=0, microsecond=0) == pedido), None)
    if turno is None:
        otros = _dos_turnos([t for t in turnos if t > datetime.now(ZoneInfo(TIMEZONE))])
        if not otros:
            return f"Ese horario ya no esta libre y no hay otros. Pasale el link: {CAL_LINK}"
        return ("Ese horario ya no esta libre. NO esta reservado. Ofrecele estos 2:\n"
                + _lista(otros))
    body = {
        "start": turno.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
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
        ini = d.get("start", body["start"])
        try:
            # A TIMEZONE explicito: .astimezone() sin argumento usa la zona del sistema,
            # que en el contenedor es UTC, y confirmaba las 16:00 como "a las 19:00".
            local = datetime.fromisoformat(ini.replace("Z", "+00:00")).astimezone(ZoneInfo(TIMEZONE))
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