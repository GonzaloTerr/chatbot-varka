"""Correctores por codigo del eval de Sofia.

Son deterministicos y gratis. Van por separado de las guardas de agent.py a
proposito: si el eval usara las mismas regex que la guarda, mediria la guarda
contra si misma. Las listas de aca son mas amplias y se escribieron aparte.

Una conversacion llega como dict con:
  turnos:    [{texto, respuesta, tools: [{nombre, entrada, salida}]}]  (lo que se evalua)
  historial: [{mensaje, respuesta}]                                   (fijo, no se evalua)
  push_name: str
"""
import re

# ---------- Estilo, por turno ----------

_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")

# Solo formas de tuteo INEQUIVOCAS: con diptongo o pronombre. "necesitas" o
# "sabes" sin tilde pueden ser voseo mal acentuado, asi que no entran.
_TUTEO = re.compile(
    r"\b(tienes|quieres|puedes|vienes|prefieres|piensas|sientes|entiendes|eres|"
    r"cu[eé]ntame|dime|contigo|t[uú]\s+(tienes|quieres|puedes|eres)|haz)\b", re.I)
_TU_CON_TILDE = re.compile(r"\btú\b", re.I)

_VOSOTROS = re.compile(r"\b(vosotr[oa]s|vuestr[oa]s?)\b", re.I)

_GROSERIAS = re.compile(
    r"\b(al pedo|bolud\w*|pelotud\w*|quilomb\w*|mierd\w*|carajo|"
    r"cag(ar|ad[oa]s?|ada|aste|u[eé]|[oó])|garp\w*|(hinch|romp)\w*\s+(las\s+)?(pelotas|bolas)|"
    r"forr[oa]s?|conchud\w*|put[oa]s?|joder|jodid[oa]s?|co[nñ]o|verga|pija|orto|choto)\b", re.I)

_SALUDO = re.compile(r"^\s*[¡!]?\s*(hola|buen[oa]s)\b", re.I)

# Desde el 10/08/2026 Varka se posiciona para EMPRESAS. Falla si define al cliente
# como pyme ("consultora para pymes", "ayudamos a pymes"). El relato de la
# experiencia ("+20 anios operando pymes") esta permitido: habla de Gonzalo, no del cliente.
_PYMES_CLIENTE = re.compile(r"\b(para|a|con)\s+(las\s+)?pymes\b", re.I)


def estilo_turno(resp: str, hay_historia: bool) -> dict[str, bool]:
    """Chequeos que aplican a CADA respuesta de Sofia. True = pasa."""
    return {
        "no_vacia": bool(resp.strip()),
        "sin_emojis": not _EMOJI.search(resp),
        "sin_tuteo": not (_TUTEO.search(resp) or _TU_CON_TILDE.search(resp)),
        "sin_vosotros": not _VOSOTROS.search(resp),
        "sin_groserias": not _GROSERIAS.search(resp),
        "largo_300": len(resp) <= 300,
        "sin_saltos": "\n" not in resp,
        "max_una_pregunta": resp.count("?") <= 1,
        "no_dice_pymes": not _PYMES_CLIENTE.search(resp),
        # Solo cuenta si ya hubo una respuesta de Sofia antes en la charla.
        "no_resaluda": not (hay_historia and _SALUDO.search(resp)),
    }


# ---------- Conversacion: reservas y horarios ----------

_DICE_RESERVA = re.compile(
    r"agendad[oa]|reservad[oa]|reserva confirmada|queda(ste|mos)?\s+(confirmad|agendad|reservad|listo)"
    r"|te llega(r[aá])?\s+(la|el)\s+(confirmaci|mail|email)|te esperamos|nos vemos\s+(el|hoy|ma[nñ]ana)", re.I)
_PIDE_EMAIL = re.compile(r"\b(tu|el|un)\s+(e-?mail|mail|correo)\b", re.I)
# Solo "a las N": "las 24 horas" o "de 10 a 18" no son horarios de turno.
_HORA = re.compile(r"\ba\s+las\s+(\d{1,2})(?::(\d{2}))?", re.I)
_HORA_EN_TURNO = re.compile(r"a las (\d{2}):(\d{2})")


def _reserva_exitosa(tools: list) -> dict | None:
    for t in tools:
        if t["nombre"] == "agendar_diagnostico" and str(t["salida"]).startswith("RESERVA CONFIRMADA"):
            return t
    return None


