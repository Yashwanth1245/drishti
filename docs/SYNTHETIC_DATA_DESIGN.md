# SYNTHETIC_DATA_DESIGN — the generator specification

## Principles

1. **Real skeleton, synthetic flesh.** Geography (districts, ranges,
   commissionerates, taluk-named stations), law (acts, IPC/BNS sections, crime-head
   taxonomy), demographics (census populations, urbanization, literacy) and crime
   proportions (NCRB Karnataka) are REAL, sourced in `reference/`. People, cases,
   narratives, accounts are synthetic.
2. **Calibrated, not uniform.** Crime mix per district follows real patterns:
   Bengaluru City dominates cyber/vehicle theft; property crime scales with
   urbanization; NDPS clusters on known corridors; per-capita rates vary by district.
3. **Adversarial by default.** Real police data is messy because people are cunning
   and data entry is human. Every mess pattern below is generated deliberately, at
   documented rates, so our analytics prove they survive reality. The happy path is
   the demo failure mode — we don't build for it.
4. **Deterministic.** One seeded RNG (`--seed 2026`). Identical inputs → identical
   DB. The demo narrative can never break from regeneration.
5. **Verifiable by police.** Same data delivered as SQLite + full CSVs + an Excel
   review workbook; a reconciliation sheet proves they match (row counts, per-table
   checksums). A data-dictionary sheet explains every column in plain language.

## Scale (chosen for "production-ready" testing)

| Table | Target rows |
|---|---|
| CaseMaster (FIRs + UDR + PAR + Zero FIR) | 200,000 |
| Accused | ~310,000 |
| Victim | ~240,000 |
| ComplainantDetails | ~205,000 |
| ActSectionAssociation | ~380,000 |
| ArrestSurrender (+junction) | ~120,000 |
| ChargesheetDetails | ~150,000 |
| x_person_master (unique identities) | ~140,000 |
| x_fin_account / x_fin_txn | ~30,000 / ~90,000 |
| Employee / Unit / Court | ~12,000 / ~1,250 / ~250 |
| x_agg_daily (rollup, sparse — only non-zero cells) | ~200k |
| x_network_edge | ~150k |
| **Total** | **~2.1 million rows** |

Time span: **2021-01-01 → 2026-06-30** (5.5 years — enough history for baselines,
seasonality, and "compare with same period last year").

### Coverage and allocation rules (locked — no subsets)

- ALL 31 districts, ALL 6 commissionerates + KGF, ALL 7 ranges, ALL ~1,100
  stations receive data. Judges click anywhere; no empty corners.
- Allocation: state total → district shares (population × urbanization ×
  NCRB calibration, e.g. Bengaluru ~30% of crime, ~80% of cyber) → station
  shares within district (urban-weighted).
- Floor rule: every station gets a minimum caseload (~80+ cases over the span);
  every district gets every major crime head at realistic proportions. No blank
  pages anywhere in the UI.
