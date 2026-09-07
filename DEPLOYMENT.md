# EconetPy Deployment — laguna.ku.lt

EconetPy is deployed as a **Python Shiny app under Shiny Server**, the same way
`SESPy` is (`Marine-SABRES/SESPy/deploy/`). It is *not* a standalone systemd
service on its own port — the previous `deploy.sh` / `econetool.service` /
`/srv/shiny-apps` / `~/miniconda3` arrangement never existed on laguna and has
been removed.

| | |
|---|---|
| **Public URL** | `https://laguna.ku.lt/EconetPy/` |
| **App dir** | `/srv/shiny-server/EconetPy` |
| **Interpreter** | `/opt/micromamba/envs/shiny/bin/python3` (shared env) |
| **Served by** | Shiny Server on `127.0.0.1:3838`, reverse-proxied by nginx |
| **Reload** | `touch restart.txt` (no sudo, no service restart) |

> **`/EcoNeTool` is a different app.** The R implementation lives at
> `/srv/shiny-server/EcoNeTool` and stays live and untouched. EconetPy is the
> Python port and is deployed alongside it at `/EconetPy`.

## Routine deployment

```bash
deploy/deploy.sh
```

No sudo. The script stages a clean copy of the runtime files, preserves the
server-owned `data/user_feedback_log.ndjson`, scps the tree, rebuilds
`BalticFW.pkl`, runs an import smoke under the server's interpreter, and only
then touches `restart.txt`. Host and path come from the gitignored
`deploy/config.env` (copy `deploy/config.env.example`).

---

## First-time server setup

Run these once, in order. Steps 1–2 need sudo; step 3 does not; steps 4–5 need
sudo. **The app is proven working on port 3838 before nginx exposes it.**

### 1. Install the pyvis fork into the shared env

The pinned version is **`pyvis-optimized` v4.4.0** (see `requirements.txt`).
The distribution was renamed `pyvis` -> `pyvis-optimized` at v4.3.1; the import
name is still `pyvis`. If the old `pyvis` dist is present it must be removed
first, or two distributions own the same import package.

```bash
ssh razinka@laguna.ku.lt

# What is there now
/opt/micromamba/envs/shiny/bin/pip list 2>/dev/null | grep -i pyvis

# Only if a dist named plain `pyvis` is listed (pre-4.3.1 installs):
sudo /opt/micromamba/envs/shiny/bin/pip uninstall -y pyvis

# site-packages is root:micromamba, so install as root
sudo env PIP_NO_CACHE_DIR=1 /opt/micromamba/envs/shiny/bin/pip install "pyvis-optimized @ git+https://github.com/razinkele/pyvis.git@v4.4.0"

# Verify: expect 4.4.0, and exactly one pyvis distribution
/opt/micromamba/envs/shiny/bin/python3 -c "import pyvis; print(pyvis.__version__)"
/opt/micromamba/envs/shiny/bin/pip list 2>/dev/null | grep -i pyvis
```

> **Shared-env warning.** `/opt/micromamba/envs/shiny` backs every Python Shiny
> app on laguna and holds ONE version, so this pin is a cross-project decision.
> **Seven apps import pyvis**: BowTie, EconetPy, EVA, MosaicSES, NiDSES, osmose,
> SESPy. (`AQUABC` is *not* one — its "pyvis" matches are vis.js and an error
> string.) Smoke the consumers after this step:
>
> ```bash
> for a in BowTie EconetPy EVA MosaicSES NiDSES osmose SESPy; do
>   printf '%-12s %s
' "$a" "$(curl -s -o /dev/null -w '%{http_code}' https://laguna.ku.lt/$a/)"
> done
> ```
>
> Roll back with (the uninstall matters — otherwise two distributions own the
> same `pyvis` import package):
>
> ```bash
> sudo /opt/micromamba/envs/shiny/bin/pip uninstall -y pyvis-optimized
> sudo env PIP_NO_CACHE_DIR=1 /opt/micromamba/envs/shiny/bin/pip install "pyvis-optimized @ git+https://github.com/razinkele/pyvis.git@v4.3.1"
> ```
>
> Do **not** `pip install -r requirements.txt` on the server — it would drag
> pytest / hypothesis / playwright onto a production env. Every other
> dependency is already present at an equal or newer version.

