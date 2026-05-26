# Execution Plan
# PhyMaC Video Auto-Edit Pipeline

**Versión**: 1.0  
**Fecha**: 2026-05-21  
**Tipo**: Greenfield · Alta Complejidad · Sistema Distribuido

---

## Análisis de Impacto

- **User-facing**: Sí — UI web completa (upload, editor, preview, descarga)
- **Estructural**: Sí — sistema nuevo con 6 servicios coordinados
- **Data model**: Sí — proyectos, transcripciones, planes, materiales, estados de fase
- **API changes**: N/A (greenfield)
- **NFR impact**: Sí — GPU compute, latencia, costo por ejecución, checkpoints

**Nivel de riesgo**: Medio-Alto  
— Múltiples servicios distribuidos, GPU en cloud, dependencias externas (3 APIs), procesamiento de video de gran tamaño. Mitigado por: enfoque iterativo fase-a-fase, checkpoints, video de prueba real disponible.

---

## Visualización del Workflow

```
[Start]
   |
   v
[INCEPTION]
   |-- [x] Workspace Detection      ← COMPLETADO
   |-- [x] Reverse Engineering      ← SKIPPED (Greenfield)
   |-- [x] Requirements Analysis    ← COMPLETADO
   |-- [x] User Stories             ← SKIPPED (herramienta interna, 1 usuario)
   |-- [x] Workflow Planning        ← EN CURSO
   |-- [ ] Application Design       ← EXECUTE
   |-- [ ] Units Generation         ← EXECUTE
   v
[CONSTRUCTION] — Per-Unit Loop
   |-- Unit 1: Core Pipeline + Storage Layer
   |     |-- Functional Design      ← EXECUTE
   |     |-- NFR Requirements       ← EXECUTE
   |     |-- Infrastructure Design  ← EXECUTE
   |     |-- Code Generation        ← EXECUTE
   |
   |-- Unit 2: Fase 1 — Ingesta & Transcripción
   |     |-- Code Generation        ← EXECUTE
   |
   |-- Unit 3: Fase 2 — Plan Narrativo (Claude API)
   |     |-- Functional Design      ← EXECUTE
   |     |-- Code Generation        ← EXECUTE
   |
   |-- Unit 4: Fase 3 — Generación de Materiales
   |     |-- Functional Design      ← EXECUTE
   |     |-- Code Generation        ← EXECUTE
   |
   |-- Unit 5: Fase 4 — Composición + Branding Multi-marca
   |     |-- Functional Design      ← EXECUTE
   |     |-- Code Generation        ← EXECUTE
   |
   |-- Unit 6: Fase 5 — Audio Processing
   |     |-- Code Generation        ← EXECUTE
   |
   |-- Unit 7: Fase 6 — Render Final + Checkpoints
   |     |-- Code Generation        ← EXECUTE
   |
   |-- Unit 8: UI — Next.js Frontend
   |     |-- Functional Design      ← EXECUTE
   |     |-- Code Generation        ← EXECUTE
   |
   |-- [ ] Build and Test           ← EXECUTE
   v
[OPERATIONS] — PLACEHOLDER
   v
[Complete]
```

---

## Fases a Ejecutar

### 🔵 INCEPTION PHASE
- [x] Workspace Detection — COMPLETADO
- [x] Reverse Engineering — SKIPPED (Greenfield, no hay código existente)
- [x] Requirements Analysis — COMPLETADO
- [x] User Stories — SKIPPED (herramienta interna de un solo usuario, sin múltiples personas ni acceptance criteria que requieran stories formales)
- [x] Workflow Planning — EN CURSO (este documento)
- [ ] Application Design — **EXECUTE** — Sistema nuevo con múltiples componentes/servicios que necesitan definición de interfaces, contratos de datos entre fases, y diseño del orquestador
- [ ] Units Generation — **EXECUTE** — 8 unidades de trabajo identificadas que se construyen iterativamente

### 🟢 CONSTRUCTION PHASE (Per-Unit Loop)

**Unit 1 — Core Pipeline + Storage Layer** (base de todo el sistema)
- [ ] Functional Design — EXECUTE — Modelos de datos, contratos entre fases, estructura de proyecto, sistema de checkpoints
- [ ] NFR Requirements — EXECUTE — Performance (GPU), costo por ejecución, resiliencia, multi-marca
- [ ] Infrastructure Design — EXECUTE — Modal.com setup, R2/S3 abstraction, estructura de carpetas en storage
- [ ] Code Generation — EXECUTE

**Unit 2 — Fase 1: Ingesta & Transcripción**
- [ ] Code Generation — EXECUTE (diseño ya definido en RF-01, sin ambigüedad que requiera Functional Design adicional)