- Scale testing: generator is parameterized (`--cases N`). Submission build =
  200k cases; pre-submission stress build = 500k cases (~5M rows, 2.5× the
  organizers' suggested maximum) with recorded API latencies at both sizes for
  the deck's production-readiness slide.

## Generation pipeline (each stage a module)

```
reference data ─► 1. org builder      districts→units(1,100 stations)→employees→courts
               ─► 2. person factory   140k identities w/ names, aliases, demographics
               ─► 3. case engine      200k cases: type→place→time→parties→sections
               ─► 4. process engine   arrests, chargesheets, statuses, court linkage
               ─► 5. story planter    inject the 5 scripted narratives (below)
               ─► 6. mess pass        realism catalog applied at documented rates
               ─► 7. finance weaver   accounts + transactions for fraud/OC cases
               ─► 8. rollups+gold     x_agg_daily, x_network_edge, x_er_gold
               ─► 9. exporters        SQLite · CSV · Excel workbook · manifest.json
               ─► 10. validator       integrity + distribution + story assertions
```

## Realism catalog (the non-happy path; rates are config constants)

**Identity & people**
1. Repeat offenders: ~12% of offenders account for ~35% of accused rows
   (criminological 80/20 skew).
2. Name variants for the same person across FIRs (transliteration: Ravi
   Kumar/Ravikumar; initials moving: B. Ravi Kumar/Ravi Kumar B): ~30% of repeat
   appearances differ from canonical spelling.
3. Deliberate aliases for career criminals (different name, same person): ~5% of
   repeat offenders carry a true alias.
4. Age drift: stated AgeYear varies ±2 years between appearances (~30%); sometimes
   lies bigger (~2%).
5. Unknown accused: property crimes registered against unknown persons (~38% of
   theft/burglary have zero named accused at registration).
6. Juvenile accused ~6%; female accused ~9% overall (higher in cheating/498A
   counter-cases); police-as-victim flag ~1%.

**Records & data entry**
7. Missing lat/long ~7%; station-centroid default coords ~10%; swapped lat/long
   ~0.3% (classic entry bug our map layer must not crash on).
8. Gender code inconsistency across tables (M/F/T vs m/f/t vs lookup INT), ~2%
   stray values.
9. Name typos/double spaces/casing noise ~4% of rows; BriefFacts with mixed
   English-Kannada phrases (~15%) to make text mining honest.
10. Duplicate FIR (same incident registered twice, later one closed as false) ~0.4%.
11. Wrong act citation for 3 months after BNS cutover (officers citing IPC out of
    habit) ~2% of Jul–Sep 2024 cases.

**Process realities**
12. Reporting delay distributions per offence: theft median 1 day; cheating median
    12 days; sexual offences long tail (months); dowry death immediate.
13. Outcome mix by crime type (calibrated): property crime largely undetected
    (cstype C); body crimes mostly chargesheeted (A); false cases (B) ~2.5% overall,
    concentrated in property/matrimonial disputes.
14. Investigation duration skew: most chargesheets in 60–90 days, long tail past
    a year; a few stations systematically slower (management insight for the demo).
15. Zero FIRs (~1.5%) with jurisdiction transfer; UDR ~6%; PAR ~2% (CrimeNo
    category codes 8/3/4 respectively).
16. Case transfers between IOs mid-investigation ~8%.

**Crime patterns (what the engines must find)**
17. Seasonality: snatching/burglary +30–40% in festival season (Oct–Nov);
    burglary spikes when houses are empty (holiday weeks); monsoon dip in street
    crime; NYE assault uptick.
18. Time-of-day signatures: burglary 23:00–04:00 (70%); chain snatching morning
    walk (05:30–08:00) and evening (18:00–21:00); cyber fraud reported office hours.
19. Geography: cyber & vehicle theft concentrated in Bengaluru City (calibrated
    share); highway dacoity on NH corridors; excise/gambling in specific belts;
    urbanization-correlated property crime (the sociological overlay must show a
    real correlation because we generated one — and the deck says exactly that).
20. Emerging trend planted: "digital arrest" / investment-app fraud category rising
    steeply through 2025–2026 (for the emerging-crime-alert demo).

## Names and narrative (locked 2026-07-02)

**Name variety.** The name factory generates from researched pools with compound
first names ("Ravi Kumar", "Shiva Prasad"), female suffix forms ("Bai", "Kumari",
"Devi"), regional styles (initials in Old Mysuru, surnames in the north, community
surnames on the coast) and community mix per Census 2011. Different people MAY
share the same display name (as in reality) — the ER engine must separate them by
age/geography, and the same person appears under variant spellings across FIRs
(the variant engine: trailing-a toggle, compound join/split, initial move/drop,
Mohammed-style transliteration maps, researched variant sets).

**BriefFacts are report-style narratives, not stubs.** Per-offence template
families produce 2–6 sentence FIR-style briefs: complainant intro, incident
date/time/place, what happened with MO detail (entry method, weapon, vehicle
direction), property/amount, suspect description or named accused, witness
mention. Consistency rule: every fact in the text is rendered from the same
variables as the structured columns — text and data never contradict, because
the chat agent will be asked about both. Realism: ~10% terse one-line entries
(data-entry laziness), ~15% contain Kannada phrases in Latin or Kannada script,
MO signal vocabulary embedded for the tagger to find.

## Planted stories (the demo's dramatic reveals; IDs reserved)

| # | Story | What it demos |
|---|---|---|
| S1 | Serial chain-snatcher, 11 cases across Hubballi-Dharwad → Belagavi → Davanagere, 2 name spellings + 1 alias, consistent MO (pillion snatch, morning), currently active spike in Hubballi | ER, cross-district MO linkage, spike alert, offender profile |
| S2 | Vehicle-theft ring: 6 members, rotating co-accused pairs, one receiver (fence) connecting all, cases in 4 districts | Network graph, organized-group detection |
| S3 | Investment-app fraud: 40+ victims statewide, money into 5 mule accounts → 2 aggregators → cash-out; one mule shared with S2's fence | Financial trail, cross-case linkage, emerging-trend alert |
| S4 | Domestic-violence offender escalating (498A → hurt → attempt to murder) over 3 years | Risk scoring / escalation detection |
| S5 | One complainant with 6 false cases (cstype B) against neighbours | Anomaly call-out |

Stories are injected AFTER bulk generation so their stats ride on top of realistic
background noise, and a `stories.json` manifest records every planted row for demo
prep and validator assertions.

## Outputs

```
exports/
  drishti.db                     SQLite, indexed, ~3M rows (system of record)
  excel/DRISHTI_database.xlsx    ONE workbook, all 50 tables as full-data sheets
                                 (color-coded blue/teal/amber) + Data dictionary
                                 (with legend) + Reconciliation (DB==sheet counts).
                                 ~124MB at 200k cases; story cases lead CaseMaster.
  csv/<TableName>.csv            optional (--csv flag) full CSV per table
  validation_report.md           human-readable calibration/defect/story proof
  manifest.json                  seed, volumes, rates used, stages, versions
  stories.json                   planted-story row registry (the demo answer key)
```

Delivery decision (2026-07-02): police verify in Excel, so the primary human
deliverable is ONE consolidated workbook (not 50 loose CSVs). Full data fits —
the largest table (~317k rows) is well under Excel's 1,048,576-row limit; a
table that ever exceeds it is auto-split into `<name>`, `<name>_2`. Written in
openpyxl write-only (streaming) mode. Tradeoff: the full-data workbook is large
(~124MB) and slow to open (~30-60s). Raw CSVs remain available via `--csv`; dev
loops skip the workbook with `--skip-export`.

### Excel three-color system (schema transparency for police reviewers)

Sheet tab colors AND header-row fills encode schema provenance, with a legend on
the data-dictionary sheet:

- **Blue** — KSP schema as-is (their 23 tables, column-faithful to the ER PDF).
- **Teal** — gap-fill: tables their PDF references but never defines, which we
  completed (GenderMaster, ArrestSurrenderTypeMaster, BloodGroupMaster,
  PlaceTypeMaster, Inv_OccuranceTime definition).
- **Amber** — DRISHTI intelligence extensions (`x_` tables: person master/roles/
  aliases, ER gold, MO tags, network edges, finance, rollups, alerts, RBAC/audit,
  provenance).

Demo line: "Blue stores records. Teal completes your schema. Amber turns records
into intelligence."

### Geography allocation (locked)

- All 31 real districts + 6 commissionerates + KGF police district ≈ 38 policing
  units under the 7 real ranges. RBAC scopes map to this structure.
- ~1,100 stations: Bengaluru City ~110; other commissionerates 20–35; large
  districts 30–45; small districts 15–25.
- Station naming: real researched names for the 8 major units; real taluk/town
  derived names elsewhere ("Gokak Town PS", "Athani PS"). Specialized stations:
  one Women PS + one CEN PS per district, Traffic PS in commissionerates
  (cyber-fraud cases register at CEN stations).
- PENDING (Phase 1 start): lat/long anchors for district HQs + taluk towns so
  stations and incidents geocode to real places.

## Validation suite (runs after every generation)

- Referential integrity on every FK; CrimeNo format + serial-per-station-year rule.
- Distribution report: generated proportions vs NCRB calibration targets (tolerance
  bands) — saved as `exports/validation_report.md`.
- Story assertions: each planted story discoverable by its intended query.
- Excel ↔ DB reconciliation: counts + checksums match.
