"""Post-deployment smoke against a DEPLOYED EconetPy instance.

Distinct from test_live_smoke.py, which spawns its own local app to test app
behaviour. This one points at a real URL and proves the things only a
deployment can break — the reverse proxy, the served static assets, and the
server env's pyvis actually rendering — so a deploy can be verified in one
command:

    ECONETOOL_DEPLOY_URL=https://laguna.ku.lt/EconetPy/ \
        pytest test_live_deploy.py -q

Skipped unless that variable is set, so the normal suite stays browser-free.
"""
import os

import pytest

pytest.importorskip("playwright")

DEPLOY_URL = os.environ.get("ECONETOOL_DEPLOY_URL")
if not DEPLOY_URL:
    pytest.skip(
        "live deploy smoke: set ECONETOOL_DEPLOY_URL to the deployed app URL",
        allow_module_level=True,
    )

from playwright.sync_api import sync_playwright  # noqa: E402

# Shiny's first paint behind a proxy is dominated by the server cold-starting a
# worker; be generous rather than flaky on a loaded box.
LOAD_WAIT_MS = int(os.environ.get("ECONETOOL_DEPLOY_LOAD_MS", "12000"))
RENDER_WAIT_MS = int(os.environ.get("ECONETOOL_DEPLOY_RENDER_MS", "15000"))


@pytest.fixture(scope="module")
def live_page():
    """One browser session against the deployed app, shared by the checks.

    Counts WebSocket frames as they arrive: the handshake succeeding is not
    enough, the proxy must also carry server->client traffic.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        frames = {"n": 0}
        page.on("websocket", lambda ws: ws.on(
            "framereceived", lambda _: frames.__setitem__("n", frames["n"] + 1)))
        page.goto(DEPLOY_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(LOAD_WAIT_MS)
        yield page, frames
        browser.close()


def test_deployed_app_serves_the_shiny_page(live_page):
    page, _ = live_page
    assert "EcoNeTool" in page.title()


def test_shiny_websocket_carries_traffic_through_the_proxy(live_page):
    """The nginx block needs the Upgrade/Connection headers and
    `proxy_buffering off`; without them the page still renders but the session
    never exchanges frames, which is the classic silent proxy misconfiguration.
    """
    page, frames = live_page
    assert frames["n"] > 0, "no WebSocket frames — Shiny did not connect through the proxy"
    assert page.locator("#shiny-disconnected-overlay").count() == 0, "session dropped"


def test_server_rendered_outputs_arrive(live_page):
    page, _ = live_page
    populated = page.evaluate(
        "[...document.querySelectorAll('.shiny-bound-output')]"
        ".filter(e => e.textContent.trim() || e.querySelector('img,svg,iframe,table')).length"
    )
    assert populated > 0, "no shiny output was populated — the server rendered nothing"


def test_pyvis_network_renders_on_the_deployed_env(live_page):
    """Guards the server env's pyvis specifically: the app can import and serve
    fine while the pinned fork is missing or wrong, and the canvas stays empty.
    """
    page, _ = live_page
    # NB: get_by_text would match the <title> ("... Food Web Network Analysis"),
    # so the nav link needs a role-based selector.
    page.get_by_role("link", name="Food Web Network", exact=True).first.click(timeout=15_000)
    page.wait_for_timeout(RENDER_WAIT_MS)

    sized = []
    for frame in (f for f in page.frames if f != page.main_frame):
        try:
            if frame.locator("canvas").count():
                box = frame.locator("canvas").first.bounding_box()
                if box:
                    sized.append((box["width"], box["height"]))
        except Exception:  # frame detached mid-navigation
            continue
    assert any(w > 100 and h > 100 for w, h in sized), (
        f"pyvis canvas did not render in any iframe; canvas boxes seen: {sized}"
    )
