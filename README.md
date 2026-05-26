# PhyMaC Video Auto-Edit Pipeline

Pipeline de post-producción de video educativo PhyMaC. Reduce el ciclo de edición de ~3 días a ~4-6 horas combinando Whisper para transcripción, un LLM para plan narrativo y FFmpeg + Remotion para composición y render.

> Estado actual (2026-05-26): Phase 1 (Ingesta & Transcripción) y Phase 2 (Plan Narrativo) implementadas y validadas E2E. Phases 3-6 pendientes (ver `aidlc-docs/aidlc-state.md`).

## Stack

| Capa | Tecnología |
|---|---|
| Compute pesado (GPU) | [Modal.com](https://modal.com/) |
| Transcripción | OpenAI Whisper (large-v3) |
| Plan narrativo | LLM vía [OpenRouter](https://openrouter.ai/) (default `openai/gpt-oss-120b:free`) |
| Storage | Cloudflare R2 / AWS S3 (cliente `boto3`) |
| Audio/video | FFmpeg |
| Animaciones | Remotion (Phase 4, pendiente) |
| Frontend | Next.js + Vercel (Unit 8, pendiente) |
| Lenguaje | Python 3.11+ (gestor `uv`) |

## Quickstart local

```bash
# 1. Instalar uv si no lo tenés: https://docs.astral.sh/uv/getting-started/installation/
# 2. Sincronizar dependencias en un .venv local
uv sync

# 3. Copiar .env.example a .env y rellenar credenciales (R2, Modal, OpenRouter)
cp .env.example .env

# 4. Correr Phase 1 sobre un video local
uv run python scripts/run_phase1.py --video ~/Videos/episodio.mp4 --title "Mi episodio"

# 5. Correr Phase 2 sobre el proyecto resultante
uv run python scripts/run_phase2.py --project-id <generated-from-step-4>
```

Variables de entorno requeridas: ver `.env.example`. Las claves OpenRouter y Modal son obligatorias para los pasos LLM y GPU; sin Modal el código cae a Whisper en CPU (lento).

## Layout del repo

```
pipeline/                Código del pipeline (orchestrator, storage, modelos, fases)
  formats.py             Loader de configuración por formato (podcast vs clase)
  phases/                Una fase por archivo (phase1_ingest, phase2_narrative, …)
formats/                 Prompts y whitelists por formato de contenido
  podcast_hablando_con_profes/
scripts/                 CLIs para correr cada fase aisladamente
tests/                   Unit tests (pytest)
aidlc-docs/              Documentación AIDLC del proyecto
docs/superpowers/specs/  Specs de diseño (brainstorming → plan → implementación)
```

## Comandos útiles

```bash
uv run pytest                 # correr tests
uv run ruff check .           # lint
uv run ruff format .          # formato
uv run mypy pipeline/         # type check
```

## Branching

GitFlow clásico:

- `develop` — branch default, integración.
- `main` — producción. Solo recibe PR desde `develop`, `release/*` o `hotfix/*`.
- `feature/<nombre>` — features individuales, PR a `develop`.
- `release/vX.Y.Z` — estabilización antes de release.
- `hotfix/vX.Y.Z+1` — fixes urgentes en producción.

Tags `vX.Y.Z` en `main` disparan release de GitHub + imagen Docker tageada.

## CI/CD

- **CI** (`.github/workflows/ci.yml`): lint, format, typecheck, test (Py 3.11 + 3.12), security audit en cada PR/push a `main`/`develop`/`release/*`/`hotfix/*`.
- **Deploy Modal** (`deploy-modal.yml`): push a `develop` → environment `staging`; push a `main` → environment `main`.
- **Docker** (`docker.yml`): publica imagen multi-stage en GHCR (`ghcr.io/johannes-talero/video-capability`).
- **Release** (`release.yml`): tag `v*` → GitHub Release con notas auto-generadas.

## Licencia

[Apache-2.0](./LICENSE) © 2026 Johannes Talero.
