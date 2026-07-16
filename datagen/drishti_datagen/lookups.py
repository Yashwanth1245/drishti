"""Seeds every lookup/master table and the legal taxonomy.

Sources: reference/legal_sections.json for acts, sections, crime heads and the
IPC<->BNS offence mapping; static lists here for the small masters the ER PDF
references but never defines. Insertion order is deterministic, so IDs are
stable across runs — later stages rely on that.
"""

RELIGIONS = ["Hindu", "Muslim", "Christian", "Jain", "Sikh", "Buddhist", "Others"]

CASTES = ["General", "OBC", "SC", "ST", "Vokkaliga", "Lingayat", "Kuruba", "Idiga",
          "Bunt", "Billava", "Mogaveera", "Brahmin", "Vishwakarma", "Madivala",
          "Uppara", "Bhovi", "Lambani", "Golla", "Bestha", "Devanga", "Nayaka", "Others"]

OCCUPATIONS = ["Farmer", "Driver", "Student", "Housewife", "Government Employee",
               "Private Employee", "Business", "Daily Wage Labourer",
               "Software Engineer", "Teacher", "Unemployed", "Auto Driver",
               "Shopkeeper", "Mason", "Carpenter", "Security Guard", "Retired",
               "Advocate", "Doctor", "Nurse", "Police", "Tailor", "Fisherman",
               "Hotel Worker", "Electrician"]

# CaseCategoryID doubles as the CrimeNo leading digit (per ER PDF examples).
CASE_CATEGORIES = [(1, "FIR"), (3, "UDR"), (8, "Zero FIR"), (4, "PAR")]

CASE_STATUSES = ["Under Investigation", "Charge Sheeted", "Final Report - False Case",
                 "Final Report - Undetected", "Disposed by Court", "Transferred"]

GENDERS = [(1, "M", "Male"), (2, "F", "Female"), (3, "T", "Transgender")]

ARREST_TYPES = ["Arrest", "Voluntary Surrender"]

BLOOD_GROUPS = ["O+", "B+", "A+", "AB+", "O-", "B-", "A-", "AB-"]

PLACE_TYPES = ["House/Residence", "Street/Road", "Highway", "ATM", "Bank",
               "Shop/Commercial", "Public Transport", "Bus Stand", "Railway Station",
               "Park/Ground", "Hotel/Lodge", "Industrial Area", "Farm/Field",
               "Lake/Water Body", "School/College", "Hospital", "Place of Worship",
               "Online/Cyberspace", "Liquor Shop", "Forest Area"]


