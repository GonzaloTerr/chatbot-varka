"""Corre el eval de Sofia contra su codigo real (agent.responder).

Reemplaza en memoria, y solo mientras corre, lo que toca el mundo exterior:
  - Cal.com: agenda simulada; NUNCA se crea una reserva real.
  - RAG: contexto fijo por caso (secciones de varka_kb.md); no llama a Voyage,
    asi no le come la cuota a produccion.
  - LangFuse: apagado; las corridas no ensucian el proyecto de produccion.
  - Supabase: no se toca; el historial se arma en memoria.
Todo lo demas (prompt, modelo, loop de tools, guardas, _acortar) es el de produccion.

Uso (costos medidos el 24/09/2026 con Haiku 4.5 + juez Sonnet 5):
  # Compuerta antes de desplegar: 1 rep, sin juez, solo reglas duras. ~USD 0,20, ~1 min.
  python evals/correr.py --variant v1 --reps 1 --sin-juez --gate

  # Medicion completa de calidad: 3 reps + juez. ~USD 0,85, ~3 min.
  python evals/correr.py --variant baseline

  python evals/correr.py --casos in-hola,ag-completo --reps 1   # solo algunos casos
  python evals/correr.py --variant v1 --resumen                  # resumen de lo ya corrido, sin correr nada
  python evals/correr.py --variant v9 --reps 1 --sin-juez --sabotaje --gate
      # reemplaza a Sofia por respuestas malas, costo cero: la compuerta TIENE que fallar

Cada variante es una carpeta en evals/corridas/ (baseline, v1, v2...). Lo ya corrido
no se repite: si se corta, se vuelve a lanzar el mismo comando y sigue donde quedo.
Si se cambian los correctores o los casos, usar una variante nueva: los resultados
corregidos con reglas distintas no se pueden comparar.
"""
import argparse
import asyncio
import contextlib
import contextvars
import json
import math
import os
import pathlib
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# LangFuse apagado ANTES de importar config: load_dotenv no pisa variables que ya existen.
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI))
sys.stdout.reconfigure(encoding="utf-8")

import agent  # noqa: E402
import rag  # noqa: E402
import tools  # noqa: E402
import trazas  # noqa: E402
from config import MODEL, TIMEZONE  # noqa: E402
from ingesta_rag import KB, trocear  # noqa: E402

import graders  # noqa: E402
import juez  # noqa: E402

FLOW = AQUI / "corridas"
TECHO_S = 300          # techo de reloj por conversacion
CONCURRENCIA = 4
# Precios por millon de tokens (tabla oficial de la API, 24/09/2026).
PRECIOS = {"claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-5": (2.0, 10.0)}

_turno = contextvars.ContextVar("turno")      # dict del turno en curso
_contexto = contextvars.ContextVar("contexto")  # texto RAG del caso
_modo_cal = contextvars.ContextVar("modo_cal")


# ---------- Agenda simulada ----------

def _agenda() -> list[tuple[str, str]]:
    """Turnos de los proximos 3 dias habiles a las 09:00 y 10:00 (hora de Argentina).
    Devuelve [(etiqueta, inicio_utc)] con el mismo formato que la herramienta real."""
    tz = ZoneInfo(TIMEZONE)
    dia = datetime.now(tz).date()
    turnos = []
    while len(turnos) < 6:
        dia += timedelta(days=1)
        if dia.weekday() >= 5:
            continue
        for hora in (9, 10):
            local = datetime(dia.year, dia.month, dia.day, hora, tzinfo=tz)
            utc = local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            turnos.append((f"{tools._DIAS_ES[local.weekday()]} {local.strftime('%d/%m')} a las {local.strftime('%H:%M')}", utc))
    return turnos


AGENDA = _agenda()


async def _ejecutar(nombre: str, args: dict) -> str:
    if nombre == "consultar_disponibilidad":
        salida = ("Turnos libres (ofrecele el dia/hora; para reservar usa el campo 'inicio' tal cual):\n"
                  + "\n".join(f"- {e}  (inicio: {u})" for e, u in AGENDA))
    elif nombre == "agendar_diagnostico":
        inicio = args.get("inicio", "")
        if _modo_cal.get() == "falla" or inicio not in {u for _, u in AGENDA}:
            salida = ("No se pudo reservar (error 400: el horario no esta disponible). "
                      f"Quiza el horario ya se ocupo; ofrecele otro o pasale el link: {tools.CAL_LINK}")
        else:
            local = datetime.fromisoformat(inicio.replace("Z", "+00:00")).astimezone(ZoneInfo(TIMEZONE))
            cuando = f"{tools._DIAS_ES[local.weekday()]} {local.strftime('%d/%m a las %H:%M')}"
            salida = (f"RESERVA CONFIRMADA para {args.get('nombre')} el {cuando}. "
                      f"Le llega la confirmacion al mail {args.get('email')}.")
    else:
        salida = await tools.EJECUTORES[nombre](**args) if nombre in tools.EJECUTORES else f"Herramienta desconocida: {nombre}"
    _turno.get()["tools"].append({"nombre": nombre, "entrada": args, "salida": salida})
    return salida


