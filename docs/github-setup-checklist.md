# Checklist — Configuración manual de GitHub (post-push)

Repo: <https://github.com/JohannesTalero/video-capability>
Estado al empezar: `main` y `develop` pusheadas, sin default branch cambiada, sin environments, sin secrets, sin branch protection.

Tiempo estimado: **10–15 min**.

Marcá los checkboxes a medida que completás cada paso.

---

## 1. Cambiar el default branch a `develop`

**Por qué**: Convención GitFlow — los PRs y los clones por defecto apuntan a `develop`. `main` queda reservado para producción.

- [ ] Ir a **Settings → General** del repo: <https://github.com/JohannesTalero/video-capability/settings>
- [ ] Bajar a la sección **Default branch**.
- [ ] Click en el icono ⇄ junto a `main`.
- [ ] Seleccionar `develop` en el dropdown.
- [ ] Click **Update**, confirmar el warning.

**Verificación**: Al volver a <https://github.com/JohannesTalero/video-capability>, el dropdown de branches debe mostrar `develop` como default (marcado con label "default").

---

## 2. Crear los environments `staging` y `production`

**Por qué**: Cada push a `develop` deploya a Modal env `staging`; cada push a `main` deploya a env `main` (prod). Los GitHub environments permiten secrets por entorno y reviewers obligatorios.

### 2.1 Environment `staging`

- [ ] Ir a **Settings → Environments**: <https://github.com/JohannesTalero/video-capability/settings/environments>
- [ ] Click **New environment**.
- [ ] Name: `staging`. Click **Configure environment**.
- [ ] Dejar todo sin marcar (sin reviewers obligatorios, sin wait timer, sin deployment branches). Click **Save protection rules** (si aparece) o simplemente cerrar — staging no necesita protecciones.

### 2.2 Environment `production`

- [ ] Volver a **Settings → Environments**.
- [ ] Click **New environment**.
- [ ] Name: `production`. Click **Configure environment**.
- [ ] Marcá **Required reviewers** y agregá tu user `JohannesTalero` (opcional pero recomendado — si lo activás vas a tener que aprobar cada deploy a producción manualmente; quita esto si no querés esa fricción).
- [ ] En **Deployment branches and tags**, seleccioná **Selected branches and tags** y agregá la rule `main` (de modo que solo `main` puede deployar a producción).
- [ ] Click **Save protection rules**.

**Verificación**: En <https://github.com/JohannesTalero/video-capability/settings/environments> debés ver los dos environments listados.

---

## 3. Subir los secrets `MODAL_TOKEN_ID` y `MODAL_TOKEN_SECRET`

**Por qué**: El workflow `deploy-modal.yml` necesita estos para autenticarse contra Modal.

**De dónde sacar los valores**: De tu `.env` local en `/mnt/c/Users/johan/Documents/PhyMaC/video-capability/.env`, líneas `MODAL_TOKEN_ID=...` y `MODAL_TOKEN_SECRET=...`. **No los pegues en chat ni los compartas con un LLM.** Copialos directo del archivo a la web UI.

- [ ] Ir a **Settings → Secrets and variables → Actions**: <https://github.com/JohannesTalero/video-capability/settings/secrets/actions>
- [ ] Click **New repository secret**.
- [ ] Name: `MODAL_TOKEN_ID`. Value: pegar el valor de tu `.env` (la línea después de `MODAL_TOKEN_ID=`).
- [ ] Click **Add secret**.
- [ ] Click **New repository secret** de nuevo.
- [ ] Name: `MODAL_TOKEN_SECRET`. Value: pegar el valor de tu `.env`.
- [ ] Click **Add secret**.

**Verificación**: La página de secrets debe listar dos: `MODAL_TOKEN_ID` y `MODAL_TOKEN_SECRET`. (Los valores no se muestran nunca, solo el nombre.)

**NO subir todavía** a GitHub secrets:
- `OPENROUTER_API_KEY`, `R2_*`, `ELEVENLABS_API_KEY` — esos se usan en runtime de Modal (no en CI). Modal los pide aparte, no acá.

---

## 4. Branch protection en `develop`

**Por qué**: Forzar que todo cambio a `develop` pase por PR + CI verde antes de mergear. Evita pushes directos accidentales.

- [ ] Ir a **Settings → Rules → Rulesets**: <https://github.com/JohannesTalero/video-capability/settings/rules>
- [ ] Click **New ruleset → New branch ruleset**.
- [ ] **Ruleset name**: `develop-protection`.
- [ ] **Enforcement status**: `Active`.
- [ ] **Bypass list**: dejar vacío (sin bypass para nadie).
- [ ] **Target branches** → **Add target** → **Include by pattern** → escribir `develop` → **Add Inclusion pattern**.
- [ ] En **Rules** marcá:
  - [x] **Restrict deletions**
  - [x] **Require a pull request before merging**
    - Required approvals: `0` (sos vos solo en el repo)
    - [x] Dismiss stale pull request approvals when new commits are pushed
    - [x] Require approval of the most recent reviewable push
  - [x] **Require status checks to pass**
    - [x] Require branches to be up to date before merging
    - Click **Add checks** y agregá estos contextos uno a uno (escribilos exactos):
      - `lint`
      - `typecheck`
      - `test (3.11)`
      - `test (3.12)`
      - `security`
  - [x] **Block force pushes**
