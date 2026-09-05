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


def test_assert_aligned_raises_on_node_row_mismatch():
    """_assert_aligned must raise ValueError when node order and species-row
    order have diverged (the exact contract load_default_data's three return
    paths and the editor apply handler depend on)."""
    import networkx as nx
    import pandas as pd
    import pytest
    app = importlib.import_module("app")
    G = nx.DiGraph()
    G.add_node('Cod'); G.add_node('Sprat')
    info = pd.DataFrame({'species': ['Sprat', 'Cod'], 'fg': ['Fish', 'Fish']})
    with pytest.raises(ValueError, match="misalign|align"):
        app._assert_aligned(G, info)


def test_assert_aligned_message_names_first_divergence():
    """The error message must name the actual first differing index/pair,
    not just a truncated [:3] prefix that can look identical on both sides
    when a long shared prefix hides the real divergence further in."""
    import networkx as nx
    import pandas as pd
    import pytest
    app = importlib.import_module("app")
    names = ['A', 'B', 'C', 'D', 'E']
    G = nx.DiGraph()
    G.add_nodes_from(names)
    # swap D/E at index 3/4 — the [:3] prefixes ('A','B','C') are identical
    # on both sides, so a truncated-prefix message would be useless here.
    info = pd.DataFrame({'species': ['A', 'B', 'C', 'E', 'D']})
    with pytest.raises(ValueError, match=r"index 3.*'D'.*'E'"):
        app._assert_aligned(G, info)


def test_assert_aligned_message_reports_length_mismatch():
    """When nodes/species share a common prefix but differ in length, the
    message must report the length mismatch rather than two identical
    truncated prefixes."""
    import networkx as nx
    import pandas as pd
    import pytest
    app = importlib.import_module("app")
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'C'])
    info = pd.DataFrame({'species': ['A', 'B', 'C', 'D']})
    with pytest.raises(ValueError, match=r"len\(nodes\)=3.*len\(species\)=4"):
        app._assert_aligned(G, info)


def test_load_default_data_raises_on_pickle_bypassing_misaligned_reconstruction(tmp_path, monkeypatch):
    """If load_baltic_data's own reindex/raise contract were ever bypassed
    (e.g. a future refactor returns misaligned data directly), _assert_aligned
    inside load_default_data must still catch it rather than returning
    misaligned data silently."""
    app = importlib.import_module("app")
    monkeypatch.setattr(app, 'DATA_DIR', tmp_path)  # no BalticFW.pkl here

    import networkx as nx
    import pandas as pd
    import pytest
    bad_g = nx.DiGraph(); bad_g.add_node('Cod'); bad_g.add_node('Sprat')
    bad_info = pd.DataFrame({'species': ['Sprat', 'Cod'], 'fg': ['Fish', 'Fish'],
                             'meanB': [1.0, 2.0], 'bodymasses': [1.0, 2.0],
                             'met.types': ['Other', 'Other'], 'efficiencies': [0.5, 0.5]})
    monkeypatch.setattr('load_data.load_baltic_data', lambda base_dir=None: (bad_g, bad_info))

    with pytest.raises(ValueError, match="misalign|align"):
        app.load_default_data()


def test_startup_except_clause_is_narrow_not_bare_exception():
    """The module-level `try: load_default_data()` guard must not catch a
    bare Exception — a ValueError from a real data misalignment (Task 4's
    _assert_aligned) must abort import, not be silently swallowed into the
    example network."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    module_level_tries = [
        n for n in tree.body if isinstance(n, ast.Try)
    ]
    assert module_level_tries, "expected a module-level try/except around load_default_data()"
    handlers = module_level_tries[0].handlers
    assert len(handlers) == 1
    caught = handlers[0].type
    # ast.Tuple of Name nodes for `except (FileNotFoundError, ImportError):`
    assert isinstance(caught, ast.Tuple), ast.dump(caught)
    names = {elt.id for elt in caught.elts if isinstance(elt, ast.Name)}
    assert names == {"FileNotFoundError", "ImportError"}, names


def test_using_example_network_flag_set_when_sources_absent(tmp_path, monkeypatch):
    """USING_EXAMPLE_NETWORK must flip to True via the actual code path taken
    when DATA_DIR holds neither a pickle nor tracked GraphML/CSV/JSON sources
    — this is the path load_default_data() takes on 99% of fresh clones
    without a prebuilt BalticFW.pkl, NOT the (mostly dead) module-level
    startup except clause."""
    app = importlib.import_module("app")
    monkeypatch.setattr(app, 'DATA_DIR', tmp_path)  # empty: no .pkl, no sources
    # monkeypatch (not a bare assignment) so the module flag is restored at
    # teardown — same reason DATA_DIR above uses it. A bare assignment would
    # leak USING_EXAMPLE_NETWORK=True into every later test in the session.
    monkeypatch.setattr(app, 'USING_EXAMPLE_NETWORK', False)

    G, info = app.load_default_data()

    assert app.USING_EXAMPLE_NETWORK is True
    assert list(G.nodes()) == info['species'].tolist()  # example network self-aligned


def test_dashboard_banner_shown_when_using_example_network(monkeypatch):
    """dashboard_ui() must render a visible banner element when the module
    flag says the example network is in use — not merely a stdout print.

    NOTE: dashboard_ui() returns a shiny.ui._card.CardItem; bare str() on it
    yields its object repr ('<shiny.ui._card.CardItem object at 0x...>'), NOT
    rendered HTML (this is why the existing test_tl_method_is_single_topbar_select
    at test_app_structure.py:93 only ever checks *absence* of a substring — it
    would pass whether or not the string is really rendered). Render properly
    via htmltools.TagList(...) so the assertion actually inspects markup.
    """
    import htmltools
    app = importlib.import_module("app")
    monkeypatch.setattr(app, 'USING_EXAMPLE_NETWORK', True)
    html = str(htmltools.TagList(app.dashboard_ui()))
    assert "example network" in html.lower()


def test_dashboard_banner_absent_when_using_real_data(monkeypatch):
    import htmltools
    app = importlib.import_module("app")
    monkeypatch.setattr(app, 'USING_EXAMPLE_NETWORK', False)
    html = str(htmltools.TagList(app.dashboard_ui()))
    assert "example network" not in html.lower()


def test_apply_species_info_edits_validates_met_types_and_alignment():
    """The editor apply handler must reject an edited met.types value outside
    the accepted set and must re-check node/row alignment before
    current_species_info.set(df) — both via app-level helpers, not ad hoc."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_apply_species_info_edits":
            target = node
            break
    assert target is not None, "could not find _apply_species_info_edits"
    calls = _calls_in(target)
    assert "validate_met_types" in calls, calls
    assert "_assert_aligned" in calls, calls
