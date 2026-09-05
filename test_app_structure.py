"""Structural guards on app.py (no runtime Shiny needed)."""
import ast
import pathlib
import importlib
import logging
import matplotlib
matplotlib.use("Agg")

APP = pathlib.Path(__file__).parent / "app.py"
RENDERERS = {
    "topological_indicators", "trophic_level_histogram", "node_weighted_indicators",
    "biomass_by_group", "biomass_distribution", "flux_indicators", "flux_heatmap",
    "flux_network_plot", "keystoneness_summary", "keystoneness_scatter",
    "mti_heatmap", "network_plot", "adjacency_heatmap",
}
FORBIDDEN = {"calculate_trophic_levels", "calculate_mti", "get_functional_group_colors"}


def _calls_in(node):
    return {n.func.id for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def test_analytical_renderers_use_caches_not_direct_compute():
    """Analytical renderers must go through the reactive caches, never recompute
    TL/MTI/colors directly. The cache-definition functions are excluded."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    offenders = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in RENDERERS:
            bad = _calls_in(node) & FORBIDDEN
            if bad:
                offenders[node.name] = sorted(bad)
    assert not offenders, f"renderers recompute cached values directly: {offenders}"


def test_safe_render_text_returns_marker_and_logs(caplog):
    app = importlib.import_module("app")
    @app.safe_render("text")
    def boom():
        raise RuntimeError("x")
    with caplog.at_level(logging.ERROR):
        out = boom()
    assert isinstance(out, str) and "could not be computed" in out.lower()
    assert any("boom" in r.getMessage() or "failed" in r.getMessage().lower()
               for r in caplog.records)


def test_safe_render_plot_returns_figure_with_marker():
    app = importlib.import_module("app")
    from matplotlib.figure import Figure
    @app.safe_render("plot")
    def boom():
        raise RuntimeError("x")
    fig = boom()
    assert isinstance(fig, Figure)
    texts = " ".join(t.get_text().lower() for ax in fig.axes for t in ax.texts)
    assert "could not be computed" in texts


def test_safe_render_ui_returns_tag_with_marker():
    app = importlib.import_module("app")
    out = app._error_element("ui")
    # ui elements stringify to HTML carrying the message
    assert "could not be computed" in str(out).lower()


def test_safe_render_passthrough_on_success():
    app = importlib.import_module("app")
    @app.safe_render("text")
    def ok():
        return "real value"
    assert ok() == "real value"


def test_safe_render_below_render_text_order():
    """@safe_render must work BELOW @render.text (render wraps the safe wrapper)."""
    from shiny import render
    app = importlib.import_module("app")
    @render.text
    @app.safe_render("text")
    def boom():
        raise RuntimeError("x")
    # Stacking @render.text above @safe_render must not raise at decoration time.
    # Invoking the safe-wrapped raw function directly must swallow the error and
    # return the uniform marker rather than propagating the RuntimeError.
    @app.safe_render("text")
    def raw_boom():
        raise RuntimeError("x")
    assert "could not be computed" in raw_boom().lower()


def test_tl_method_is_single_topbar_select():
    """The trophic-level method control lives once, in the persistent top bar,
    as a <select> dropdown — not in the dashboard sidebar, and not duplicated."""
    import re
    app = importlib.import_module("app")
    shell = str(app.app_ui)
    # Exactly one tl_method input, in the always-rendered app shell.
    assert shell.count('id="tl_method"') == 1, shell.count('id="tl_method"')
    # It is a dropdown (<select>), not radio buttons.
    assert re.search(r'<select[^>]*id="tl_method"', shell), "tl_method must be a <select>"
    # It is NOT left behind in the dashboard sidebar.
    assert 'id="tl_method"' not in str(app.dashboard_ui()), "tl_method still in dashboard sidebar"


def test_editor_uses_data_patched_not_data_view():
    """The species-info update must read data_patched() (original node order +
    edits), not data_view() (display/sorted order) which permutes rows."""
    src = APP.read_text(encoding="utf-8")
    assert ".data_patched()" in src, "editor must use data_patched()"
    assert "species_info_editor.data_view()" not in src, "data_view() reorders rows"


def test_editor_registers_a_patch_fn():
    """species/fg columns must be protected from edits via a registered patch fn
    (editable_columns= does not exist on render.DataGrid in this Shiny version)."""
    src = APP.read_text(encoding="utf-8")
    assert "set_patch_fn" in src, "editor must register a patch fn to protect key columns"


def test_flux_effect_guards_temperature_and_bodymasses():
    """The flux effect must req()-guard against a cleared temperature input and
    against non-finite/non-positive bodymasses before calling calculate_losses,
    instead of letting a TypeError/inf-NaN escape into calculate_losses."""
    src = APP.read_text(encoding="utf-8")
    assert "req(temp is not None)" in src, "missing req() guard on temperature"
    assert "req(np.all(np.isfinite(bodymasses)) and np.all(bodymasses > 0))" in src, \
        "missing req() guard on bodymasses finiteness/positivity"


def test_logging_configured():
    src = APP.read_text(encoding="utf-8")
    assert "logging.basicConfig(" in src
    assert "ECONETPY_LOG_LEVEL" in src


EXPECTED_PAGES = {
    "dashboard": ("menu_dashboard", "dashboard_ui"),
    "network": ("menu_network", "network_ui"),
    "topology": ("menu_topology", "topology_ui"),
    "biomass": ("menu_biomass", "biomass_ui"),
    "fluxes": ("menu_fluxes", "fluxes_ui"),
    "keystoneness": ("menu_keystoneness", "keystoneness_ui"),
    "editor": ("menu_editor", "editor_ui"),
}


def test_pages_registry_maps_keys_to_menu_ids_and_builders():
    """A single ordered PAGES registry (module-level) must map each of the 7
    navigable page keys to its (menu_input_id, ui_builder) pair, replacing the
    old duplicated per-page menu effects and if/elif dispatch chain."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    pages_assign = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PAGES" for t in node.targets
        ):
            pages_assign = node
            break
    assert pages_assign is not None, "no module-level PAGES = {...} assignment found"
    assert isinstance(pages_assign.value, ast.Dict), "PAGES must be a dict literal"

    found = {}
    for key_node, val_node in zip(pages_assign.value.keys, pages_assign.value.values):
        assert isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)
        assert isinstance(val_node, ast.Tuple) and len(val_node.elts) == 2
        menu_node, builder_node = val_node.elts
        assert isinstance(menu_node, ast.Constant) and isinstance(menu_node.value, str)
        assert isinstance(builder_node, ast.Name)
        found[key_node.value] = (menu_node.value, builder_node.id)

    assert found == EXPECTED_PAGES

    app = importlib.import_module("app")
    assert app.PAGES.keys() == EXPECTED_PAGES.keys()
    for key, (menu_id, builder_name) in EXPECTED_PAGES.items():
        registered_menu_id, builder = app.PAGES[key]
        assert registered_menu_id == menu_id
        assert builder is getattr(app, builder_name)

    # named module attributes preserved (a downstream test calls app.dashboard_ui())
    assert app.dashboard_ui() is not None