def seed_lookups(conn, ref):
    """Populate masters + legal taxonomy. Returns the offence registry used by
    the case engine: [{short, ipc, bns, head_id, subhead_id, gravity_id}]."""
    cur = conn.cursor()

    cur.executemany("INSERT INTO ReligionMaster VALUES (?,?)",
                    list(enumerate(RELIGIONS, 1)))
    cur.executemany("INSERT INTO CasteMaster VALUES (?,?)",
                    list(enumerate(CASTES, 1)))
    cur.executemany("INSERT INTO OccupationMaster VALUES (?,?)",
                    list(enumerate(OCCUPATIONS, 1)))
    cur.executemany("INSERT INTO CaseCategory VALUES (?,?)", CASE_CATEGORIES)
    cur.executemany("INSERT INTO GravityOffence VALUES (?,?)",
                    [(1, "Heinous"), (2, "Non-Heinous")])
    cur.executemany("INSERT INTO CaseStatusMaster VALUES (?,?)",
                    list(enumerate(CASE_STATUSES, 1)))
    cur.executemany("INSERT INTO GenderMaster VALUES (?,?,?)", GENDERS)
    cur.executemany("INSERT INTO ArrestSurrenderTypeMaster VALUES (?,?)",
                    list(enumerate(ARREST_TYPES, 1)))
    cur.executemany("INSERT INTO BloodGroupMaster VALUES (?,?)",
                    list(enumerate(BLOOD_GROUPS, 1)))
    cur.executemany("INSERT INTO PlaceTypeMaster VALUES (?,?)",
                    list(enumerate(PLACE_TYPES, 1)))

    # ---- crime heads & sub-heads ------------------------------------------
    legal = ref["legal"]
    head_ids, subhead_ids = {}, {}
    for head in legal["crimeHeads"]:
        hid = len(head_ids) + 1
        head_ids[head["head"]] = hid
        cur.execute("INSERT INTO CrimeHead VALUES (?,?,1)", (hid, head["head"]))
        for seq, sub in enumerate(head.get("subHeads", []), 1):
            sid = len(subhead_ids) + 1
            subhead_ids[(head["head"], sub)] = sid
            cur.execute("INSERT INTO CrimeSubHead VALUES (?,?,?,?)",
                        (sid, hid, sub, seq))

    def ensure_head(name):
        if name not in head_ids:
            hid = len(head_ids) + 1
            head_ids[name] = hid
            cur.execute("INSERT INTO CrimeHead VALUES (?,?,1)", (hid, name))
        return head_ids[name]

    def ensure_subhead(head, sub):
        key = (head, sub)
        if key not in subhead_ids:
            sid = len(subhead_ids) + 1
            subhead_ids[key] = sid
            cur.execute("INSERT INTO CrimeSubHead VALUES (?,?,?,99)",
                        (sid, ensure_head(head), sub))
        return subhead_ids[key]

    # ---- acts & sections ---------------------------------------------------
    cur.execute("INSERT INTO Act VALUES ('IPC','Indian Penal Code, 1860','IPC',1)")
    cur.execute("INSERT INTO Act VALUES ('BNS','Bharatiya Nyaya Sanhita, 2023','BNS',1)")
    for act in legal["acts"]:
        code = act.get("code") or act["name"]
        cur.execute("INSERT OR IGNORE INTO Act VALUES (?,?,?,1)",
                    (code, f"{act['name']}, {act.get('year','')}".strip(", "), code))
        for s in act.get("commonSections", []):
            cur.execute("INSERT OR IGNORE INTO Section VALUES (?,?,?,1)",
                        (code, s["section"], s.get("desc", "")))

    # ---- offence registry (IPC<->BNS mapped offences) ----------------------
    def _clean_section(s):
        """Extract a usable section code from research prose.
        '— (new; formerly 379/356 IPC)' -> '379'; '304(2)' -> '304(2)'."""
        import re
        m = re.search(r"\d+[0-9A-Za-z().]*", s or "")
        return m.group(0).rstrip(".") if m else None

    registry = []
    for off in legal["offences"]:
        short = off["name"].split(" — ")[0].split(" - ")[0].strip()
        head = off.get("crimeHead") or "Miscellaneous IPC/BNS Crimes"
        sub = off.get("crimeSubHead") or short
        gravity_id = 1 if (off.get("gravity", "").lower().startswith("hein")) else 2
        for act, sec in (("IPC", _clean_section(off.get("ipcSection"))),
                         ("BNS", _clean_section(off.get("bnsSection")))):
            if sec:
                cur.execute("INSERT OR IGNORE INTO Section VALUES (?,?,?,1)",
                            (act, sec, short))
                cur.execute("INSERT INTO CrimeHeadActSection VALUES (?,?,?)",
                            (ensure_head(head), act, sec))
        registry.append({
            "short": short, "ipc": _clean_section(off.get("ipcSection")),
            "bns": _clean_section(off.get("bnsSection")),
            "head_id": ensure_head(head), "subhead_id": ensure_subhead(head, sub),
            "gravity_id": gravity_id,
        })

    # ---- RBAC roles ---------------------------------------------------------
    cur.executemany("INSERT INTO x_role VALUES (?,?,?)", [
        (1, "DGP", "state"), (2, "SCRB_ANALYST", "state"), (3, "RANGE_DIG", "range"),
        (4, "DISTRICT_SP", "district"), (5, "STATION_IO", "station"),
    ])

    conn.commit()
    return registry
