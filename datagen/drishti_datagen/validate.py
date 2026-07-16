"""The human-readable validation report: proof the data is calibrated, messy,
and story-complete — written for a reviewer, not a machine (machine checks live
in __main__.verify). Emitted as exports/validation_report.md every run; the
deck cites it as evidence that the synthetic database mirrors NCRB reality.
"""

import datetime as dt
import json

from .config import EXPORT_DIR, SPAN_END, SPAN_START


def _one(conn, sql):
    return conn.execute(sql).fetchone()[0]


def build_report(conn, seed):
    q = lambda sql: _one(conn, sql)
    lines = []
    add = lines.append

    add("# DRISHTI synthetic database — validation report")
    add("")
    add(f"Seed `{seed}` · span {SPAN_START} → {SPAN_END} · fully deterministic "
        "(same seed ⇒ byte-identical data)")
    add("")

    add("## Volumes")
    add("")
    add("| Table | Rows |")
    add("|---|---|")
    for t in ["CaseMaster", "Accused", "Victim", "ComplainantDetails",
              "ActSectionAssociation", "ArrestSurrender", "ChargesheetDetails",
              "x_person_master", "x_person_alias", "x_identity_capture",
              "x_mo_tag", "x_property", "Employee", "Unit"]:
        add(f"| {t} | {q(f'SELECT COUNT(*) FROM {t}'):,} |")
    add("")

    add("## Calibration vs published reality (NCRB Crime in India 2023, Karnataka)")
    add("")
    add("| Metric | Generated | Published target |")
    add("|---|---|---|")
    night = q("SELECT ROUND(100.0*SUM(CASE WHEN OccurrenceHourBand IN "
              "('21-24','00-03','03-06') THEN 1 ELSE 0 END)/COUNT(*),1) "
              "FROM Inv_OccuranceTime t JOIN x_mo_tag m ON "
              "m.CaseMasterID=t.CaseMasterID WHERE m.tag LIKE '%entry%'")
    add(f"| Night share of house-breaking | {night}% | 80.5% (NCRB day/night split) |")
    sll = q("SELECT ROUND(100.0*(SELECT COUNT(*) FROM CaseMaster c JOIN CrimeHead h "
            "ON h.CrimeHeadID=c.CrimeMajorHeadID WHERE h.CrimeGroupName LIKE "
            "'%SLL%')/COUNT(*),1) FROM CaseMaster")
    add(f"| SLL share of all cases | {sll}% | ~24% (cyber+NDPS+gambling+excise) |")
    cyber_tags = ("'otp-fraud','investment-app-fraud','digital-arrest-scam',"
                  "'kyc-fraud','olx-marketplace-fraud','loan-app-extortion'")
    blr = q("SELECT ROUND(100.0*SUM(CASE WHEN d.DistrictName='Bengaluru Urban' "
            "THEN 1 ELSE 0 END)/COUNT(*),1) FROM CaseMaster c JOIN x_mo_tag m ON "
            "m.CaseMasterID=c.CaseMasterID JOIN Unit u ON u.UnitID=c.PoliceStationID "
            f"JOIN District d ON d.DistrictID=u.DistrictID WHERE m.tag IN ({cyber_tags})")
    add(f"| Bengaluru share of cyber fraud | {blr}% | 80.5% |")
    cs = q("SELECT ROUND(100.0*SUM(CASE WHEN cstype='A' THEN 1 ELSE 0 END)"
           "/COUNT(*),1) FROM ChargesheetDetails")
    add(f"| Chargesheet rate among final reports | {cs}% | ~77% overall KA |")
    prop_cs = q("SELECT ROUND(100.0*SUM(CASE WHEN s.cstype='A' THEN 1 ELSE 0 END)"
                "/COUNT(*),1) FROM ChargesheetDetails s JOIN CaseMaster c ON "
                "c.CaseMasterID=s.CaseMasterID JOIN CrimeHead h ON "
                "h.CrimeHeadID=c.CrimeMajorHeadID WHERE h.CrimeGroupName="
                "'Offences Against Property'")
    add(f"| Property-crime chargesheet rate | {prop_cs}% | ~35.8% (theft 29.8, burglary 43.6) |")
    add("")

    add("## Deliberate data-quality defects (the platform must survive these)")
    add("")
    add("| Defect | Count |")
    add("|---|---|")
    add(f"| Cases with missing coordinates | "
        f"{q('SELECT COUNT(*) FROM CaseMaster WHERE latitude IS NULL'):,} |")
    add(f"| Cases with swapped lat/long | "
        f"{q('SELECT COUNT(*) FROM CaseMaster WHERE latitude > 60'):,} |")
    gender_noise = q("SELECT COUNT(*) FROM Accused WHERE GenderID IN ('m','f')")
    dup_firs = q("SELECT COUNT(*) FROM (SELECT CrimeNo FROM CaseMaster GROUP BY "
                 "PoliceStationID, IncidentFromDate, BriefFacts HAVING COUNT(*)>1)")
    wrong_act = q("SELECT COUNT(DISTINCT a.CaseMasterID) FROM ActSectionAssociation "
                  "a JOIN CaseMaster c ON c.CaseMasterID=a.CaseMasterID WHERE "
                  "a.ActID='IPC' AND c.IncidentFromDate >= '2024-07-01'")
    add(f"| Inconsistent gender codes (m/f) | {gender_noise:,} |")
    add(f"| Duplicate-registered FIRs | {dup_firs:,} |")
    add(f"| Post-BNS cases wrongly citing IPC (Jul–Sep 2024) | {wrong_act:,} |")
    add("")

    add("## Entity-resolution challenge (ground truth planted)")
    add("")
    repeat_rows = q(
        "SELECT COUNT(*) FROM x_er_gold WHERE true_person_id IN (SELECT "
        "true_person_id FROM x_er_gold GROUP BY true_person_id HAVING COUNT(*)>1)")
    total_rows = q("SELECT COUNT(*) FROM x_er_gold")
    add(f"- {q('SELECT COUNT(DISTINCT true_person_id) FROM x_er_gold'):,} true "
        f"persons behind {total_rows:,} accused rows")
    add(f"- Repeat offenders account for {repeat_rows:,} accused rows "
        f"({100 * repeat_rows // total_rows}% — criminological skew by design)")
    add(f"- {q('SELECT COUNT(*) FROM x_person_alias'):,} alias/variant rows "
        f"(spelling variants + true street aliases)")
    aadhaar_caps = q("SELECT COUNT(*) FROM x_identity_capture "
                     "WHERE id_type='aadhaar'")
    add(f"- {aadhaar_caps:,} masked Aadhaar captures (partial by design; "
        f"arrest-time capture ramps 35%→65% over 2021–2026)")
    add("")

    add("## Planted stories (demo answer key: exports/stories.json)")
    add("")
    stories = json.loads((EXPORT_DIR / "stories.json").read_text())
    for key, s in stories.items():
        add(f"- **{key}**: {len(s['cases'])} cases")
    add("")
    add("_Machine-checked by `python -m drishti_datagen --verify` (40+ assertions)._")

    path = EXPORT_DIR / "validation_report.md"
    path.write_text("\n".join(lines))
    return {"report": str(path.relative_to(EXPORT_DIR)), "lines": len(lines)}