**Unit 3 — Fase 2: Plan Narrativo Claude API**
- [ ] Functional Design — EXECUTE — Diseño del prompt system, estructura del JSON de plan, contrato de aprobación usuario→sistema
- [ ] Code Generation — EXECUTE

**Unit 4 — Fase 3: Generación Paralela de Materiales**
- [ ] Functional Design — EXECUTE — Diseño del dispatcher paralelo Modal.map(), contratos por tipo de material
- [ ] Code Generation — EXECUTE

**Unit 5 — Fase 4: Composición + Branding Multi-marca**
- [ ] Functional Design — EXECUTE — Arquitectura multi-marca (config JSON por marca), pipeline FFmpeg de composición
- [ ] Code Generation — EXECUTE

**Unit 6 — Fase 5: Audio Processing**
- [ ] Code Generation — EXECUTE (limpieza + normalización, sin lógica de negocio compleja adicional)

**Unit 7 — Fase 6: Render Final + Sistema de Checkpoints**
- [ ] Code Generation — EXECUTE

**Unit 8 — UI Next.js Frontend**
- [ ] Functional Design — EXECUTE — Flujo de pantallas, estados de la UI, contrato con el backend (API REST/WebSocket)
- [ ] Code Generation — EXECUTE

**Fase final**
- [ ] Build and Test — EXECUTE — Instrucciones de build completas, tests end-to-end con video real de PhyMaC

### 🟡 OPERATIONS PHASE
- [ ] Operations — PLACEHOLDER

---

## Secuencia de Construcción (Orden Recomendado)

El orden respeta las dependencias entre unidades:

```
1. Unit 1 (Core + Storage)     ← BASE — todo lo demás lo necesita
2. Unit 2 (Fase 1 Transcripción) ← Primera fase funcional verificable
3. Unit 3 (Fase 2 Plan Narrativo) ← Depende de transcripción
4. Unit 8 (UI Frontend) — en paralelo con Unit 4 si hay tiempo
5. Unit 4 (Fase 3 Materiales)  ← Depende de plan narrativo
6. Unit 5 (Fase 4 Composición) ← Depende de materiales + assets PhyMaC
7. Unit 6 (Fase 5 Audio)       ← Depende de video compuesto
8. Unit 7 (Fase 6 Render)      ← Integra todo + sistema de checkpoints
```

---

## Criterios de Éxito por Día

| Día | Unidad(es) | Criterio de Done |
|-----|-----------|-----------------|
| 1 | Unit 1 + Unit 2 | Subís un MP4/MOV con título → transcripción editada en browser/CLI en < 10 min |
| 2 | Unit 3 + Unit 8 (básica) | Plan narrativo generado por Claude, aprobable. UI con upload + transcripción |
| 3 | Unit 4 | 10 materiales de apoyo generados en paralelo en < 5 min |
| 4 | Unit 5 + Unit 6 | Video compuesto con branding PhyMaC + audio limpio |
| 5 | Unit 7 + Unit 8 (completa) | Video final 1080p descargable. Checkpoint funcional. UI completa con preview |

---

## Prerrequisitos a Resolver Antes de Arrancar

| Prerrequisito | Urgencia | Para cuándo |
|---------------|----------|-------------|
| Modal.com account | 🔴 Crítico | Antes de Día 1 |
| OpenAI API key (Whisper) | 🔴 Crítico | Antes de Día 1 |
| Anthropic API key (Claude) | 🟠 Alto | Antes de Día 2 |
| Cloudflare R2 o AWS S3 | 🟠 Alto | Antes de Día 1 |
| Inventario de assets PhyMaC | 🟡 Medio | Antes de Día 4 |
| Node.js + Python local | 🔴 Crítico | Antes de Día 1 |

---

## Timeline Estimado

- **Fases de Inception restantes**: Application Design + Units Generation (~2-3 horas de sesión)
- **Construction Phase**: 5 días de desarrollo (puede variar según disponibilidad de API keys y assets)
- **Total proyecto**: ~7-8 sesiones de trabajo

---

## Éxito del Proyecto

**Objetivo primario**: Procesar el video real de PhyMaC (> 30 min) en < 4 horas con calidad publicable en YouTube.

**Entregables clave**:
1. Pipeline Python ejecutable en Modal.com (6 fases con checkpoints)
2. UI Next.js completa (upload → preview → descarga)
3. Sistema de branding multi-marca (PhyMaC + arquitectura para nuevas marcas)
4. Costo de operación < $5 USD por video

**Calidad**:
- Cada fase verificada end-to-end con video real antes de avanzar
- Sistema de checkpoints que permite reanudar desde cualquier fase
- Costo monitoreado por video desde el primer día