### 2. Create the app directory

`/srv/shiny-server` is `root:root`, so razinka cannot create the dir. Mode
`2775` (setgid, group `shiny`) is the house convention here — it lets the
`shiny` user write the feedback log and the pickle cache while razinka deploys.

```bash
sudo mkdir -p /srv/shiny-server/EconetPy
sudo chown razinka:shiny /srv/shiny-server/EconetPy
sudo chmod 2775 /srv/shiny-server/EconetPy
```

### 3. Deploy the code (no sudo — run on your laptop)

```bash
deploy/deploy.sh
```

Do not continue until this prints `import OK` and `Done.`

> **Deploying from a fresh clone?** `deploy/config.env` is gitignored, so it
> will not exist. Create it first:
> `cp deploy/config.env.example deploy/config.env` and fill in the host/path.

### 4. Register the app with Shiny Server

First render the configs from the CURRENT live copies and stage them (this
also prints the diff, so you can see exactly what you are about to change):

```bash
deploy/server/render-configs.sh --stage
```

Then, on the server:

```bash
ssh razinka@laguna.ku.lt

sudo cp /etc/shiny-server/shiny-server.conf \
        /etc/shiny-server/shiny-server.conf.bak.$(date +%Y%m%d)
sudo cp ~/econetpy-deploy/shiny-server.conf /etc/shiny-server/shiny-server.conf
sudo chown root:root /etc/shiny-server/shiny-server.conf
sudo chmod 644 /etc/shiny-server/shiny-server.conf

# reload, NOT restart — restart kills every running session on the box
sudo systemctl reload shiny-server

# Prove the app answers on 3838 before exposing it publicly
curl -sI http://127.0.0.1:3838/EconetPy/ | head -1     # expect HTTP/1.1 200 OK
```

If that is not a 200: `sudo tail -50 /var/log/shiny-server/EconetPy-*.log`

### 5. Expose it through nginx

Already staged by `render-configs.sh --stage` in step 4.

```bash
ssh razinka@laguna.ku.lt

sudo cp /etc/nginx/sites-available/nid4ocean \
        /etc/nginx/sites-available/nid4ocean.bak.$(date +%Y%m%d)
sudo cp ~/econetpy-deploy/nid4ocean /etc/nginx/sites-available/nid4ocean
sudo chown root:root /etc/nginx/sites-available/nid4ocean
sudo chmod 644 /etc/nginx/sites-available/nid4ocean

sudo nginx -t          # must say "syntax is ok" / "test is successful"
sudo systemctl reload nginx
```

`sites-enabled/nid4ocean` is already a symlink to `sites-available/nid4ocean`,
so no re-linking is needed.

Then open **https://laguna.ku.lt/EconetPy/**.

---

## How the server configs are managed

**This repo is public, so the server's own configs are never committed.** The
site vhost maps every service, internal port, admin path and auth file on the
host — that is an attack-surface map and belongs on the host only.

What *is* tracked is the two EconetPy-specific fragments:

* **`deploy/server/econetpy.shiny-server.conf`** — a `location /EconetPy`
  block with the `python` directive (Python apps require it; R apps must not
  have it).
* **`deploy/server/econetpy.nginx.conf`** — a `location /EconetPy/` proxy
  block to `127.0.0.1:3838` with the WebSocket upgrade headers Shiny needs and
  `proxy_buffering off`, plus the `location = /EconetPy` → `/EconetPy/` 301,
  matching every other Shiny app in the vhost.

