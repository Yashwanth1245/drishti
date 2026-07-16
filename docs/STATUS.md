# STATUS — single source of truth for project state

> Update this file at the end of every working session. Keep entries short.
> Last updated: **2026-07-03** (Phases 1–5 complete: RBAC + audit + deploy
> artifacts built and verified; Catalyst upload waits only on the project)

> Doc currency (audited 2026-07-03): ALL markdown files match the built product
> — CLAUDE.md, README.md, ARCHITECTURE.md, DATA_MODEL.md, DEMO_SCRIPT.md,
> SYNTHETIC_DATA_DESIGN.md, and PLAN.md (now carries per-phase ✅ status
> markers). STATUS.md is the live granular tracker. validation_report.md is
> auto-generated each datagen run. reference/README.md documents the curated
> real-world data.

## Done

- [x] Challenge selected: **Challenge 2** (Crime Intelligence & Analytical Platform).
      Chat panel included as Challenge 2's agentic layer; we do NOT pitch Challenge 1.
- [x] ER diagram analyzed (`~/Downloads/Police_FIR_ER_Diagram.pdf`, 23 tables).
      Gaps identified: no person master, no MO field, no financial tables, no
      Gender/BloodGroup lookups, Inv_OccuranceTime referenced but undefined.
- [x] Explainer-session transcript analyzed. Key rules captured in PLAN.md
      (synthetic data only, Catalyst mandatory, 1–2 lakh cases suggested,
      agentic AI wanted, production-grade judging).
- [x] Git repo initialized; folder structure; documentation set written
      (README, CLAUDE.md, PLAN, ARCHITECTURE, DATA_MODEL, SYNTHETIC_DATA_DESIGN,
      DEMO_SCRIPT).
- [x] Reference research complete → `reference/*.json` (4 verified files: police
      structure 31 districts/7 ranges/6 commissionerates + real station names,
      32 IPC↔BNS offence mappings + 12 acts, census demographics + name pools +
      18 variant sets, NCRB 2023 calibration). Caveats in `reference/README.md` —
      generator MUST honor them (BNS cutover follows offence date; 80.5% night
      burglary; snatching hides under theft/robbery; gentle monthly seasonality).

## In progress — Phase 1 datagen build (increments; resume at first unchecked)

Run/verify command after any increment:
`cd datagen && python3 -m drishti_datagen && python3 -m drishti_datagen --verify`

- [x] **1a. Foundation + org builder** — DONE 2026-07-02, verify ALL PASS.
      Files: config.py, util.py, reference.py, names.py, lookups.py,
      orgbuilder.py, schema.sql, __main__.py. Produces: 31 districts, 7 ranges,
      6 commissionerates + KGF, 1,163 stations (all with x_unit_geo coords),
      12,540 employees, 240 courts, 14 acts / 119 sections / 10 crime heads,
      32 offence IPC<->BNS mappings. Notes for next session: seed_lookups()
      returns the offence registry the case engine needs; IDs are insertion-
      order-stable; DistrictIDs are 1001-1031 in police-file order; station
      UnitIDs start after org units (~46). Runtime ~0.1s.
- [x] **1b. Person factory** — DONE 2026-07-02. persons.py builds the offender
      pool IN MEMORY each run (144k identities = cases*0.72; 17,491 repeaters
      with case budgets avg ~3.5, capacity 187k accused-rows; 6,205 with
      spelling variants via names.variant_of(); 897 true street aliases; 10,591
      cross-district repeaters; 34,707 distinct display names — duplicates are
      deliberate, ER must separate by age/geo). NOTE: pool is NOT persisted by
      1b — the case engine (1c) inserts only the persons actually used into
      x_person_master/x_person_alias and writes x_er_gold truth links.
      names.py gained compound names, female suffixes, and the variant engine
      (trailing-vowel toggle, join, initial move/drop, transliteration sets).
      Decision: BriefFacts = 2-6 sentence report-style narratives from the same
      variables as structured columns (never contradict); ~10% terse, ~15%
      Kannada-mixed; MO vocabulary embedded (spec in SYNTHETIC_DATA_DESIGN.md).
- [x] **1c. Case engine** — DONE 2026-07-02, verify ALL PASS (22 checks),
      runtime ~11s for the full pipeline. Files: crimetypes.py (26-type catalog:
      every offence's calibrated share, legal keyword/SLL sections, timing,
      places, parties, property, MO vocab, templates) + cases.py (engine).
      Produces per run: 200k cases (unique CrimeNos in official format; UDR/PAR/
      Zero FIR categories), ~248k accused rows, ~170k victims, ~225k persons
      persisted with gold ER labels (~6k alias rows), ~163k identity captures,
      ~267k MO tags, ~46k property rows, act-sections IPC pre / BNS post
      offence-date cutover. Calibration validated: night burglary 79-80% (NCRB
      80.5%), SLL share 25.9% (target ~24%), Bengaluru cyber share 84% (NCRB
      80.5%). Narratives render from the same variables as columns.
      Known accepted quirks: ~20k one-off persons minted beyond the pool when a
      district's supply runs dry (by design); station-name suffix appears in
      place text. NEXT (1d): arrests + chargesheets must honor cstype mix by
      crime type, set CaseStatusID (currently all 1 = Under Investigation),
      write arrest-time aadhaar captures (time-ramped 35%->65%).
