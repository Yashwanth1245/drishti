# ARCHITECTURE — DRISHTI system design

## Shape of the system

One fused data foundation (the "ontology"), four intelligence engines, five lenses,
and an evidence/audit spine through everything. Maven-style: every lens is a view
into the same truth; pivoting between map → network → profile → chat never loses
the entity you were looking at.

```
reference/*.json ──┐
                   ├─► datagen ─► exports/drishti.db (SQLite) + CSV + Excel
planted stories ───┘                    │
                                        ▼
                    backend (FastAPI, Python 3.12)
     ┌──────────────┬──────────────┬──────────────┬─────────────┐
     │ patterns     │ networks     │ risk         │ alerts      │   engines
     │ hotspots,    │ ER + link    │ explainable  │ spikes +    │
     │ trends       │ graph        │ scoring      │ anomalies   │
     └──────┬───────┴──────┬───────┴──────┬───────┴──────┬──────┘
            ▼              ▼              ▼              ▼
       REST API  (every response carries evidence: [CrimeNo...])
            │
            ▼
     frontend (React + Vite)
     Command map · Trends · Alerts · Network · Ask the data (bilingual EN/ಕನ್ನಡ)
            │
     RBAC + audit log on every request
```

## Stack and why

| Layer | Choice | Why |
|---|---|---|
| Data store | SQLite (WAL) shipped inside the app image; rollup tables precomputed | Zero-ops, read-mostly workload, 2M rows trivial with indexes; judges test the app, not our DB ops |
| Mutable state | Ships inside the SQLite DB (users/audit, WAL single-writer); Catalyst Data Store is the documented production path | Prototype keeps one system of record; the Data Store migration is config, not code |
| Backend | FastAPI + rapidfuzz (entity resolution) + Python stdlib `statistics` | Lean footprint — NO heavy DS stack (no pandas/sklearn/NetworkX); every threshold lives in `config.py`, auditable in one file |
| Frontend | React + Vite, MapLibre GL (map), Cytoscape.js (graph), ECharts (charts); full English/ಕನ್ನಡ i18n | All open source, no keys needed, proven for exactly these visualizations |
| Geo | Karnataka district GeoJSON (public), station points from generator | District choropleth + point drill-down |
| LLM | `ZohoLLM` client (backend/app/llm/zoho.py) → real Catalyst QuickML: GLM 4.7 `crm-di-glm47b_30b_it` powers the agentic "ask the data" layer (English + Kannada), OAuth auto-refresh | Mandated platform; LLM features degrade gracefully (rest of app never touches the LLM) |
| Deploy | Zoho Catalyst AppSail, single Docker image (backend serves built frontend) | Mandatory platform; one container = fewest moving parts |

## Backend API surface (Phase 2 target)

```
GET  /api/kpis?scope=...                      headline numbers for role's scope
GET  /api/map/districts?head=&from=&to=       choropleth counts + spike flags
GET  /api/map/stations?district=&hour_band=   station-level points + hotspots
GET  /api/trends?scope=&head=&granularity=    series + baseline + spike markers
GET  /api/alerts?scope=                       active early-warning alerts
GET  /api/network/person/{id}?depth=          ego graph (nodes typed person/case/
                                              location/account, edges typed)
GET  /api/person/{id}                         profile: cases, timeline, MO, risk,
                                              aliases, ER-merge provenance
GET  /api/cases/{id}                          case detail + similar cases
POST /api/chat                                ask-the-data agent (tools + citations)
POST /api/brief                               monitoring-agent intelligence brief
                                              ({district_id} or {alert_id};
                                              print-to-PDF in the UI)
GET  /api/er/metrics                          ER precision/recall (honesty endpoint)
POST /api/auth/login · GET /api/auth/me       login (PBKDF2 + stateless HMAC tokens)
GET  /api/auth/demo                           demo role roster for the login screen
GET  /api/audit                               audit trail (state roles only)
```

BUILT (Phases 2–5): all of the above are implemented and live-tested — see
`backend/app/main.py`, `auth.py`, `chat.py`, `brief.py`. The chat agent
uses 8 typed, parameter-bound query tools (the model never writes SQL) and its
answers carry `[CrimeNo]` citations plus the full tool trace. LLM access goes
through `backend/app/llm/zoho.py` (real Zoho QuickML endpoints, OAuth
auto-refresh, response shape `{"response": str, "tool_calls": [...]}`).
In production the same FastAPI process serves the built frontend
(`frontend/dist`) — one container is the whole deployment (`Dockerfile`,
`docs/DEPLOYMENT.md`).

Every data-bearing response includes `evidence`: the list of CrimeNo values (or
row references) behind the figure. The UI renders this as an expandable drawer.

## The engines

