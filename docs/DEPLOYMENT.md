# DEPLOYMENT — DRISHTI on Zoho Catalyst AppSail

One container/bundle is the whole system: FastAPI serves the API, the built
React app, and the SQLite intelligence database. No external services except
Zoho QuickML (LLM features), which degrade to 503 gracefully if absent.

## Target service: AppSail, NOT Slate

Catalyst **Slate** hosts *client-side frontends only* (static React/Vue/Next
builds) — it cannot run DRISHTI's FastAPI backend or its SQLite database. The
whole app (every `/api` call, RBAC, chat) must run on **AppSail** (Catalyst's
general app-hosting service), which serves the API, the built React UI, and the
DB from one process. Slate is not used.

## Status

- The image is **self-provisioning**: `docker build` generates the deterministic
  DB (seed 2026) + intelligence layer *inside the build*, so the git repo needs
  no multi-hundred-MB data artifact and a build-from-repo just works.
- Two prepared paths:
  - **Path A (preferred): Docker image** — `Dockerfile` at repo root.
  - **Path B: native Python bundle** — `deploy/build_appsail_bundle.sh`
    produces `deploy/bundle/` with vendored deps + `app-config.json` template
    (bakes the pre-built DB; deploy via the Catalyst CLI).
- Remaining external step: point AppSail at this repo/image and set the env vars
  below (`DRISHTI_SECRET` is required — auth fails closed without it).

## Path A — Docker

```bash
# No pre-steps: the build generates the DB + intelligence layer itself.
docker build -t drishti .
docker run -p 9000:9000 -e DRISHTI_SECRET=$(openssl rand -hex 32) --env-file .env drishti
# open http://localhost:9000 — sign in with a demo role
```

The container honours `X_ZOHO_CATALYST_LISTEN_PORT` (AppSail), then `PORT`,
then 9000. `DRISHTI_SECRET` is mandatory in a deployed environment.

## Connect on Catalyst (AppSail)

1. Push this repo to a public GitHub repo (submission requirement).
2. Catalyst console → **AppSail** → New app. Either connect the GitHub repo
   (Docker build) **or** deploy the CLI bundle:
   `npm i -g zcatalyst-cli && catalyst login && catalyst deploy` (Path B).
3. AppSail app → **Environment**: set `DRISHTI_SECRET` and the `ZOHO_*` LLM
   vars from `.env.example`. Do NOT upload `.env`.
4. Deploy, then run the smoke test below against the AppSail URL.

## Path B — native AppSail bundle

```bash
bash deploy/build_appsail_bundle.sh     # -> deploy/bundle/
# then: catalyst deploy  (from the Catalyst CLI, inside the project;
# confirm exact stack id in app-config.json at the workshop)
```

## Environment variables (AppSail console → app → Environment)

| Var | Required | Purpose |
|---|---|---|
| `DRISHTI_SECRET` | yes (prod) | signs RBAC login tokens; any long random hex |
| `ZOHO_ACCESS_TOKEN` | for LLM | QuickML OAuth (auto-refreshes) |
| `ZOHO_REFRESH_TOKEN` | for LLM | " |
| `ZOHO_CLIENT_ID` / `ZOHO_CLIENT_SECRET` | for LLM | " |
| `ZOHO_ACCOUNTS_BASE`, `QUICKML_BASE`, `QUICKML_PROJECT_ID`, `CATALYST_ORG`, `GLM_MODEL`, `VLM_MODEL` | for LLM | prefilled in `.env.example` |
| `DRISHTI_STATIC` | no | override built-frontend dir (default `frontend/dist`) |

`backend/app/llm/zoho.py` reads process env first, repo `.env` second — the
container needs no `.env` file. Without LLM vars the app runs fully; only
chat / brief / scan return 503 with a clear message.

## Users, audit log, and container restarts

- Demo users are seeded idempotently at first request into `x_app_user` /
  `x_role` inside the shipped SQLite DB (see `backend/app/auth.py`; the
  roster + shared demo password are in README.md — the data is synthetic).
- The audit trail writes to `x_audit_log` in the same DB (WAL: one writer +
  read-only request connections). AppSail's disk is ephemeral, so audit rows
  reset on redeploy — acceptable for the prototype; the production story
  (deck + ARCHITECTURE.md) is Catalyst Data Store for mutable state. If the
  filesystem is read-only, the sink degrades to an in-memory ring buffer and
  logins fall back to an in-memory roster — the app never 500s over audit.
- Login tokens are stateless HMAC (`DRISHTI_SECRET`), so restarts don't log
  anyone out.

## Smoke test on the deployed URL (the "clean machine" exit criterion)

1. `GET /api/health` → `{"ok": true, "cases": 200846, ...}` (no auth needed).
2. Open the URL → login screen → demo role buttons visible.
3. Sign in as `dgp` → 31 districts on the map, KPI strip populated.
4. Sign in as `sp.dharwad` → 1 district; open the S1 profile → 6 of 11 cases
   with the amber outside-jurisdiction note; open a Belagavi FIR → 403 page.
5. As `dgp`, Audit tab → the sp.dharwad denial is in the trail.
6. Chat: "How many chain snatching cases in Dharwad in 2026?" → answer with
   FIR citations (needs LLM env vars).
7. `docker run` locally with `-e DRISHTI_SECRET=...` only (no ZOHO vars) and
   confirm chat returns the friendly 503 — graceful-degradation check.

## Known limits / accepted tradeoffs

- Single process, SQLite read-mostly: right-sized for the judged workload
  (200k cases, warm API < 300 ms). Horizontal scaling story: stateless API +
  read-only DB replicas; audit to Data Store (documented, not built).
- Demo roster uses one shared password by design (synthetic data, judge
  ergonomics); PBKDF2 hashing + real per-user credentials are already in the
  code path, so production hardening is config, not code.
