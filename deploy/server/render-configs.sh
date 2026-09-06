#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Render the server's shiny-server / nginx configs with the EconetPy blocks
# inserted, WITHOUT keeping the server's configs in this (public) repo.
#
# Why this exists: the site vhost maps every service, internal port, admin
# path and auth file on the host. That belongs on the host, not in a public
# git history. So the repo carries only the two EconetPy-specific fragments
# (econetpy.nginx.conf, econetpy.shiny-server.conf); this script pulls the
# CURRENT live config down, inserts the fragment after the /SESPy block,
# and writes the result next to it as a gitignored file for you to review
# and copy back with sudo.
#
# Output (all gitignored):
#   deploy/server/shiny-server.conf       + .orig
#   deploy/server/nid4ocean               + .orig   (named after the vhost)
#
# Usage:
#   deploy/server/render-configs.sh          # render + show diffs
#   deploy/server/render-configs.sh --stage  # also scp them to the server
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
[ -f "$SCRIPT_DIR/../config.env" ] && source "$SCRIPT_DIR/../config.env"

SERVER="${DEPLOY_SERVER:?set DEPLOY_SERVER in deploy/config.env}"
VHOST="${DEPLOY_NGINX_VHOST:?set DEPLOY_NGINX_VHOST in deploy/config.env (the /etc/nginx/sites-available/<name> file)}"
STAGE_DIR="${DEPLOY_STAGE_DIR:-~/econetpy-deploy}"
ANCHOR="${DEPLOY_ANCHOR_APP:-SESPy}"   # insert after this app's block

cd "$SCRIPT_DIR"

# --- 1. Pull the live configs -------------------------------------------------
echo "==> Fetching live configs from ${SERVER}"
ssh "$SERVER" "cat /etc/shiny-server/shiny-server.conf" > shiny-server.conf.orig
ssh "$SERVER" "cat /etc/nginx/sites-available/${VHOST}"  > nid4ocean.orig

# --- 2. Insert the fragments --------------------------------------------------
python3 - "$ANCHOR" <<'PY'
import re, sys
from pathlib import Path

anchor_app = sys.argv[1]

def insert(live_path, out_path, fragment_path, anchor_re, label):
    live = Path(live_path).read_text(encoding="utf-8")
    frag = Path(fragment_path).read_text(encoding="utf-8")
    # Strip the fragment's leading explanatory comment block (up to the first
    # blank line following it); keep the block itself.
    frag = frag.split("\n\n", 1)[1] if "\n\n" in frag else frag
    frag = frag.rstrip("\n")

    if "/EconetPy" in live:
        print(f"    {label}: already contains /EconetPy — nothing to insert")
        Path(out_path).write_text(live, encoding="utf-8", newline="\n")
        return

    m = re.search(anchor_re, live)
    if not m:
        sys.exit(f"!! {label}: could not find the /{anchor_app} anchor block; "
                 "insert the fragment by hand and re-check the diff")
    out = live[:m.end()] + "\n\n" + frag + "\n" + live[m.end():]
    Path(out_path).write_text(out, encoding="utf-8", newline="\n")
    print(f"    {label}: inserted after /{anchor_app}")

# shiny-server.conf: after the anchor app's `location /X { ... }` block
insert("shiny-server.conf.orig", "shiny-server.conf", "econetpy.shiny-server.conf",
       rf"  location /{anchor_app} \{{\n(?:.*\n)*?  \}}\n", "shiny-server.conf")

# nginx: after the anchor app's `location = /X {{ return 301 ...; }}` redirect
insert("nid4ocean.orig", "nid4ocean", "econetpy.nginx.conf",
       rf"    location = /{anchor_app} \{{\n        return 301 /{anchor_app}/;\n    \}}\n", "nginx vhost")
PY

# --- 3. Prove the only change is the EconetPy addition ------------------------
echo "==> Diff vs live (should be ONLY the EconetPy block)"
diff -u shiny-server.conf.orig shiny-server.conf || true
diff -u nid4ocean.orig nid4ocean || true

echo "==> Brace balance (nginx)"
awk '{o+=gsub(/{/,"{"); c+=gsub(/}/,"}")} END{print "    open:",o," close:",c,(o==c?" BALANCED":" *** UNBALANCED — DO NOT DEPLOY ***")}' nid4ocean

# --- 4. Optionally stage on the server ----------------------------------------
if [ "${1:-}" = "--stage" ]; then
  echo "==> Staging to ${SERVER}:${STAGE_DIR}"
  ssh "$SERVER" "mkdir -p ${STAGE_DIR}"
  scp -q shiny-server.conf nid4ocean "$SERVER:${STAGE_DIR}/"
  echo "    staged — now run the sudo cp steps from DEPLOYMENT.md"
fi
