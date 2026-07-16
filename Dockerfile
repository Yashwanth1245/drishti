# DRISHTI — single-container deployment for Zoho Catalyst AppSail (or any Docker
# host). Stage 1 builds the React frontend. Stage 2 is the Python runtime that
# GENERATES the deterministic SQLite intelligence database at build time — so the
# image is fully self-contained and the git repo needs no multi-hundred-MB data
# artifact — then serves the API + built UI + DB from one process.
#
# Build for Catalyst AppSail — its custom runtime accepts ONLY linux/amd64 OCI
# images, so ALWAYS pass --platform (emulated on Apple Silicon Macs):
#   docker build --platform linux/amd64 -t drishti .
# Run locally to smoke-test (no data pre-step — the build generates it):
#   docker run -p 9000:9000 -e DRISHTI_SECRET=$(openssl rand -hex 32) --env-file .env drishti
# Then open http://localhost:9000 and sign in with a demo role.
#
# Catalyst AppSail sets X_ZOHO_CATALYST_LISTEN_PORT; we honour it, then PORT,
# then default 9000. LLM credentials arrive as env vars (see .env.example) —
# without them the app still runs; only chat/brief/scan return 503.
# DRISHTI_SECRET is REQUIRED in a deployed environment (auth fails closed).

FROM node:20-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Source needed to BUILD the data and RUN the app. The layout mirrors the repo
# so backend/app/config.py and the datagen package both resolve ROOT=/app.
COPY backend/ backend/
COPY datagen/ datagen/
COPY reference/ reference/

# Generate the deterministic dataset (seed 2026) + the intelligence layer
# (entity resolution, network, risk, alerts, rollups) into /app/exports. This
# runs datagen then precompute — the exact sequence in docs/DEPLOYMENT.md.
RUN mkdir -p /app/exports \
 && (cd datagen && python -m drishti_datagen --seed 2026 --skip-export) \
 && (cd backend && python -m app.precompute)

COPY --from=ui /ui/dist /app/frontend/dist

ENV PYTHONUNBUFFERED=1
WORKDIR /app/backend
EXPOSE 9000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${X_ZOHO_CATALYST_LISTEN_PORT:-${PORT:-9000}}"]
