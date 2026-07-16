"""x_agg_daily: station x crime-head x day counts.

The single rollup behind maps, KPIs and trend lines — turns every "count cases
where..." dashboard query into an indexed sum over a few thousand rows instead
of a scan over lakhs.
"""


def build(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM x_agg_daily")
    cur.execute(
        "INSERT INTO x_agg_daily "
        "SELECT c.PoliceStationID, u.DistrictID, c.CrimeMajorHeadID, "
        "       c.CrimeRegisteredDate, COUNT(*) "
        "FROM CaseMaster c JOIN Unit u ON u.UnitID = c.PoliceStationID "
        "GROUP BY c.PoliceStationID, c.CrimeMajorHeadID, c.CrimeRegisteredDate")
    conn.commit()
    return {"agg_rows": cur.execute("SELECT COUNT(*) FROM x_agg_daily").fetchone()[0]}