async def _buscar(consulta: str, k: int = 4) -> str:
    return _contexto.get()


@contextlib.contextmanager
def _paso(nombre, tipo, entrada=None):
    if nombre.startswith("guarda"):
        _turno.get()["guardas"].append(nombre)
    yield None


_crear_original = agent.client.messages.create


async def _crear(**kw):
    resp = await _crear_original(**kw)
    _turno.get()["llamadas"].append({"model": resp.model, "stop_reason": resp.stop_reason,
                                     "usage": resp.usage.model_dump()})
    return resp


tools.ejecutar = _ejecutar
rag.buscar_contexto = _buscar
trazas.paso = _paso
agent.client.messages.create = _crear

_SECCIONES = {c["seccion"]: c["contenido"] for c in trocear(KB.read_text(encoding="utf-8"))}


def contexto_de(caso: dict) -> str:
    return "\n\n".join(_SECCIONES[t] for t in caso.get("contexto", []))


# ---------- Una conversacion ----------

async def conversar(caso: dict, sabotaje: bool) -> dict:
    _contexto.set(contexto_de(caso))
    _modo_cal.set(caso.get("cal", "ok"))
    historial = [dict(h) for h in caso.get("historial", [])]
    turnos = []
    for texto in caso["turnos"]:
        t = {"texto": texto, "respuesta": "", "tools": [], "guardas": [], "llamadas": [], "latencia_s": 0.0}
        _turno.set(t)
        t0 = time.perf_counter()
        if sabotaje:
            t["respuesta"] = "Hola! 😀 Tienes que agendar ya, ¿cuándo puedes? ¿Qué quieres? Queda agendado."
        else:
            t["respuesta"] = await agent.responder(historial, texto, caso["push_name"], phone_key="eval")
        t["latencia_s"] = round(time.perf_counter() - t0, 2)
        for ll in t["llamadas"]:
            if not ll["model"].startswith(MODEL):
                raise RuntimeError(f"modelo servido {ll['model']} != pedido {MODEL}")
        turnos.append(t)
        # main.py solo guarda en memoria si hubo respuesta: el historial replica eso.
        if t["respuesta"]:
            historial.append({"mensaje": texto, "respuesta": t["respuesta"]})
        if caso.get("checks", {}).get("cortar_al_reservar") and graders._reserva_exitosa(t["tools"]):
            break
    return {"push_name": caso["push_name"], "historial": caso.get("historial", []), "turnos": turnos}


async def corregir(caso: dict, conv: dict, sin_juez: bool) -> tuple[dict, dict, dict]:
    hay_historia = bool(conv["historial"])
    estilo = {}
    for t in conv["turnos"]:
        for k, v in graders.estilo_turno(t["respuesta"], hay_historia).items():
            estilo[k] = estilo.get(k, True) and v
        hay_historia = hay_historia or bool(t["respuesta"])
    checks = {**graders.conversacion(conv), **graders.caso(conv, caso.get("checks", {}))}
    veredictos = {}
    if not sin_juez and caso.get("juez"):
        ctx = contexto_de(caso)
        res = await asyncio.gather(*(juez.juzgar(c, conv, caso["esperado"], ctx) for c in caso["juez"]))
        for c, r in zip(caso["juez"], res):
            if not r["model"].startswith(juez.MODELO_JUEZ):
                raise RuntimeError(f"juez servido {r['model']} != pedido {juez.MODELO_JUEZ}")
            veredictos[c] = r
    return estilo, checks, veredictos


def _traza(caso: dict, conv: dict) -> list:
    out = [{"role": "system", "content": agent.SYSTEM}]
    for h in conv["historial"]:
        out += [{"role": "user", "content": h["mensaje"]}, {"role": "assistant", "content": h["respuesta"] + "\n\n[historial fijo, no se evalua]"}]
    for t in conv["turnos"]:
        out.append({"role": "user", "content": f"{caso['push_name']}: {t['texto']}"})
        for x in t["tools"]:
            out.append({"role": "tool_call", "name": x["nombre"], "content": json.dumps(x["entrada"], ensure_ascii=False, indent=2)})
            out.append({"role": "tool_result", "content": str(x["salida"])})
        guardas = f"\n\n[actuaron las guardas: {', '.join(t['guardas'])}]" if t["guardas"] else ""
        out.append({"role": "assistant", "content": (t["respuesta"] or "[respuesta vacia: no se envia nada]") + guardas})
    return out


