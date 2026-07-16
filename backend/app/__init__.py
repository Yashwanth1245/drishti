"""DRISHTI backend: intelligence engines + API over the crime database.

Two halves:
  app.precompute  — one-shot builders run after data generation (rollups,
                    entity resolution, network edges, risk scores, alerts).
                    Run: .venv/bin/python -m app.precompute   (from backend/)
  app.main        — FastAPI serving the five lenses; every data-bearing
                    response carries `evidence` (CrimeNo list).
"""

__version__ = "0.1.0"
