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
    "trophic_levels_table", "keystoneness_table",
}
FORBIDDEN = {"calculate_trophic_levels", "calculate_mti", "get_functional_group_colors"}


def _calls_in(node):
    names = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                names.add(n.func.id)
            elif isinstance(n.func, ast.Attribute):
                names.add(n.func.attr)
    return names


def test_analytical_renderers_use_caches_not_direct_compute():
    """Analytical renderers must go through the reactive caches, never recompute
    TL/MTI/colors directly (whether called as a bare name or via attribute
    access, e.g. `module.calculate_mti(...)`). The cache-definition functions
    are excluded. Every name in RENDERERS must actually be found as a
    function in app.py -- a renamed/removed renderer must not silently drop
    out of this guard's coverage."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    offenders = {}
    visited = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in RENDERERS:
            visited.add(node.name)
            bad = _calls_in(node) & FORBIDDEN
            if bad:
                offenders[node.name] = sorted(bad)
    assert visited == RENDERERS, f"renderers not found in app.py (renamed/removed?): {RENDERERS - visited}"
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
    """@safe_render must work BELOW @render.text (render wraps the safe
    wrapper). Actually invokes the stacked-decorated function's underlying
    callable -- not merely checks that decoration succeeds."""
    import asyncio
    from shiny import render
    app = importlib.import_module("app")

    @render.text
    @app.safe_render("text")
    def boom():
        raise RuntimeError("x")

    # boom is a shiny Renderer; its wrapped callable lives at .fn (an
    # AsyncValueFn). Invoking it must swallow the RuntimeError raised inside
    # the safe_render-wrapped body and return the uniform marker -- proving
    # the two decorators are stacked in the correct order.
    result = asyncio.run(boom.fn())
    assert "could not be computed" in result.lower()


def test_functional_groups_legend_has_safe_render_ui():
    """functional_groups_legend must be wrapped in @safe_render('ui') like every
    other panel renderer, so a bad functional-group value can't crash the
    whole dashboard instead of showing the uniform error element."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    node = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "functional_groups_legend"
    )
    safe_render_calls = [
        d for d in node.decorator_list
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "safe_render"
    ]
    assert safe_render_calls, "functional_groups_legend must carry @safe_render(...)"
    assert safe_render_calls[0].args[0].value == "ui"


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


def test_load_default_data_resaves_pickle_after_stale_fallthrough(tmp_path, monkeypatch):
    """After the pickle is found stale/misaligned and load_default_data falls
    through to reconstruction, it must re-save the rebuilt pickle to DATA_DIR
    so the next start uses the fast path instead of rebuilding every time."""
    import pickle as pkl
    import networkx as nx
    import pandas as pd
    app = importlib.import_module("app")
    monkeypatch.setattr(app, 'DATA_DIR', tmp_path)

    # A stale pickle: valid schema, but info/node order do not match.
    stale_g = nx.DiGraph(); stale_g.add_node('Cod'); stale_g.add_node('Sprat')
    stale_info = pd.DataFrame({'species': ['Sprat', 'Cod'], 'fg': ['Fish', 'Fish'],
                               'meanB': [1.0, 2.0], 'bodymasses': [1.0, 2.0],
                               'met.types': ['Other', 'Other'], 'efficiencies': [0.5, 0.5]})
    with open(tmp_path / "BalticFW.pkl", 'wb') as f:
        pkl.dump({'network': stale_g, 'info': stale_info}, f)

    rebuilt_g = nx.DiGraph(); rebuilt_g.add_node('Cod'); rebuilt_g.add_node('Sprat')
    rebuilt_info = pd.DataFrame({'species': ['Cod', 'Sprat'], 'fg': ['Fish', 'Fish'],
                                 'meanB': [1.0, 2.0], 'bodymasses': [1.0, 2.0],
                                 'met.types': ['Other', 'Other'], 'efficiencies': [0.5, 0.5]})
    monkeypatch.setattr('load_data.load_baltic_data',
                         lambda base_dir=None: (rebuilt_g, rebuilt_info))

    G, info = app.load_default_data()
    assert list(G.nodes()) == info['species'].tolist() == ['Cod', 'Sprat']

    with open(tmp_path / "BalticFW.pkl", 'rb') as f:
        resaved = pkl.load(f)
    assert list(resaved['network'].nodes()) == resaved['info']['species'].tolist() == ['Cod', 'Sprat']