def _horas(texto: str) -> set[tuple[int, int]]:
    return {(int(h), int(m or 0)) for h, m in _HORA.findall(texto or "")}


def conversacion(conv: dict) -> dict[str, bool]:
    """Chequeos globales que aplican a TODAS las conversaciones."""
    reservado = False
    ofrecidas: set[tuple[int, int]] = set()
    del_usuario: set[tuple[int, int]] = set()
    falsa = inventada = False
    for t in conv["turnos"]:
        del_usuario |= _horas(t["texto"])
        for tool in t["tools"]:
            if tool["nombre"] == "consultar_disponibilidad":
                ofrecidas |= {(int(h), int(m)) for h, m in _HORA_EN_TURNO.findall(str(tool["salida"]))}
        if _reserva_exitosa(t["tools"]):
            reservado = True
        if _DICE_RESERVA.search(t["respuesta"]) and not reservado:
            falsa = True
        # Toda hora que nombra Sofia tiene que venir de la agenda o de lo que dijo la persona.
        if _horas(t["respuesta"]) - ofrecidas - del_usuario:
            inventada = True
    return {"no_reserva_falsa": not falsa, "sin_horarios_inventados": not inventada}


# ---------- Chequeos propios de cada caso ----------

def _todas(conv):
    return [t["respuesta"] for t in conv["turnos"]]


def _tools(conv, *nombres):
    return [x for t in conv["turnos"] for x in t["tools"] if x["nombre"] in nombres]


def caso(conv: dict, checks: dict) -> dict[str, bool]:
    r = {}
    resps = _todas(conv)
    for nombre, param in checks.items():
        if nombre == "sin_herramientas":
            # calificar_lead es interno e inocuo; lo que importa es la agenda.
            r[nombre] = not _tools(conv, "consultar_disponibilidad", "agendar_diagnostico")
        elif nombre == "consulta_agenda":
            r[nombre] = bool(_tools(conv, "consultar_disponibilidad"))
        elif nombre == "sin_link":
            r[nombre] = not any(re.search(r"cal\.com|https?://", x, re.I) for x in resps)
        elif nombre == "sin_pregunta":
            r[nombre] = not any("?" in x for x in resps)
        elif nombre == "breve":
            r[nombre] = all(len(x) <= param for x in resps)
        elif nombre == "menciona":
            r[nombre] = any(re.search(param, x, re.I) for x in resps)
        elif nombre == "no_contiene":
            r[nombre] = not any(re.search(p, x, re.I) for p in param for x in resps)
        elif nombre == "sin_representarse":
            r[nombre] = not any(re.search(r"\bsoy sof[ií]a\b", x, re.I) for x in resps)
        elif nombre == "reserva_ok":
            r[nombre] = _reserva_ok(conv)
        elif nombre == "horarios_antes_de_email":
            r[nombre] = _horarios_antes_de_email(conv)
        elif nombre == "cortar_al_reservar":
            continue  # es una instruccion para el runner, no un chequeo
        else:
            raise ValueError(f"Check desconocido: {nombre}")
    return r


def _reserva_ok(conv: dict) -> bool:
    """Reservo con un 'inicio' que devolvio la agenda, a nombre de la persona y con notas."""
    inicios = set()
    for t in conv["turnos"]:
        for tool in t["tools"]:
            if tool["nombre"] == "consultar_disponibilidad":
                inicios |= set(re.findall(r"inicio: (\S+?)\)", str(tool["salida"])))
            if tool["nombre"] == "agendar_diagnostico" and str(tool["salida"]).startswith("RESERVA CONFIRMADA"):
                e = tool["entrada"]
                return (e.get("inicio") in inicios
                        and conv["push_name"].lower() in (e.get("nombre") or "").lower()
                        and bool((e.get("notas") or "").strip()))
    return False


def _horarios_antes_de_email(conv: dict) -> bool:
    """Muestra horarios reales antes de pedir el email (o no lo pide porque ya lo tiene)."""
    consulta = pide = None
    for i, t in enumerate(conv["turnos"]):
        if consulta is None and any(x["nombre"] == "consultar_disponibilidad" for x in t["tools"]):
            consulta = i
        if pide is None and _PIDE_EMAIL.search(t["respuesta"]):
            pide = i
    return consulta is not None and (pide is None or consulta <= pide)
