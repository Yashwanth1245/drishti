"""Database access helpers shared by precompute and the API."""

import math
import sqlite3

from .config import DB_PATH, NEIGHBOR_DEG


def connect(readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True,
                               check_same_thread=False)
    else:
        conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def district_neighbors(conn):
    """district_id -> set of neighboring district_ids, by station-centroid
    distance (self-contained: derived from x_unit_geo, no external gazetteer)."""
    cent = {}
    for did, lat, lon in conn.execute(
            "SELECT u.DistrictID, AVG(g.latitude), AVG(g.longitude) "
            "FROM Unit u JOIN x_unit_geo g ON g.UnitID=u.UnitID "
            "WHERE u.TypeID>=5 GROUP BY 1"):
        cent[did] = (lat, lon)
    out = {d: set() for d in cent}
    ids = list(cent)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            d = math.hypot(cent[a][0] - cent[b][0], cent[a][1] - cent[b][1])
            if d <= NEIGHBOR_DEG:
                out[a].add(b)
                out[b].add(a)
    return out
