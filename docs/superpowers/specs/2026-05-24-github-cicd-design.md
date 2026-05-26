# Diseño: Llevar repo a GitHub + CI/CD

**Fecha**: 2026-05-24
**Estado**: En implementación (2026-05-26)
**Repo real**: https://github.com/JohannesTalero/video-capability (público) — el spec original anotaba `johannes-talero`; el login real es `JohannesTalero` (CamelCase). GHCR namespaces se rebajan a lowercase: `ghcr.io/johannestalero/...`.
**Licencia**: Apache-2.0

## 1. Objetivos

1. Inicializar el directorio actual como repositorio git y publicarlo en GitHub como **público** (`johannes-talero/video-capability`).
2. Adoptar **GitFlow clásico** (`main` + `develop` + `feature/*` + `release/*` + `hotfix/*`).
3. Estandarizar el gestor de dependencias con **uv** (Astral), eliminando `requirements.txt`.
4. Configurar CI que valide cada PR/push a `main` y `develop` con: lint, formato, tipos, tests, security.
5. Configurar CD diferenciado por entorno:
   - `develop` → Modal environment **staging** + Docker `:develop`.
   - `main` → Modal environment **main** (prod) + Docker `:latest`.
   - Tags `vX.Y.Z` → Docker `:vX.Y.Z` + GitHub Release con changelog.
6. Aplicar protección a **ambas** `main` y `develop` (PR + CI verde requeridos). `main` solo acepta PR desde `develop`, `release/*` o `hotfix/*`.

## 1.1 Estrategia de branching — GitFlow clásico

```
main          ●────●─────────●──────●──────●     ← producción (taggeable)
                ╲    ╲       ╱       ╲    ╱
release/*        ╲    ╲     ╱         ●──╱       ← preparación (estabilizar release)
                  ╲    ╲   ╱         ╱   ╲
develop      ●─────●────●─●─────●───●─────●──    ← integración (default branch)
              ╲   ╱       ╲   ╱       ╲
feature/*      ●─●         ●─●         ●─●       ← desarrollo de features
                                                  ← (hotfix/* sale de main, vuelve a main + develop)
```

**Reglas**:
- **Default branch** del repo: `develop` (no `main`). Los devs/PRs apuntan ahí por defecto.
- `feature/<nombre>` → PR a `develop`. Squash merge preferido.
- `release/<vX.Y.Z>` → creada desde `develop` cuando se va a cerrar una versión. Solo acepta fixes (no features). Cuando está lista: PR a `main` (merge commit, no squash) + back-merge a `develop`.
- `hotfix/<vX.Y.Z+1>` → creada desde `main` para bugs urgentes en producción. PR a `main` + back-merge a `develop`.
- **Tags `vX.Y.Z`** solo se crean en commits de `main` (tras merge de `release/*` o `hotfix/*`). El tag dispara `release.yml`.

## 2. Estado actual del repo

- **No es git repo**. Sin `.gitignore`, `README.md`, `LICENSE`, ni `pyproject.toml`.
- Tiene `requirements.txt` (a eliminar), `.env.example` con credenciales esperadas (R2, Modal, OpenRouter, ElevenLabs).
- Código: `pipeline/` (orchestrator, storage, models, validator, llm, config, phases) + `scripts/`.
- Sin tests ni `tests/`.
- Documentación AIDLC en `aidlc-docs/` (a conservar tal cual).
- Archivos a ignorar y NO commitear: `firebase-debug.log`, futuro `.env`, futuro `.venv/`.

## 3. Estructura final de archivos a crear/modificar

