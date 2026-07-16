# reference/ — curated real-world data

These files contain **researched, real facts** (verified 2026-07-02 against official
sources by four web-research agents). They are the "real skeleton" of the synthetic
database. Do not regenerate casually; fix errors surgically and record the source.

| File | Contents | Key sources |
|---|---|---|
| `police_structure.json` | 31 districts (official names, HQs, taluks), 6 city commissionerates, 7 police ranges with member districts, unit hierarchy DGP→station, real station names for 8 major units, ~1,100 total stations | ksp.karnataka.gov.in, district police sites, Wikipedia |
| `legal_sections.json` | IPC↔BNS mapping for 32 common offences with crime head/sub-head + gravity; 12 special acts with key sections; NCRB crime-head taxonomy; BNS cutover rule | India Code, PRS, MHA notifications |
| `demographics_names.json` | Census 2011 per-district population/urbanization/literacy/sex-ratio + ~2026 estimates; Karnataka name pools by community with regional flavor, initials convention, 18 transliteration-variant sets | census2011.co.in (PCA data), censusindia.gov.in, Wikipedia |
| `crime_calibration.json` | NCRB Crime in India 2023 Karnataka: yearly IPC/SLL totals (2021–23), 20 offence-level annual counts and shares, chargesheeting rates by scope, Bengaluru City shares, seasonality + time-of-day evidence | ncrb.gov.in CII-2023 Vol I–III, credible news for patterns NCRB doesn't publish |

## Caveats the generator must respect (from researcher notes)

1. **BNS cutover follows the OFFENCE date, not the FIR date** (in force 2024-07-01).
   A crime committed 2024-06-28 but reported 2024-07-05 is still charged under IPC.
2. **Vijayanagara district** (created 2021) has no verified literacy figure —
   estimate flagged as unverified. Ballari/Davanagere figures are post-split
   approximations. Ramanagara was renamed **Bengaluru South** in 2024.
3. **Population estimates for ~2026 are unofficial projections** (Census 2021 never
   happened); treat as ±5–10%, Bengaluru Urban most uncertain.
4. **NCRB has no "snatching" head for Karnataka** — snatching hides inside theft
   (379) and robbery (392). The 153 figure is Bengaluru City chain-snatching 2023.
5. **No official month-wise crime data exists** — seasonality entries are
   directional (news/studies), so the generator keeps monthly swings gentle
   (±10–15%) except the documented festival-quarter property bump.
6. **Hard facts to honor exactly**: 80.5% of Karnataka burglaries are at night
   (NCRB table); Karnataka is India's #1 cyber-crime state (21,889 cases in 2023,
   ~80% in Bengaluru); gambling cases are unusually high (21% of SLL) and mostly
   OUTSIDE Bengaluru; dacoity is near-zero (56/year); chargesheet rate ~77% overall
   but theft ~30% and cyber ~18%.
7. Name-pool relative frequencies are indicative (no official corpus exists);
   community mix per Census 2011: Hindu 84.0%, Muslim 12.9%, Christian 1.9%.
8. KGF (Kolar Gold Field) is a separate police district within Kolar revenue
   district; city commissionerates cover city areas while district police cover
   the rest of the same revenue district (e.g. Belagavi City vs Belagavi District).
