"""Test de los correctores por codigo: cada uno tiene que rechazar su caso malo y
aceptar el bueno. Si un corrector no detecta el caso malo armado a mano, no sirve.

Uso:  python evals/test_graders.py
"""
import sys

import graders as g

sys.stdout.reconfigure(encoding="utf-8")
fallas = []


def ok(cond, que):
    if not cond:
        fallas.append(que)
    print(("OK   " if cond else "MAL  ") + que)


# ---------- Estilo por turno: (check, respuesta buena, respuesta mala) ----------
ESTILO = [
    ("no_vacia", "Perfecto, contame más.", "   "),
    ("sin_emojis", "Genial, lo vemos.", "Genial, lo vemos 😀"),
    ("sin_tuteo", "¿Qué tenés hoy en la trastienda? Contame.", "¿Qué tienes hoy? Cuéntame."),
    ("sin_tuteo", "Si querés, lo vemos.", "Si quieres, lo vemos."),
    ("sin_vosotros", "Empresas grandes como la de ustedes.", "Empresas grandes como la vuestra."),
    ("sin_groserias", "La IA no es chamuyo: ahorra horas.", "¿En qué área se les va el tiempo al pedo?"),
    ("sin_groserias", "Lo que te complica el día a día.", "Lo que te rompe las pelotas a diario."),
    ("sin_groserias", "Computadoras y reputación.", "Esto es un quilombo."),
    ("largo_300", "Corto.", "x" * 301),
    ("sin_saltos", "Todo en un bloque.", "Linea uno\nLinea dos"),
    ("max_una_pregunta", "¿A qué se dedican?", "¿A qué se dedican? ¿Cuántos son?"),
    ("no_dice_pymes", "Consultora de IA para empresas.", "Soy Sofia, consultora de IA para pymes."),
    ("no_dice_pymes", "Más de 20 años operando pymes argentinas.", "Ayudamos a pymes a automatizar."),
]
for check, bueno, malo in ESTILO:
    ok(g.estilo_turno(bueno, True)[check], f"{check} acepta: {bueno[:40]!r}")
    ok(not g.estilo_turno(malo, True)[check], f"{check} rechaza: {malo[:40]!r}")

ok(g.estilo_turno("Hola, soy Sofia de Varka.", False)["no_resaluda"], "no_resaluda acepta el saludo del primer mensaje")
ok(not g.estilo_turno("Hola Martin, ¿cómo va?", True)["no_resaluda"], "no_resaluda rechaza el saludo con historia")


# ---------- Conversacion ----------
AGENDA = ("Turnos libres (ofrecele el dia/hora; para reservar usa el campo 'inicio' tal cual):\n"
          "- vie 25/09 a las 09:00  (inicio: 2026-09-25T12:00:00.000Z)\n"
          "- vie 25/09 a las 10:00  (inicio: 2026-09-25T13:00:00.000Z)")
CONSULTA = {"nombre": "consultar_disponibilidad", "entrada": {}, "salida": AGENDA}
RESERVA_OK = {"nombre": "agendar_diagnostico",
              "entrada": {"nombre": "Martin", "email": "m@x.com", "inicio": "2026-09-25T12:00:00.000Z", "notas": "Distribuidora"},
              "salida": "RESERVA CONFIRMADA para Martin el vie 25/09 a las 09:00."}


def conv(*turnos):
    return {"push_name": "Martin", "historial": [],
            "turnos": [{"texto": t[0], "respuesta": t[1], "tools": t[2] if len(t) > 2 else []} for t in turnos]}


buena = conv(("quiero agendar", "Tengo el viernes a las 9 o a las 10, ¿cuál te sirve?", [CONSULTA]),
             ("el de las 9", "Perfecto, ¿me pasás tu email?"),
             ("m@x.com", "Listo, quedó reservado; te llega la confirmación al mail.", [CONSULTA, RESERVA_OK]))
