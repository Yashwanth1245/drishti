# DRISHTI synthetic database — validation report

Seed `2026` · span 2021-01-01 → 2026-06-30 · fully deterministic (same seed ⇒ byte-identical data)

## Volumes

| Table | Rows |
|---|---|
| CaseMaster | 200,846 |
| Accused | 235,084 |
| Victim | 170,300 |
| ComplainantDetails | 200,046 |
| ActSectionAssociation | 281,059 |
| ArrestSurrender | 192,748 |
| ChargesheetDetails | 128,297 |
| x_person_master | 186,956 |
| x_person_alias | 14,035 |
| x_identity_capture | 307,572 |
| x_mo_tag | 266,520 |
| x_property | 63,024 |
| Employee | 12,540 |
| Unit | 1,209 |

## Calibration vs published reality (NCRB Crime in India 2023, Karnataka)

| Metric | Generated | Published target |
|---|---|---|
| Night share of house-breaking | 79.6% | 80.5% (NCRB day/night split) |
| SLL share of all cases | 25.7% | ~24% (cyber+NDPS+gambling+excise) |
| Bengaluru share of cyber fraud | 84.2% | 80.5% |
| Chargesheet rate among final reports | 72.6% | ~77% overall KA |
| Property-crime chargesheet rate | 41.7% | ~35.8% (theft 29.8, burglary 43.6) |

## Deliberate data-quality defects (the platform must survive these)

| Defect | Count |
|---|---|
| Cases with missing coordinates | 14,061 |
| Cases with swapped lat/long | 604 |
| Inconsistent gender codes (m/f) | 4,700 |
| Duplicate-registered FIRs | 800 |
| Post-BNS cases wrongly citing IPC (Jul–Sep 2024) | 144 |

## Entity-resolution challenge (ground truth planted)

- 186,954 true persons behind 235,084 accused rows
- Repeat offenders account for 71,148 accused rows (30% — criminological skew by design)
- 14,035 alias/variant rows (spelling variants + true street aliases)
- 225,929 masked Aadhaar captures (partial by design; arrest-time capture ramps 35%→65% over 2021–2026)

## Planted stories (demo answer key: exports/stories.json)

- **S1_serial_snatcher**: 11 cases
- **S2_vehicle_ring**: 10 cases
- **S3_investment_fraud**: 15 cases
- **S4_escalating_offender**: 4 cases
- **S5_false_complainant**: 6 cases

_Machine-checked by `python -m drishti_datagen --verify` (40+ assertions)._