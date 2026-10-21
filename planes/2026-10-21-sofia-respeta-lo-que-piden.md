# Sofía: que siga lo que la persona pide y no confunda el nombre del perfil con la empresa

## Qué resuelve
El 21/10 Gonzalo pidió "quiero un chatbot" cuatro veces y Sofía lo llevó tres veces a la "trastienda": "pero antes de armar el chatbot…", "lo que más ahorra es automatizar adentro…". Además preguntó "¿A qué se dedica Varka Consultora?", porque tomó el nombre del perfil de WhatsApp como nombre de la empresa. Pasa con cualquier cliente que tenga el perfil a nombre de su negocio.

Causa: el system prompt define el rol como "detectar dónde pierde tiempo en tareas internas" y dice que el chatbot es "puerta de entrada, pero el ahorro grande está en la trastienda". No hay ninguna regla para cuando la persona ya sabe qué quiere. Además, el push_name se le pasa como "esta persona se llama X" y en el mensaje como "X dice:".

## Qué voy a hacer
1. Backup: tag de git `antes-respeta-pedido` sobre el commit actual (7a97ec7). Producción corre la versión `2026-09-25-b`.
2. `agent.py`, system prompt:
   - En "Tu rol", primero entender **qué necesita la persona** y acompañarla en eso.
   - Regla nueva, **SI LA PERSONA YA SABE QUÉ QUIERE**: si pide algo concreto (un chatbot, por ejemplo), seguís por ahí. Preguntás lo que hace falta para eso (canal, qué consultas recibe) y no le cambiás el tema. La automatización interna se menciona **como mucho una vez en toda la charla**, solo si viene natural y sin "pero antes" ni "lo que más ahorra es…". Si la persona insiste, nunca más.
   - En "Qué hace Varka", el enfoque de la trastienda queda, pero como orientación para quien **no sabe** por dónde empezar.
3. `agent.py`, nota del push_name: "Es el nombre del perfil de WhatsApp. Puede ser el de la persona o el de su negocio; no lo uses como nombre de la empresa ni preguntes a qué se dedica ese nombre". Para agendar se sigue usando como nombre, como hoy.
4. Evals: caso nuevo `in-pide-chatbot` con la conversación del 21/10 (push_name de negocio, "quiero un chatbot" repetido). Checks: `no_contiene` (trastienda, "antes de armar", "lo que más ahorra", "ahorro grande") y `sin_herramientas`. Juez: `responde_lo_que_preguntan` y `no_repregunta`.
5. Correr la compuerta (`--sin-juez --gate`) y, solo para el caso nuevo, una corrida con juez.
6. Subir `APP_VERSION`, hacer commit, push y verificar el deploy.

## Qué NO voy a hacer
- No cambiar el modelo (Haiku 4.5), las guardas, las herramientas ni el agendado.
- No tocar la base de conocimiento (`varka_kb.md`) ni el RAG.
- No sacar el posicionamiento de la trastienda: queda para quien no sabe qué quiere.
- No agregar una guarda por código para esto, salvo que el prompt no alcance en la compuerta. Si no alcanza, se frena y se avisa.

## Qué no se tiene que romper
- Recibe y contesta por WhatsApp. El RAG responde con contexto y, si Voyage falla, contesta en silencio.
- La presentación como IA en el primer mensaje.
- El agendado: horarios reales, email después de los horarios, reserva con notas.
- Los 24 casos actuales pasan la compuerta (umbrales.json).
- El deploy: `GET /` devuelve el `APP_VERSION` nuevo.

## Cómo verifico
- Compuerta con los 25 casos: tiene que decir PASA.
- El caso nuevo, con juez: sin mención de la trastienda después del pedido, y sin "a qué se dedica <nombre del perfil>".
- `curl` a `GET /` con la versión nueva.
- Gonzalo repite la charla del 21/10 por WhatsApp, con el chat de su número borrado antes.

## Costo
- Compuerta sin juez: ~USD 0,20 por corrida. Estimado: 2 corridas.
- Caso nuevo con juez: ~USD 0,05.
- Total estimado: **~USD 0,45**, contra la misma clave de Anthropic que atiende a Sofía.

---

## Segunda parte (21/10, después de la prueba de Gonzalo)

En la prueba con la versión `2026-10-21-a`, Sofía siguió con el chatbot, pero falló el agendado. Las trazas de Langfuse muestran esto:
- Ofreció 4 turnos ("9 u 10, o 9 u 10").
- Con el email ya dado, consultó la agenda (el PASO 3 la obligaba) y cortó ahí: no reservó y volvió a pedir el email.
- La guarda de reserva falsa lo rescató y la reserva salió bien (jue 22/10, 09:00). Pero el texto final de Haiku fue "en una hora nos vemos, te llamamos".
- Interpretó "sobre precios" (lo que preguntan los clientes de la persona) como una pregunta por el precio de Varka y dio US$1.500 + US$200.

Cambios (aprobados por Gonzalo, sin correr pruebas pagas):
1. `tools.py`:
   - `consultar_disponibilidad` devuelve exactamente 2 turnos, el primero de cada uno de los dos primeros días con lugar.
   - `agendar_diagnostico` recibe `inicio` en hora local (`AAAA-MM-DDTHH:MM`) y busca el turno solo en Cal.com. Ya no hace falta consultar dos veces.
   - Si el turno no está libre, devuelve 2 alternativas. Sigue aceptando un ISO con zona.
2. `agent.py`:
   - PASO 1 a 3 del prompt: los 2 turnos de la herramienta, nunca pedir el email dos veces y reservar en el mismo mensaje.
   - Regla de PRECIOS: solo si preguntan cuánto cuesta Varka.
   - Guarda 4: la confirmación de la reserva la arma el código con lo que devuelve la herramienta.
3. `evals/correr.py`: la agenda simulada usa el formato nuevo (2 turnos, `inicio` local).
4. `APP_VERSION` `2026-10-21-b`. Deploy por la API de EasyPanel (`autoDeploy` está en false).

Verificado sin gastar: sintaxis, y `_dos_turnos`, `_a_local` y `_confirmacion` corridos en local, sin llamadas a ninguna API.