- [x] **1d. Process engine** — DONE 2026-07-02, verify ALL PASS (30 checks),
      pipeline ~13s. process.py: per-crime-type outcome table (OUTCOMES dict,
      NCRB-calibrated), arrests+surrenders (~204k; SLL red-handed same-day;
      1.5% out-of-state, 8% other-district), chargesheets A/B/C (~128k final
      reports; overall A rate 72% vs KA 77%; theft-group 41%), statuses (34%
      under investigation, disposed-by-court for old chargesheets), 58 slow
      stations (1.6x duration — dashboard insight), arrest-time aadhaar capture
      time-ramped (~103k captures; 122k total accused aadhaar captures).
      cases.py now returns (stats, proc) — the in-memory per-case handoff.
      Time integrity enforced: no arrest/chargesheet before registration or
      after span end; recent cases stay open.
- [x] **1e. Stories + realism** — DONE 2026-07-02, verify ALL PASS (40 checks),
      pipeline ~14s. stories.py: StoryWriter helper + S1-S5 planted with full
      lifecycles and rich briefs; manifest at exports/stories.json (the demo
      answer key; validator asserts against it). S1 snatcher: person "B. Ravi
      Kumar" (pid in manifest), 11 cases across Belagavi/Davanagere/Dharwad,
      3 spellings + alias "Chikka Ravi", aadhaar 738492016453 captured at BOTH
      arrests (2024 real name, 2025 alias -> the alias-exposure demo), live
      4-case Hubballi spike Apr-Jun 2026. S2 ring: 6 thieves rotating pairs +
      fence "Salim Mujawar" (pid in manifest) in 4 cases. S3 fraud: "GoldenBull
      Trading App", 15 CEN cases rising 2025-26, 5 mule pids incl. the fence
      (finance trail wiring for 1f is in the manifest). S4 escalation
      (Manjunatha D, Mysuru). S5 false complainant (Gangamma, Tumakuru, 6 B
      cases). realism.py mess pass (story cases protected): 14k missing coords,
      20k station-default coords, 600 swapped lat/long, 24.7k name typos, 800
      duplicate FIRs (with copied act-sections), 144 wrong-act citations
      confined to Jul-Sep 2024. LESSON RECORDED: serials must be MAX(substr(
      CrimeNo,-5))+1 per (station,category,year), never COUNT-based — counts
      drift once multiple stages insert at the same key.
- [ ] **1f. Finance weaver — DEFERRED by user decision (2026-07-02) to a later
      phase** (build alongside the financial-analysis UI). Wiring preserved:
      exports/stories.json carries S3 mule_pids + fence_pid; x_fin_account /
      x_fin_txn tables already exist in schema.sql. When built: victim payments
      -> 5 mule accounts -> 2 aggregators -> cash-out; fence is a mule.
- [x] **1g. Exports** — DONE 2026-07-02, updated to CONSOLIDATED workbook.
      export.py now produces ONE file exports/excel/DRISHTI_database.xlsx (52
      sheets: Data dictionary + legend, Reconciliation with DB==sheet counts,
      then all 50 tables as FULL-DATA sheets, blue/teal/amber tabs+headers,
      story cases lead CaseMaster). Streaming write-only mode; 3.1M rows.
      Tradeoff: ~124MB, ~30-60s to open in Excel; export step ~80s (dev uses
      --skip-export -> ~15s). CLI: --csv also emits raw CSVs; --skip-export
      skips the workbook. x_provenance seeded. Tables auto-split if they ever
      exceed Excel's 1,048,576-row limit (none do at 200k/500k cases).
      NOTE: rollups (x_agg_daily, x_network_edge) split out to Phase 2 start.
- [x] **1h. Validation report** — DONE 2026-07-02. validate.py writes
      exports/validation_report.md (human-readable proof for judges/deck):
      volumes, calibration-vs-NCRB table (night burglary 79.6%/80.5%, SLL
      25.9%/~24%, Bengaluru cyber 84.3%/80.5%, chargesheet 72%/77%), defect
      counts, ER-challenge stats, story list. Machine checks stay in --verify
      (40+ assertions, ALL PASS).
      Repeater fix included: SPEC_MAP lacked "body" mappings so body-spec
      repeaters were never drawn (13% repeat share); after mapping + any-spec
      fallback + pick rate 0.45 -> repeat offenders now carry 30% of accused
      rows (186,954 persons behind 235,084 rows) — matches the criminological
      claim in the deck.

