"""Memoria de conversacion en Supabase (tabla 'conversaciones').
Es la MISMA tabla que escribe el flujo n8n ventas-maps, asi que el agente
retoma conversaciones que Varka inicio por ventas salientes (match por phone_key)."""
import httpx
from config import SUPABASE_URL, SUPABASE_KEY

_BASE = f"{SUPABASE_URL}/rest/v1/conversaciones"
_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


async def cargar_historial(phone_key: str, limite: int = 10) -> list[dict]:
    """Devuelve los ultimos intercambios [{mensaje, respuesta}, ...] en orden cronologico."""
    params = {
        "remote_jid": f"eq.{phone_key}",
        "order": "created_at.asc",
        "limit": str(limite),
        "select": "mensaje,respuesta",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(_BASE, headers=_HEADERS, params=params)
        filas = r.json() if r.status_code == 200 else []
    return [f for f in filas if f.get("mensaje") and f.get("respuesta")]


async def guardar(phone_key: str, push_name: str, mensaje: str, respuesta: str) -> None:
    headers = {**_HEADERS, "Prefer": "return=minimal"}
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(
            _BASE,
            headers=headers,
            json={
                "remote_jid": phone_key,
                "push_name": push_name,
                "mensaje": mensaje,
                "respuesta": respuesta,
            },
        )
