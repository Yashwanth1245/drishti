"""The mess pass: deliberate data-quality defects at documented rates.

Real police data is entered by tired constables at 1,100 stations — a platform
that only works on clean data is a demo toy. Every defect here is something the
DRISHTI engines must and do survive (map layer filters bad coords, ER survives
typos, trend engine dedups double-registered FIRs). Planted-story cases are
protected — the demo script depends on them being intact.

Rates (see docs/SYNTHETIC_DATA_DESIGN.md realism catalog):
"""

MISSING_COORDS = 0.07        # lat/long simply not entered
STATION_DEFAULT_COORDS = 0.10  # IO lazily entered the station's own location
SWAPPED_COORDS = 0.003       # classic lat/long swap
GENDER_CODE_NOISE = 0.02     # m/f instead of M/F
NAME_TYPOS = 0.04            # transposed letters / double spaces
DUPLICATE_FIR = 0.004        # same incident registered twice
WRONG_ACT_AFTER_CUTOVER = 0.02  # officers citing IPC out of habit, Jul-Sep 2024


def _typo(name, rng):
    if not name or len(name) < 5:
        return name
    if rng.random() < 0.4:
        return name.replace(" ", "  ", 1)
    i = rng.randrange(1, len(name) - 2)
    return name[:i] + name[i + 1] + name[i] + name[i + 2:]


def apply_realism(conn, rngf, seq, protect_case_ids):
    rng = rngf.stream("realism")
    cur = conn.cursor()
    protect = set(protect_case_ids)
    stats = {}

    case_ids = [r[0] for r in cur.execute("SELECT CaseMasterID FROM CaseMaster")
                if r[0] not in protect]
    rng.shuffle(case_ids)

    # Non-overlapping coordinate defects (shuffled list, consumed in slices).
    n1 = int(len(case_ids) * MISSING_COORDS)
    n2 = int(len(case_ids) * STATION_DEFAULT_COORDS)
    n3 = int(len(case_ids) * SWAPPED_COORDS)
    missing, station_default, swapped = (case_ids[:n1], case_ids[n1:n1 + n2],
                                         case_ids[n1 + n2:n1 + n2 + n3])
    cur.executemany("UPDATE CaseMaster SET latitude=NULL, longitude=NULL "
                    "WHERE CaseMasterID=?", [(i,) for i in missing])
    cur.executemany(
        "UPDATE CaseMaster SET latitude=(SELECT g.latitude FROM x_unit_geo g "
        "WHERE g.UnitID=CaseMaster.PoliceStationID), longitude=(SELECT g.longitude "
        "FROM x_unit_geo g WHERE g.UnitID=CaseMaster.PoliceStationID) "
        "WHERE CaseMasterID=?", [(i,) for i in station_default])
    cur.executemany("UPDATE CaseMaster SET latitude=longitude, longitude=latitude "
                    "WHERE CaseMasterID=?", [(i,) for i in swapped])
    stats["coords_missing"] = len(missing)
    stats["coords_station_default"] = len(station_default)
    stats["coords_swapped"] = len(swapped)

    # Gender-code inconsistency on Victim/Accused (TEXT columns in the source).
    protect_sql = ",".join(str(i) for i in sorted(protect)) or "0"
    for table, col in (("Victim", "VictimMasterID"), ("Accused", "AccusedMasterID")):
        rows = [r[0] for r in cur.execute(
            f"SELECT {col} FROM {table} WHERE CaseMasterID NOT IN ({protect_sql})")]
        picked = rng.sample(rows, int(len(rows) * GENDER_CODE_NOISE))
        cur.executemany(f"UPDATE {table} SET GenderID=lower(GenderID) WHERE {col}=?",
                        [(i,) for i in picked])
        stats[f"gender_noise_{table.lower()}"] = len(picked)

    # Name typos across all three party tables.
    typo_total = 0
    for table, idcol, namecol in (("Accused", "AccusedMasterID", "AccusedName"),
                                  ("Victim", "VictimMasterID", "VictimName"),
                                  ("ComplainantDetails", "ComplainantID",
                                   "ComplainantName")):
        rows = cur.execute(f"SELECT {idcol}, {namecol} FROM {table} "
                           f"WHERE CaseMasterID NOT IN ({protect_sql})").fetchall()
        picked = rng.sample(rows, int(len(rows) * NAME_TYPOS))
        cur.executemany(f"UPDATE {table} SET {namecol}=? WHERE {idcol}=?",
                        [(_typo(nm, rng), rid) for rid, nm in picked])
        typo_total += len(picked)
    stats["name_typos"] = typo_total

    # Duplicate FIRs: the same incident registered twice; the copy is later
    # closed as a false case (cstype B semantics kept simple).
    dup_src = cur.execute(
        "SELECT * FROM CaseMaster WHERE CaseCategoryID=1 ORDER BY CaseMasterID "
        "LIMIT ?", (int(cur.execute("SELECT COUNT(*) FROM CaseMaster").fetchone()[0]
                        * DUPLICATE_FIR),)).fetchall()
    top_serial = {}      # (station, cat, year) -> highest serial (MAX-based,
    dup_rows, dup_asa = [], []   # not COUNT — counts drift once stages mix)
    for row in dup_src:
        if row[0] in protect:
            continue
        (cid, crime_no, case_no, reg, iop, st_uid, cat, grav, h, sh, _st, court,
         ifrom, ito, info, lat, lon, brief) = row
        key = (st_uid, cat, reg[:4])
        if key not in top_serial:
            top_serial[key] = cur.execute(
                "SELECT MAX(CAST(substr(CrimeNo,-5) AS INTEGER)) FROM CaseMaster "
                "WHERE PoliceStationID=? AND CaseCategoryID=? AND "
                "substr(CrimeNo,10,4)=?", (st_uid, cat, reg[:4])).fetchone()[0] or 0
        top_serial[key] += 1
        serial = top_serial[key]
        new_id = seq.next("case")
        dup_rows.append((new_id, f"{cat}{crime_no[1:5]}{st_uid:04d}{reg[:4]}"
                         f"{serial:05d}", f"{reg[:4]}{serial:05d}", reg, iop,
                         st_uid, cat, grav, h, sh, 3, court, ifrom, ito, info,
                         lat, lon, brief))
        dup_asa.append((new_id, cid))
    cur.executemany("INSERT INTO CaseMaster VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    dup_rows)
    cur.executemany(
        "INSERT INTO ActSectionAssociation SELECT ?, ActID, SectionID, ActOrderID, "
        "SectionOrderID FROM ActSectionAssociation WHERE CaseMasterID=?", dup_asa)
    stats["duplicate_firs"] = len(dup_rows)

    # Post-cutover cases where the officer cited IPC out of habit (Jul-Sep 2024):
    # the act label flips, the section number stays — the classic real error.
    habit = [r[0] for r in cur.execute(
        "SELECT DISTINCT a.CaseMasterID FROM ActSectionAssociation a JOIN CaseMaster "
        "c ON c.CaseMasterID=a.CaseMasterID WHERE a.ActID='BNS' AND "
        "c.IncidentFromDate >= '2024-07-01' AND c.IncidentFromDate < '2024-10-01'")
        if r[0] not in protect]
    picked = rng.sample(habit, int(len(habit) * WRONG_ACT_AFTER_CUTOVER))
    cur.executemany("UPDATE ActSectionAssociation SET ActID='IPC' WHERE CaseMasterID=?",
                    [(i,) for i in picked])
    stats["wrong_act_citations"] = len(picked)

    conn.commit()
    return stats