**PHASE 1 COMPLETE (2026-07-02)** — data foundation done in one day: 50 tables,
~3.2M rows, 19s full pipeline, deterministic, NCRB-calibrated, adversarially
messy, 5 verified demo stories, CSV+Excel dual delivery. Deferred: finance
(user decision). Moved to Phase 2 start: rollups (x_agg_daily, x_network_edge).

## Pending (build order)

- [ ] **Phase 1 — Data foundation** (target Jul 5): datagen package, schema DDL,
      generator with realism + planted stories, SQLite + CSV + Excel exports,
      validation suite, entity-resolution gold labels
- [ ] **Phase 2 — Backend + engines** (target Jul 10) — increments:
      - [x] 2a. id_hash upgrade DONE 2026-07-02: x_identity_capture 7th column
            (salted sha256[:16] of full entered value; masked display kept);
            all 4 writers updated; 225,929 hashed captures; S1's hash appears
            exactly twice (alias-exposure link). Datagen verify ALL PASS.
      - [x] 2b. rollups DONE: x_agg_daily 182,033 rows (station x head x day),
            totals reconcile with CaseMaster.
      - [x] 2c. ER DONE — precision 0.9406, recall 0.2911, F1 0.44, 215,789
            entities from 235,084 rows in ~3s; largest cluster 11 (no blobs).
            Three passes: (1) hard links via id_hash/phone (16,183); (2) rare-
            name attribute match ONLY in blocks <= 8 rows statewide (1,694) —
            common names NEVER merge on attributes (with only name/age/gender
            in Accused, two 'Nagaraju, 28, Mysuru' are indistinguishable — we
            refuse rather than guess); (3) MO linkage grouped by (name-skel,
            gender, RARE tag), two rounds, strong/semi/weak tiers (1,418).
            JOURNEY (do not regress): naive fuzzy = 0.0098 precision (chained
            blobs of 839); +MO-required = 0.011; rare-name-only pass2 = 0.94
            but S1 shattered (pass3 blocks too big); tag-scoped pass3 = S1
            whole but 0.30 (weak branch chained mono-token names); final
            tiered rules = 0.94 + ALL stories resolve. Low recall is DOCTRINE
            (precision-first), improves as ID capture ramps — deck insight.
      - [x] 2d. network DONE: 163,922 co-accused entity edges w/ case evidence
            (shared-phone edges legitimately 0 — same-phone rows are same
            entity after pass 1).
      - [x] 2e. risk + alerts DONE: explainable risk factors JSON per entity
            (S4 escalation=1.0 detected; S1 rank 41 of 215,789); 301 spikes
            (subhead-level AND MO-pattern-level — pattern-level added because
            4 snatchings drown inside broad robbery volume; Dharwad
            'two-wheeler-pillion-snatch' fires at +220%, z>=2), 3 emerging
            trends (cyber YoY), 17 anomalies (Gangamma serial-false, duplicate
            FIRs, slow stations).
      - [x] 2f. FastAPI DONE 2026-07-02: app/main.py — /api/health, /api/meta,
            /api/kpis, /api/map/districts (+spike flags, per-lakh rates),
            /api/map/stations (hour-band filter), /api/trends, /api/alerts
            (evidence as CrimeNos), /api/entities/{id} (profile: cases,
            aliases, captured IDs, risk factors, associates, evidence),
            /api/network/entity/{id} (ego graph, evidence per edge),
            /api/cases/{crime_no} (full detail + similar-case retrieval via
            shared MO tags), /api/cases (filterable list), /api/search
            (entities by any shown name + CrimeNo prefix), /api/er/metrics
            (the honesty endpoint). CORS open for frontend dev.
            Serve: ../.venv/bin/uvicorn app.main:app --port 8000 (from backend/)
      - [x] 2g. selfcheck.py DONE: 14 engine assertions ALL PASS
            (../.venv/bin/python -m app.selfcheck); apicheck.py DONE: 18 API
            assertions ALL PASS incl. the full demo pivot (search 'Ravikumar'
            -> entity 11 cases + same visible aadhaar on both arrests -> case
            detail + similar cases; fence ego network with edge evidence;
            Dharwad pattern spike with evidence). Warm latencies: max 169ms
            (case detail), rest < 132ms — inside the 300ms architecture target
            (../.venv/bin/python -m app.apicheck).