```
.
├── .github/
│   └── workflows/
│       ├── ci.yml              # lint + typecheck + test + security (PR + push main)
│       ├── deploy-modal.yml    # modal deploy en push main (post-CI)
│       ├── docker.yml          # build + push GHCR en push main y tags v*
│       └── release.yml         # GitHub Release en tags v*
├── .gitignore                  # Python + WSL + uv + .env + firebase-debug
├── .python-version             # 3.11 (default local)
├── Dockerfile                  # multi-stage uv → runtime con ffmpeg
├── LICENSE                     # Apache-2.0 (Johannes Talero, 2026)
├── README.md                   # qué es, stack, quickstart, link a aidlc-docs
├── pyproject.toml              # deps + ruff + mypy + pytest config
├── uv.lock                     # COMMITTEADO (reproducibilidad)
├── tests/
│   ├── __init__.py
│   ├── test_imports.py         # smoke: módulos importan sin errores
│   ├── test_models.py          # smoke: instanciar Project/PhaseState
│   └── test_orchestrator.py    # smoke: orchestrator con storage mockeado
├── aidlc-docs/                 # (sin cambios)
├── ai-dlc-rules-v0.1.8/        # (sin cambios)
├── pipeline/                   # (sin cambios funcionales)
├── scripts/                    # (sin cambios funcionales)
├── .env.example                # (sin cambios)
└── pipeline-phymac-plan.md     # (sin cambios)
```

Archivos a **eliminar**: `requirements.txt`, `firebase-debug.log` (este último nunca commiteado).

## 4. `pyproject.toml`

```toml
[project]
name = "phymac-pipeline"
version = "0.1.0"
description = "PhyMaC Video Auto-Edit Pipeline (AIDLC)"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "Apache-2.0" }
authors = [{ name = "Johannes Talero", email = "johannes.talero@gmail.com" }]
dependencies = [
    "boto3>=1.34.0",
    "openai-whisper>=20231117",
    "torch>=2.0.0",
    "openai>=1.40.0",
    "modal>=0.63.0",
    "pydub>=0.25.1",
    "python-dotenv>=1.0.0",
    "fastapi>=0.111.0",
    "uvicorn>=0.30.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
    "pip-audit>=2.7.0",
    "bandit>=1.7.9",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]
ignore = ["E501"]  # delegado a formatter

[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true       # tolerante con boto3/whisper/modal stubs
disallow_untyped_defs = false       # permisivo MVP
warn_unused_ignores = true
warn_redundant_casts = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.bandit]
exclude_dirs = ["tests", ".venv"]
```

## 5. `.gitignore`

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# uv / venv
.venv/

# Entornos / secretos
.env
.env.local
*.local

# Modelos y artefactos del pipeline
*.pt
*.bin
outputs/
checkpoints/

# Modal
.modal/

# Frontend futuro
node_modules/
.next/

# Logs y debug
*.log
firebase-debug.log

# OS
.DS_Store
Thumbs.db

# IDE
.idea/
.vscode/
```

Nota: `.python-version` SÍ se commitea (lo lee `uv` y `pyenv`) — por eso NO aparece en `.gitignore`.

## 6. CI — `.github/workflows/ci.yml`

```yaml
name: CI
on:
  pull_request:
    branches: [main, develop, "release/**"]
  push:
    branches: [main, develop, "release/**", "hotfix/**"]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { enable-cache: true }
      - run: uv sync --frozen --only-group dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { enable-cache: true }
      - run: uv sync --frozen
      - run: uv run mypy pipeline/

  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { enable-cache: true }
      - run: uv python install ${{ matrix.python }}
      - run: uv sync --frozen --python ${{ matrix.python }}
      - run: uv run pytest -v

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { enable-cache: true }
      - run: uv sync --frozen
      - run: uv run pip-audit
      - run: uv run bandit -r pipeline/ -c pyproject.toml