def _sumar_usage(llamadas: list) -> dict:
    tot = {}
    for ll in llamadas:
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            tot[k] = tot.get(k, 0) + (ll["usage"].get(k) or 0)
    return tot


async def un_intento(caso, rep, dirv, args, lock, sem):
    async with sem:
        try:
            conv = await asyncio.wait_for(conversar(caso, args.sabotaje), TECHO_S)
            estilo, checks, veredictos = await asyncio.wait_for(corregir(caso, conv, args.sin_juez), TECHO_S)
        except Exception as e:  # noqa: BLE001 - toda falla de plumbing va al sidecar, nunca como nota
            clase = "timeout" if isinstance(e, asyncio.TimeoutError) else type(e).__name__
            with lock:
                with open(dirv / "errors.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps({"prompt_id": caso["id"], "rep": rep, "clase": clase, "error": str(e)[:500]}, ensure_ascii=False) + "\n")
            print(f"  ERROR {caso['id']} rep{rep}: {clase} {str(e)[:120]}")
            return

    llamadas = [ll for t in conv["turnos"] for ll in t["llamadas"]]
    truncado = any(ll["stop_reason"] == "max_tokens" for ll in llamadas)
    fallas = [f"estilo:{k}" for k, v in estilo.items() if not v] + [f"caso:{k}" for k, v in checks.items() if not v]
    fallas += [f"juez:{k}" for k, v in veredictos.items() if not v["pasa"]]
    grade = {"estilo": float(all(estilo.values())), "comportamiento": float(all(checks.values()))}
    if veredictos:
        grade["juez"] = float(all(v["pasa"] for v in veredictos.values()))
    grade = {"pasa": float(all(grade.values())), **grade}
    judge_usage = {}
    for v in veredictos.values():
        for k, n in v["usage"].items():
            if isinstance(n, int):
                judge_usage[k] = judge_usage.get(k, 0) + n
    fila = {
        "prompt_id": caso["id"], "rep": rep, "tags": [caso["grupo"]],
        "prompt": " / ".join(caso["turnos"]),
        "status": "truncated" if truncado else "ok",
        "stop_reason": llamadas[-1]["stop_reason"] if llamadas else None,
        "grade": grade,
        "explanation": {"pasa": "; ".join(fallas) or "todo OK",
                        **{f"juez_{k}": v["motivo"] for k, v in veredictos.items()}},
        "model": llamadas[0]["model"] if llamadas else None,
        "usage": _sumar_usage(llamadas),
        "judge_model": juez.MODELO_JUEZ if veredictos else None,
        "judge_usage": judge_usage,
        "latency_s": round(sum(t["latencia_s"] for t in conv["turnos"]), 2),
        "tool_calls": sum(len(t["tools"]) for t in conv["turnos"]),
        "meta": {"estilo": estilo, "checks": checks,
                 "juez": {k: {"pasa": v["pasa"], "motivo": v["motivo"]} for k, v in veredictos.items()},
                 "guardas": [g for t in conv["turnos"] for g in t["guardas"]],
                 "respuestas_sofia": len(conv["turnos"]),
                 "llamadas_sofia": len(llamadas)},
    }
    with lock:
        (dirv / "traces").mkdir(parents=True, exist_ok=True)
        (dirv / "traces" / f"{caso['id']}_rep{rep}.json").write_text(json.dumps(_traza(caso, conv), ensure_ascii=False, indent=1), encoding="utf-8")
        with open(dirv / "results.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    print(f"  {'PASA' if grade['pasa'] else 'FALLA'} {caso['id']} rep{rep}  {'; '.join(fallas)}")


# ---------- Resumen y compuerta ----------

def _wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, c - m), min(1.0, c + m))


def _costo(model, usage):
    base = next((v for k, v in PRECIOS.items() if model and model.startswith(k)), None)
    if not base or not usage:
        return 0.0
    i, o = base
    return (usage.get("input_tokens", 0) * i + usage.get("output_tokens", 0) * o
            + usage.get("cache_read_input_tokens", 0) * i * 0.1
            + usage.get("cache_creation_input_tokens", 0) * i * 1.25) / 1e6