Phase 3 MAP BUGFIX (2026-07-02, user-reported): (1) circles drifted on zoom —
were HTML markers (pixel-anchored); replaced with GeoJSON circle LAYERS
(district-fill + animated dspike-glow + station-fill) that transform with the
basemap → zero drift. Removed the symbol label layer (its glyph font 404'd and
retried every frame → console error spam); district names now via hover popup +
side panel. (2) "every district showed a spike" — 301 spikes across all 31
districts; map flag now honors the crime-head filter and, for "all heads",
flags only the top-6 by peak z (→3 real hotspots). Endpoint returns spike_z +
summary. DEMO_SCRIPT cold-open updated (Dharwad no longer top-6 in all-heads;
its snatching story surfaces on Alerts tab). Verified live: remount renders,
htmlMarkers=0, leaderboard shows 2 spike chips not 31.

**PHASE 2 COMPLETE (2026-07-02)** — engines + API done in one day. Next:
Phase 3 frontend (map, trends, network explorer, profiles, alerts feed) on
these endpoints; then Phase 4 agentic layer; Phase 5 Catalyst deploy.
      NOTES: venv at .venv/ (PEP 668); run backend with .venv/bin/python.
      2026-07-02 (user decision): x_identity_capture.id_value now stores the
      FULL synthetic Aadhaar (was masked) — synthetic data, and full numbers
      make the demo's identity matching visibly obvious; id_hash retained (ER
      matches on it; production story = mask display, match on hash).
      Consistency audited: 94,190 captured persons, 0 inconsistent numbers,
      0 captures differing from person master, 0 cross-person collisions;
      S1 shows 'Ravikumar B' (2024) and alias 'Chikka Ravi' (2025) with the
      SAME visible number 738492016453. Indexes added on x_er_gold(source/
      person) + x_identity_capture(role, source_row_id) — gold joins were
      quadratic without them. Engines re-run: ER 0.9406 unchanged, selfcheck
      ALL PASS.
      Datagen change in 2e: snatching now its own subhead ('Theft — Snatching')
      via kw="Snatching" + section-string cleanup in lookups (_clean_section;
      pre-BNS books as IPC 379). Exports workbook is STALE (regens used
      --skip-export) — run full datagen before submission.
- [x] **Phase 3 — Frontend lenses** DONE 2026-07-02 (target was Jul 16 — 14 days
      early). React 18 + Vite + MapLibre + ECharts + Cytoscape, dark command-
      center theme (frontend/src/styles.css). Hash router, all deep-linkable.
      VERIFIED LIVE in browser (screenshots), zero console errors:
      - Command map: MapLibre + CARTO dark tiles, district circles sized by
        volume, PULSING markers on spike districts, click -> station drill-down
        layer, crime-head + hour-band filters, rate-per-lakh leaderboard.
      - Trends: ECharts monthly line + baseline markline + in-scope spike list.
      - Alerts: grouped cards (spike/emerging/anomaly), z-score + observed/
        baseline, evidence FIRs as clickable chips -> case.
      - Network: Cytoscape ego graph, nodes sized by cases + coloured by risk,
        edges labelled + carrying evidence FIRs; double-click opens profile.
      - Entity profile: risk badge + explainable factor bars, case timeline
        with per-case match_basis, alias chips, captured-ID table (same aadhaar
        visible twice), associates.
      - Case detail: brief, incident->chargesheet timeline, sections, parties
        (accused link to entities), MO, property, similar-case retrieval.
      - Search: debounced, shows DISTINCT same-named entities (ER proof).
      Demo pivot walked end-to-end live: search 'Ravikumar' -> 11-case profile
      w/ alias exposed via aadhaar-hash -> ring network -> case. BNS/IPC by
      date correct in UI (2025 cruelty case shows BNS 85).
      Bug fixed: lone-node network zoomed to fill viewport -> added maxZoom 1.6
      + cy.fit clamp. Lone-wolf offenders (snatcher) legitimately have 0 edges;
      demo network on the S2 fence entity (7 nodes/6 edges).
      RUN: backend `cd backend && ../.venv/bin/uvicorn app.main:app --port 8000`;
      frontend `cd frontend && npm run dev` (proxies /api -> :8000).
      Launch config at .claude/launch.json (frontend uses --prefix frontend).