r = g.conversacion(buena)
ok(r["no_reserva_falsa"] and r["sin_horarios_inventados"], "conversacion acepta un agendado correcto")

mentira = conv(("m@x.com", "Listo, queda agendado para el viernes a las 9.", [CONSULTA]))
ok(not g.conversacion(mentira)["no_reserva_falsa"], "no_reserva_falsa rechaza 'queda agendado' sin reserva")

inventa = conv(("quiero agendar", "Te puedo ofrecer el lunes a las 15.", []))
ok(not g.conversacion(inventa)["sin_horarios_inventados"], "sin_horarios_inventados rechaza una hora que no dio la agenda")

eco = conv(("¿puede ser el domingo a las 22?", "El domingo a las 22 no tengo; ¿te sirve el viernes a las 9?", [CONSULTA]))
ok(g.conversacion(eco)["sin_horarios_inventados"], "sin_horarios_inventados acepta repetir la hora que pidio la persona")

ok(g.conversacion(conv(("hola", "Atendemos las 24 horas, de 10 a 18 también.")))["sin_horarios_inventados"],
   "sin_horarios_inventados no confunde '24 horas' con un turno")


# ---------- Chequeos de caso ----------
ok(g.caso(buena, {"reserva_ok": True})["reserva_ok"], "reserva_ok acepta inicio real + nombre + notas")
sin_notas = conv(("m@x.com", "Listo.", [CONSULTA, dict(RESERVA_OK, entrada=dict(RESERVA_OK["entrada"], notas=""))]))
ok(not g.caso(sin_notas, {"reserva_ok": True})["reserva_ok"], "reserva_ok rechaza sin notas")
otro_inicio = conv(("m@x.com", "Listo.", [CONSULTA, dict(RESERVA_OK, entrada=dict(RESERVA_OK["entrada"], inicio="2026-09-26T12:00:00.000Z"))]))
ok(not g.caso(otro_inicio, {"reserva_ok": True})["reserva_ok"], "reserva_ok rechaza un inicio que no dio la agenda")

ok(g.caso(buena, {"horarios_antes_de_email": True})["horarios_antes_de_email"], "horarios_antes_de_email acepta horarios primero")
email_primero = conv(("quiero agendar", "Dale, ¿me pasás tu email?"), ("m@x.com", "Tengo el viernes a las 9.", [CONSULTA]))
ok(not g.caso(email_primero, {"horarios_antes_de_email": True})["horarios_antes_de_email"], "horarios_antes_de_email rechaza email primero")

no_gracias = conv(("no gracias", "Perfecto, cualquier cosa quedo a disposición."))
ok(all(g.caso(no_gracias, {"sin_link": True, "sin_pregunta": True, "breve": 160, "sin_herramientas": True}).values()),
   "cierre cordial pasa sin_link / sin_pregunta / breve / sin_herramientas")
insiste = conv(("no gracias", "¿Seguro? Mirá, agendá acá: https://cal.com/x", [CONSULTA]))
r = g.caso(insiste, {"sin_link": True, "sin_pregunta": True, "sin_herramientas": True})
ok(not any(r.values()), "insistir con link, pregunta y agenda falla los tres")

geo = conv(("¿cuánto sale por mes?", "El mensual arranca en USD 1.200 + 350 por mes."))
ok(not g.caso(geo, {"no_contiene": ["1[.,]?200", "350"]})["no_contiene"], "no_contiene rechaza el mensual de GEO")
ok(g.caso(conv(("¿cuánto dura?", "Dura una hora.")), {"menciona": "(1|una) hora"})["menciona"], "menciona encuentra 'una hora'")
ok(not g.caso(conv(("hola", "Hola, soy Sofia de Varka.")), {"sin_representarse": True})["sin_representarse"], "sin_representarse rechaza 'soy Sofia'")

print(f"\n{len(fallas)} fallas")
sys.exit(1 if fallas else 0)