```

## 7. CD — `.github/workflows/deploy-modal.yml`

```yaml
name: Deploy to Modal
on:
  push:
    branches: [main, develop]
  workflow_dispatch:
    inputs:
      environment:
        description: "Modal environment override"
        required: false
        type: choice
        options: [staging, main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    # No usa `needs:` entre workflows: branch protection garantiza que cualquier
    # commit en `main`/`develop` ya pasó CI verde (no se permite push directo, solo merge tras PR).
    environment: ${{ github.ref == 'refs/heads/main' && 'production' || 'staging' }}
    env:
      MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}
      MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}
      MODAL_ENVIRONMENT: >-
        ${{
          inputs.environment != ''
            && inputs.environment
            || (github.ref == 'refs/heads/main' && 'main' || 'staging')
        }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { enable-cache: true }
      - run: uv sync --frozen
      - name: Verify Modal token
        run: uv run modal token verify
      - name: Show target environment
        run: echo "Deploying to Modal environment → $MODAL_ENVIRONMENT"
      - name: Deploy (placeholder)
        # TODO: reemplazar por `uv run modal deploy pipeline/modal_app.py`
        # cuando exista el archivo de app Modal (Unit 7 — Render Final).
        run: echo "Modal app file not yet present — verify only"
```

**Mapping de branch → Modal environment**:
| Branch          | Modal environment | GitHub environment (para approvals/secrets) |
|-----------------|-------------------|---------------------------------------------|
| `develop`       | `staging`         | `staging`                                   |
| `main`          | `main`            | `production`                                |
| `release/*`     | (sin deploy)      | —                                           |
| `hotfix/*`      | (sin deploy)      | — (deploy ocurre al mergear a `main`)       |

**Nota sobre secrets**: usamos un único par `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` (mismo workspace Modal). La separación de entornos es por `MODAL_ENVIRONMENT`, no por token. Si en el futuro se requieren tokens distintos, se mueven a los GitHub environments `staging` / `production` ya configurados.

## 8. CD — `.github/workflows/docker.yml`

```yaml
name: Docker
on:
  push:
    branches: [main, develop]
    tags: ["v*.*.*"]

jobs:
  build-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/johannes-talero/video-capability
          # Mapping:
          #   push develop  → :develop, :sha-xxxxxxx
          #   push main     → :latest,  :sha-xxxxxxx
          #   tag  vX.Y.Z   → :vX.Y.Z, :X.Y.Z, :X.Y, :X
          tags: |
            type=raw,value=develop,enable=${{ github.ref == 'refs/heads/develop' }}
            type=raw,value=latest,enable=${{ github.ref == 'refs/heads/main' }}
            type=sha,prefix=sha-,format=short
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=semver,pattern={{major}}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

## 9. CD — `.github/workflows/release.yml`

```yaml
name: Release
on:
  push:
    tags: ["v*.*.*"]

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          draft: false
          prerelease: ${{ contains(github.ref, '-rc') || contains(github.ref, '-beta') || contains(github.ref, '-alpha') }}
```

## 10. `Dockerfile` (multi-stage con uv)

```dockerfile
# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY pipeline/ ./pipeline/
COPY scripts/ ./scripts/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── runtime ─────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["python", "-m", "pipeline.orchestrator"]
```

## 11. Smoke tests

**`tests/test_imports.py`** — valida que todos los módulos del pipeline importan sin error.

**`tests/test_models.py`** — instancia `Project`, `PhaseState`, `ValidationResult` con valores válidos y verifica defaults.

**`tests/test_orchestrator.py`** — instancia `PipelineOrchestrator` pasándole un `StorageAdapter` mockeado (`unittest.mock.MagicMock`), valida que se construye sin tocar red ni filesystem.

Sin tests E2E ni de red en CI. Sin fixtures pesadas (sin descargar modelos Whisper).

## 12. Branch protection en `main` y `develop`

**`develop`** (default branch):
- Require pull request before merging: **on** (sin aprobadores obligatorios al ser solo-dev).
- Require status checks: **on**, contextos: `lint`, `typecheck`, `test (3.11)`, `test (3.12)`, `security`.
- Require branches to be up to date before merging: **on**.
- Do not allow force pushes: **on**.
- Do not allow deletions: **on**.

**`main`** (producción):
- Todas las reglas de `develop`, **más**:
- Restrict who can push to matching branches: **on** (lista vacía → solo merges via PR).
- **Restrict source branches** vía ruleset: solo PRs desde `develop`, `release/*` o `hotfix/*` pueden mergearse a `main`. (Implementación: GitHub Repository Ruleset con `required_pull_request_source_branch_pattern`.)

Comandos `gh api` para aplicar ambas reglas se incluyen en el plan de implementación.

## 13. Secretos y environments en GitHub

**Environments** (Settings → Environments):
- `staging` — sin protection rules. Asociado a `develop`.
- `production` — `required reviewers: johannes-talero` (opcional pero recomendado). Asociado a `main`.

Esto permite que en el futuro, si se requieren secrets distintos por entorno (p.ej. tokens Modal separados), se muevan a nivel environment sin tocar workflows.

**Repository secrets** (configurar vía `gh secret set`):
- `MODAL_TOKEN_ID`
- `MODAL_TOKEN_SECRET`

`GITHUB_TOKEN` es automático (no configurar).

NO ir a CI ni a GitHub secrets por ahora:
- `OPENROUTER_API_KEY`, `R2_*`, `ELEVENLABS_API_KEY` (solo runtime de Modal, no CI).

## 14. Pasos de ejecución (orden)

1. Instalar `gh` + `uv` localmente; usuario hace `gh auth login`.
2. `git init -b main`, crear `.gitignore`, `README.md`, `LICENSE` (Apache-2.0), `pyproject.toml`, `.python-version`.
3. `uv lock` para generar `uv.lock`. Eliminar `requirements.txt`.
4. Crear `tests/` con los 3 smoke tests.
5. Crear `Dockerfile`.
6. Crear los 4 workflows en `.github/workflows/`.
7. Commit inicial en `main`.
8. **Crear branch `develop` desde `main`**: `git branch develop && git checkout develop`.
9. `gh repo create johannes-talero/video-capability --public --source=. --remote=origin --push` (empuja ambas branches).
10. **Establecer `develop` como default branch**: `gh repo edit johannes-talero/video-capability --default-branch develop`.
11. Configurar GitHub environments `staging` y `production` (`gh api`).
12. Configurar secretos repo (`gh secret set MODAL_TOKEN_ID` etc.).
13. Aplicar branch protection a `main` y `develop` (`gh api`).
14. Verificar: crear `feature/ci-smoke-test` desde `develop`, abrir PR a `develop`, ver CI verde, mergear.
15. Verificar: PR de `develop` → `main`, ver que se dispara CI + Modal staging deploy + Docker `:develop` build al mergear a develop, y luego prod + `:latest` al mergear a main.

## 15. Fuera de alcance (explícito)

- Frontend Next.js / Vercel CD (Unit 8, pendiente).
- E2E tests con servicios reales.
- Pre-commit hooks locales (puede agregarse después).
- Dependabot / Renovate (puede agregarse después).
- Coverage reporting (puede agregarse después).

## 16. Riesgos y mitigaciones

- **`openai-whisper` y `torch` son pesados** → el job `security` y `test` instalan todo. Mitigación: cache de uv habilitada, suficiente. Si CI se vuelve lento (>5 min), evaluar split deps en grupo opcional `[ml]`.
- **`modal deploy` requiere archivo de app Modal que aún no existe** → workflow corre solo `token verify` con TODO documentado hasta Unit 7.
- **Pipeline aún en construcción (Units 3-8 pendientes)** → tests smoke aceptan esto; CI valida lo que existe sin bloquear avance de AIDLC.

## 17. Criterios de aceptación

- [ ] Repo público visible en `https://github.com/johannes-talero/video-capability` con **default branch = `develop`**.
- [ ] `uv sync && uv run pytest && uv run ruff check . && uv run mypy pipeline/` corre verde localmente.
- [ ] PR `feature/* → develop` dispara los 4 jobs CI y todos terminan verdes.
- [ ] Push/merge a `develop` dispara `deploy-modal` con `MODAL_ENVIRONMENT=staging` y `docker` publica `:develop` + `:sha-xxx` en GHCR.
- [ ] Push/merge a `main` dispara `deploy-modal` con `MODAL_ENVIRONMENT=main` y `docker` publica `:latest` + `:sha-xxx`.
- [ ] Tag `v0.1.0` crea Release de GitHub con notas auto-generadas y Docker `:v0.1.0` + `:0.1.0` + `:0` en GHCR.
- [ ] Branch protection bloquea push directo a `main` y `develop`.
- [ ] PR directo de `feature/* → main` es rechazado por ruleset (solo `develop`/`release/*`/`hotfix/*` permitidos).
