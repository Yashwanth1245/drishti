"""x_network_edge: the criminal-association graph between entities.

Edge types (evidence = JSON list of CaseMasterIDs, capped):
  co-accused    — two entities named in the same FIR (weight = shared cases)
  shared-phone  — the same phone number captured against both entities
"""

import json
from collections import defaultdict

EVIDENCE_CAP = 20


def build(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM x_network_edge")

    ent_of = dict(cur.execute(
        "SELECT AccusedMasterID, entity_id FROM x_entity_member"))

    case_entities = defaultdict(set)
    for aid, cid in cur.execute(
            "SELECT AccusedMasterID, CaseMasterID FROM x_entity_member"):
        case_entities[cid].add(ent_of[aid])

    co = defaultdict(list)
    for cid, ents in case_entities.items():
        if len(ents) < 2:
            continue
        e = sorted(ents)
        for i in range(len(e)):
            for j in range(i + 1, len(e)):
                co[(e[i], e[j])].append(cid)

    phone_ents = defaultdict(lambda: defaultdict(list))
    for aid, value, cid in cur.execute(
            "SELECT source_row_id, id_value, CaseMasterID FROM x_identity_capture "
            "WHERE role='accused' AND id_type='phone'"):
        if aid in ent_of:
            phone_ents[value][ent_of[aid]].append(cid)

    rows = []
    for (a, b), cids in co.items():
        rows.append(("entity", a, "entity", b, "co-accused", len(cids),
                     json.dumps(sorted(set(cids))[:EVIDENCE_CAP])))
    shared_phone_edges = 0
    for value, ents in phone_ents.items():
        if len(ents) < 2:
            continue
        e = sorted(ents)
        for i in range(len(e)):
            for j in range(i + 1, len(e)):
                cids = sorted(set(ents[e[i]] + ents[e[j]]))[:EVIDENCE_CAP]
                rows.append(("entity", e[i], "entity", e[j], "shared-phone",
                             len(cids), json.dumps(cids)))
                shared_phone_edges += 1

    cur.executemany("INSERT INTO x_network_edge VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()
    return {"co_accused_edges": len(co), "shared_phone_edges": shared_phone_edges}