- [x] **Phase 4 — Agentic layer** DONE 2026-07-02 (target was Jul 20 — early).
      ALL three GLM/Qwen features live-tested against real Zoho Catalyst
      endpoints, in API and browser.
      - [x] 4a. Zoho QuickML client DONE 2026-07-02 (backend/app/llm/zoho.py):
            real endpoints from user — GLM chat (model crm-di-glm47b_30b_it)
            + Qwen VLM (VL-Qwen3.6-35B-A3B, base64 images) at
            api.catalyst.zoho.in/quickml/v1/project/50351000000013025;
            CATALYST-ORG 60075642221; IN data center. AUTO-REFRESH: on 401/
            invalid-token -> POST accounts.zoho.in/oauth/v2/token
            (grant_type=refresh_token) -> retry once; fresh token cached in
            .zoho_token_cache.json (gitignored; .env never modified).
            Credentials in repo-root .env (chmod 600, gitignored; .env.example
            committed). Probe: `../.venv/bin/python -m app.llm.probe`
            (--vlm <image path> for Qwen). Creds pasted + probe PASS.
            GLM response shape (verified live): {"response": str, "tool_calls":
            [...], "usage": {...}} — NOT OpenAI choices[]. chat_text/tool_calls
            in zoho.py handle this + OpenAI fallback.
      - [x] 4b. Ask-the-Data chat DONE (backend/app/chat.py + frontend
            ChatView): GLM + 8 TYPED query tools (count/list cases, find_person,
            person_profile, person_associates, top_risk_offenders,
            active_alerts, case_detail) — model NEVER writes SQL (params bound;
            injection-safe). Tool loop (max 4 steps), evidence auto-collected,
            answers cite [CrimeNo] (clickable in UI), full tool trace shown
            ("How I got this"). Live tested: "7 chain snatching in Dharwad 2026"
            (1 tool); "tell me about Ravikumar B" -> full 11-case history +
            aliases incl Chikka Ravi (3 tools, 11 FIR citations).
            LESSON: never inject synthetic assistant "(requested tools: X)"
            turns — GLM MIMICS them and echoes instead of answering. Feed tool
            results as a USER turn only; guard nudges if reply < 15 chars or
            starts "(requested".
      - [x] 4c. Monitoring-agent brief DONE (backend/app/brief.py + Alerts
            "Generate brief" button -> markdown brief w/ ## Situation/Emerging
            patterns/Entities/Recommended deployment, FIR citations, print-to-
            PDF). Live tested: Dharwad brief, 29 evidence FIRs, real numbers.
      - [x] 4d. Qwen scan-ingestion DONE (backend /api/ingest/scan + ScanView):
            upload FIR photo -> Qwen VLM -> structured draft JSON (fir_no,
            station, parties, sections, brief, property) + "officer must verify"
            note. Live tested on a generated FIR scan (exports/demo_fir_scan.png)
            -> extracted all fields correctly incl BNS 304(2)/3(5), accused
            "Ravikumar B", 40g gold chain.
      NEXT: Phase 5 (Catalyst deploy single Docker container + RBAC login/audit)
      then Phase 6 (video, deck, submit). Demo asset: exports/demo_fir_scan.png.
