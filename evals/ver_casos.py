"""Genera una pagina HTML para revisar a ojo los casos del eval, y opcionalmente
lo que respondio Sofia en una corrida con el veredicto de cada corrector.

Uso:
  python evals/ver_casos.py                          -> evals/casos.html (solo los casos)
  python evals/ver_casos.py --resultados baseline    -> evals/resultados.html (conversaciones + veredictos)
"""
import argparse
import html
import json
import pathlib

AQUI = pathlib.Path(__file__).parent
GRUPOS = {
    "entrante": "Escriben ellos",
    "agendado": "Agendado",
}


def e(t):
    return html.escape(str(t))


def _chat_del_caso(c):
    burbujas = []
    for h in c.get("historial", []):
        burbujas.append(f'<div class="p">{e(h["mensaje"])}</div>')
        burbujas.append(f'<div class="s">{e(h["respuesta"])}<span class="tag">historial fijo</span></div>')
    for t in c["turnos"]:
        burbujas.append(f'<div class="p">{e(t)}</div><div class="s pend">… responde Sofia …</div>')
    return "".join(burbujas)


def _chat_de_la_traza(traza):
    burbujas = []
    for t in traza[1:]:  # el [0] es el system prompt
        if t["role"] == "user":
            burbujas.append(f'<div class="p">{e(t["content"])}</div>')
        elif t["role"] == "assistant":
            fijo = "[historial fijo, no se evalua]" in t["content"]
            texto = t["content"].replace("\n\n[historial fijo, no se evalua]", "")
            burbujas.append(f'<div class="s{" fijo" if fijo else ""}">{e(texto)}'
                            f'{"<span class=tag>historial fijo</span>" if fijo else ""}</div>')
        elif t["role"] == "tool_call":
            burbujas.append(f'<div class="tool">herramienta <b>{e(t["name"])}</b> {e(t["content"])}</div>')
        elif t["role"] == "tool_result":
            burbujas.append(f'<div class="tool res">{e(t["content"])}</div>')
    return "".join(burbujas)


def _veredicto(fila):
    m = fila["meta"]
    items = []
    for k, v in {**m["estilo"], **m["checks"]}.items():
        if not v:
            items.append(f'<li class="mal">código · {e(k)}</li>')
    for k, v in m["juez"].items():
        items.append(f'<li class="{"ok" if v["pasa"] else "mal"}">juez · <b>{e(k)}</b>: {"pasa" if v["pasa"] else "FALLA"} — {e(v["motivo"])}</li>')
    ok_codigo = sum(1 for v in {**m["estilo"], **m["checks"]}.values() if v)
    items.insert(0, f'<li class="ok">código · {ok_codigo} de {len(m["estilo"]) + len(m["checks"])} chequeos pasan</li>')
    if m["guardas"]:
        items.append(f'<li>actuaron las guardas: {e(", ".join(m["guardas"]))}</li>')
    return "".join(items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resultados", default="")
    args = ap.parse_args()
    casos = json.loads((AQUI / "casos.json").read_text(encoding="utf-8"))["casos"]

    filas = {}
    if args.resultados:
        dirv = AQUI / "corridas" / args.resultados
        for linea in (dirv / "results.jsonl").read_text(encoding="utf-8").splitlines():
            if linea.strip():
                f = json.loads(linea)
                filas.setdefault(f["prompt_id"], []).append(f)

    partes = []
    for grupo, titulo in GRUPOS.items():
        del_grupo = [c for c in casos if c["grupo"] == grupo and (not args.resultados or c["id"] in filas)]
        if not del_grupo:
            continue
        partes.append(f"<h2>{e(titulo)} <small>({len(del_grupo)})</small></h2>")
        for c in del_grupo:
            checks = ", ".join(f"{k}={v}" if v is not True else k for k, v in c.get("checks", {}).items()) or "—"
            extra = ' · <b>Cal.com: la reserva FALLA</b>' if c.get("cal") == "falla" else ""
            if args.resultados:
                cuerpo = ""
                for f in sorted(filas[c["id"]], key=lambda x: x["rep"]):
                    traza = json.loads((dirv / "traces" / f"{c['id']}_rep{f['rep']}.json").read_text(encoding="utf-8"))
                    pasa = f["grade"]["pasa"] == 1
                    cuerpo += (f'<div class="rep"><p class="estado {"ok" if pasa else "mal"}">Repetición {f["rep"] + 1}: '
                               f'{"PASA" if pasa else "FALLA"}</p><div class="chat">{_chat_de_la_traza(traza)}</div>'
                               f'<ul class="ver">{_veredicto(f)}</ul></div>')
            else:
                cuerpo = f'<div class="chat">{_chat_del_caso(c)}</div>'
            partes.append(f"""
<section>
  <h3>{e(c['descripcion'])} <code>{e(c['id'])}</code></h3>
  <p class="meta">Nombre en WhatsApp: <b>{e(c['push_name'])}</b> · Contexto RAG: {e(', '.join(c.get('contexto', [])) or 'VACIO (sin base)')}{extra}</p>
  <p class="esp"><b>Qué se espera:</b> {e(c['esperado'])}</p>
  {cuerpo}
  <p class="meta">Checks por código: {e(checks)} · Juez: {e(', '.join(c.get('juez', [])) or '—')}</p>
</section>""")

    titulo = f"Resultados del eval de Sofía · {args.resultados}" if args.resultados else "Casos del eval de Sofía"
    intro = ("Cada conversación con lo que respondió Sofía y el veredicto de cada corrector. "
             "Las burbujas verdes marcadas 'historial fijo' vienen del caso; las demás las generó Sofía."
             if args.resultados else
             f"{len(casos)} casos sintéticos, calcados de conversaciones reales. Izquierda: la persona que escribe. Derecha: Sofía. "
             "Los checks de estilo (voseo, emojis, groserías, largo, una pregunta, no re-saludar) corren en todos los turnos.")
    pagina = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo)}</title>
