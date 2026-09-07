#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Deploy EconetPy to a Shiny Server app directory via scp.
#
# Modelled on the SESPy deploy script (Marine-SABRES/SESPy/deploy/deploy.sh):
# ship ONLY runtime files, preserve server-owned state, then touch restart.txt
# so Shiny Server reloads the app's workers on the next request.
#
# Ships: app.py + the four sibling modules it imports, the tracked BalticFW_*
# sources, VERSION (rendered in the UI footer), www/img, examples/, and the
# env manifests. NOT shipped: tests, docs, lib/ (pyvis vendors it at render),
# BalticFW.pkl (rebuilt server-side, step 5), *.R, the .ewemdb blobs.
#
# Prerequisites:
#   * passwordless (key-based) SSH to $SERVER for the deploy user
#   * $APP_DIR exists and is writable by that user — created once with sudo,
#     see DEPLOYMENT.md "First-time server setup"
#   * the shared env /opt/micromamba/envs/shiny already has the deps,
#     including the razinkele pyvis fork (dist 'pyvis-optimized'). This script
#     ships code, not the env; see DEPLOYMENT.md if requirements.txt changed.
#
# Config: set DEPLOY_SERVER / DEPLOY_DIR / DEPLOY_PYTHON in a gitignored
# deploy/config.env (copy deploy/config.env.example), or pass them as env
# vars. The real host/path are intentionally NOT hard-coded here so this
# script is safe in a public repo.
#
# Usage (run from anywhere; the script resolves the repo root):
#   deploy/deploy.sh
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
[ -f "$SCRIPT_DIR/config.env" ] && source "$SCRIPT_DIR/config.env"

SERVER="${DEPLOY_SERVER:?set DEPLOY_SERVER (in deploy/config.env or the env), e.g. user@host}"
APP_DIR="${DEPLOY_DIR:?set DEPLOY_DIR (in deploy/config.env or the env), e.g. /srv/shiny-server/EconetPy}"
PYTHON="${DEPLOY_PYTHON:-/opt/micromamba/envs/shiny/bin/python3}"

REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Runtime files to ship. Anything not listed (tests, docs/, .git/, lib/,
# *.R, *.ewemdb, deployment_logs/, .superpowers/) is intentionally excluded.
# VERSION ships because app.py renders it in the footer at runtime.
RUNTIME=(
  app.py
  network_analysis.py
  network_viz.py
  flux_calculations.py
  load_data.py
  feedback_reporter.py
  BalticFW_network.graphml
  BalticFW_species_info.csv
  BalticFW_metadata.json
  VERSION
  LICENSE
  README.md
  README_PYTHON.md
  requirements.txt
  environment.yml
  www
  examples
)

VERSION="$(git describe --tags --always 2>/dev/null || echo unknown)"
echo "==> Deploying EconetPy ${VERSION} to ${SERVER}:${APP_DIR}"

# 1. Stage a clean copy locally so no __pycache__/*.pyc (stale bytecode) ships.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
for item in "${RUNTIME[@]}"; do
  if [ -e "$item" ]; then
    cp -R "$item" "$STAGE/"
  else
    echo "    ! missing '$item' — skipping" >&2
  fi
done
find "$STAGE" -name __pycache__ -type d -prune -exec rm -rf {} +
find "$STAGE" -name '*.pyc' -delete
# www/*.html are gitignored legacy render artifacts (pre pyvis-shiny
# migration); only www/img is a real static asset.
find "$STAGE/www" -maxdepth 1 -name '*.html' -delete 2>/dev/null || true
# Never ship the local feedback log. The server OWNS data/ — its
# user_feedback_log.ndjson is production feedback and is preserved across
# the deploy in steps 2/4 below.
rm -rf "$STAGE/data"

# 2. Ensure the target exists, then clear stale top-level bytecode so an
#    old .pyc cannot shadow the new modules (scp overwrites but never
#    deletes). The server-owned data/ is stashed aside first and restored in
#    step 4, so a deploy never destroys collected feedback.
ssh "$SERVER" "
  mkdir -p '$APP_DIR' &&
  if [ -d '$APP_DIR/data' ]; then
    rm -rf '$APP_DIR/.deploy-keep' &&
    mkdir -p '$APP_DIR/.deploy-keep' &&
    cp -a '$APP_DIR/data' '$APP_DIR/.deploy-keep/data';
  fi &&
  rm -rf '$APP_DIR/__pycache__'
"

# 3. Copy the staged runtime tree.
scp -rq "$STAGE"/* "$SERVER:$APP_DIR/"

# 4. Restore the preserved feedback log and make sure data/ exists and is
#    group-writable — feedback_reporter.py appends to it as the 'shiny' user.
ssh "$SERVER" "
  mkdir -p '$APP_DIR/data' &&
  if [ -d '$APP_DIR/.deploy-keep/data' ]; then
    cp -a '$APP_DIR/.deploy-keep/data/.' '$APP_DIR/data/';
  fi &&
  rm -rf '$APP_DIR/.deploy-keep' &&
  chmod g+ws '$APP_DIR/data'
"

# 5. Rebuild the pickle cache from the shipped .graphml/.csv sources. It is
#    gitignored and never shipped; building it here as the deploy user (not
#    lazily as 'shiny' on first request) keeps the first page load fast and
#    surfaces a data problem now rather than in a user's browser.
echo "==> Rebuilding BalticFW.pkl on the server"
ssh "$SERVER" "cd '$APP_DIR' && '$PYTHON' load_data.py"

# 6. Import smoke: the shared env is upgraded independently of this app, so
#    prove app.py actually imports under the server's interpreter BEFORE
#    restart.txt makes the new code live.
echo "==> Import smoke"
ssh "$SERVER" "cd '$APP_DIR' && '$PYTHON' -c 'import app; print(\"import OK\")'"

# 7. Pin drift check. The shared env is upgraded out-of-band and by sudo, so
#    requirements.txt can name a version the server does not have — a silent
#    dev/prod skew that makes local test results stop predicting production.
#    Warn loudly rather than fail: the env is shared and deliberately managed
#    separately, so a mismatch is a fact to surface, not a deploy to block.
PINNED="$(grep -o "pyvis.git@v[0-9.]*" requirements.txt | head -1 | cut -d@ -f2)"
INSTALLED="$(ssh "$SERVER" "'$PYTHON' -c 'import pyvis; print(pyvis.__version__)'" 2>/dev/null)"
if [ -n "$PINNED" ] && [ -n "$INSTALLED" ] && [ "${PINNED#v}" != "$INSTALLED" ]; then
  echo ""
  echo "  !! pyvis PIN DRIFT: requirements.txt pins ${PINNED}, server has ${INSTALLED}"
  echo "     The app is being deployed against a version it is not pinned to."
  echo "     Fix (needs sudo on the server) - see DEPLOYMENT.md step 1:"
  echo "       sudo env PIP_NO_CACHE_DIR=1 ${PYTHON%/*}/pip install \\"
  echo "         \"pyvis-optimized @ git+https://github.com/razinkele/pyvis.git@${PINNED}\""
  echo ""
else
  echo "==> pyvis pin OK (${INSTALLED:-unknown})"
fi

# 8. Reload: Shiny Server restarts an app's workers when restart.txt changes.
ssh "$SERVER" "touch '$APP_DIR/restart.txt'"

echo "==> Done. ${APP_DIR} updated to ${VERSION}; Shiny Server reloads on next request."
