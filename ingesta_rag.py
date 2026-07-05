"""Ingesta la base de conocimiento (conocimiento/varka_kb.md) a Supabase pgvector.

Corta el corpus por secciones (##), genera un embedding por seccion con Voyage y
reemplaza el contenido de la tabla kb_varka.

Correr UNA vez despues de crear la tabla (rag_setup.sql), y cada vez que edites el
corpus:   python ingesta_rag.py
"""
import re
import pathlib

import httpx

from config import SUPABASE_URL, SUPABASE_KEY, VOYAGE_API_KEY, MODEL_EMBED

KB = pathlib.Path(__file__).parent / "conocimiento" / "varka_kb.md"
_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_TABLA = f"{SUPABASE_URL}/rest/v1/kb_varka"
_H = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def trocear(texto: str) -> list[dict]:
    """Un chunk por cada encabezado de nivel 2 (##). Ignora los de nivel 1 (# grupo)."""
    bloques = re.split(r"^## ", texto, flags=re.M)
    chunks = []
    for b in bloques[1:]:  # el [0] es el preambulo antes del primer ##
        partes = b.strip().split("\n", 1)
        seccion = partes[0].strip()
        cuerpo = partes[1].strip() if len(partes) > 1 else ""
        contenido = f"{seccion}\n{cuerpo}".strip()
        if contenido:
            chunks.append({"seccion": seccion, "contenido": contenido})
    return chunks


def embed(textos: list[str]) -> list[list[float]]:
    r = httpx.post(
        _VOYAGE_URL,
        timeout=60,
        headers={"Authorization": f"Bearer {VOYAGE_API_KEY}"},
        json={"input": textos, "model": MODEL_EMBED, "input_type": "document"},
    )
    r.raise_for_status()
    return [d["embedding"] for d in r.json()["data"]]


def main() -> None:
    if not VOYAGE_API_KEY:
        raise SystemExit("Falta VOYAGE_API_KEY en el entorno (.env o EasyPanel).")

    chunks = trocear(KB.read_text(encoding="utf-8"))
    print(f"{len(chunks)} secciones encontradas. Generando embeddings con {MODEL_EMBED}...")

    vectores = embed([c["contenido"] for c in chunks])
    filas = [
        {"seccion": c["seccion"], "contenido": c["contenido"], "embedding": v}
        for c, v in zip(chunks, vectores)
    ]

    # Vaciar la tabla y reinsertar (idempotente: podes correrlo cuantas veces quieras).
    httpx.delete(f"{_TABLA}?id=gt.0", headers=_H, timeout=30)
    r = httpx.post(_TABLA, headers={**_H, "Prefer": "return=minimal"}, json=filas, timeout=60)
    r.raise_for_status()
    print(f"Listo: {len(filas)} fragmentos cargados en kb_varka.")


if __name__ == "__main__":
    main()