<style>
:root {{ --bg:#f6f5f2; --card:#fff; --tx:#1d1d1b; --mut:#6b6b66; --p:#e7e5df; --s:#dcf2e3; --bd:#e2e0da; --ok:#1f7a45; --mal:#b3261e; --tool:#eef0f6; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161615; --card:#1f1f1d; --tx:#ecebe7; --mut:#9a9994; --p:#2c2c29; --s:#1e3a2a; --bd:#33332f; --ok:#6fcf97; --mal:#f28b82; --tool:#23252e; }} }}
body {{ background:var(--bg); color:var(--tx); font:15px/1.5 system-ui,sans-serif; margin:0; padding:24px 16px; }}
main {{ max-width:760px; margin:0 auto; }}
section {{ background:var(--card); border:1px solid var(--bd); border-radius:10px; padding:14px 16px; margin:12px 0; }}
h3 {{ margin:0 0 4px; font-size:16px; }} code {{ color:var(--mut); font-size:12px; font-weight:400; }}
.meta {{ color:var(--mut); font-size:13px; margin:4px 0; }} .esp {{ margin:8px 0 4px; }}
.chat {{ display:flex; flex-direction:column; gap:6px; margin:10px 0; }}
.p,.s {{ max-width:85%; padding:8px 11px; border-radius:10px; white-space:pre-wrap; overflow-wrap:anywhere; }}
.p {{ background:var(--p); align-self:flex-start; }} .s {{ background:var(--s); align-self:flex-end; }}
.fijo {{ opacity:.6; }} .pend {{ opacity:.55; font-style:italic; }} .tag {{ display:block; font-size:11px; color:var(--mut); margin-top:4px; }}
.tool {{ align-self:flex-end; max-width:85%; font:12px/1.4 ui-monospace,monospace; background:var(--tool); padding:6px 9px; border-radius:6px; white-space:pre-wrap; overflow-wrap:anywhere; }}
.rep {{ border-top:1px dashed var(--bd); margin-top:10px; padding-top:6px; }}
.estado {{ font-weight:600; margin:4px 0; }} .ok {{ color:var(--ok); }} .mal {{ color:var(--mal); }}
ul.ver {{ margin:4px 0 0; padding-left:18px; font-size:13px; }}
</style></head><body><main>
<h1>{e(titulo)}</h1>
<p class="meta">{intro}</p>
{''.join(partes)}
</main></body></html>"""
    salida = AQUI / ("resultados.html" if args.resultados else "casos.html")
    salida.write_text(pagina, encoding="utf-8")
    print(salida)


if __name__ == "__main__":
    main()
