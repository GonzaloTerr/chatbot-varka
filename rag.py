"""RAG: recupera de la base de conocimiento de Varka (Supabase pgvector) los
fragmentos mas relevantes para la consulta, para que Sofia responda con datos exactos.

Es tolerante a fallos: si falta la clave, o Voyage/Supabase fallan, devuelve "" y
Sofia sigue respondiendo con su system prompt (no rompe la conversacion)."""
import asyncio
import logging

import httpx

from config import SUPABASE_URL, SUPABASE_KEY, VOYAGE_API_KEY, MODEL_EMBED

log = logging.getLogger("rag")

_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_RPC_URL = f"{SUPABASE_URL}/rest/v1/rpc/match_kb"


async def _embed(texto: str) -> list[float] | None:
    if not VOYAGE_API_KEY:
        return None
    async with httpx.AsyncClient(timeout=15) as c:
        # Un reintento si Voyage devuelve 429 (rate limit del plan free, ~3/min).
        for intento in range(2):
            r = await c.post(
                _VOYAGE_URL,
                headers={"Authorization": f"Bearer {VOYAGE_API_KEY}"},
                json={"input": [texto], "model": MODEL_EMBED, "input_type": "query"},
            )
            if r.status_code == 200:
                return r.json()["data"][0]["embedding"]
            if r.status_code == 429 and intento == 0:
                log.warning("Voyage 429 (rate limit del plan free): reintento en 2s")
                await asyncio.sleep(2)
                continue
            log.warning("Voyage fallo con %s: se responde SIN base de conocimiento", r.status_code)
            return None
    return None


async def buscar_contexto(texto: str, k: int = 4) -> str:
    """Devuelve los k fragmentos mas relevantes concatenados, o "" si no hay o falla."""
    try:
        emb = await _embed(texto)
        if emb is None:
            if not VOYAGE_API_KEY:
                log.warning("RAG apagado: falta VOYAGE_API_KEY")
            return ""
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(_RPC_URL, headers=headers,
                             json={"query_embedding": emb, "match_count": k})
        if r.status_code != 200:
            log.warning("Supabase respondio %s: se responde SIN base de conocimiento", r.status_code)
            return ""
        filas = r.json()
        if not filas:
            log.info("RAG sin coincidencias para: %.80s", texto)
            return ""
        return "\n\n".join(f["contenido"] for f in filas if f.get("contenido"))
    except Exception as e:
        log.warning("RAG fallo (%s): se responde SIN base de conocimiento", e)
        return ""