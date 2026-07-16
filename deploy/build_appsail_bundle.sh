#!/usr/bin/env bash
# Assembles deploy/bundle/ — the zip-ready layout for Zoho Catalyst AppSail's
# NATIVE Python stack (the fallback path if the org's Catalyst plan doesn't
# take Docker images; docs/DEPLOYMENT.md explains when to use which).
#
# AppSail native runtimes don't pip-install for you, so dependencies are
# vendored into the bundle with pip -t. Run on a machine whose Python matches
# the AppSail stack version (confirm the exact version at the AppSail
# workshop; pure-Python deps here make mismatches unlikely to bite).
#
# Usage (repo root):  bash deploy/build_appsail_bundle.sh
set -euo pipefail
cd "$(dirname "$0")/.."

test -f exports/drishti.db || { echo "exports/drishti.db missing — run datagen first"; exit 1; }

echo "==> building frontend"
npm run build --prefix frontend

echo "==> assembling deploy/bundle"
rm -rf deploy/bundle
mkdir -p deploy/bundle/backend deploy/bundle/exports deploy/bundle/frontend

echo "==> vendoring python dependencies"
python3 -m pip install --quiet -r backend/requirements.txt -t deploy/bundle/vendor

cp -R backend/app deploy/bundle/backend/app
cp exports/drishti.db exports/stories.json exports/metrics.json deploy/bundle/exports/
cp -R frontend/dist deploy/bundle/frontend/dist

# Entry point: put vendored deps on the path, then boot uvicorn on the port
# AppSail assigns. config.py resolves ROOT relative to backend/app, so the
# bundle mirrors the repo layout.
cat > deploy/bundle/start.py <<'PY'
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
import uvicorn
uvicorn.run("app.main:app", host="0.0.0.0",
            port=int(os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT",
                                    os.environ.get("PORT", 9000))))
PY

# AppSail app config — TEMPLATE: confirm stack id + memory at the workshop.
cat > deploy/bundle/app-config.json <<'JSON'
{
  "command": "python start.py",
  "stack": "python_3_10",
  "env_variables": {
    "NOTE": "set ZOHO_* and DRISHTI_SECRET in the AppSail console, not here"
  },
  "memory": 512
}
JSON

echo "==> done: deploy/bundle ($(du -sh deploy/bundle | cut -f1))"
echo "    next: catalyst deploy (see docs/DEPLOYMENT.md)"