def test_load_default_data_survives_a_corrupt_pickle(tmp_path, monkeypatch):
    """A truncated/corrupt BalticFW.pkl must fall through to reconstruction,
    not raise UnpicklingError out of load_default_data() (and hence out of
    `import app`)."""
    import networkx as nx
    import pandas as pd
    app = importlib.import_module("app")
    monkeypatch.setattr(app, 'DATA_DIR', tmp_path)
    (tmp_path / "BalticFW.pkl").write_bytes(b"\x80\x04garbage-not-a-pickle")

    rebuilt_g = nx.DiGraph(); rebuilt_g.add_node('Cod'); rebuilt_g.add_node('Sprat')
    rebuilt_info = pd.DataFrame({'species': ['Cod', 'Sprat'], 'fg': ['Fish', 'Fish'],
                                 'meanB': [1.0, 2.0], 'bodymasses': [1.0, 2.0],
                                 'met.types': ['Other', 'Other'], 'efficiencies': [0.5, 0.5]})
    monkeypatch.setattr('load_data.load_baltic_data',
                         lambda base_dir=None: (rebuilt_g, rebuilt_info))

    G, info = app.load_default_data()
    assert list(G.nodes()) == info['species'].tolist() == ['Cod', 'Sprat']


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


def test_adjacency_and_flux_heatmap_titles_state_correct_matrix_orientation():
    """A10: nx.to_numpy_array(G, nodelist=species)[i,j] is the edge species[i]->species[j],
    and edges run prey->predator (app.py:1107's own comment, app.py:139's own comment), so
    row i is prey and column j is predator. Both heatmap titles currently say the opposite,
    and neither sets an explicit xlabel/ylabel."""
    src = APP.read_text(encoding="utf-8")
    assert "Food Web Adjacency Matrix\\n(Rows = Prey, Columns = Predators)" in src
    assert "Energy Flux Matrix (log-transformed)\\n(Rows = Prey, Columns = Predators)" in src
    assert "(Rows = Predators, Columns = Prey)" not in src
    assert src.count('ax.set_xlabel("Predator")') == 2
    assert src.count('ax.set_ylabel("Prey")') == 2


def test_flux_effect_warns_on_unbalanced_equilibrium():
    """A11: validate_flux_equilibrium's verdict must reach the user - a
    logger.warning plus a warning notification when validation['balanced'] is
    False - not sit unused in flux_results()['validation']."""
    src = APP.read_text(encoding="utf-8")
    assert "if not validation['balanced']:" in src, \
        "flux effect never branches on the equilibrium verdict"
    branch = src.split("if not validation['balanced']:", 1)[1][:400]
    assert "logger.warning(" in branch
    assert 'type="warning"' in branch


def test_flux_indicators_panel_reports_balance_status():
    """The flux indicators text panel must show the equilibrium verdict, not
    just the lwC/lwG/lwV numbers."""
    src = APP.read_text(encoding="utf-8")
    assert "Equilibrium:" in src


def test_editor_apply_clears_flux_results_before_updating_info():
    """A12: flux_results must be cleared before current_species_info is updated, so a
    flux panel already rendered can't display a pre-edit flux matrix against
    post-edit species labels/order."""
    src = APP.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_apply_species_info_edits")
    body = ast.get_source_segment(src, fn)
    assert body is not None
    assert "flux_results.set(None)" in body, \
        "editor apply handler must clear flux_results"
    assert body.index("flux_results.set(None)") < body.index("current_species_info.set(df)"), \
        "flux_results must be cleared BEFORE current_species_info is updated"


def test_keystoneness_scatter_uses_computed_thresholds_not_hardcoded():
    """A13: draw the real Q3(KS)/Q1(biomass) cutoffs from calculate_keystoneness's
    df.attrs, not the hardcoded axhline(y=1)/axvline(x=0.05)."""
    src = APP.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "keystoneness_scatter")
    body = ast.get_source_segment(src, fn)
    assert "attrs['ks_hi']" in body or 'attrs["ks_hi"]' in body
    assert "attrs['bm_lo']" in body or 'attrs["bm_lo"]' in body
    assert "axhline(y=1," not in body
    assert "axvline(x=0.05," not in body


def test_keystoneness_summary_only_labels_true_keystone_species():
    """A13: 'Top Keystone Species' must come from a status=='Keystone' row, not
    just row 0 (which can be 'Dominant' - high impact but not low biomass)."""
    src = APP.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "keystoneness_summary")
    body = ast.get_source_segment(src, fn)
    assert "keystone_status'] == 'Keystone'" in body or 'keystone_status"] == "Keystone"' in body


def test_dev_dependencies_declared_in_manifests():
    """pytest and hypothesis (test_network_analysis.py uses @given/@settings
    from hypothesis at its top) must be declared in BOTH environment.yml and
    requirements.txt, or a fresh clone following either file cannot run the
    test suite it ships."""
    root = pathlib.Path(__file__).parent
    env_text = (root / "environment.yml").read_text(encoding="utf-8")
    req_text = (root / "requirements.txt").read_text(encoding="utf-8")
    for dep in ("pytest", "hypothesis"):
        assert dep in env_text, f"{dep} missing from environment.yml"
        assert dep in req_text, f"{dep} missing from requirements.txt"
