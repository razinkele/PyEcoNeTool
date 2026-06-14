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