1. **Patterns**: daily rollup table `agg_daily(unit_id, crime_head_id, date, n)`
   powers trends; spike = count in window vs seasonal baseline (median of same
   window over prior 12 periods) exceeding z-threshold; hotspots = station-grid
   density weighted by hour band (the "time-of-day layer" judges asked for).
2. **Networks**: after entity resolution, edges = co-accused in case, shared
   incident location cluster, shared financial account, arrested together.
   Connected components + degree/betweenness surface "organized groups"; stored to
   `network_edges` so graph queries are instant.
3. **Entity resolution**: blocking (soundex/metaphone of name token + district +
   gender) → rapidfuzz scoring (name similarity, age within ±3, geography) →
   threshold merge into `person_master`; every merge stores its score and inputs
   (explainability); precision/recall measured against generator gold labels and
   REPORTED in the UI ("ER accuracy on test set: X%") — honesty as a feature.
4. **Risk & alerts**: offender risk = recency/frequency/gravity/escalation/breadth
   composite (documented formula in `config.py`, not a black box; every factor is
   reported in the profile); spike alerts = z-score of a 90-day window vs 8 trailing
   windows; emerging-trend alerts = year-over-year growth; anomalies = rule-based
   (serial false complainant, duplicate FIRs, slow stations).
   **Honest scope**: the intelligence is deterministic statistics + rapidfuzz entity
   resolution + hosted-LLM orchestration — there is NO trained ML model, and
   forward-looking crime FORECASTING is roadmap, not built.

## RBAC model (mirrors real rank hierarchy) — BUILT (Phase 5)

| Role | Demo user | Scope |
|---|---|---|
| DGP / SCRB analyst | `dgp`, `scrb` | Whole state + audit trail |
| DIG (range) | `dig.northern` | Their range's districts (resolved from Unit.ParentUnit) |
| SP / DCP (district/city) | `sp.dharwad` | Their district |
| Inspector / IO (station) | `io.hubballi` | Their station's case records |

Enforced server-side on every endpoint via a FastAPI dependency
(`auth.current_user`) whose resolved district/station set is injected into
every SQL WHERE clause — the UI additionally adapts, but hiding is UX, not
security. Out-of-scope requests return 403 with a human explanation.

Audit trail = ACTIONS, not HTTP traffic (`x_audit_log`). It records what
oversight actually asks about: sign-ins (incl. failures), name searches,
profile / FIR / network / case-list access (with the record identity in the
summary), AI usage (chat questions + tools used, briefs, scans), and every
DENIED attempt (logged centrally by the 403 handler). Dashboard aggregates
(KPIs, map, trends) are deliberately not audited — logging them drowns the
signal; uvicorn's access log already covers ops telemetry. Future write
paths (saving a scanned-FIR draft, record edits) log as `record-update`
events in the same vocabulary — who changed what, with references.

Access doctrine — GRADUATED DISCLOSURE (the design decision that resolves
every scoping question):
- **Identity intelligence** (entities, aliases, risk scores, accused ID
  captures, network graph, name search, linked case NUMBERS) is statewide
  shared intel — the linkage picture is never fragmented by rank.
- **Following a link** to an out-of-jurisdiction FIR shows its STRUCTURAL
  record: number, dates, station, sections, status, MO tags, accused
  identity links, similar cases. Victim/complainant details, the narrative,
  captured identifiers and property are redacted (with counts) behind a
  "Request access" action that is logged as an `access-request` audit event
  (production: routed to the owning SP for approval).
- **Bulk browsing** of another jurisdiction (case lists, another district's
  map drill) is refused outright — linkage is shared, trawling is not.
This mirrors how inter-jurisdiction criminal intelligence sharing actually
works and keeps the ER layer useful to every rank.

Auth mechanics: PBKDF2 password hashes in `x_app_user` (seeded idempotently
at startup); stateless HMAC-signed tokens (`DRISHTI_SECRET`) so restarts
never log anyone out; the chat agent receives the caller's scope and its
tools filter server-side (prompt injection cannot cross jurisdictions).

## Performance targets (judges probe this)

- Warm queries (rollups): < 300 ms. Cold analytical queries: < 5 s on 2M rows.
- Graph ego queries: < 500 ms (precomputed edges).
- Startup: rollups + network edges are built at generation time, not runtime.
- Load: API stateless → AppSail horizontal scaling story; SQLite read-only
  concurrency is fine (WAL, no writers at serve time except audit → Data Store).

## Security notes

- Chat agent never free-writes SQL: it selects from parameterized query templates
  (tool calls with typed arguments), so prompt injection cannot exfiltrate or mutate.
- AuthZ on every endpoint (scope filter), not just navigation hiding.
- No PII concerns (all data synthetic) — but we treat it as if real: audit trail,
  role scoping, no secrets in repo (.env pattern).