`deploy/server/render-configs.sh` pulls the **current** live configs down,
inserts those fragments after the anchor app's block, and writes the full
files locally as gitignored artifacts (`shiny-server.conf`, `nid4ocean`, plus
`.orig` copies). It then diffs them against live and checks nginx brace
balance, so you can confirm the only change is the EconetPy addition before
anything is copied with sudo:

```bash
deploy/server/render-configs.sh          # render + show diffs
deploy/server/render-configs.sh --stage  # also scp them to the server
```

Rendering from live each time also means a config someone else changed in the
meantime is picked up, instead of being silently reverted by a stale copy.

## Verifying a deployment

After any deploy, check the deployed instance end to end — this exercises the
reverse proxy, the served assets and the server env's pyvis, none of which the
offline suite can reach:

```bash
ECONETOOL_DEPLOY_URL=https://laguna.ku.lt/EconetPy/     pytest test_live_deploy.py -q
```

Four checks: the Shiny page is served; the WebSocket carries frames through
nginx (a proxy missing the `Upgrade`/`Connection` headers or `proxy_buffering
off` still serves HTML but exchanges nothing); server-rendered outputs arrive;
and the pyvis canvas actually draws. It skips unless that variable is set, so
it never runs in the normal suite.

## Troubleshooting

```bash
# App logs (one file per worker process)
ssh razinka@laguna.ku.lt 'sudo ls -lt /var/log/shiny-server/ | grep EconetPy | head'
ssh razinka@laguna.ku.lt 'sudo tail -100 /var/log/shiny-server/EconetPy-*.log'

# Force a worker reload without redeploying
ssh razinka@laguna.ku.lt 'touch /srv/shiny-server/EconetPy/restart.txt'

# Reproduce an import failure the way the server sees it
ssh razinka@laguna.ku.lt 'cd /srv/shiny-server/EconetPy && \
  /opt/micromamba/envs/shiny/bin/python3 -c "import app"'
```

**Version skew (shared env vs. local dev) — checked, currently clean.**
`pyvis-optimized` is aligned at **4.4.0** on both the server and locally, and
`deploy.sh` now warns on every deploy if that drifts from the pin. The rest
still differs: the server runs `pandas 3.0.3` / `numpy 2.3.5` /
`shinyswatch 0.11.0`; local dev is on `pandas 2.3.3` / `numpy 2.4.3` /
`shinyswatch 0.9.0`. pandas 3.0 changes
copy-on-write and string-dtype defaults, so this was verified rather than
assumed: the core suite was run against the server interpreter on 2026-09-06
and passed **89/89** (`test_network_analysis.py` excluded — it needs
`hypothesis`, deliberately not installed on the production env).

Reproduce that check after any pandas- or numpy-touching change:

```bash
ssh razinka@laguna.ku.lt 'rm -rf ~/econetpy-testcheck && mkdir ~/econetpy-testcheck'
scp app.py network_analysis.py network_viz.py flux_calculations.py     load_data.py feedback_reporter.py conftest.py test_*.py BalticFW_*     VERSION environment.yml requirements.txt     razinka@laguna.ku.lt:~/econetpy-testcheck/
scp -r examples www razinka@laguna.ku.lt:~/econetpy-testcheck/
ssh razinka@laguna.ku.lt 'cd ~/econetpy-testcheck &&   /opt/micromamba/envs/shiny/bin/python3 -m pytest -q --ignore=test_network_analysis.py'
ssh razinka@laguna.ku.lt 'rm -rf ~/econetpy-testcheck'
```

The import smoke and the `load_data.py` rebuild in `deploy.sh` are the
per-deploy gate for the same class of problem.

**The feedback log is server-owned.** `data/user_feedback_log.ndjson` on the
server is production data. `deploy.sh` never ships the local copy and stashes
the server's aside across the file transfer. If you ever wipe the app dir by
hand, back that file up first.