def resumen(dirv: pathlib.Path) -> dict:
    filas = [json.loads(x) for x in (dirv / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    ok = [f for f in filas if f.get("status", "ok") == "ok"]
    errores = (dirv / "errors.jsonl").read_text(encoding="utf-8").count("\n") if (dirv / "errors.jsonl").exists() else 0
    n = len(ok)
    k = int(sum(f["grade"]["pasa"] for f in ok))
    lo, hi = _wilson(k, n)
    print(f"\n=== {dirv.name}: {n} conversaciones puntuadas, {len(filas) - n} truncadas, {errores} errores de plumbing")
    print(f"PASA: {k}/{n} = {k / max(n, 1):.0%}  (IC 95%: {lo:.0%}-{hi:.0%})")
    tasas = {}
    for grupo in ("estilo", "checks", "juez"):
        conteo = {}
        for f in ok:
            for c, v in f["meta"][grupo].items():
                v = v["pasa"] if isinstance(v, dict) else v
                a, b = conteo.get(c, (0, 0))
                conteo[c] = (a + bool(v), b + 1)
        for c, (a, b) in sorted(conteo.items()):
            tasas[c] = a / b
            print(f"  {grupo:7} {c:28} {a:3}/{b:<3} {a / b:5.0%}")
    print("\nPor caso (pasa / reps):")
    por_caso = {}
    for f in ok:
        a, b = por_caso.get(f["prompt_id"], (0, 0))
        por_caso[f["prompt_id"]] = (a + int(f["grade"]["pasa"]), b + 1)
    for c, (a, b) in por_caso.items():
        print(f"  {'OK ' if a == b else 'MAL' if a == 0 else '~  '} {c:32} {a}/{b}")
    guardas = {}
    for f in ok:
        for g in f["meta"]["guardas"]:
            guardas[g] = guardas.get(g, 0) + 1
    respuestas = sum(f["meta"]["respuestas_sofia"] for f in ok)
    c_sofia = sum(_costo(f["model"], f["usage"]) for f in ok)
    c_juez = sum(_costo(f["judge_model"], f["judge_usage"]) for f in ok)
    print(f"\nGuardas que actuaron: {guardas or 'ninguna'} (sobre {respuestas} respuestas de Sofia)")
    print(f"Costo medido: Sofia USD {c_sofia:.3f} ({respuestas} respuestas, USD {c_sofia / max(respuestas, 1):.4f} por respuesta) "
          f"+ juez USD {c_juez:.3f} = USD {c_sofia + c_juez:.3f}")
    return {"pasa": k / max(n, 1), **tasas}


def gate(tasas: dict) -> bool:
    ruta = AQUI / "umbrales.json"
    if not ruta.exists():
        print("\nCOMPUERTA: no hay umbrales.json todavia (se fijan despues de la linea base).")
        return True
    umbrales = json.loads(ruta.read_text(encoding="utf-8"))["umbrales"]
    bien = True
    print("\nCOMPUERTA:")
    for c, minimo in umbrales.items():
        real = tasas.get(c)
        cumple = real is not None and real >= minimo
        bien &= cumple
        print(f"  {'OK   ' if cumple else 'FALLA'} {c:28} {'-' if real is None else f'{real:.0%}':>5} (minimo {minimo:.0%})")
    print("COMPUERTA: " + ("PASA" if bien else "NO PASA: no desplegar"))
    return bien


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="baseline")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--casos", default="")
    ap.add_argument("--sin-juez", action="store_true")
    ap.add_argument("--sabotaje", action="store_true")
    ap.add_argument("--resumen", action="store_true")
    ap.add_argument("--gate", action="store_true")
    args = ap.parse_args()
    if args.variant != "baseline" and not (args.variant.startswith("v") and args.variant[1:].isdigit()):
        raise SystemExit("--variant tiene que ser 'baseline' o vN (v1, v2...)")
    dirv = FLOW / args.variant
    dirv.mkdir(parents=True, exist_ok=True)

    if not args.resumen:
        casos = json.loads((AQUI / "casos.json").read_text(encoding="utf-8"))["casos"]
        if args.casos:
            pedidos = set(args.casos.split(","))
            casos = [c for c in casos if c["id"] in pedidos]
        hechos = set()
        if (dirv / "results.jsonl").exists():
            hechos = {(f["prompt_id"], f["rep"]) for f in (json.loads(x) for x in (dirv / "results.jsonl").read_text(encoding="utf-8").splitlines() if x.strip())}
        pendientes = [(c, r) for c in casos for r in range(args.reps) if (c["id"], r) not in hechos]
        random.Random(0).shuffle(pendientes)
        print(f"{len(pendientes)} conversaciones por correr en {dirv} ({len(hechos)} ya hechas)")
        import threading
        lock, sem = threading.Lock(), asyncio.Semaphore(CONCURRENCIA)
        t0 = time.perf_counter()
        await asyncio.gather(*(un_intento(c, r, dirv, args, lock, sem) for c, r in pendientes))
        print(f"Tiempo: {time.perf_counter() - t0:.0f} s")

    tasas = resumen(dirv)
    if args.gate and not gate(tasas):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
