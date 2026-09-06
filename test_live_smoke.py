"""Post-Phase-6 live smoke. Skipped unless ECONETOOL_LIVE_SMOKE=1 so the normal
suite (and every phase gate) stays browser-free and warning-clean."""
import os
import re

import pytest

pytest.importorskip("playwright")
pytest.importorskip("shiny.playwright")

if os.environ.get("ECONETOOL_LIVE_SMOKE") != "1":
    pytest.skip("live smoke: set ECONETOOL_LIVE_SMOKE=1 to run", allow_module_level=True)

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.pytest import create_app_fixture
from shiny.run import ShinyAppProc

# Cold start is dominated by third-party imports (seaborn, shinyswatch, matplotlib,
# pyvis), which on a loaded machine — OneDrive sync, a CI runner, a busy laptop —
# can take well over a minute between them even though the app itself is fine.
# 60s proved too tight in exactly that situation, so default generously and let a
# slower or faster environment override it rather than editing this file.
APP_READY_TIMEOUT_SECS = float(os.environ.get("ECONETOOL_APP_READY_TIMEOUT", "300"))

app = create_app_fixture("app.py", timeout_secs=APP_READY_TIMEOUT_SECS)

# species_info column order is species, fg, meanB, bodymasses, met.types, efficiencies
COL_SPECIES = 0
COL_MEANB = 2


def _open_editor(page: Page, app: ShinyAppProc) -> controller.OutputDataFrame:
    page.goto(app.url)
    page.get_by_text("Data Editor").first.click()
    grid = controller.OutputDataFrame(page, "species_info_editor")
    # Wait for the grid to actually paint before touching cells; the row count is
    # data-dependent (Baltic vs example network), so wait on the first cell.
    expect(grid.cell_locator(row=0, col=COL_SPECIES)).to_be_visible(timeout=30_000)
    return grid


def test_live_species_info_edit_round_trips_through_data_patched(page: Page, app: ShinyAppProc):
    """(a) An edit made in the DataGrid must reach current_species_info via
    data_patched(), and an edit to a key column must be reverted by set_patch_fn."""
    grid = _open_editor(page, app)

    original = grid.cell_locator(row=0, col=COL_MEANB).inner_text().strip()
    new_value = "12345.0"
    assert original != new_value

    grid.set_cell(new_value, row=0, col=COL_MEANB, finish_key="Enter")
    page.get_by_role("button", name="Update Species Info").click()
    expect(page.get_by_text("Species info updated.")).to_be_visible(timeout=15_000)

    # The grid re-renders from current_species_info(); the value survives only if
    # data_patched() -> current_species_info.set(df) actually happened.
    grid.expect_cell(re.compile(r"12345"), row=0, col=COL_MEANB, timeout=15_000)

    # set_patch_fn must refuse an edit to a key column: the cell reverts.
    species_before = grid.cell_locator(row=0, col=COL_SPECIES).inner_text().strip()
    grid.set_cell("NOT_A_SPECIES", row=0, col=COL_SPECIES, finish_key="Enter")
    grid.expect_cell(species_before, row=0, col=COL_SPECIES, timeout=15_000)


def test_live_safe_render_shows_clean_panel_not_traceback(page: Page, app: ShinyAppProc):
    """(b) A renderer that raises must surface app._ERROR_MSG, not a traceback."""
    page.goto(app.url)
    page.get_by_text("Topological Metrics").first.click()
    panel = page.locator("#topological_indicators")
    expect(panel).to_contain_text("could not be computed", timeout=30_000)
    assert "Traceback" not in panel.inner_text()
    assert "ECONETOOL_FORCE_RENDER_ERROR" not in panel.inner_text()


def test_live_downloaded_network_html_is_self_contained(page: Page, app: ShinyAppProc, tmp_path):
    """(c) The downloaded network HTML must inline its assets — no src="lib/."""
    page.goto(app.url)
    # NOTE: get_by_text("Food Web Network") also matches the document <title>
    # ("EcoNeTool - Food Web Network Analysis", app.py's ui.page_navbar title=),
    # which is a substring hit in the DOM but never visible, so .first can resolve
    # to the (invisible) <title> element instead of the sidebar menu link and time
    # out waiting for it to become clickable. Target the menu item by its id
    # instead (app.py: ui.input_action_link("menu_network", ...)).
    page.locator("#menu_network_div").click()
    # NOTE: ui.download_button renders an <a class="btn ... shiny-download-link">,
    # NOT a <button> — its ARIA role is "link", so get_by_role("button", ...) does
    # not match. Locate it by id (verified against `ui.download_button(...)` output).
    with page.expect_download(timeout=60_000) as dl_info:
        page.locator("#download_network").click()
    target = tmp_path / "network.html"
    dl_info.value.save_as(target)

    html = target.read_text(encoding="utf-8", errors="replace")
    assert 'src="lib/' not in html, 'downloaded HTML still references local lib/ assets'
    assert 'href="lib/' not in html, 'downloaded HTML still references local lib/ assets'
    assert "vis-network" in html, "downloaded HTML does not appear to embed the vis-network bundle"
    # Size floor verified empirically on this pyvis fork with a 3-node network:
    # cdn_resources="local" -> ~7.2 KB, cdn_resources="in_line" -> ~660 KB.
    assert len(html) > 200_000, f"downloaded HTML is only {len(html)} bytes — assets not inlined"