- [ ] Click **Create**.

**Nota**: Los status checks pueden aparecer como "X required check has not been completed" hasta que CI corra por primera vez. Es normal — el primer PR los va a registrar.

**Verificación**: En la página de rulesets, `develop-protection` debe aparecer como `Active`.

---

## 5. Branch protection en `main` (más estricta)

**Por qué**: `main` es producción. Solo recibe merges desde `develop`, `release/*` o `hotfix/*`. Nunca PRs directos desde `feature/*`.

- [ ] Volver a **Settings → Rules → Rulesets** y click **New ruleset → New branch ruleset**.
- [ ] **Ruleset name**: `main-protection`.
- [ ] **Enforcement status**: `Active`.
- [ ] **Bypass list**: dejar vacío.
- [ ] **Target branches** → **Add target** → **Include by pattern** → `main`.
- [ ] En **Rules** marcá lo mismo que en `develop`, **más**:
  - [x] **Restrict deletions**
  - [x] **Require a pull request before merging**
    - Required approvals: `0`
    - [x] Dismiss stale pull request approvals when new commits are pushed
    - [x] Require approval of the most recent reviewable push
    - **Allowed merge methods**: dejá solo **Merge commit** (sin squash, sin rebase — GitFlow usa merge commits para releases).
  - [x] **Require status checks to pass**
    - [x] Require branches to be up to date before merging
    - Mismos 5 contextos: `lint`, `typecheck`, `test (3.11)`, `test (3.12)`, `security`.
  - [x] **Block force pushes**
  - [x] **Restrict pull request source branches** → Pattern: `develop|release/.*|hotfix/.*` (esto fuerza que solo esas branches puedan abrir PRs hacia main).
- [ ] Click **Create**.

**Verificación**: En la página de rulesets debés ver `develop-protection` y `main-protection`, ambos `Active`.

---

## 6. Verificación end-to-end con un PR de prueba

**Por qué**: Confirmar que CI corre, status checks aparecen, y branch protection se aplica.

```bash
# En tu terminal (mismo directorio del repo)
git checkout develop
git pull
git checkout -b feature/ci-smoke
echo "# Smoke test" >> docs/github-setup-checklist.md
git add docs/github-setup-checklist.md
git commit -m "test: trigger CI smoke run"
git push -u origin feature/ci-smoke
```

- [ ] Abrir <https://github.com/JohannesTalero/video-capability/pulls> → New pull request.
- [ ] Base: `develop` ← Compare: `feature/ci-smoke`. Click **Create pull request**.
- [ ] Esperar que los 5 status checks aparezcan y se pongan verdes (5–8 min — la primera vez baja torch, así que puede demorar).
- [ ] Una vez verde, click **Merge pull request** → confirmar.
- [ ] Verificar que después del merge a `develop` se disparan:
  - `Deploy to Modal` workflow → debe correr en environment `staging` (verificalo en <https://github.com/JohannesTalero/video-capability/actions>).
  - `Docker` workflow → debe publicar `ghcr.io/johannestalero/video-capability:develop` y `:sha-xxxxxxx`.
- [ ] Borrar la branch `feature/ci-smoke` después del merge (botón "Delete branch" aparece en el PR cerrado).

---

## Criterios de aceptación final

- [ ] Default branch es `develop`.
- [ ] Environments `staging` y `production` existen.
- [ ] Secrets `MODAL_TOKEN_ID` y `MODAL_TOKEN_SECRET` están seteados.
- [ ] Branch protection activa en `main` y `develop` con los 5 status checks requeridos.
- [ ] PR de prueba pasó CI y mergeó a `develop`.
- [ ] `deploy-modal` corrió en `staging` y `docker` publicó `:develop` tras el merge.

Cuando termines todo esto, decime y procedemos con el primer release real (Unit 3 ya está implementada, solo falta merge `develop → main` vía PR para taggear v0.1.0).

---

## Si algo falla

- **CI rojo en `test`**: el job descarga `torch` y `openai-whisper` — pesa ~2 GB. Puede tardar la primera vez. Si falla por timeout, re-runear el job en la pestaña Actions.
- **CI rojo en `typecheck`**: probablemente algún tipo incompatible. Mirar el output del job — los errores de `mypy` son específicos.
- **CI rojo en `security` (pip-audit / bandit)**: revisar si hay alguna vulnerability nueva en deps. `pip-audit` falla si hay CVE conocidas; `bandit` chequea código Python por patrones inseguros.
- **`deploy-modal` falla con "Could not authenticate"**: verificar que los secrets están bien copiados (sin espacios, sin saltos de línea al final del valor).
- **Branch protection no bloquea push directo**: verificar que el ruleset está `Active` y que tu usuario NO está en la lista de bypass.
# Smoke test
