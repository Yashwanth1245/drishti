# PLAN — DRISHTI build plan for KSP Datathon 2026

## Mission

Win Challenge 2 by shipping the most production-credible crime intelligence platform
in the field: real reference data, lakhs of adversarially-messy synthetic records,
analytics that survive that mess, and a demo that tells one continuous investigation
story in four minutes.

## Hard constraints (from the organizers' explainer session, 2026-06-08)

1. No real data — only schema + master tables provided. Teams generate synthetic data.
   Suggested volume: 1–2 lakh cases (~1,100 police stations in reality).
2. Deployment on **Zoho Catalyst** is mandatory. LLMs must run on Zoho cloud;
   we use GLM 4.7 `crm-di-glm47b_30b_it` (text) for the agentic layer. (Qwen
   VLM is also available on the platform but our FIR-scan feature was removed.)
3. One team pitches ONE challenge. We pitch Challenge 2 only.
4. Submission (re-submittable until deadline): prototype brief + public GitHub +
   public demo video + Catalyst deployed link + deck in official template.
5. Registration closes Jul 19; prototype deadline **Jul 26**; then shortlist →
   mentor-guided refinement → in-person grand finale.

## What judges said they want (verbatim signals → features)

| Judge signal | Our answer |
|---|---|
| "Static handbook → dynamic drill-down" (DGP) | Map lens: state → district → station, filters by crime head / period / hour band |
| "Proactive, not reactive" | Spike alerts vs historical baseline (z-score), rate-per-lakh hotspot ranking, early-warning feed |
| "Today's crimes are done by networks" | Entity resolution + link graph (co-accused, shared locations, shared accounts), MO tracking |
| "We would like to see agentic AI" | Monitoring agent (watches data, investigates spikes, drafts briefs) + ask-the-data agent |
| "Production grade, model-flat, sustain a decade" | Catalyst deploy, RBAC by real rank, audit log, 2M rows, rollups, load-tested API |
| "Reduce investigation time" | Offender full history in one click, similar-case retrieval, auto case timeline |
| Explainability (challenge text §9) | Every figure/claim cites CrimeNo; evidence drawer in every view |

## Phases

> Live status (2026-07-16): Phases 1–5 COMPLETE + audited + hardened. Scan-FIR
> removed; interface now bilingual English / ಕನ್ನಡ. Public GitHub repo LIVE
> (github.com/Yashwanth1245/drishti); Catalyst AppSail deploy prepared (Docker
> custom runtime + GitHub Actions CI). Phase 6 in progress: deck + demo video
> built; remaining = run the Catalyst deploy, upload the video, submit.
> See `STATUS.md` for the authoritative, granular state.

### Phase 1 — Data foundation (Jul 2–5) — ✅ DONE 2026-07-02
Reference research → `reference/*.json`; datagen package (`datagen/`); DDL for source
schema + extensions; generator with realism catalog + planted stories; outputs
(SQLite, CSV, Excel review workbook, manifest); validation suite; ER gold labels.
**Exit criteria**: `python -m drishti_datagen` produces a validated 2M-row dataset;
Excel workbook opens clean; all planted stories present and discoverable by SQL.

### Phase 2 — Backend + intelligence engines (Jul 6–10) — ✅ DONE 2026-07-02
FastAPI app; SQLite with indexes + rollup tables (daily station × crime-head counts);
engines: hotspots (grid/KDE + hour-band layering), trends & spike detection (baseline
z-scores), entity resolution runner (blocking + fuzzy scoring → PersonMaster),
network builder (co-occurrence edges, plain SQL — no NetworkX), offender risk
scoring, anomaly flags, similar-case retrieval. Every endpoint returns
`evidence: [crimeNos]`.
**Exit criteria**: all engines answer over the full dataset in <1s warm (rollups),
<5s cold; unit tests on engine correctness against planted stories.

### Phase 3 — Frontend lenses (Jul 11–16) — ✅ DONE 2026-07-02
React + MapLibre (district GeoJSON drill-down, hotspot dots, pulsing spike zones),
ECharts (trends, seasonality, hour-of-day heatmap), Cytoscape.js (network explorer),
offender profile page (timeline, MO tags, risk, aliases), alerts feed, KPI header.
**Exit criteria**: demo storyline walkable end-to-end by hand.

### Phase 4 — Agentic layer (Jul 17–20) — ✅ DONE 2026-07-02
LLM client (real Zoho GLM 4.7, OAuth auto-refresh); ask-the-data agent (8 typed
query tools — model never writes SQL — + citation enforcement, bilingual
English/Kannada answers); monitoring-agent intelligence briefs (print-to-PDF).
(Scan-FIR / Qwen VLM was later removed by product decision, 2026-07-16.) Note:
MO extraction is rule-based in datagen (GLM batch extraction is an available
upgrade).
**Exit criteria met**: multi-tool questions answered with FIR citations live
(English + Kannada); Dharwad brief generated — verified live against the real
Catalyst GLM endpoint (API + browser).

### Phase 5 — Production hardening (Jul 21–23) — ✅ DONE 2026-07-03
Login + RBAC by rank (state/range/district/station) on x_app_user/x_role,
enforced server-side on EVERY endpoint incl. the chat agent's tools; audit
log of every query to x_audit_log (+ Audit lens for state roles); backend
serves the built frontend (single-container); Dockerfile + AppSail bundle
script + docs/DEPLOYMENT.md; perf pass (gzip, meta cache, warm max ~170ms);
security pass (401/403 everywhere, PBKDF2, HMAC tokens, env-based secrets).
**Exit criteria met locally**: apicheck 33 assertions ALL PASS incl. the rank
ladder; role demo verified in browser; Docker image built + smoke-tested.
Remaining: the Catalyst upload itself — blocked on the Catalyst project (see
STATUS blocked list).

### Phase 6 — Submission (Jul 24–26) — IN PROGRESS
Public GitHub repo LIVE (github.com/Yashwanth1245/drishti). Submission deck
built in the official template (`DRISHTI_Submission.pptx`). Captioned demo video
recorded (`DRISHTI_demo.mp4`; 3-min shot list in `VIDEO_SCRIPT_3MIN.md`).
REMAINING: run the Catalyst AppSail deploy → paste the live URL + the uploaded
video URL into deck slide 13, verify all three links open, submit. Re-submittable
until the deadline.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Catalyst platform surprises (unknown runtime limits) | Deploy a hello-world AppSail app in Phase 2, not Phase 5; keep everything in one container |
| Zoho LLM quality/latency | All LLM features degrade gracefully; demo pre-warms; batch MO extraction done offline at generation time |
| Scope explosion | STATUS.md pending list is the only backlog; anything not on it is out |
| Solo-coder bus factor | This docs set + deterministic generator = anyone can rebuild state |
| Demo-day network failure | Video + local fallback + screenshot deck |

## Submission checklist (from portal)

- [x] Prototype brief — in the deck (slides 2–4)
- [x] Public GitHub repository — github.com/Yashwanth1245/drishti
- [~] Public demo video — recorded (`DRISHTI_demo.mp4`); upload to YouTube/Drive
- [ ] Deployed solution link on Catalyst — run the AppSail deploy
- [x] Deck built (official template); confirm Challenge 2 on submit
