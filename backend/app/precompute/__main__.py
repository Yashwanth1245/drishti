"""Run all intelligence builders in order. From backend/:

    ../.venv/bin/python -m app.precompute

Idempotent: every builder clears and rebuilds its own tables. Writes a summary
to exports/metrics.json and prints per-stage stats/timings.
"""

import json
import time

from ..config import METRICS_PATH
from ..db import connect
from . import alerts, er, network, risk, rollups


def main():
    conn = connect()
    summary = {}
    for name, builder in (("rollups", rollups.build), ("er", er.build),
                          ("network", network.build), ("risk", risk.build),
                          ("alerts", alerts.build)):
        t0 = time.time()
        stats = builder(conn)
        stats["sec"] = round(time.time() - t0, 1)
        summary[name] = stats
        print(f"[{name:<8}] " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    METRICS_PATH.write_text(json.dumps(summary, indent=2))
    print(f"[done    ] metrics -> {METRICS_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
