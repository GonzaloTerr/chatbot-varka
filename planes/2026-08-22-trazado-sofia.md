# Trazado de Sofía con LangFuse Cloud

> Actualizado el 22/08/2026 tras instalar el skill oficial `langfuse`
> (github.com/langfuse/skills). Los puntos marcados 🆕 salieron de ahí y no estaban
> en la primera versión del plan.

## Qué resuelve

Hoy, cuando Sofía falla, no hay rastro: no explota nada, contesta igual. El caso de
Voyage agotado (se quedó sin RAG y siguió respondiendo en silencio) y el de las tool
calls perdidas entre turnos se detectaron a mano, tarde y por casualidad. El trazado
deja ver, por conversación, qué se llamó, qué devolvió, cuántos tokens costó y cuánto
tardó.

Motivo secundario, y es el que lo puso en la cola: evals + observabilidad de agentes
apareció como requisito en dos avisos de la búsqueda laboral (Coderio 14/08, Adaption
Labs 22/08).

## Decisiones ya tomadas

- **LangFuse Cloud, plan Hobby, región EU.** No se autohospeda: los seis contenedores
  que pide (web, worker, Postgres, ClickHouse, Redis y storage S3) no entran en 1 vCPU
  y 4 GB que ya corren doce servicios.
- **Las claves ya están en el `.env` local.** `LANGFUSE_PUBLIC_KEY`,
  `LANGFUSE_SECRET_KEY` y `LANGFUSE_BASE_URL`. En EasyPanel todavía no.

## Qué voy a hacer

1. **Leer la documentación oficial antes de escribir una línea.** El skill lo pone como
   principio número uno: *"NEVER implement based on memory"*. Ya se pagó una vez en este
   mismo trabajo — usé `LANGFUSE_HOST` de memoria y la variable correcta es
   `LANGFUSE_BASE_URL`.
2. `requirements.txt`: agregar `langfuse` con la versión fija más reciente.
3. `config.py`: leer las tres variables, las dos claves con default `""`.
   **Sin claves, el trazado queda apagado y el código corre idéntico a hoy.**
4. **Archivo nuevo `trazas.py`** — todo el trazado encapsulado, con no-op si no hay
   claves y `try/except` en cada punto de contacto. Ningún otro archivo importa
   `langfuse` directamente.
   🆕 **Trampa de orden de import:** `langfuse` tiene que importarse DESPUÉS de que
   corra `load_dotenv()`, o arranca sin credenciales. `config.py` lo llama al importarse,
   así que `trazas.py` importa `config` primero y `langfuse` después.
5. `agent.py`: envolver `responder()`. **La lógica no se toca**, solo se agregan
   observaciones alrededor de lo que ya hace. La jerarquía que va a quedar:

   ```
   traza  "sofia-responder"          ← una por mensaje entrante
   ├── retriever  "rag-buscar"       ← rag.buscar_contexto
   ├── generation "claude-haiku"     ← cada vuelta del loop, con modelo y tokens
   └── tool       "consultar_disponibilidad" / "agendar_diagnostico" / "calificar_lead"
   ```

   🆕 **Tipos de observación correctos**, no todo `span`: el RAG va como `retriever` y
   las llamadas a Claude como `generation` (es lo que habilita el cálculo automático de
   costo y las métricas por modelo).
6. 🆕 **`session_id` = `phone_key`.** Agrupa todos los mensajes de una misma persona en
   una sola conversación navegable, en vez de trazas sueltas. Para un chatbot de WhatsApp
   de varios turnos, es la diferencia entre poder reconstruir el caso "pidió el mail dos
   veces" y no poder.
7. 🆕 **Input explícito, no los argumentos crudos.** Si no se declara qué es el input,
   entra *todo* lo que recibe la función — incluido el historial completo. Se setea a
   mano: el mensaje de la persona.
8. 🆕 **Enmascarado de PII — propuesta a confirmar** (ver abajo).
9. Subir `APP_VERSION` en `main.py`.
10. Probar en local, con claves y sin claves.
11. 🆕 **Auto-auditoría de la traza, obligatoria.** No alcanza con que compile: correr el
    camino entero, traer la traza generada con `langfuse-cli`, auditarla contra
    `langfuse.com/docs/observability/best-practices` —leída fresca, no de memoria— y
    corregir lo que falte. Repetir hasta que pase.
12. Recién ahí: cargar las variables en EasyPanel, deploy y verificación en vivo.

Orden deliberado: el interruptor de apagado (paso 3) antes que nada que pueda encenderse;
lo riesgoso (paso 5, el agente) antes del deploy.

## 🆕 Enmascarado de PII — decisión pendiente

Las trazas van a llevar mensajes reales de clientes a un servidor de terceros. Propuesta:

| Dato | Qué hago | Por qué |
|---|---|---|
| Texto del mensaje | **Se guarda** | Es el objeto del trazado; sin esto no se puede depurar la calidad |
| Emails | **Enmascarados** | Aparecen al agendar y no hacen falta para depurar |
| Teléfono (`session_id`) | **Se guarda** | Es la clave para correlacionar con Supabase; sin él las trazas no sirven |

Si preferís enmascarar también el teléfono, se puede — pero pierde la correlación con el
historial, y hay que decidirlo ahora y no después.

## Qué NO voy a hacer

- **No persistir `tool_use` / `tool_result` en Supabase.** El trazado deja *ver* que el
  estado se pierde entre turnos; no lo arregla. Es un plan aparte.
- No tocar el system prompt, el modelo, `_acortar()`, el debounce ni el post-proceso
  de estilo.
- No editar `rag.py`, `tools.py`, `whatsapp.py` ni `memory.py`.
- No instrumentar el SaaS de diagnósticos ni los flujos de n8n.
- No armar el eval set ni el check de degradación del RAG. Van después, con los tokens
  reales que dé este trazado.
- No migrar el system prompt al gestor de prompts de LangFuse, aunque el skill lo ofrezca.
  Es un cambio grande sobre el prompt de un sistema que atiende clientes.
- No autohospedar LangFuse.

## Qué no se tiene que romper

| Qué | Cómo se comprueba |
|---|---|
| Sofía recibe y contesta por WhatsApp | Mensaje real de prueba desde otro número |
| El RAG sigue devolviendo contexto | Preguntarle algo que solo esté en `varka_kb.md` (un precio) |
| El agendado en Cal.com sigue andando | Reserva de prueba end-to-end, con email |
| Las alertas por email siguen saliendo | Que `alerts.py` no quede tapado por un `except` nuevo |
| La latencia de respuesta no sube | El envío de trazas va en background, nunca bloqueando |
| No hay datos de clientes en los logs del contenedor | `docker logs` después de la prueba |
| Si LangFuse se cae o la clave es inválida, Sofía responde igual | Probar en local con una clave falsa |

## Cómo verifico

1. **Local, sin claves:** Sofía responde exactamente igual que hoy. Es el rollback.
2. **Local, con claves:** aparece la traza con su jerarquía, tokens, costo y latencia.
3. **Local, con clave inválida:** Sofía responde igual y no se cuelga.
4. **Auditoría de la traza** contra la guía oficial, con `langfuse-cli`.
5. **Producción:** `curl https://<dominio>/` y confirmar `APP_VERSION` nueva. Si no
   cambió, el deploy no entró aunque el log diga que sí.
6. Recorrer la tabla de arriba punto por punto y reportar las dos cosas: lo nuevo y lo
   viejo.

## Rollback

Vaciar `LANGFUSE_PUBLIC_KEY` en EasyPanel. El trazado se apaga y el agente vuelve al
camino de hoy. No requiere revertir código ni redeploy de emergencia.

---

## Resultado (22/08/2026) — hecho y verificado EN LOCAL

Construido: `trazas.py` (nuevo), `agent.py` (envuelto, lógica intacta), `main.py`
(lifespan + `phone_key`), `config.py` y `requirements.txt`.

| Chequeo | Resultado |
|---|---|
| Traza con jerarquía correcta | ✅ `sofia-responder` → `rag-buscar` (RETRIEVER) + `anthropic.chat` (GENERATION) + `consultar_disponibilidad` (TOOL) |
| Modelo, tokens y costo | ✅ `claude-haiku-4-5`, 4.954 in / 90 out, USD 0,0054 por mensaje |
| `session_id` y `user_id` | ✅ el `phone_key`, cruza con Supabase |
| Emails enmascarados, teléfono no | ✅ `[EMAIL OCULTO]`, `sessionId` intacto |
| Sin claves → apagado | ✅ `ACTIVO=False`, responde igual |
| Clave inválida → no rompe | ✅ loguea `401`, Sofía responde igual |
| Latencia | ✅ 4,55 s con trazado vs 4,90 s sin él: sin costo medible |
| RAG sigue dando contexto | ✅ `hubo_contexto: true`, 1.768 caracteres |
| Agendado en Cal.com | ✅ ofreció horarios reales; no se reservó nada |

**NO desplegado.** Falta cargar las tres variables en EasyPanel, desplegar y verificar
`APP_VERSION = 2026-08-22-a` con `GET /`.

## Dos cosas que aparecieron y NO se tocaron

1. 🔴 **El prompt caching de Sofía no funciona.** El system prompt va con
   `cache_control` pero dos llamadas idénticas dan `cache_creation=0` y
   `cache_read=0` en el `usage` crudo de Anthropic. Son 3.141 de los 4.954 tokens de
   entrada —el 63%— pagados a tarifa plena en cada mensaje. Causa sin diagnosticar.
2. ⚠️ **Las pruebas agotaron la cuota de Voyage** (429). Es el modo de falla conocido:
   el RAG devuelve vacío y Sofía sigue contestando sin fuente, en silencio.
