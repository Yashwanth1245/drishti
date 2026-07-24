# CLAUDE.md — session bootstrap for this repository

This is the DRISHTI project: KSP Datathon 2026, Challenge 2. Two-person team
(user + Claude). Hard deadline: prototype submission **26 July 2026**.

## Start every session like this

1. Read `docs/STATUS.md` — it says exactly what is done, in progress, and pending.
   Do NOT re-derive project state from scratch or re-read every document.
2. Open `docs/PLAN.md` only if you need the roadmap; open design docs only for the
   part you are working on.
3. At the end of every working session, update `docs/STATUS.md` (move items between
   sections, add dated decision entries). This file is the single source of truth
   for continuity across context clears.

## Non-negotiable project rules

- **Determinism**: the data generator must be fully reproducible — single RNG seeded
  with `--seed` (default 2026). Never use unseeded randomness. Same seed + same
  reference data = byte-identical output.
- **Reference data is curated, not generated**: files in `reference/` contain
  researched real-world facts (districts, police stations, IPC/BNS sections, census
  numbers, NCRB calibration). Do not overwrite them casually; fix errors surgically
  and note the source.
- **Every claim cites evidence**: any API response or UI element that states a fact
  must be able to point to CaseMasterID / CrimeNo rows. This is a judged feature.
- **Dual delivery of data**: every generated table ships as (a) SQLite, (b) full CSV,
  (c) sampled Excel review workbook with a reconciliation sheet (row counts +
  checksums) so police can verify Excel ↔ DB equivalence.
- **Deployment target is Zoho Catalyst** (AppSail). LLM calls go through
  `backend/app/llm/zoho.py` — never call a model API directly from feature code.
  The real Zoho QuickML GLM 4.7 endpoint is wired with OAuth auto-refresh;
  credentials live in repo-root `.env` (gitignored, never commit).
  QuickML's GLM response is `{"response": str, "tool_calls": [...]}` — NOT
  OpenAI `choices[]`. Never inject synthetic assistant turns into the chat loop
  (GLM mimics them); feed tool results back as user turns.

## Code conventions (for the next developer, human or AI)

- Every module starts with a docstring explaining WHY it exists and how it fits the
  pipeline, not just what it does.
- Every non-obvious constant (rates, thresholds, distributions) is named, documented
  with its source (e.g. "NCRB 2022 Karnataka"), and lives in a config module — never
  inline magic numbers.
- Functions small and single-purpose; prefer plain SQL in named `.sql` files or
  clearly named query constants over ORM cleverness.
- Generator realism behaviors (typos, aliases, missing coords, false cases) are each
  a small, independently testable function in `datagen/drishti_datagen/realism/`.
- If you add a feature, add its line to `docs/STATUS.md` and, if it changes design,
  the relevant design doc. Docs that lie are worse than no docs.

## Domain glossary (read once)

- **FIR** — First Information Report, one registered case (CaseMaster row).
- **CrimeNo** — structured ID: 1-digit category + 4-digit district + 4-digit station
  + 4-digit year + 5-digit serial.
- **UDR / PAR / Zero FIR** — case categories (unnatural death report / petition,
  and FIRs registered outside the incident's jurisdiction then transferred).
- **Chargesheet cstype** — A = chargesheeted, B = false case, C = undetected.
- **BNS cutover** — FIRs registered on/after 2024-07-01 cite Bharatiya Nyaya Sanhita
  sections; before that, IPC.
- **Entity resolution (ER)** — linking accused rows across cases to one PersonMaster
  identity despite name variants; the platform's core differentiator.
