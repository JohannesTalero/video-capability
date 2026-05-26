# Requirement Verification Questions
# PhyMaC Video Auto-Edit Pipeline

**Instrucciones**: Responde con la letra de tu opción (A, B, C...) después de cada `[Answer]:`. Si eliges "Otro", describe tu respuesta.

---

## BLOQUE 1 — Scope del MVP (lo que construimos primero)

### Q1: ¿Cuál es el alcance del MVP inicial?

El plan tiene 6 fases. Para construir iterativamente, necesito saber cuál es la versión mínima funcional.

```
A) Solo Fase 1: Ingesta + Transcripción (subir video → ver transcripción en el browser)
B) Fases 1 + 2: Transcripción + Plan Narrativo generado por Claude (sin generación de materiales)
C) Fases 1 + 2 + 3: Transcripción + Plan + Generación de materiales de apoyo (sin composición final)
D) Pipeline completo (las 6 fases) desde el primer día
X) Otro (describe):
```

[Answer]:

---

### Q2: ¿Dónde se ejecuta el sistema?

```
A) Local en tu máquina (sin cloud, sin deployment)
B) Modal.com para procesamiento pesado + Next.js en Vercel para la UI
C) Todo en Modal.com (backend + frontend como servicio)
D) AWS completo (Lambda, ECS, S3)
X) Otro (describe):
```

[Answer]:

---

## BLOQUE 2 — Inputs y Outputs

### Q3: ¿Cuáles son los formatos de video de entrada?

```
A) Solo MP4 (el más común)
B) MP4 + MOV (grabaciones de cámara y pantalla)
C) Cualquier formato que FFmpeg soporte (MP4, MOV, MKV, AVI, WebM)
X) Otro (describe):
```

[Answer]:

---

### Q4: ¿Cuál es la duración típica del video crudo que vas a subir?

```
A) Clips cortos (< 15 minutos) — entrevistas cortadas, reels
B) Videos medios (15–60 minutos) — episodios de podcast normales
C) Videos largos (1–3 horas) — entrevistas completas sin editar
D) Variable — puede ser cualquier duración
X) Otro (describe):
```

[Answer]:

---

### Q5: ¿Cuál es el output final esperado del pipeline?

```
A) Un solo video MP4 listo para subir a YouTube (resolución 1080p)
B) Video principal (YouTube) + versión recortada para Reel/Short
C) Video principal + múltiples cortes (reel, short, clip de LinkedIn)
D) Solo el material editado/cortado — el render final lo hago yo en otro editor
X) Otro (describe):
```

[Answer]:

---

## BLOQUE 3 — UI y Experiencia

### Q6: ¿Qué tan importante es la UI de revisión en el MVP?

```
A) Mínima — prefiero scripts de línea de comandos para el MVP, UI después
B) Básica — solo necesito ver la transcripción y aprobar el plan (sin drag & drop)
C) Completa — quiero la UI con editor de plan, timeline y preview desde el día 1
D) Headless primero — API/CLI que funcione, UI como segunda iteración
X) Otro (describe):
```

[Answer]:

---

### Q7: ¿Cómo se identificará cada proyecto de video en el sistema?

```
A) Nombre del archivo de video subido
B) Título que escribo manualmente al crear el proyecto
C) UUID generado automáticamente (transparente para el usuario)
D) Combinación: título manual + fecha automática
X) Otro (describe):
```

[Answer]:

---

## BLOQUE 4 — Identidad Visual PhyMaC

### Q8: ¿Los assets de identidad de PhyMaC (intro, outro, logo, cortinillas) ya existen en formato digital listo para usar?

```
A) Sí, tengo todos los assets listos (MP4 de intro/outro, PNG de logo, etc.)
B) Tengo algunos assets pero me faltan otros (especifica cuáles en X)
C) No tengo assets todavía — el pipeline debe funcionar sin branding primero
D) No tengo assets, pero puedo generarlos antes de comenzar a construir
X) Otro (describe):
```

[Answer]:

---

### Q9: ¿La generación de material de apoyo (ecuaciones, diagramas) debe usar el estilo visual de PhyMaC (colores, fuentes) o puede ser genérica en el MVP?

```
A) Genérica en el MVP — colores neutros, ajuste de marca después
B) Con marca básica desde el inicio — al menos los colores correctos (#XXXXXX)
C) Completamente on-brand desde el inicio — fuentes, colores, logo en cada elemento
X) Otro (describe):
```

[Answer]:

---

## BLOQUE 5 — Audio

### Q10: ¿La generación de música de fondo (Fase 5) es parte del MVP o puede esperar?

```
A) Puede esperar — el MVP procesa el audio existente (limpieza + normalización) pero no genera música nueva
B) Es parte del MVP — quiero música de fondo generada automáticamente desde el día 1
C) La música la pongo yo manualmente — el sistema solo limpia y normaliza el audio
X) Otro (describe):
```

[Answer]:

---

## BLOQUE 6 — Infraestructura y Costo

### Q11: ¿Ya tienes cuentas y API keys configuradas?

Marca todas las que aplican con Sí/No:

- Modal.com account: [Answer]:
- OpenAI API key (Whisper): [Answer]:
- Anthropic API key (Claude): [Answer]:
- Cloudflare R2 o AWS S3: [Answer]:
- ElevenLabs account: [Answer]:

---

### Q12: ¿Cuál es el límite de costo por video que considerás aceptable?

```
A) < $2 USD por video (muy austero, optimizar todo)
B) $3–5 USD por video (el estimado del plan está bien)
C) $5–20 USD por video (calidad sobre costo)
D) Sin límite para el MVP — optimizamos cuando tengamos volumen
X) Otro (describe):
```

[Answer]:

---

## BLOQUE 7 — Testing y Calidad

### Q13: ¿Tenés un video de prueba de PhyMaC disponible para testear el pipeline end-to-end durante la construcción?

```
A) Sí, tengo un video real de PhyMaC disponible (< 30 min)
B) Sí, tengo un video real pero es largo (> 30 min)
C) No tengo video disponible ahora — usaría un video de ejemplo genérico
D) Prefiero testear con un video muy corto grabado específicamente para testing
X) Otro (describe):
```

[Answer]:

---

### Q14: ¿Qué pasa si una fase del pipeline falla?

```
A) El proceso falla completamente — quiero saber que algo salió mal y empezar de nuevo
B) Retry automático (hasta 3 intentos) antes de fallar
C) El proceso se pausa en la fase que falló y me notifica para intervenir
D) Sistema de checkpoint — si falla en Fase 4, puedo reanudar desde Fase 4 sin repetir 1-3
X) Otro (describe):
```

[Answer]:

---

> **Una vez que respondas estas preguntas, generaré el documento de requisitos completo y el plan de construcción definitivo.**
