"""Debounce: agrupa los mensajes rapidos de un mismo numero en una sola respuesta.
Si llegan varios seguidos, espera VENTANA segundos desde el ultimo y recien ahi
procesa todo junto. En Python con asyncio esto es trivial (cancelar la tarea previa).
Funciona porque uvicorn corre en un solo proceso: el estado en memoria se comparte."""
import asyncio

VENTANA = 5  # segundos a esperar desde el ultimo mensaje antes de responder

_buffers: dict[str, list[str]] = {}   # phone -> textos acumulados
_tasks: dict[str, asyncio.Task] = {}  # phone -> tarea en espera
_ctx: dict[str, dict] = {}            # phone -> {frm, push}


async def encolar(phone: str, frm: str, push: str, texto: str, procesar) -> None:
    """Acumula el mensaje y (re)programa el procesamiento. `procesar` es una
    corutina procesar(frm, phone, push, texto_combinado)."""
    _buffers.setdefault(phone, []).append(texto)
    _ctx[phone] = {"frm": frm, "push": push}

    # cancelar la espera anterior: llego un mensaje nuevo, reiniciamos el reloj
    anterior = _tasks.get(phone)
    if anterior and not anterior.done():
        anterior.cancel()

    _tasks[phone] = asyncio.create_task(_esperar_y_procesar(phone, procesar))


async def _esperar_y_procesar(phone: str, procesar) -> None:
    try:
        await asyncio.sleep(VENTANA)
    except asyncio.CancelledError:
        return  # llego otro mensaje dentro de la ventana: esta tarea se descarta

    textos = _buffers.pop(phone, [])
    ctx = _ctx.pop(phone, {})
    _tasks.pop(phone, None)
    if textos:
        await procesar(ctx.get("frm"), phone, ctx.get("push"), "\n".join(textos))
