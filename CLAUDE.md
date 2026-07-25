# Sofía — Chatbot de WhatsApp de Varka

**Está en producción atendiendo clientes reales.** Un error acá se ve en el celular de alguien que está esperando respuesta.

Agente conversacional en Python que atiende WhatsApp, responde consultas sobre Varka con base de conocimiento propia, y agenda reuniones sola en Cal.com.

Deploy: EasyPanel, servicio `chatbot-varka` en el proyecto `varka` del VPS. Ver el skill `vps-varka` para operar el servidor.

---

## Cómo está armado

```
WhatsApp (Meta Cloud API)
        ↓  POST /webhook
    main.py          webhook FastAPI · texto y voz · debounce
        ↓
    agent.py         arma el prompt, llama a Claude, aplica el estilo
        ↓
    ├── memory.py    historial de la conversación (Supabase)
    ├── rag.py       busca en la base de conocimiento (pgvector)
    └── tools.py     reserva turnos en Cal.com
        ↓
   whatsapp.py       envía la respuesta
```

| Archivo | Qué hace |
|---|---|
| `main.py` | Webhook. Verificación de Meta, transcripción de audios, debounce, indicador de "escribiendo". |
| `agent.py` | El agente: system prompt, llamada a Claude, post-proceso del estilo. |
| `memory.py` | Historial por número de teléfono, en Supabase. |
| `rag.py` / `ingesta_rag.py` | Búsqueda semántica y carga del corpus. Embeddings de **Voyage** (`voyage-3.5-lite`, 1024 dim) sobre **Supabase pgvector**. Esquema en `rag_setup.sql`. |
| `tools.py` | Cal.com: disponibilidad y reserva. |
| `transcribe.py` | Audios de WhatsApp vía Groq. |
| `debounce.py` | Agrupa los mensajes cortos seguidos para responder una sola vez. |
| `alerts.py` | Si falla el procesamiento, avisa **por email** (Resend). |
| `waha.py` | **Legacy.** Quedó del transporte anterior; ya no se usa. |

La base de conocimiento vive en `conocimiento/varka_kb.md`.

---

## Decisiones que no son obvias

**Las alertas van por email, no por WhatsApp.** A propósito: si lo que se rompió es justamente WhatsApp, un aviso por WhatsApp tampoco saldría.

**El modelo es Haiku (`claude-haiku-4-5`) y no obedece las reglas de estilo del prompt.** Ignora las instrucciones de largo y de saltos de línea aunque estén escritas. Por eso el estilo se fuerza **por código** en `agent.py`: se colapsan los saltos de línea a un espacio y hay un `max_tokens=110` como red de seguridad física. El voseo y el no repreguntar sí respondieron al prompt; el formato no. Si se cambia el modelo, revisar si ese post-proceso sigue haciendo falta.

**`APP_VERSION` en `main.py` es un marcador de deploy.** Subirlo en cada cambio de prompt o de lógica. Después del redeploy, pegarle a `GET /` y confirmar que devuelve la versión nueva: es la única forma de saber que EasyPanel levantó el código y no una copia vieja.

**No probar durante el swap del contenedor** — te atiende el viejo y parece que el cambio no funcionó.

**Para un test limpio**, borrar el historial de ese número en Supabase. Si no, Sofía sigue con el contexto de la charla anterior y no se ve el comportamiento nuevo.

---

## WhatsApp

Corre sobre la **API oficial de Meta (Cloud API)** con token permanente de System User, y con un **número real dedicado**, no el de prueba.

Se migró desde WAHA después de un baneo. `waha.py` y las variables `WAHA_*` quedaron por compatibilidad; no tocarlas ni volver a usarlas.

Dos cosas que costaron encontrar en su momento: hay que **suscribir la WABA a la app** (`subscribed_apps`), y los números argentinos necesitan el reintento con el "15" que está implementado en `whatsapp.py`.

Límite actual: 250 conversaciones iniciadas por el negocio por día (las respuestas dentro de la ventana de 24 h son ilimitadas). Verificar el negocio solo sube ese tope; no bloquea nada.

---

## Configuración

Todo por variables de entorno, sin claves en el código (`config.py`). En producción las carga EasyPanel; en local hay un `.env` que **no se commitea**.

Obligatorias: `ANTHROPIC_API_KEY`, `SUPABASE_KEY`. Las demás degradan con valores por defecto.

La base de Supabase es la misma que usan los flujos de ventas y **se pausa por inactividad en el plan free**: hay un flujo keep-alive en n8n que la pinga. Si Sofía deja de responder de golpe, es de las primeras cosas a mirar.

---

## Cuando Sofía "recibe pero no contesta"

Casi nunca es la IA. En orden:

1. Logs del contenedor en el VPS (skill `vps-varka`).
2. ¿Está viva la base de Supabase, o se pausó?
3. ¿El webhook de Meta sigue apuntando acá y la WABA suscripta?
4. Recién ahí, mirar el agente.
