# DATA_MODEL — source schema + DRISHTI extensions

## Source of truth

The official ER diagram (`Police_FIR_ER_Diagram.pdf`, "Police FIR System", 23 tables).
We implement it faithfully — judges will map our DB against their schema. Extensions
live in clearly separated tables prefixed `x_` so reviewers instantly see what is
KSP-schema vs DRISHTI-added.

## Source tables (as given)

Core: `CaseMaster` (FIR: CrimeNo, CaseNo, dates incl. IncidentFrom/To DATETIME,
InfoReceivedPSDate, lat/long, BriefFacts, FKs to everything), `ComplainantDetails`
(with Occupation/Religion/Caste FKs), `Victim`, `Accused`, `ArrestSurrender` (+
junction `inv_arrestsurrenderaccused`), `ChargesheetDetails` (cstype A/B/C),
`ActSectionAssociation`.

Classification: `Act`, `Section`, `CrimeHead`, `CrimeSubHead`, `CrimeHeadActSection`,
`CaseCategory` (FIR/UDR/PAR…), `GravityOffence`, `CaseStatusMaster`.

Org & lookups: `State`, `District`, `Unit` (station hierarchy via ParentUnit),
`UnitType`, `Employee`, `Rank`, `Designation`, `Court`, `CasteMaster`,
`ReligionMaster`, `OccupationMaster`.

### Schema quirks we must honor (from the PDF)

- `CrimeNo` = 1-digit category code + 4-digit district + 4-digit station (unit) +
  4-digit year + 5-digit running serial, serial per station × category × year.
  Category codes: 1 = FIR, 3 = UDR, 8 = Zero FIR, 4 = PAR (per PDF examples).
- `CaseNo` = YYYY + 5-digit serial (last 9 digits of CrimeNo).
- `Accused.PersonID` is NOT an identity — it is A1/A2/A3 ordering within a case.
- Caste/Religion/Occupation exist ONLY on complainant.
- `Victim.VictimPolice` is a VARCHAR holding 1/0 (kept as-is for fidelity).
- Gender codes are inconsistent across tables in the source (INT lookup vs M/F/T
  vs m/f/t) — we generate that inconsistency deliberately (realism) and normalize
  in a view.
- `Inv_OccuranceTime` is referenced (1:1 with CaseMaster) but undefined in the PDF.
  We define it: `(CaseMasterID PK/FK, OccurrenceHourBand, PlaceTypeID, POIName)` —
  documented as our interpretation, flagged in the deck.

### Lookup tables the PDF references but never defines (we supply)

`GenderMaster`, `ArrestSurrenderTypeMaster` (arrest/surrender), `BloodGroupMaster`,
`PlaceTypeMaster` (house/street/ATM/highway/shop/…).

## DRISHTI extension tables (`x_` prefix)

| Table | Purpose |
|---|---|
| `x_person_master` | Resolved identities: person_id, canonical_name, gender, birth_year_est, home_district_id, aadhaar + phone (synthetic world truth), risk_score, first/last_seen |
| `x_identity_capture` | IDs police ACTUALLY captured per case record, deliberately partial: complainant ~55%, victim ~45%, **arrested accused time-ramped ~35% (2021) → ~65% (2026)** reflecting digitization progress, named-only accused ~8%, ~2% typos. `id_value` holds the FULL synthetic number (user decision 2026-07-02: data is synthetic, full numbers make ER matching visibly obvious in the demo); `id_hash` holds a salted hash — what the ER engine actually matches on, and what a production deployment would store with the display masked (governance talking point preserved). Consistency audited: same person = same number across all records (0 inconsistencies over 94,190 captured persons; 0 cross-person collisions). Design rationale: Aadhaar on every row would make ER a trivial join and is unrealistic (accused often unknown at registration; Aadhaar Act limits collection). Matching rules: hard ID match = certain merge (exposes aliases across arrests); otherwise name-variant + age + geography + MO must jointly clear a conservative threshold — identical names with incompatible age/geography NEVER merge (precision over recall; every merge stores its evidence). Shared phone = network edge |
| `x_district_indicators` | Census socio-economic data in-DB (pop 2011/estimate, urban %, literacy %, sex ratio) — powers the sociological-correlation dashboards |
| `x_property` | Stolen/recovered property incl. vehicles with reg numbers (recovery-rate KPIs mirror the real Crime in Karnataka handbook; shared vehicle identifier = network edge) |
| `x_person_case_role` | person_id ↔ (CaseMasterID, role accused/victim/complainant, source row id) — the ER output |
| `x_person_alias` | Every raw name spelling observed for a person |
| `x_er_gold` | Generator's ground truth (true person per accused row) — used ONLY to score ER accuracy, never by the engines |
| `x_mo_tag` | CaseMasterID, tag (e.g. two-wheeler-pillion-snatch, gas-cutter-burglary), source (rule/GLM), confidence |
| `x_fin_account` | Synthetic accounts: account_id, type (bank/UPI/wallet), holder person_id, bank name |
| `x_fin_txn` | account→account transfers: amount, ts, channel, case link nullable |
| `x_network_edge` | Precomputed graph: src/dst node (typed), edge type, weight, evidence CaseMasterIDs |
| `x_agg_daily` | unit_id × crime_head_id × date → case count (rollup powering trends/maps) |
| `x_alert` | Materialized spike/anomaly alerts with baseline stats + evidence |
| `x_app_user`, `x_role`, `x_audit_log` | RBAC + audit (audit also mirrored to Catalyst Data Store in prod) |
| `x_provenance` | Per-table note: which columns are real reference data vs synthetic |

## Backend-owned tables (created by `app.precompute`, not by datagen)

| Table | Purpose |
|---|---|
| `x_entity` | The ER engine's OUTPUT: resolved person entities (canonical name, attrs, n_cases, risk_score + risk_factors JSON). The app's "person" = an entity; `x_person_master` remains generator ground truth used only for evaluation |
| `x_entity_member` | Entity ↔ Accused-row membership with `match_basis` (explainability: why each row joined its entity) |
| `x_metric` | Key-value store for engine metrics (ER precision/recall etc.) served by `/api/er/metrics` |

## Keys, indexes, conventions

- All source-table PKs are INTEGER as per PDF; FKs enforced at generation time and
  by `PRAGMA foreign_keys` in dev.
- Indexes (created by datagen): CaseMaster(CrimeRegisteredDate), (PoliceStationID),
  (CrimeMajorHeadID), (lat, long); Accused/Victim/Complainant(CaseMasterID);
  x_person_case_role(person_id), (CaseMasterID); x_agg_daily(unit_id, date);
  x_network_edge(src), (dst); x_fin_txn(from_account), (to_account).
- Dates stored ISO-8601 TEXT (SQLite convention); hour band derived, not stored,
  except in Inv_OccuranceTime.
- Every extension row that an engine writes stores enough provenance to explain
  itself (scores, inputs, evidence case IDs).
