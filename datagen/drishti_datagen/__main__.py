"""CLI entry point: python -m drishti_datagen [--seed N] [--cases N] [--verify]

Runs every implemented pipeline stage in order against exports/drishti.db,
recreating the database from scratch each time (regeneration is cheap and
guarantees determinism). --verify runs sanity checks without regenerating.
"""

import argparse
import json
import sqlite3
import sys
import time

from . import __version__
from .config import DB_PATH, DEFAULT_CASES, DEFAULT_SEED, EXPORT_DIR, PKG_DIR
from .cases import build_cases
from .export import export_all
from .lookups import seed_lookups
from .process import build_process
from .realism import apply_realism
from .stories import build_stories
from .validate import build_report
from .names import NameFactory
from .orgbuilder import build_org
from .persons import build_offender_pool
from .reference import load as load_reference
from .util import IdSeq, Rng


def generate(seed: int, cases: int, skip_export: bool = False,
             also_csv: bool = False) -> None:
    EXPORT_DIR.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript((PKG_DIR / "schema.sql").read_text())

    ref = load_reference()
    rngf = Rng(seed)
    seq = IdSeq()
    names = NameFactory(ref["demo"]["names"])

    t0 = time.time()
    registry = seed_lookups(conn, ref)
    print(f"[lookups]  masters + legal taxonomy seeded "
          f"({len(registry)} offence mappings)")

    org = build_org(conn, ref, rngf, seq, names)
    print(f"[org]      {org['districts']} districts, {org['units']} units "
          f"({org['stations']} stations), {org['employees']} employees, "
          f"{org['courts']} courts")

    # Offender pool sized so its case capacity comfortably covers the named-
    # accused rows the case engine will need (~1.3 slots per pool member;
    # accused rows run ~1.27x cases).
    pool, pstats = build_offender_pool(ref, rngf, names, int(cases * 1.10))
    assert pstats["case_capacity"] > cases * 1.2, "offender capacity too low"
    print(f"[persons]  pool {pstats['pool']:,} ({pstats['repeaters']:,} repeaters, "
          f"capacity {pstats['case_capacity']:,} accused-rows), "
          f"{pstats['distinct_display_names']:,} distinct names, "
          f"{pstats['with_spelling_variants']:,} with variants, "
          f"{pstats['with_true_alias']:,} with aliases, "
          f"{pstats['cross_district']:,} cross-district")

    cstats, proc = build_cases(conn, ref, rngf, seq, names, pool, registry, cases)
    print(f"[cases]    {cstats['cases']:,} cases ({cstats['unknown_cases']:,} with "
          f"unknown accused), {cstats['accused_rows']:,} accused rows, "
          f"{cstats['victim_rows']:,} victims, {cstats['persons_used']:,} persons "
          f"used, {cstats['aliases']:,} alias rows, "
          f"{cstats['minted_extra_persons']:,} extra minted")

    prstats = build_process(conn, rngf, seq, proc)
    print(f"[process]  {prstats['arrests']:,} arrests + {prstats['surrenders']:,} "
          f"surrenders, {prstats['chargesheets']:,} chargesheets, "
          f"{prstats['false_cases']:,} false, {prstats['undetected']:,} undetected, "
          f"{prstats['disposed']:,} court-disposed, "
          f"{prstats['arrest_aadhaar_captures']:,} arrest-aadhaar captures, "
          f"{prstats['slow_stations']} slow stations")

    ststats = build_stories(conn, seq, registry, rngf)
    print(f"[stories]  {ststats['stories']} planted stories, "
          f"{ststats['story_cases']} story cases (manifest: exports/stories.json)")

    rlstats = apply_realism(conn, rngf, seq, ststats["case_ids"])
    print(f"[realism]  coords: {rlstats['coords_missing']:,} missing / "
          f"{rlstats['coords_station_default']:,} station-default / "
          f"{rlstats['coords_swapped']} swapped; {rlstats['name_typos']:,} name "
          f"typos, {rlstats['duplicate_firs']} duplicate FIRs, "
          f"{rlstats['wrong_act_citations']} wrong-act citations")

    stages = ["lookups", "org", "persons", "cases", "process", "stories",
              "realism"]
    exstats = {}
    if not skip_export:
        exstats = export_all(conn, ststats["case_ids"], also_csv=also_csv)
        stages.append("export")
        print(f"[export]   {exstats['tables']} tables -> {exstats['workbook']} "
              f"({exstats['workbook_rows_total']:,} rows, full data)"
              + (" + CSVs" if also_csv else ""))

    vstats = build_report(conn, seed)
    print(f"[report]   exports/{vstats['report']}")
    stages.append("report")

    # Remaining stages (finance — deferred; rollups move to Phase 2) plug in here.

    manifest = {"version": __version__, "seed": seed, "cases_target": cases,
                "stages_done": stages,
                "org": org, "persons": pstats, "cases": cstats, "process": prstats,
                "stories": {k: v for k, v in ststats.items() if k != "case_ids"
                            and k != "manifest"},
                "realism": rlstats, "export": exstats,
                "elapsed_sec": round(time.time() - t0, 1)}
    (EXPORT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    conn.close()
    print(f"[done]     {DB_PATH} written in {manifest['elapsed_sec']}s; "
          f"manifest.json updated")


def verify() -> int:
    """Fast integrity checks; returns a process exit code."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    failures = []

    def check(label, sql, ok):
        value = cur.execute(sql).fetchone()[0]
        status = "PASS" if ok(value) else "FAIL"
        if status == "FAIL":
            failures.append(label)
        print(f"  {status}  {label}: {value}")

    check("districts", "SELECT COUNT(*) FROM District", lambda v: v == 31)
    check("stations (types 5-8)", "SELECT COUNT(*) FROM Unit WHERE TypeID>=5",
          lambda v: 1000 <= v <= 1300)
    check("stations missing coords",
          "SELECT COUNT(*) FROM Unit u LEFT JOIN x_unit_geo g ON g.UnitID=u.UnitID "
          "WHERE u.TypeID>=5 AND g.UnitID IS NULL", lambda v: v == 0)
    check("districts without stations",
          "SELECT COUNT(*) FROM District d WHERE NOT EXISTS "
          "(SELECT 1 FROM Unit u WHERE u.DistrictID=d.DistrictID AND u.TypeID>=5)",
          lambda v: v == 0)
    check("employees", "SELECT COUNT(*) FROM Employee", lambda v: v > 8000)
    check("stations without staff",
          "SELECT COUNT(*) FROM Unit u WHERE u.TypeID>=5 AND NOT EXISTS "
          "(SELECT 1 FROM Employee e WHERE e.UnitID=u.UnitID)", lambda v: v == 0)
    check("acts", "SELECT COUNT(*) FROM Act", lambda v: v >= 14)
    check("sections", "SELECT COUNT(*) FROM Section", lambda v: v >= 60)
    check("crime heads", "SELECT COUNT(*) FROM CrimeHead", lambda v: v >= 10)
    check("coords inside Karnataka box",
          "SELECT COUNT(*) FROM x_unit_geo WHERE latitude NOT BETWEEN 11.5 AND 18.5 "
          "OR longitude NOT BETWEEN 74.0 AND 78.6", lambda v: v == 0)
    check("district socio-economic indicators",
          "SELECT COUNT(*) FROM x_district_indicators", lambda v: v == 31)
    check("cases", "SELECT COUNT(*) FROM CaseMaster", lambda v: v > 0)
    if cur.execute("SELECT COUNT(*) FROM CaseMaster").fetchone()[0]:
        check("CrimeNo uniqueness",
              "SELECT COUNT(*) - COUNT(DISTINCT CrimeNo) FROM CaseMaster",
              lambda v: v == 0)
        check("cases missing act-sections",
              "SELECT COUNT(*) FROM CaseMaster c WHERE NOT EXISTS "
              "(SELECT 1 FROM ActSectionAssociation a WHERE a.CaseMasterID=c.CaseMasterID)",
              lambda v: v == 0)
        check("districts with zero cases",
              "SELECT COUNT(*) FROM District d WHERE NOT EXISTS (SELECT 1 FROM "
              "CaseMaster c JOIN Unit u ON c.PoliceStationID=u.UnitID "
              "WHERE u.DistrictID=d.DistrictID)", lambda v: v == 0)
        check("gold rows == named accused rows",
              "SELECT (SELECT COUNT(*) FROM x_er_gold) - (SELECT COUNT(*) FROM Accused)",
              lambda v: v == 0)
        check("night share of burglary occurrences (pct, NCRB ~80)",
              "SELECT CAST(100.0*SUM(CASE WHEN OccurrenceHourBand IN "
              "('21-24','00-03','03-06') THEN 1 ELSE 0 END)/COUNT(*) AS INT) "
              "FROM Inv_OccuranceTime t JOIN CaseMaster c ON c.CaseMasterID=t.CaseMasterID "
              "JOIN x_mo_tag m ON m.CaseMasterID=c.CaseMasterID "
              "WHERE m.tag LIKE '%entry%'", lambda v: 65 <= v <= 92)
        check("IPC-after-cutover outside the habit window (must be clean)",
              "SELECT COUNT(*) FROM CaseMaster c JOIN ActSectionAssociation a ON "
              "a.CaseMasterID=c.CaseMasterID WHERE a.ActID='IPC' AND "
              "c.IncidentFromDate >= '2024-10-01'", lambda v: v == 0)
        check("wrong-act citations inside Jul-Sep 2024 (planted realism)",
              "SELECT COUNT(DISTINCT a.CaseMasterID) FROM CaseMaster c JOIN "
              "ActSectionAssociation a ON a.CaseMasterID=c.CaseMasterID WHERE "
              "a.ActID='IPC' AND c.IncidentFromDate >= '2024-07-01' AND "
              "c.IncidentFromDate < '2024-10-01'", lambda v: 1 <= v <= 3000)
        check("identity captures", "SELECT COUNT(*) FROM x_identity_capture",
              lambda v: v > 0)
        check("mo tags", "SELECT COUNT(*) FROM x_mo_tag", lambda v: v > 0)
        check("SLL-head case share pct (cyber+ndps+gambling+excise ~24)",
              "SELECT CAST(100.0*(SELECT COUNT(*) FROM CaseMaster c JOIN CrimeHead h "
              "ON h.CrimeHeadID=c.CrimeMajorHeadID WHERE h.CrimeGroupName LIKE '%SLL%')"
              "/COUNT(*) AS INT) FROM CaseMaster", lambda v: 15 <= v <= 32)
        check("same person twice in one case",
              "SELECT COUNT(*) FROM (SELECT a.CaseMasterID, g.true_person_id, "
              "COUNT(*) n FROM x_er_gold g JOIN Accused a ON "
              "a.AccusedMasterID=g.source_row_id GROUP BY 1,2 HAVING n>1)",
              lambda v: v == 0)
        check("arrests", "SELECT COUNT(*) FROM ArrestSurrender", lambda v: v > 0)
        check("arrests before registration",
              "SELECT COUNT(*) FROM ArrestSurrender a JOIN CaseMaster c ON "
              "c.CaseMasterID=a.CaseMasterID WHERE a.ArrestSurrenderDate < "
              "c.CrimeRegisteredDate", lambda v: v == 0)
        check("chargesheets before registration",
              "SELECT COUNT(*) FROM ChargesheetDetails s JOIN CaseMaster c ON "
              "c.CaseMasterID=s.CaseMasterID WHERE s.csdate < c.CrimeRegisteredDate",
              lambda v: v == 0)
        check("overall chargesheet pct of final reports A/(A+B+C) (KA ~77)",
              "SELECT CAST(100.0*SUM(CASE WHEN cstype='A' THEN 1 ELSE 0 END)"
              "/COUNT(*) AS INT) FROM ChargesheetDetails", lambda v: 62 <= v <= 85)
        check("theft-group chargesheet pct among concluded (low, ~25-45)",
              "SELECT CAST(100.0*SUM(CASE WHEN s.cstype='A' THEN 1 ELSE 0 END)"
              "/COUNT(*) AS INT) FROM ChargesheetDetails s JOIN CaseMaster c ON "
              "c.CaseMasterID=s.CaseMasterID JOIN CrimeHead h ON "
              "h.CrimeHeadID=c.CrimeMajorHeadID WHERE h.CrimeGroupName="
              "'Offences Against Property'", lambda v: 15 <= v <= 55)
        check("status mix: still under investigation pct (25-55)",
              "SELECT CAST(100.0*SUM(CASE WHEN CaseStatusID=1 THEN 1 ELSE 0 END)"
              "/COUNT(*) AS INT) FROM CaseMaster", lambda v: 25 <= v <= 55)
        check("arrest aadhaar captures",
              "SELECT COUNT(*) FROM x_identity_capture WHERE role='accused' "
              "AND id_type='aadhaar'", lambda v: v > 10000)
        check("missing-coords pct (realism target ~7)",
              "SELECT CAST(100.0*SUM(CASE WHEN latitude IS NULL THEN 1 ELSE 0 END)"
              "/COUNT(*) AS INT) FROM CaseMaster", lambda v: 4 <= v <= 10)
        check("swapped coords present (map layer must survive them)",
              "SELECT COUNT(*) FROM CaseMaster WHERE latitude > 60",
              lambda v: 100 <= v <= 1500)
        check("lowercase gender noise present",
              "SELECT COUNT(*) FROM Accused WHERE GenderID IN ('m','f')",
              lambda v: v > 1000)
        # ---- planted-story assertions (the demo answer key must hold) ----
        import json as _json
        from .config import EXPORT_DIR as _exp
        stories = _json.loads((_exp / "stories.json").read_text())
        s1 = stories["S1_serial_snatcher"]
        check("S1: snatcher case count (11)",
              f"SELECT COUNT(*) FROM x_person_case_role WHERE person_id="
              f"{s1['person_id']} AND role='accused'", lambda v: v == 11)
        check("S1: appears in 3 districts",
              f"SELECT COUNT(DISTINCT u.DistrictID) FROM x_person_case_role r "
              f"JOIN CaseMaster c ON c.CaseMasterID=r.CaseMasterID JOIN Unit u ON "
              f"u.UnitID=c.PoliceStationID WHERE r.person_id={s1['person_id']}",
              lambda v: v == 3)
        check("S1: 2026 Hubballi spike (>=4 cases Apr-Jun 2026)",
              f"SELECT COUNT(*) FROM x_person_case_role r JOIN CaseMaster c ON "
              f"c.CaseMasterID=r.CaseMasterID WHERE r.person_id={s1['person_id']} "
              f"AND c.CrimeRegisteredDate >= '2026-04-01'", lambda v: v >= 4)
        check("S1: aadhaar captured at both arrests (alias exposure)",
              f"SELECT COUNT(*) FROM x_identity_capture i JOIN x_person_case_role r "
              f"ON r.CaseMasterID=i.CaseMasterID AND r.source_row_id=i.source_row_id "
              f"WHERE r.person_id={s1['person_id']} AND i.id_type='aadhaar'",
              lambda v: v == 2)
        s2 = stories["S2_vehicle_ring"]
        check("S2: fence linked to >=4 ring cases",
              f"SELECT COUNT(*) FROM x_person_case_role WHERE person_id="
              f"{s2['fence_pid']} AND role='accused'", lambda v: v >= 4)
        s5 = stories["S5_false_complainant"]
        check("S5: serial false complainant (6 B-type cases)",
              "SELECT COUNT(*) FROM ChargesheetDetails s JOIN ComplainantDetails "
              "cd ON cd.CaseMasterID=s.CaseMasterID WHERE cd.ComplainantName="
              "'Gangamma' AND s.cstype='B'", lambda v: v == 6)

    conn.close()
    print("VERIFY:", "ALL PASS" if not failures else f"FAILURES: {failures}")
    return 1 if failures else 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="drishti_datagen")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--cases", type=int, default=DEFAULT_CASES)
    ap.add_argument("--verify", action="store_true",
                    help="run sanity checks on the existing DB and exit")
    ap.add_argument("--skip-export", action="store_true",
                    help="skip the Excel export (faster dev iteration)")
    ap.add_argument("--csv", action="store_true",
                    help="also emit one raw CSV per table (default: workbook only)")
    args = ap.parse_args()
    if args.verify:
        sys.exit(verify())
    generate(args.seed, args.cases, skip_export=args.skip_export,
             also_csv=args.csv)


if __name__ == "__main__":
    main()