- [x] **Phase 5 — Production hardening** DONE 2026-07-03 (target was Jul 23 —
      20 days early). Everything built + verified locally; only the Catalyst
      upload itself waits on the Catalyst project (blocked list).
      - [x] 5a. RBAC (backend/app/auth.py): PBKDF2 logins seeded idempotently
            into x_app_user/x_role (tables reserved since Phase 1); stateless
            HMAC tokens (DRISHTI_SECRET env, 12h TTL — restarts never log out);
            rank -> jurisdiction resolved from org tables (range = districts
            under Unit.ParentUnit). Demo roster (password drishti2026, in
            README): dgp + scrb (state), dig.northern (range unit 4 -> 5
            districts), sp.dharwad (1014), io.hubballi (station 183 = Hubballi
            Town PS, where S1's live spike sits).
            ACCESS DOCTRINE (resolves every scoping question; in
            ARCHITECTURE.md): case records are jurisdiction-scoped; identity
            intelligence (entities, aliases, risk, network, search) is
            statewide — profiles show in-scope cases + "N outside your
            jurisdiction" counter; out-of-scope FIR detail 403s with a human
            message. Enforced via Depends(current_user) + scope SQL injected
            into EVERY endpoint (hiding in UI is UX, not security). Chat
            agent's tools receive the scope too — prompt injection cannot
            cross jurisdictions (ScopeError -> model relays the refusal).
      - [x] 5b. Audit trail — REDESIGNED 2026-07-03 (user insight: v1 logged
            every HTTP request = a request log, not an audit trail). Now
            SEMANTIC EVENTS ONLY, written by the endpoints that hold the
            context: login/login-failed, search ("searched 'Ravikumar' → 10
            persons"), profile-view (entity + name + n/n cases in scope),
            case-view (FIR + station), network-view, case-list (filters +
            rows), chat (question + tools + FIRs cited), brief, scan-ingest
            (the future record-update template), and access-denied — ALL
            403s logged centrally via the exception handler with their
            human-readable reason. Dashboard aggregates (kpis/map/trends/
            meta) deliberately NOT audited; audit reads don't self-log (the
            5s UI poll was spamming its own trail). Old request-log rows
            wiped. WAL: one writer + ro readers; falls back to an in-memory
            ring (and in-memory users) on read-only FS — never a 500.
            GET /api/audit + Audit lens = state roles only; denials render
            highlighted (proof of enforcement).
      - [x] 5c. Frontend: LoginView (one-click demo roles from
            /api/auth/demo), token in localStorage via api.js (401 anywhere ->
            login screen), live role chip + Sign out, Audit tab (state roles),
            amber outside-jurisdiction note on entity profiles, all direct
            fetch() calls routed through api() so headers are uniform.
      - [x] 5d. Single-container serving: main.py mounts frontend/dist after
            the API routes (hash router needs no SPA fallback); GZip
            middleware (~85% on map/meta JSON); /api/meta cached in-process;
            zoho.py reads process env over .env (container-friendly);
            requirements.txt gained httpx + python-multipart (were
            venv-only — would have broken the Docker build).
      - [x] 5e. Deploy artifacts: Dockerfile (node build stage -> python:3.12
            runtime, honours X_ZOHO_CATALYST_LISTEN_PORT/PORT/9000),
            .dockerignore, deploy/build_appsail_bundle.sh (native AppSail
            fallback w/ vendored deps + app-config.json TEMPLATE — confirm
            stack id at workshop), docs/DEPLOYMENT.md (both paths, env table,
            smoke checklist, restart semantics), .env.example +
            DRISHTI_SECRET, launch.json backend gained --app-dir backend.
      - [x] 5f. Verification: apicheck rewritten — 33 assertions ALL PASS
            (login, 401s, rank-ladder map counts 31/5/1, S1 profile 11/9/6
            visible with hidden counters, SP-vs-DIG on the same Belagavi FIR
            403/200, IO pinned to station, audit records denials); warm max
            171ms (< 300ms target) WITH auth+audit overhead; selfcheck ALL
            PASS. Browser-verified live: login screen, DGP statewide + Audit
            tab, SP single-district + scoped KPIs + S1 amber note + 403 page,
            audit lens 120 rows/7 denials; zero console errors. Production
            static path verified on :8000. NOTE: apicheck's stale "Dharwad
            carries spike flag (all-heads)" assertion updated to the
            documented top-6 behavior (Dharwad z=5.66 < statewide top-6
            floor 7.39; it flags under head 5 and inside its own scope).
            Docker image BUILT + smoke-tested (clean-machine criterion):
            health 200, UI served, anon 401, in-container login works
            (users self-seed), SP map = Dharwad only, chat w/o LLM creds =
            graceful 503. Live GLM chat AS SCOPED SP verified against the
            real endpoint: "7 chain snatching in Dharwad 2026" + correct
            jurisdiction refusal for Belagavi relayed by the model.
      - [x] 5g. Network tab landing (2026-07-03, user-reported "no data"):
            bare #/network used to show only a hint line (ego graphs needed
            an entity). Now GET /api/network/top (cached, 1.6ms) ranks the
            12 most-connected entities by degree -> clickable "organized
            groups" leaderboard -> click opens the association graph
            (#1 Siddappa Murthy, 29 associates, 30-node graph). Statewide
            for every rank (identity-intel doctrine). apicheck 35 ALL PASS;
            verified in browser. NOTE: rebuild the Docker image at deploy
            time — the one built today predates this endpoint.
- [ ] **Phase 6 — Submission** (Jul 24–26): demo video, deck (official template),
      final deploy, submit (early submission from ~Jul 18, re-submit until deadline)

## Blocked / waiting on user

- [x] RESOLVED 2026-07-02: Zoho Catalyst GLM/Qwen credentials — pasted into
      `.env`, probe PASS, all agentic features live.
- [ ] Official Resource-tab files still not in `resources/` (master data /
      header files, **evaluation parameters**, submission deck template) — user
      has them, needs to drop them in. Eval parameters especially: audit our
      feature list against the scoring rubric before locking scope.
- [ ] Catalyst PROJECT to deploy into (separate from the QuickML model creds
      we already have) + AppSail-workshop confirmation of deploy flow /
      runtime limits / whether Docker images are accepted. Everything else is
      ready: `docker build -t drishti .` or
      `bash deploy/build_appsail_bundle.sh`; steps + smoke checklist in
      docs/DEPLOYMENT.md. Once the project exists this is a ~30-minute task.

## Decision log

- **2026-07-02** Product name DRISHTI (working title; user may rename).
- **2026-07-02** Volumes chosen: ~200k cases over 2021-01-01 → 2026-06-30, ~1,100
  stations on real district structure, ~2M total rows. Rationale: organizers said
  1–2 lakh cases is a good production test; SQLite handles this comfortably with
  indexes + precomputed rollups.
- **2026-07-02** Dual data delivery: SQLite (system of record) + full CSVs + Excel
  review workbook with reconciliation sheet, because police stakeholders verify in
  Excel.
- **2026-07-02** Everything deterministic from seed 2026 so demos are reproducible
  and re-generation never breaks the demo narrative.
- **2026-07-02** Excel three-color schema transparency: blue = KSP schema as-is,
  teal = gap-fill lookups their PDF references but never defines, amber = DRISHTI
  `x_` intelligence extensions. Same story told in the deck.
- **2026-07-02** Geography locked: all 31 districts + 6 commissionerates + KGF
  (~38 policing units) under the 7 real ranges; ~1,100 stations (Bengaluru City
  ~110); real station names for 8 major units, taluk-derived elsewhere; Women PS +
  CEN PS per district, Traffic PS in cities. Pending: taluk/HQ lat-long anchors
  (small research task at Phase 1 start).
- **2026-07-02** Full-coverage rule: EVERY unit gets data (floor ~80+ cases per
  station); no subset generation ever. Submission build 200k cases (~2.1M rows);
  stress build 500k cases (~5M rows) with recorded latencies at both sizes for
  the production-readiness slide.
- **2026-07-02** Workbook policy (user request): ONE consolidated Excel file
  (DRISHTI_database.xlsx) with full data, and EMPTY tables get NO sheet — the
  7 reserved tables (x_agg_daily, x_network_edge, x_alert, x_app_user,
  x_audit_log, x_fin_account, x_fin_txn) stay in the DB schema for later
  phases but appear only in the Data dictionary marked "reserved". Do not
  hand-edit the workbook: it is regenerated from scratch each run — encode
  any presentation change in export.py instead.
- **2026-07-02** Identity design: NO Aadhaar column on KSP tables (would make ER
  a trivial join and is unrealistic — accused often unknown at registration,
  Aadhaar Act limits collection). Instead: x_person_master carries synthetic
  aadhaar + phone as world truth (aadhaar never starts 0/1); x_identity_capture
  records what police actually captured per case record (complainant 55%,
  victim 45%, arrested accused TIME-RAMPED ~35% in 2021 -> ~65% in 2026,
  named-only accused 8%, 2% typos; aadhaar always displayed masked
  XXXX XXXX 1234). ER rule: hard-ID match = certain merge (exposes aliases);
  otherwise name+age+geo+co-occurrence jointly clear a conservative threshold —
  identical names with incompatible age/geo NEVER merge. Case engine (1c)
  writes the captures.
  Challenge-2 gap re-check also added: x_district_indicators (census data now
  IN the DB — seeded + verified, 31 rows) and x_property (stolen/recovered
  values + vehicle reg numbers; 1c writes rows; enables recovery-rate KPIs and
  shared-vehicle/shared-phone network edges).
- **2026-07-03** RBAC access doctrine: case records jurisdiction-scoped;
  identity intelligence statewide (profiles show hidden-case counters, FIR
  detail 403s). Chose this over entity-level 403s because it mirrors real
  inter-jurisdiction intel sharing and demos better (SP sees the offender
  exists with 5 unreachable cases -> escalation story).
- **2026-07-03** Users + audit live in drishti.db's reserved tables (seeded
  at startup, WAL single-writer) — NOT a separate runtime DB — keeping one
  system of record; on read-only filesystems both degrade to memory.
  Datagen re-runs wipe users/audit; they re-seed on next backend start.
