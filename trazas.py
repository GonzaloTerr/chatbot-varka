"""Trazado de las conversaciones de Sofia con LangFuse.

TODO el trazado vive aca. Ningun otro archivo importa `langfuse`: si manana se
cambia de herramienta, se reescribe este modulo y nada mas.

REGLA DE ORO: esto NUNCA puede romper a Sofia. Si faltan las claves, si LangFuse
esta caido o si la libreria falla, cada funcion de este modulo se vuelve un no-op
silencioso y el agente responde igual que si LangFuse no existiera. Vaciar
LANGFUSE_PUBLIC_KEY en EasyPanel es el interruptor de apagado y el rollback.

OJO CON EL ORDEN DE IMPORTS: el SDK de LangFuse lee las credenciales del entorno
al inicializarse, asi que `config` —que es quien corre load_dotenv()— tiene que
importarse ANTES que `langfuse`. Por eso los imports de langfuse estan adentro de
iniciar() y no arriba.
"""
import contextlib
import logging
import re

from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

log = logging.getLogger("trazas")

# Hay trazado solo si estan las dos claves. Sin ellas todo este modulo no hace nada.
ACTIVO = bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)

_cliente = None

# Enmascarado de PII. Decision del 22/08/2026:
#   - El TEXTO de los mensajes se guarda: es el objeto del trazado, sin el no se
#     puede depurar la calidad de las respuestas.
#   - Los EMAILS se tapan: aparecen al agendar y no hacen falta para depurar.
#   - El TELEFONO NO se tapa: es la clave que correlaciona la traza con el
#     historial en Supabase (remote_jid). Sin el, las trazas no sirven para
#     reconstruir un caso.
_EMAIL = re.compile(r"\b[\w.-]+?@[\w.-]+?\.\w+?\b")


def _enmascarar(*, params):
    """Hook de LangFuse: corre sobre los atributos crudos de cada span antes de
    exportarlos, incluidos los que genera la instrumentacion de Anthropic.
    Tiene que ser rapido y no lanzar: si lanza, LangFuse descarta el lote entero."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    parches = {}
    for identificador, span in params.spans.items():
        reemplazos = {}
        for clave, valor in span.attributes.items():
            if isinstance(valor, str):
                tapado = _EMAIL.sub("[EMAIL OCULTO]", valor)
                if tapado != valor:
                    reemplazos[clave] = tapado
        if reemplazos:
            parches[identificador] = OtelSpanPatch(set_attributes=reemplazos)

    return MaskOtelSpansResult(span_patches=parches)


def iniciar() -> None:
    """Arranca el cliente y la instrumentacion automatica del SDK de Anthropic.
    Idempotente. Si algo falla, deja el trazado apagado y sigue."""
    global _cliente
    if not ACTIVO or _cliente is not None:
        return
    try:
        from langfuse import Langfuse
        from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

        # Las credenciales las toma de las variables de entorno que ya cargo config.
        _cliente = Langfuse(mask_otel_spans=_enmascarar)

        # Esto es lo que captura, solo, cada llamada a Claude como 'generation'
        # con modelo, tokens y costo. Sin tocar una linea de agent.py.
        AnthropicInstrumentor().instrument()
        log.info("Trazado LangFuse activo")
    except Exception:
        log.exception("No se pudo iniciar el trazado; Sofia sigue sin el")
        _cliente = None


def cerrar() -> None:
    """Vacia el buffer pendiente al apagar el servicio. Sin esto se pierden las
    ultimas trazas, que quedan en cola en memoria."""
    if _cliente is None:
        return
    try:
        _cliente.shutdown()
    except Exception:
        log.exception("Fallo al cerrar el trazado")


@contextlib.contextmanager
def conversacion(session_id: str, mensaje: str, push_name: str):
    """Traza raiz: una por mensaje entrante. `session_id` es el phone_key, que es
    lo que agrupa todos los mensajes de una persona en una sola conversacion
    navegable en LangFuse (y lo que permite cruzarla con Supabase).

    Los fallos de ARMADO se tragan; los errores del cuerpo se propagan tal cual,
    para que Sofia se comporte igual que siempre (y para que LangFuse los registre)."""
    if _cliente is None:
        yield None
        return

    pila = contextlib.ExitStack()
    raiz = None
    try:
        from langfuse import propagate_attributes

        raiz = pila.enter_context(
            _cliente.start_as_current_observation(
                as_type="span",
                name="sofia-responder",
                # Input explicito: si no se declara, entra TODO lo que recibe la
                # funcion, historial completo incluido.
                input={"mensaje": mensaje},
            )
        )
        pila.enter_context(
            propagate_attributes(
                session_id=session_id,
                user_id=session_id,
                metadata={"push_name": push_name},
            )
        )
    except Exception:
        log.exception("Trazado: no se pudo abrir la traza")
        pila.close()
        raiz = None

    try:
        yield raiz
    finally:
        try:
            pila.close()
        except Exception:
            log.exception("Trazado: fallo al cerrar la traza")


@contextlib.contextmanager
def paso(nombre: str, tipo: str, entrada=None):
    """Observacion hija. `tipo` es el tipo de observacion de LangFuse: 'retriever'
    para la busqueda en el RAG, 'tool' para las herramientas de Cal.com. Poner el
    tipo correcto (y no un span generico) es lo que habilita las metricas por tipo."""
    if _cliente is None:
        yield None
        return

    pila = contextlib.ExitStack()
    obs = None
    try:
        obs = pila.enter_context(
            _cliente.start_as_current_observation(as_type=tipo, name=nombre, input=entrada)
        )
    except Exception:
        log.exception("Trazado: no se pudo abrir el paso %s", nombre)
        pila.close()
        obs = None

    try:
        yield obs
    finally:
        try:
            pila.close()
        except Exception:
            log.exception("Trazado: fallo al cerrar el paso %s", nombre)


def salida(observacion, valor) -> None:
    """Registra el resultado de una observacion. Acepta None para no obligar a
    quien llama a preguntar si el trazado esta activo."""
    if observacion is None:
        return
    try:
        observacion.update(output=valor)
    except Exception:
        log.exception("Trazado: fallo al registrar la salida")
