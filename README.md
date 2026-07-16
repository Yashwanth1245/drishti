# DRISHTI — Karnataka Crime Intelligence Platform

**KSP Datathon 2026 · Challenge 2: Crime Intelligence & Analytical Platform**

DRISHTI (ದೃಷ್ಟಿ, "vision") turns the static *Crime in Karnataka* handbook into a living
command center for the State Crime Records Bureau and district officers: interactive
drill-down crime maps, spatiotemporal hotspot detection, criminal network graphs built
on entity resolution, offender risk profiles, predictive spike alerts, and an agentic
"ask the data" layer — every number traceable to specific FIR records.

Because KSP provides only the database **schema** (no real data), DRISHTI ships with a
calibrated synthetic data generator that produces lakhs of realistic Karnataka crime
records: real districts, real police structure, real IPC/BNS sections, NCRB-calibrated
crime proportions — with deliberately messy, adversarial data (aliases, typos, missing
coordinates, false cases) so the platform proves itself against reality, not a happy path.

## Repository map

| Path | What lives here |
|---|---|
| `docs/` | All planning and design documents — **start with `docs/STATUS.md`** |
| `reference/` | Curated real-world reference data (districts, sections, names, stats) |
| `datagen/` | Synthetic data generator (Python) — outputs SQLite DB + CSV + Excel |
| `backend/` | FastAPI service: analytics engines + API |
| `frontend/` | React dashboard: map, network, profiles, chat, reports |
| `exports/` | Generated data deliverables (DB, CSVs, Excel review workbook) |
| `resources/` | Official datathon files (master data, evaluation params, deck template) |
| `scripts/` | One-off utilities (deploy, validation, packaging) |

## Documents

- [docs/STATUS.md](docs/STATUS.md) — what is done, in progress, pending (always current)
- [docs/PLAN.md](docs/PLAN.md) — build plan, timeline to July 26, submission checklist
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design, stack, Catalyst deployment
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — source schema + our extension tables
- [docs/SYNTHETIC_DATA_DESIGN.md](docs/SYNTHETIC_DATA_DESIGN.md) — generator spec: volumes, realism, planted stories
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — the 4-minute judge walkthrough

## Quick start

```bash
# 0. one-time setup
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm install)
cp .env.example .env   # then paste Zoho QuickML credentials (LLM features)

# 1. generate the database (deterministic; ~15s, ~100s with Excel export)
cd datagen && python3 -m drishti_datagen --seed 2026 --cases 200000
python3 -m drishti_datagen --verify        # 40+ integrity/calibration checks
#   flags: --csv (raw CSVs too)  --skip-export (fast dev loop)

# 2. build the intelligence layer (ER, network, risk, alerts, rollups; ~10s)
cd ../backend && ../.venv/bin/python -m app.precompute
../.venv/bin/python -m app.selfcheck       # 14 engine assertions
../.venv/bin/python -m app.apicheck        # 33 API + RBAC assertions + latency

# 3. run the platform
../.venv/bin/uvicorn app.main:app --port 8000        # backend (from backend/)
cd ../frontend && npm run dev                         # frontend on :5173
# production path (one container serves API + built UI):
#   (cd frontend && npm run build) then open http://localhost:8000
#   or: docker build -t drishti . && docker run -p 9000:9000 drishti
```

Six lenses in the UI (plus Audit for state roles): Command map · Trends ·
Alerts · Network · Ask the data (GLM agent with cited answers) · Scan FIR
(Qwen document extraction). Demo scan asset: `exports/demo_fir_scan.png`.

## Sign-in (RBAC demo roles)

Access control mirrors the real KSP hierarchy and is enforced server-side on
every endpoint; every sensitive action — searches, profile/FIR access, AI
usage, sign-ins, and denied attempts — lands in the audit trail. All demo
accounts use password **`drishti2026`** (publishing this is deliberate — the
data is 100% synthetic and judges must switch ranks in one click):

| Username | Rank / jurisdiction | Sees |
|---|---|---|
| `dgp` | DGP — state | everything + audit trail |
| `scrb` | SCRB analyst — state | everything + audit trail |
| `dig.northern` | DIG — Northern Range (Belagavi) | 5 districts |
| `sp.belagavi` | SP — Belagavi district | 1 district |
| `sp.davanagere` | SP — Davanagere district | 1 district |
| `sp.dharwad` | SP — Dharwad district | 1 district |
| `io.market` | Inspector — Market PS (Belagavi) | their station's case records |
| `io.davanagere` | Inspector — Davanagere Town PS | their station's case records |
| `io.hubballi` | Inspector — Hubballi Town PS (Dharwad) | their station's case records |

The three SPs and three IOs are deliberately the districts AND stations of
the flagship S1 story: every rank sees all 11 of the offender's linked case
numbers, but the 🔒-restricted count walks the whole ladder — state 0,
range 2, SPs 8/9/5, station IOs 8/9/5 — the "fragmented information"
problem made visible and resolved by rank.

Doctrine — **graduated disclosure**: identity intelligence (entities,
aliases, risk, networks, linked case numbers) is statewide; following a link
to an out-of-jurisdiction FIR shows its structural record (dates, sections,
status, MO, accused links) while victim/party details and the narrative stay
with the owning jurisdiction behind a logged **Request access** action. Only
bulk browsing of another jurisdiction is refused outright. Deployment guide:
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Datathon constraints (non-negotiable)

- Deployment on **Zoho Catalyst** is mandatory; LLMs must run on Zoho cloud
  (GLM 4.7 `crm-di-glm47b_30b_it` for text, Qwen VLM `VL-Qwen3.6-35B-A3B` for
  images — both wired live via `backend/app/llm/zoho.py` with OAuth auto-refresh).
- Prototype submission deadline: **26 July 2026** (re-submission allowed until then).
- Submission = public GitHub repo + public demo video + deployed Catalyst link +
  deck in the official template.