- **2026-07-03** One shared demo password (drishti2026) documented in README:
  synthetic data + judges must switch ranks in one click. PBKDF2 hashing and
  per-user credentials are in the code path, so production hardening is
  config, not code.
- **2026-07-03** Docker path is primary for AppSail; native-bundle script kept
  as fallback until the workshop confirms Docker support. app-config.json
  stack id is a TEMPLATE VALUE — verify before deploying.
- **2026-07-03** Audit doctrine (user decision): the trail records ACTIONS
  (record access, AI usage, sign-ins, denials), never HTTP telemetry —
  "who looked up whom" is the production requirement (insider-misuse
  accountability); request logs belong to uvicorn. Event vocabulary is
  future-proofed for mutations (record-update) when write paths arrive.
- **2026-07-03** Network tab landing = organized-groups leaderboard
  (/api/network/top, degree-ranked) after user reported the bare tab looked
  empty — association DISCOVERY without needing a suspect name first.
- **2026-07-03** Spike-flag honesty rules (user-reported: red spike shown on
  a 0-FIR filtered view): (1) hour-band views carry NO spike flags — spikes
  are daily-volume signals, claiming them on an hourly slice is false
  precision; (2) a district displaying n=0 is never flagged; (3) the spike
  always NAMES its crime/pattern — drill card shows the full summary
  ("Cruelty by Husband... 250% above baseline"), leaderboard chip gets it
  as tooltip; head-filtered spikes were already head-specific. apicheck 45
  ALL PASS. Verified live: Dharwad+CAW shows named spike; +00-03 the chip
  and red glow disappear with the 0-case view.
