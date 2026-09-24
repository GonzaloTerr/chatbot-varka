# Evals de Sofía

Pruebas automáticas de comportamiento para Sofía. Corren **el código real** del agente contra 24 conversaciones de prueba y corrigen cada respuesta. Sirven para dos cosas: saber si un cambio de prompt, modelo o base de conocimiento rompió algo **antes** de desplegarlo, y medir la calidad con números.

## Cómo está armado

```
casos.json ──► correr.py ──► agent.responder()   ← el código de producción, sin cambios
 (24 casos)       │            │   ├─ Cal.com   → agenda SIMULADA (nunca reserva de verdad)
                  │            │   ├─ RAG       → contexto FIJO por caso (no gasta Voyage)
                  │            │   └─ LangFuse  → apagado
                  │            ▼
                  │        respuestas de Sofía + herramientas + guardas + tokens
                  ▼
        ┌─────────┴──────────┐
   graders.py             juez.py
   (código, gratis)       (Sonnet 5, solo si no se pasa --sin-juez)
   estilo por respuesta   no insiste · fiel al contexto · no repregunta ·
   reservas y horarios    admite ser IA · mantiene el rol · …
   chequeos del caso
        └─────────┬──────────┘
                  ▼
   corridas/<variante>/results.jsonl + traces/   ──►  resumen · compuerta (umbrales.json)
```

| Archivo | Qué es |
|---|---|
| `casos.json` | Los 24 casos: 20 de gente que escribe y 4 de agendado. Sintéticos, calcados de conversaciones reales, sin datos de nadie. |
| `graders.py` | Correctores por código. Separados a propósito de las guardas de `agent.py`, para no medir la guarda contra sí misma. |
| `test_graders.py` | Prueba que cada corrector rechace su caso malo y acepte el bueno. Gratis. |
| `juez.py` | Un criterio por llamada, rúbrica concreta, salida JSON forzada por esquema. |
| `correr.py` | El runner: concurrencia, techo de 5 min por conversación, retoma donde quedó, errores de plumbing aparte. |
| `umbrales.json` | Mínimos de la compuerta. Hoy solo reglas duras. |
| `ver_casos.py` | Genera `casos.html` (los casos) o `resultados.html` (conversaciones + veredictos). |

## Cómo se usa

**Antes de desplegar un cambio** de prompt, modelo o lógica (~USD 0,20, ~1 min):

```
venv\Scripts\python.exe evals\correr.py --variant v1 --reps 1 --sin-juez --gate
```

Si dice `COMPUERTA: NO PASA`, no se despliega. Cada cambio va en una variante nueva (`v1`, `v2`…).

**Medición completa de calidad**, de vez en cuando (~USD 0,85, ~3 min): `evals\correr.py --variant baseline`. Después, `evals\ver_casos.py --resultados baseline` para leer las conversaciones con los motivos del juez.

**Si se cambia algo del propio eval** (casos, correctores, rúbricas): `evals\test_graders.py` y una corrida saboteada, que es gratis y **tiene** que fallar:

```
venv\Scripts\python.exe evals\correr.py --variant v9 --reps 1 --sin-juez --sabotaje --gate
```

## Qué mide cada cosa

- **Estilo, en cada respuesta:** no vacía, sin emojis, voseo (sin tuteo), sin *vosotros*, sin groserías, ≤300 caracteres, sin saltos de línea, como mucho una pregunta, no vuelve a saludar, no se define como consultora "para pymes".
- **Conversación, siempre:** nunca dice que reservó sin haber reservado, nunca nombra un horario que no salió de la agenda o de la persona.
- **Del caso:** reserva con un horario real, a nombre de la persona y con notas; muestra horarios antes de pedir el email; no usa la agenda cuando no corresponde; sin link; montos prohibidos; etc.
- **Juez:** los criterios que necesitan leer la conversación. Cada veredicto guarda su motivo.

## Estado al 24/09/2026

- ✅ Construido y verificado: los tests de los correctores pasan, Sofía saboteada saca 0% y la compuerta la frena, y el juez rechaza respuestas vacías, "no sé" y respuestas a otra pregunta. Sobre la misma conversación da el mismo veredicto 3 de 3 veces.
- ✅ Piloto de 8 casos en `corridas/piloto/`: 7/8. La falla es real: después de ofrecer el diagnóstico, Sofía lo vuelve a ofrecer sin que la persona muestre un interés nuevo. El piloto se corrigió con una versión anterior de los correctores, por eso no está en `baseline`.
- ⏸️ **Falta la línea base completa** (se decidió no pagarla todavía). Cuando exista, se fijan mínimos para las métricas de calidad.
- ⏸️ **Falta calibrar el juez** contra unas 20 respuestas etiquetadas a mano. Hasta entonces, sus veredictos orientan, pero no bloquean.
- ⏸️ **No existe todavía el eval del recuperador** (si el RAG trae la sección correcta). Usa Voyage real y comparte la cuota con producción.