- **2026-07-03** Drill-down lockstep bugfix (user-reported): with a district
  open, changing the crime-head filter left the station table + district
  card stale (only hour changes refreshed it). Now ONE effect re-syncs the
  drill from the fresh district row whenever filters change (no camera
  re-fly). Station table header "n" renamed to "FIRs" (+ tooltip). Verified:
  Dharwad under Crimes-Against-Women re-sorts to the Women PSs (24/22),
  night band drops to 0, card count follows (115 -> 0 cases).
- **2026-07-03** KPI strip audit (user asked what to add/remove): KEPT all
  six (each maps to a persona need + challenge pillar); ADDED "Property
  value recovered %" (value-weighted from x_property — the classic KSP
  performance metric; 15.6% statewide, scopes by rank: Dharwad 19.5%,
  Hubballi Town PS 20.6%; idx_property_case added live + schema.sql);
  chips with a lens behind them are now CLICKABLE (FIRs->Trends,
  Repeat offenders->Network, Active alerts->Alerts — evidence doctrine
  applied to the strip). DELIBERATELY NOT added: crimes-against-women chip
  (reachable via head filter; keeps the strip apolitical), a "forecast"
  scalar (no honest model behind a single number — risk stays explainable
  on profiles), arrest counts (vanity; no decision follows). apicheck 44
  ALL PASS; kpis 154ms warm.
- **2026-07-03** Hour-band filter now applies at the STATE map too (user
  noticed it silently did nothing until district drill). New path counts
  CaseMaster x Inv_OccuranceTime directly (rollup has no hour dim);
  idx_occtime_case added to schema.sql AND created on the live DB (regens
  keep it). 114ms warm statewide. Demo beat upgraded: flip 21-24 at state
  view -> night-crime geography (leaderboard reorders). apicheck 44 ALL
  PASS. KEEP the filter: it is the challenge's "layering time of day with
  location" requirement verbatim.
- **2026-07-03** GRADUATED DISCLOSURE replaces the hard 403 wall on case
  records (user decision): any officer following a link sees an
  out-of-jurisdiction FIR's STRUCTURAL record (number, dates, station,
  sections, status, MO, accused identity links, similar cases) — but party
  details (victims/complainants), the narrative, identifiers and property
  are redacted with counts + a "Request access" action (logged as
  access-request on the audit trail; production story: routed to the owning
  SP). Entity profiles now list ALL linked case numbers for every rank with
  restricted flags (was: hidden rows + a counter); accused ID captures are
  statewide identity intel again, so the S1 aadhaar alias-exposure demo now
  works at SP rank too. Bulk BROWSING of another jurisdiction (case lists)
  still 403s. Chat case_detail mirrors this (redacted view + note instead
  of a refusal). apicheck 41 ALL PASS; verified in browser as sp.dharwad on
  a Belagavi FIR.
- **2026-07-03** Demo roster widened to 3 SPs + 3 IOs (user requests) —
  the S1 story's three districts (sp.belagavi/sp.davanagere/sp.dharwad,
  Davanagere is Eastern Range -> the DIG boundary shows) AND their three
  story stations (io.market=224 Market PS Belagavi, io.davanagere=592
  Davanagere Town PS, io.hubballi=183): a complete 9-account ladder,
  station->district->range->state, all on one offender. Roster is
  server-driven; login screen + rank dropdown picked it up with zero
  frontend changes. apicheck 43 ALL PASS (ladder asserted per rank).
- **2026-07-03** Station-rank map scoping (user caught the inconsistency: IO
  KPIs were station-level but the map exposed every Dharwad station's
  counts). Doctrine refined: district TOTALS are handbook-public aggregate
  context (kept), but the STATION-WISE breakdown follows jurisdiction —
  /api/map/stations returns only the IO's own station; the UI auto-drills
  station ranks into their district view and says so in a note. apicheck 36
  ALL PASS (new: "IO station layer shows ONLY their own station").
- **2026-07-03** Map control panel (user-reported): the overlay card now has
  "hide ⟨" -> collapses to a "☰ Map controls" chip (with an active-filter
  dot); the MapLibre instance survives the toggle and filters are preserved.
  Horizontal scrollbar root-caused: the crime-head <select>'s intrinsic width
  (long offence names) exceeded the 330px panel -> .map-side selects now
  width:100% and the panel is overflow-x:hidden.
- **2026-07-03** Rank switching (user decision): the topbar role chip is a
  DROPDOWN — picking a rank re-logs-in behind the scenes (real token, real
  server-side scoping, switch logged as a login event) so judges never do
  the sign-out/re-login roundtrip. Login screen kept for first entry; Sign
  out kept. Switching away from the Audit tab as a non-state rank lands on
  /map. Verified live: dgp->sp (KPIs 4,711->111, Audit tab gone),
  ->io.hubballi (KPIs 2, redirect off audit), ->dig.northern (739); all
  switches in the audit trail.
