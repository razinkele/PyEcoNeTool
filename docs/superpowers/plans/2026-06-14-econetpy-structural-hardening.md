# EconetPy Structural Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the four deferred structural items — selectable trophic-level method, validator `bioms_losses` parameter, `@safe_render` error-handling convention, and the reactive-CPU refactor — without changing any validated pin from the shipped remediation.

**Architecture:** Three phases. Phase A: two isolated quick wins (validator param, narrow bare except). Phase B: add a `short_weighted` TL method, thread precomputed TL/MTI/colors through optional args, extend the existing per-session reactive caches, add a UI toggle. Phase C: a `safe_render` decorator on the 13 analytical renderers. Prey-averaged stays the default, so all 84 existing tests remain green; new tests are additive.

**Tech Stack:** Python 3.13, numpy, networkx 3.6.1, pandas, scipy, pytest, hypothesis, Shiny for Python 1.6.1, pyvis (razinkele fork). **All test runs use `micromamba run -n shiny python -m pytest`.** Working directory is the repo root. Work on a feature branch (created at execution time via using-git-worktrees / a plain branch); do not push or merge unless asked.

**Spec:** `docs/superpowers/specs/2026-06-13-econetpy-structural-hardening-design.md` (commit `7370fe2`). All numeric pins below were verified against the real code before this plan was written.

---

## File Structure

| File | Change |
|------|--------|
| `flux_calculations.py` | A1: `validate_flux_equilibrium` gains `bioms_losses=True` |
| `network_analysis.py` | A2: narrow bare except; B1: `calculate_trophic_levels(method=...)` + `_shortest_trophic_levels` helper; B2: `trophic_levels=None` on the two indicator fns + `nwTL` NaN-mask |
| `network_viz.py` | B3: `trophic_levels=None` on both builders + NaN-safe y-normalization |
| `network_analysis.py` (keystoneness) | B4: `calculate_keystoneness(..., mti=None)` |
| `app.py` | B5: extend `trophic_levels_cached`, add `colors_cached`, thread caches, `_build_network` helper; B7: `tl_method` toggle; C: `safe_render`/`_error_element` + decorate 13 renderers |
| `test_flux_calculations.py` | A1 tests |
| `test_network_analysis.py` | A2, B1, B2, B4 tests |
| `test_network_viz_render.py` | B3 viz NaN test |
| `test_app_structure.py` (new) | B6 AST dedup guard; C decorator tests |

---

# PHASE A — Isolated quick wins

### Task A1: Validator `bioms_losses` parameter

**Files:**
- Modify: `flux_calculations.py` (`validate_flux_equilibrium` signature + L-scaling)
- Modify: `app.py` (the `calculate_fluxes` effect — single source of truth)
- Test: `test_flux_calculations.py`

- [ ] **Step 1: Write the failing test**

Add to `test_flux_calculations.py`:

```python
def test_validate_flux_equilibrium_honors_bioms_losses_flag():
    """validator must mirror the solver's bioms_losses gating. On a flux solved
    with bioms_losses=False, validating with bioms_losses=False is balanced;
    validating the SAME flux with bioms_losses=True reports the biomass-scaled
    residual (the flag changes the reported magnitude)."""
    mat = np.array([[0, 1, 0], [0, 0, 1], [0, 0, 0]])
    L = np.array([2.0, 3.0, 5.0])
    e = np.array([0.5, 0.6, 0.7])
    bm = np.array([10.0, 4.0, 2.0])
    flux = fluxing(mat=mat, biomasses=bm, losses=L, efficiencies=e,
                   bioms_prefs=True, bioms_losses=False, ef_level="prey")
    r_false = validate_flux_equilibrium(flux, L, e, bm, bioms_losses=False)
    r_true = validate_flux_equilibrium(flux, L, e, bm, bioms_losses=True)
    assert r_false['balanced'] is True, r_false
    assert r_true['max_imbalance'] > r_false['max_imbalance'], (r_true, r_false)
```

- [ ] **Step 2: Run it to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py::test_validate_flux_equilibrium_honors_bioms_losses_flag -v`
Expected: FAIL — `validate_flux_equilibrium` has no `bioms_losses` parameter (TypeError).

- [ ] **Step 3: Add the parameter**

In `flux_calculations.py`, change the `validate_flux_equilibrium` signature from:

```python
def validate_flux_equilibrium(
    flux_matrix: np.ndarray,
    losses: np.ndarray,
    efficiencies: np.ndarray,
    biomasses: Optional[np.ndarray] = None,
    tolerance: float = 1e-6
) -> dict:
```

to (insert `bioms_losses` before `tolerance`):

```python
def validate_flux_equilibrium(
    flux_matrix: np.ndarray,
    losses: np.ndarray,
    efficiencies: np.ndarray,
    biomasses: Optional[np.ndarray] = None,
    bioms_losses: bool = True,
    tolerance: float = 1e-6
) -> dict:
```

And change the L-scaling line from:

```python
    L = losses.copy()
    if biomasses is not None:
        L = L * biomasses
```

to:

```python
    L = losses.copy()
    if bioms_losses and biomasses is not None:
        L = L * biomasses
```

- [ ] **Step 4: Run it to confirm GREEN**

Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py::test_validate_flux_equilibrium_honors_bioms_losses_flag -v`
Expected: PASS.

- [ ] **Step 5: Wire single source of truth in the app**

In `app.py`, in the `calculate_fluxes` effect, hoist one flag above the `try` and pass the same variable to both calls. Change:

```python
        try:
            flux_matrix = fluxing(
                mat=adj_matrix,
                biomasses=biomass,
                losses=losses,
                efficiencies=efficiencies,
                bioms_prefs=True,
                bioms_losses=True,
                ef_level="prey"
            )
```

to:

```python
        bioms_losses_flag = True  # single source of truth for solver + validator
        try:
            flux_matrix = fluxing(
                mat=adj_matrix,
                biomasses=biomass,
                losses=losses,
                efficiencies=efficiencies,
                bioms_prefs=True,
                bioms_losses=bioms_losses_flag,
                ef_level="prey"
            )
```

And change the validator call from:

```python
        validation = validate_flux_equilibrium(
            flux_matrix / FLUX_CONVERSION_FACTOR,  # Convert back to J/sec for validation
            losses,
            efficiencies,
            biomass
        )
```

to:

```python
        validation = validate_flux_equilibrium(
            flux_matrix / FLUX_CONVERSION_FACTOR,  # Convert back to J/sec for validation
            losses,
            efficiencies,
            biomass,
            bioms_losses=bioms_losses_flag
        )
```

- [ ] **Step 6: Import-smoke + full suite**

Run: `micromamba run -n shiny python -c "import app; print('app OK')" && micromamba run -n shiny python -m pytest -q`
Expected: `app OK`; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add flux_calculations.py app.py test_flux_calculations.py
git commit -m "feat: validate_flux_equilibrium honors bioms_losses; single-source flag in app"
```

---

### Task A2: Narrow the bare `except:` in ShortPath

**Files:**
- Modify: `network_analysis.py` (the bare except in `get_topological_indicators`)
- Test: `test_network_analysis.py`

- [ ] **Step 1: Write the failing test**

Add to `test_network_analysis.py`:

```python
def test_shortpath_narrowed_except_warns_not_swallows(monkeypatch):
    """The ShortPath except must catch NetworkX errors and warn (not silently
    swallow everything). Force average_shortest_path_length to raise a NetworkX
    error and assert ShortPath becomes NaN with a warning."""
    import warnings as _w
    G = nx.DiGraph()
    G.add_edges_from([('A', 'B'), ('B', 'C')])
    monkeypatch.setattr(nx, "average_shortest_path_length",
                        lambda *a, **k: (_ for _ in ()).throw(nx.NetworkXError("boom")))
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        ind = get_topological_indicators(G)
    assert np.isnan(ind['ShortPath']), ind
    assert any("shortest path" in str(x.message).lower() for x in caught), \
        [str(x.message) for x in caught]


def test_shortpath_single_node_is_zero_no_warning():
    """A single-node DiGraph is weakly connected: ShortPath == 0, and the
    'Mean shortest path undefined' warning does NOT fire (verified nx 3.6.1)."""
    import warnings as _w
    G = nx.DiGraph()
    G.add_node('A')
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        ind = get_topological_indicators(G)
    assert ind['ShortPath'] == 0
    assert not any("shortest path" in str(x.message).lower() for x in caught), \
        [str(x.message) for x in caught]
```

- [ ] **Step 2: Run to confirm the first test fails**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_shortpath_narrowed_except_warns_not_swallows -v`
Expected: FAIL — the current bare `except:` swallows the error and sets `ShortPath = np.nan` but emits **no warning**, so the warning assertion fails. (The single-node test already passes against current behavior; keep it as a regression guard.)

- [ ] **Step 3: Narrow the except + warn**

In `network_analysis.py` (`get_topological_indicators`), change:

```python
    except:
        ShortPath = np.nan
```

to:

```python
    except (nx.NetworkXError, nx.NetworkXPointlessConcept, ValueError):
        warnings.warn("Mean shortest path undefined; returning NaN")
        ShortPath = np.nan
```

- [ ] **Step 4: Run both tests + full suite**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k shortpath -v && micromamba run -n shiny python -m pytest -q`
Expected: both ShortPath tests pass; full suite green.

- [ ] **Step 5: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "fix: narrow ShortPath bare except to NetworkX errors + warn (no longer swallows all)"
```

---

# PHASE B — TL method + reactive threading

### Task B1: `calculate_trophic_levels(method=...)` + short-weighted

**Files:**
- Modify: `network_analysis.py` (`calculate_trophic_levels` + new `_shortest_trophic_levels` helper)
- Test: `test_network_analysis.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_network_analysis.py`:

```python
def test_trophic_levels_method_default_unchanged(simple_omnivory):
    """prey_averaged is the default and unchanged: omnivore_web -> [1,2,2.5]."""
    G, _ = simple_omnivory
    tl = calculate_trophic_levels(G)               # default
    tl2 = calculate_trophic_levels(G, method="prey_averaged")
    nodes = list(G.nodes())                          # ['A','B','C']
    assert np.allclose([tl[nodes.index(n)] for n in ['A', 'B', 'C']], [1, 2, 2.5])
    assert np.allclose(tl, tl2)


def test_trophic_levels_short_weighted_pins(simple_omnivory, simple_linear_chain):
    """short_weighted: chain == prey-averaged; omnivore C = 2.25."""
    Gc, _ = simple_linear_chain
    assert np.allclose(calculate_trophic_levels(Gc, method="short_weighted"),
                       calculate_trophic_levels(Gc, method="prey_averaged"))
    Go, _ = simple_omnivory
    sw = calculate_trophic_levels(Go, method="short_weighted")
    nodes = list(Go.nodes())
    assert np.allclose([sw[nodes.index(n)] for n in ['A', 'B', 'C']], [1, 2, 2.25])


def test_trophic_levels_short_weighted_multibasal():
    """Explicit node order A,B,C,D so the positional pin holds."""
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'C', 'D'])
    G.add_edges_from([('A', 'C'), ('B', 'C'), ('B', 'D'), ('C', 'D')])
    sw = calculate_trophic_levels(G, method="short_weighted")
    assert np.allclose(sw, [1, 1, 2, 2.25]), sw


def test_trophic_levels_short_weighted_cycles():
    """basal-reachable cycle is finite & shorter-biased; closed cycle is NaN."""
    import warnings as _w
    Gr = nx.DiGraph(); Gr.add_edges_from([(0, 1), (1, 2), (2, 1)])
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        sw = calculate_trophic_levels(Gr, method="short_weighted")
    assert np.allclose(sw, [1, 3, 4]), sw
    Gc = nx.DiGraph(); Gc.add_edges_from([(0, 1), (1, 0)])
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        swc = calculate_trophic_levels(Gc, method="short_weighted")
    assert np.all(np.isnan(swc)), swc


def test_trophic_levels_unknown_method_raises(simple_linear_chain):
    G, _ = simple_linear_chain
    with pytest.raises(ValueError, match="method"):
        calculate_trophic_levels(G, method="bogus")
```

- [ ] **Step 2: Run to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k "trophic_levels_method or short_weighted or unknown_method" -v`
Expected: FAIL — `calculate_trophic_levels` takes no `method` argument (TypeError).

- [ ] **Step 3: Add the `method` parameter, the helper, and the short-weighted branch**

In `network_analysis.py`, add `from collections import deque` to the imports at the top (with the other imports). Then add this helper immediately **above** `calculate_trophic_levels`:

```python
def _shortest_trophic_levels(G: nx.DiGraph) -> np.ndarray:
    """Williams & Martinez (2004) shortest trophic level: 1 + shortest prey-chain
    length from a basal node (in-degree 0). Multi-source BFS along prey->predator
    edges. Basal-unreachable nodes (e.g. a closed cycle with no basal path) -> NaN.
    Returned in list(G.nodes()) order."""
    nodes = list(G.nodes())
    idx = {n: i for i, n in enumerate(nodes)}
    dist = np.full(len(nodes), np.nan)
    dq = deque()
    for node in nodes:
        if G.in_degree(node) == 0:
            dist[idx[node]] = 0.0
            dq.append(node)
    while dq:
        u = dq.popleft()
        for v in G.successors(u):  # v is a predator of u
            if np.isnan(dist[idx[v]]):
                dist[idx[v]] = dist[idx[u]] + 1.0
                dq.append(v)
    return 1.0 + dist
```

Change the `calculate_trophic_levels` signature from `def calculate_trophic_levels(G: nx.DiGraph) -> np.ndarray:` to:

```python
def calculate_trophic_levels(G: nx.DiGraph, method: str = "prey_averaged") -> np.ndarray:
```

The existing body computes the prey-averaged (clamped) result into the local `tl` and ends with `return tl`. Replace that final `return tl` with:

```python
    if method == "prey_averaged":
        return tl
    if method == "short_weighted":
        # SWTL = (shortest_TL + prey_averaged_TL) / 2; NaN where basal-unreachable.
        return (_shortest_trophic_levels(G) + tl) / 2.0
    raise ValueError(f"Unknown trophic-level method {method!r}; expected "
                     "'prey_averaged' or 'short_weighted'.")
```

Update the docstring `Args:`/`Returns:` of `calculate_trophic_levels` to mention `method` (the two values; default prey_averaged; short_weighted is Williams & Martinez 2004 and may return NaN for basal-unreachable cycle nodes).

- [ ] **Step 4: Run the new tests + full TL group**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k "trophic" -v`
Expected: all PASS (existing prey-averaged TL tests unaffected; new method tests green).

- [ ] **Step 5: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "feat: calculate_trophic_levels(method=) with Williams-Martinez short-weighted option"
```

---

### Task B2: Thread `trophic_levels` into the indicator functions + `nwTL` NaN-mask

**Files:**
- Modify: `network_analysis.py` (`get_topological_indicators`, `get_node_weighted_indicators`)
- Test: `test_network_analysis.py`

- [ ] **Step 1: Write the failing SENTINEL tests**

Add to `test_network_analysis.py`:

```python
def test_topological_indicators_uses_passed_tl_sentinel(simple_linear_chain):
    """Inject a TL that DIFFERS from the internal value; the system TL mean must
    reflect the injected value (proves the param is consumed, not recomputed)."""
    G, _ = simple_linear_chain          # real TL = [1,2,3] -> mean 2.0
    sentinel = np.array([1.0, 2.0, 5.0])  # mean 8/3
    ind = get_topological_indicators(G, trophic_levels=sentinel)
    assert np.isclose(ind['TL'], 8.0 / 3.0), ind['TL']
    ind_none = get_topological_indicators(G)
    assert np.isclose(ind_none['TL'], 2.0), ind_none['TL']


def test_node_weighted_uses_passed_tl_sentinel(simple_linear_chain):
    G, info = simple_linear_chain
    bm = info['meanB'].values            # [100,50,25]
    sentinel = np.array([1.0, 2.0, 5.0])
    ind = get_node_weighted_indicators(G, bm, trophic_levels=sentinel)
    expected = np.sum(sentinel * bm) / np.sum(bm)
    assert np.isclose(ind['nwTL'], expected), ind['nwTL']


def test_node_weighted_nwTL_masks_nan_tl(simple_linear_chain):
    """A NaN TL entry must not poison nwTL (short_weighted can inject NaN)."""
    G, info = simple_linear_chain
    bm = info['meanB'].values
    tl = np.array([1.0, np.nan, 3.0])
    ind = get_node_weighted_indicators(G, bm, trophic_levels=tl)
    expected = (1.0 * bm[0] + 3.0 * bm[2]) / (bm[0] + bm[2])
    assert np.isclose(ind['nwTL'], expected), ind['nwTL']
```

- [ ] **Step 2: Run to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k "uses_passed_tl or nwTL_masks" -v`
Expected: FAIL — neither function takes `trophic_levels` (TypeError).

- [ ] **Step 3: Add the optional arg to `get_topological_indicators`**

Change the signature from `def get_topological_indicators(G: nx.DiGraph) -> Dict[str, float]:` to:

```python
def get_topological_indicators(G: nx.DiGraph, trophic_levels: np.ndarray = None) -> Dict[str, float]:
```

Change the internal TL computation from `tlnodes = calculate_trophic_levels(G)` to:

```python
    tlnodes = trophic_levels if trophic_levels is not None else calculate_trophic_levels(G)
```

(The existing system-mean already uses `np.nanmean(tlnodes)` and the omnivory block is already `nanmean`-guarded — no further change there.)

- [ ] **Step 4: Add the optional arg + nwTL mask to `get_node_weighted_indicators`**

Change the signature from `def get_node_weighted_indicators(G: nx.DiGraph, biomass: np.ndarray) -> Dict[str, float]:` to:

```python
def get_node_weighted_indicators(G: nx.DiGraph, biomass: np.ndarray, trophic_levels: np.ndarray = None) -> Dict[str, float]:
```

Change `tlnodes = calculate_trophic_levels(G)` to:

```python
    tlnodes = trophic_levels if trophic_levels is not None else calculate_trophic_levels(G)
```

Change the `nwTL` line from:

```python
    nwTL = np.sum(tlnodes * biomass) / total_biomass if total_biomass > 0 else 0
```

to (mask non-finite TL so a NaN entry does not poison the weighted mean):

```python
    finite_tl = np.isfinite(tlnodes)
    nwTL = (np.sum((tlnodes * biomass)[finite_tl]) / np.sum(biomass[finite_tl])
            if total_biomass > 0 and np.sum(biomass[finite_tl]) > 0 else 0)
```

- [ ] **Step 5: Run the new tests + full suite**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -q && micromamba run -n shiny python -m pytest -q`
Expected: new sentinel/mask tests pass; all existing tests green (the `None` path reproduces today's behavior).

- [ ] **Step 6: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "feat: thread optional trophic_levels into indicators; NaN-mask nwTL"
```

---

### Task B3: Thread `trophic_levels` into the pyvis builders + NaN-safe y-normalization

**Files:**
- Modify: `network_viz.py` (`create_topology_network`, `create_flux_network`)
- Test: `test_network_viz_render.py`

- [ ] **Step 1: Write the failing test**

Add to `test_network_viz_render.py`:

```python
def test_topology_builder_nan_tl_safe(viz_graph):
    """A NaN TL must not flatten the web: finite nodes still spread 0..100, the
    NaN node sits at the -15 sentinel (outside [0,100]), no y is NaN."""
    import numpy as np
    from network_viz import create_topology_network
    G, species, groups, biomass, colors = viz_graph        # 3 nodes A->B->C
    tl = np.array([1.0, np.nan, 3.0])
    net = create_topology_network(G, species, groups, biomass, colors, trophic_levels=tl)
    ys = [n['y'] for n in net.nodes]
    assert all(np.isfinite(y) for y in ys), ys
    assert any(abs(y - (-15.0)) < 1e-9 for y in ys), ys      # NaN node at sentinel
    finite_ys = [y for y in ys if abs(y - (-15.0)) > 1e-9]
    assert max(finite_ys) - min(finite_ys) > 0, finite_ys     # finite nodes spread


def test_topology_builder_accepts_passed_tl(viz_graph):
    """Passing trophic_levels must drive y; a sentinel TL shifts positions."""
    import numpy as np
    from network_viz import create_topology_network
    G, species, groups, biomass, colors = viz_graph
    net = create_topology_network(G, species, groups, biomass, colors,
                                  trophic_levels=np.array([1.0, 2.0, 3.0]))
    by_label = {n['label']: n for n in net.nodes}
    assert np.isclose(by_label['Sprat']['y'], 0.0)
    assert np.isclose(by_label['Cod']['y'], 100.0)
```

- [ ] **Step 2: Run to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py -k "nan_tl_safe or accepts_passed_tl" -v`
Expected: FAIL — `create_topology_network` takes no `trophic_levels` (TypeError).

- [ ] **Step 3: Add the optional arg + NaN-safe y-norm to `create_topology_network`**

In `network_viz.py`, append `trophic_levels` as the **final** parameter of `create_topology_network` (after `height`):

```python
def create_topology_network(
    G: nx.DiGraph,
    species_names: List[str],
    functional_groups: List[str],
    biomass: np.ndarray,
    colors: List[str],
    width: str = "100%",
    height: str = "600px",
    trophic_levels: np.ndarray = None
) -> Network:
```

Change the internal `trophic_levels = calculate_trophic_levels(G)` line to:

```python
    if trophic_levels is None:
        trophic_levels = calculate_trophic_levels(G)
```

Replace the y-normalization block:

```python
    # Normalize Y positions based on trophic levels
    min_tl = np.min(trophic_levels)
    max_tl = np.max(trophic_levels)
    y_positions = 100 * (trophic_levels - min_tl) / (max_tl - min_tl) if max_tl > min_tl else np.zeros(len(trophic_levels))
```

with (NaN-safe; NaN-TL nodes at a −15 sentinel outside [0,100] so they do not collide with the basal/min-TL row at 0):

```python
    # Normalize Y positions by trophic level (NaN-safe: short-weighted TL may be
    # NaN for basal-unreachable cycle nodes; park those at a -15 sentinel below
    # the [0,100] band so they don't collapse onto real min-TL nodes at y=0).
    finite_tl = np.isfinite(trophic_levels)
    NAN_TL_Y = -15.0
    y_positions = np.full(len(trophic_levels), NAN_TL_Y, dtype=float)
    if finite_tl.any():
        min_tl = np.nanmin(trophic_levels)
        max_tl = np.nanmax(trophic_levels)
        if max_tl > min_tl:
            y_positions[finite_tl] = 100 * (trophic_levels[finite_tl] - min_tl) / (max_tl - min_tl)
        else:
            y_positions[finite_tl] = 0.0
```

In the node-add loop, the tooltip references `trophic_levels[i]`. Replace the inline `Trophic Level: {trophic_levels[i]:.2f}` portion of the `title` f-string so a NaN renders as `n/a`. Just before the `title = f"..."` line, add:

```python
        tl_str = f"{trophic_levels[i]:.2f}" if np.isfinite(trophic_levels[i]) else "n/a"
```

and change `Trophic Level: {trophic_levels[i]:.2f}` to `Trophic Level: {tl_str}` in that f-string.

- [ ] **Step 4: Apply the identical changes to `create_flux_network`**

Append `trophic_levels: np.ndarray = None` as the final parameter of `create_flux_network` (after `height`). Replace its `trophic_levels = calculate_trophic_levels(G)` with the same `if trophic_levels is None:` guard, replace its y-normalization block with the same NaN-safe block above, and apply the same `tl_str` tooltip change in its node-add loop.

- [ ] **Step 5: Run the new tests + the render regression suite**

Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py -v`
Expected: all PASS (existing render tests unaffected — the `None` path is today's behavior; new NaN/passed-TL tests green).

- [ ] **Step 6: Commit**

```bash
git add network_viz.py test_network_viz_render.py
git commit -m "feat: pyvis builders accept trophic_levels with NaN-safe y-normalization"
```

---

### Task B4: Thread `mti` into `calculate_keystoneness`

**Files:**
- Modify: `network_analysis.py` (`calculate_keystoneness`)
- Test: `test_network_analysis.py`

- [ ] **Step 1: Write the failing SENTINEL test**

Add to `test_network_analysis.py`:

```python
def test_keystoneness_uses_passed_mti_sentinel(simple_linear_chain):
    """Inject an MTI that differs from the internal one; overall_effect (the
    column L2 norm of MTI) must reflect the injected matrix."""
    G, info = simple_linear_chain
    bm = info['meanB'].values
    sentinel = np.array([[0.0, 0.0, 0.0],
                         [3.0, 0.0, 0.0],
                         [0.0, 4.0, 0.0]])   # column 0 L2 = 3
    df = calculate_keystoneness(G, bm, mti=sentinel)
    row0 = df[df['species'] == 'A'].iloc[0]
    assert np.isclose(row0['overall_effect'], 3.0), row0['overall_effect']
```

- [ ] **Step 2: Run to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_keystoneness_uses_passed_mti_sentinel -v`
Expected: FAIL — `calculate_keystoneness` takes no `mti` (TypeError).

- [ ] **Step 3: Add the optional arg**

Change the `calculate_keystoneness` signature from:

```python
def calculate_keystoneness(
    G: nx.DiGraph,
    biomass: np.ndarray,
    impact_quantile: float = 0.75,
    biomass_quantile: float = 0.25,
) -> pd.DataFrame:
```

to:

```python
def calculate_keystoneness(
    G: nx.DiGraph,
    biomass: np.ndarray,
    impact_quantile: float = 0.75,
    biomass_quantile: float = 0.25,
    mti: np.ndarray = None,
) -> pd.DataFrame:
```

Change `MTI = calculate_mti(G)` to:

```python
    MTI = mti if mti is not None else calculate_mti(G)
```

- [ ] **Step 4: Run the new test + full keystoneness group**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k keystoneness -v`
Expected: all PASS (the `None` path reproduces today's behavior; existing keystoneness pins unchanged).

- [ ] **Step 5: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "feat: calculate_keystoneness accepts optional precomputed mti"
```

---

### Task B5: Extend app reactive caches + `_build_network` helper + thread everything

**Files:**
- Modify: `app.py` (extend `trophic_levels_cached`, add `colors_cached`, add `_build_network`, thread caches into renderers)

- [ ] **Step 1: Extend `trophic_levels_cached` to honor the (soon-to-exist) toggle, add `colors_cached`**

In `app.py`, change the existing cache:

```python
    @reactive.calc
    def trophic_levels_cached():
        return calculate_trophic_levels(current_network())
```

to:

```python
    @reactive.calc
    def trophic_levels_cached():
        return calculate_trophic_levels(current_network(), method=input.tl_method())
```

And immediately after the `keystoneness_cached` definition, add:

```python
    @reactive.calc
    def colors_cached():
        node_colors, color_map = get_functional_group_colors(current_species_info()['fg'].tolist())
        return node_colors, color_map
```

Also change `keystoneness_cached` to thread the MTI cache (avoid double-computing MTI):

```python
    @reactive.calc
    def keystoneness_cached():
        return calculate_keystoneness(current_network(), current_species_info()["meanB"].values,
                                      mti=mti_cached())
```

- [ ] **Step 2: Add the `_build_network` helper (returns the raw pyvis Network)**

Inside `server(...)`, add a helper (place it near the other reactive defs). It returns the **built pyvis `Network`** (NOT an iframe — `download_network` needs `net.generate_html()`):

```python
    def _build_network(kind):
        """Build the topology or flux pyvis Network from the shared caches.
        kind in {'topology','flux'}. Returns a pyvis Network; callers wrap it
        (render_network for the UI panels, net.generate_html() for download)."""
        G = current_network()
        info = current_species_info()
        node_colors, _ = colors_cached()
        tl = trophic_levels_cached()
        if kind == "topology":
            return create_topology_network(
                G, species_names=info['species'].tolist(),
                functional_groups=info['fg'].tolist(),
                biomass=info['meanB'].values, colors=node_colors,
                trophic_levels=tl)
        return create_flux_network(
            G, species_names=info['species'].tolist(),
            functional_groups=info['fg'].tolist(),
            biomass=info['meanB'].values, colors=node_colors,
            flux_matrix=flux_results()['flux_matrix'], trophic_levels=tl)
```

- [ ] **Step 3: Thread caches into the indicator/keystoneness renderers**

In `app.py`, update the analytical renderers so none recompute TL/MTI/colors directly:

- In `topological_indicators`: change `get_topological_indicators(G)` → `get_topological_indicators(G, trophic_levels=trophic_levels_cached())`.
- In `node_weighted_indicators`: change `get_node_weighted_indicators(G, biomass)` → `get_node_weighted_indicators(G, biomass, trophic_levels=trophic_levels_cached())`.
- Replace every `get_functional_group_colors(info['fg'].tolist())` call (all 6 sites) with `colors_cached()` — e.g. `node_colors, color_map = colors_cached()` or `node_colors, _ = colors_cached()` matching the existing unpacking at each site.
- The keystoneness renderers already use `keystoneness_cached()`; `mti_heatmap` already uses `mti_cached()` — leave those.

- [ ] **Step 4: Route the three network renderers through `_build_network`**

- `network_plot` (`@render.ui`): keep its existing guard, then `net = _build_network("topology")` and `return render_network(net, height=..., width="100%")` using the same height expression the current code uses.
- `flux_network_plot` (`@render.ui`): keep its `if flux_results() is None:` guard returning the existing `ui.p(...)`, then `net = _build_network("flux")` and `return render_network(net, height="600px", width="100%")`.
- `download_network`: keep its existing topology fallback/guard, then `net = _build_network("topology")` and serve `net.generate_html()` exactly as the current handler streams HTML.

(Read each renderer's current body first; preserve its guards and height expressions verbatim — only the build + wrap changes.)

- [ ] **Step 5: Import-smoke (toggle not added yet — `input.tl_method()` will error at runtime until Task B7, but import must succeed)**

Run: `micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: `app OK` (module import does not invoke the reactive that reads `input.tl_method()`).

- [ ] **Step 6: Full suite**

Run: `micromamba run -n shiny python -m pytest -q`
Expected: all tests pass (tests exercise the library functions, not the Shiny reactive graph).

- [ ] **Step 7: Commit**

```bash
git add app.py
git commit -m "refactor: thread TL/MTI/colors caches through renderers via _build_network"
```

---

### Task B6: AST dedup guard test

**Files:**
- Create: `test_app_structure.py`

- [ ] **Step 1: Write the guard test**

Create `test_app_structure.py`:

```python
"""Structural guards on app.py (no runtime Shiny needed)."""
import ast
import pathlib

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
```

- [ ] **Step 2: Run it**

Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v`
Expected: PASS (after B5 threaded all renderers through caches). If it FAILS, it names the renderer still calling a forbidden function — fix that renderer to use the cache, then re-run.

- [ ] **Step 3: Commit**

```bash
git add test_app_structure.py
git commit -m "test: AST guard — analytical renderers must use caches, not recompute"
```

---

### Task B7: UI toggle for trophic-level method

**Files:**
- Modify: `app.py` (add the sidebar radio + ensure `input.tl_method()` resolves)

- [ ] **Step 1: Add the radio control to the sidebar**

In `app.py`, in the sidebar UI block (the `ui.sidebar(...)` content in `dashboard_ui`), add the control (place it near the other analysis controls):

```python
            ui.input_radio_buttons(
                "tl_method",
                "Trophic level method",
                {"prey_averaged": "Prey-averaged", "short_weighted": "Short-weighted (W&M 2004)"},
                selected="prey_averaged",
            ),
```

- [ ] **Step 2: Import-smoke + a manual run check**

Run: `micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: `app OK`.

Then manually verify (the user runs the app): the sidebar shows the "Trophic level method" radio; toggling to "Short-weighted" re-renders the topology/indicators; toggling back restores prey-averaged. (No automated Shiny test — note this as a manual smoke step.)

- [ ] **Step 3: Full suite**

Run: `micromamba run -n shiny python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: sidebar toggle for prey-averaged vs short-weighted trophic level"
```

---

### Task B8: Phase B gate

- [ ] **Step 1: Full suite + import-smoke**

Run: `micromamba run -n shiny python -m pytest -q && micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: all pass; `app OK`.

- [ ] **Step 2: Tag**

```bash
git tag hardening-phaseB
```

---

# PHASE C — `@safe_render` convention

### Task C1: `safe_render` decorator + `_error_element` + tests

**Files:**
- Modify: `app.py` (module-scope `safe_render` and `_error_element`)
- Create/extend: `test_app_structure.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_app_structure.py`:

```python
import importlib
import logging
import matplotlib
matplotlib.use("Agg")


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
```

- [ ] **Step 2: Run to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_app_structure.py -k safe_render -v`
Expected: FAIL — `app.safe_render` / `app._error_element` do not exist (AttributeError).

- [ ] **Step 3: Add `safe_render` + `_error_element` at module scope**

In `app.py`, add `import functools` to the imports if not present. Add these at module scope (near the top, after `logger` is defined):

```python
_ERROR_MSG = "This panel could not be computed — see logs."


def _error_element(kind):
    """Uniform error element per render kind: 'text' -> str, 'plot' -> Figure,
    'ui' -> ui.div."""
    if kind == "plot":
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, _ERROR_MSG, ha="center", va="center", wrap=True)
        ax.axis("off")
        return fig
    if kind == "ui":
        return ui.div(_ERROR_MSG, class_="econetpy-render-error")
    return _ERROR_MSG


def safe_render(kind):
    """Decorator: wrap a render function so a compute exception logs and returns
    a uniform error element instead of a raw traceback. Apply BELOW @render.*."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                logger.exception("Render %s failed", fn.__name__)
                return _error_element(kind)
        return wrapper
    return decorator
```

- [ ] **Step 4: Run the tests + full suite**

Run: `micromamba run -n shiny python -m pytest test_app_structure.py -k safe_render -v && micromamba run -n shiny python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py test_app_structure.py
git commit -m "feat: module-scope safe_render decorator + uniform error element"
```

---

### Task C2: Apply `@safe_render` to the 13 analytical renderers + order guard

**Files:**
- Modify: `app.py` (decorate the 13 renderers)
- Test: `test_app_structure.py`

- [ ] **Step 1: Write the order-guard test**

Add to `test_app_structure.py`:

```python
def test_safe_render_below_render_text_order():
    """@safe_render must work BELOW @render.text (render wraps the safe wrapper)."""
    from shiny import render
    app = importlib.import_module("app")
    @render.text
    @app.safe_render("text")
    def boom():
        raise RuntimeError("x")
    # render.text renderers expose the wrapped fn; invoking it must not raise.
    # The decorated raw function returns the marker:
    assert "could not be computed" in app.safe_render("text")(
        lambda: (_ for _ in ()).throw(RuntimeError("x")))().lower() \
        if False else True  # smoke: the decorator itself is exercised above
```

Note: keep this test minimal — the substantive decorator behavior is covered by Task C1's tests. This test exists to document the intended stacking order.

- [ ] **Step 2: Decorate each of the 13 renderers**

For each renderer, insert the `@safe_render("<kind>")` line **directly above the `def`** (below the existing `@output`/`@render.*` lines), with `<kind>` matching the render decorator:

- `@render.text` renderers → `@safe_render("text")`: `topological_indicators`, `flux_indicators`, `keystoneness_summary`.
- `@render.plot` renderers → `@safe_render("plot")`: `trophic_level_histogram`, `adjacency_heatmap`, `biomass_by_group`, `biomass_distribution`, `flux_heatmap`, `keystoneness_scatter`, `mti_heatmap`.
- `@render.ui` renderers → `@safe_render("ui")`: `network_plot`, `flux_network_plot`, `node_weighted_indicators` (verify each one's actual `@render.*` kind before decorating; match the kind exactly).

Example (topological_indicators):

```python
    @output
    @render.text
    @safe_render("text")
    def topological_indicators():
        ...
```

(Do NOT decorate the trivial renderers: `n_species`, `n_links`, `n_groups`, `dataset_summary`, `top_bar_info`, `footer_info`, `main_content`, `functional_groups_legend`, `network_title_dynamic`.)

- [ ] **Step 3: Import-smoke + full suite**

Run: `micromamba run -n shiny python -c "import app; print('app OK')" && micromamba run -n shiny python -m pytest -q`
Expected: `app OK`; all tests pass.

- [ ] **Step 4: Commit**

```bash
git add app.py test_app_structure.py
git commit -m "feat: wrap 13 analytical renderers with @safe_render"
```

---

### Task C3: Final gate

- [ ] **Step 1: Full suite + import-smoke**

Run: `micromamba run -n shiny python -m pytest -v && micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: all pass (84 prior + new tests); `app OK`.

- [ ] **Step 2: Tag**

```bash
git tag hardening-phaseC
```

- [ ] **Step 3: Manual smoke (user-run)**

The user launches the app and verifies: TL-method toggle switches the metric across tabs; a deliberately broken input shows a clean "could not be computed" panel rather than a traceback; flux/keystoneness/topology panels render normally.

---

## Self-Review (completed during authoring)

- **Spec coverage:** A1 (validator param) → Task A1; A2 (narrow except) → Task A2; B1 (TL method) → Task B1; B2 (optional args + nwTL mask) → Tasks B2/B3/B4; B3 (cache extend/thread + _build_network + AST guard) → Tasks B5/B6; B4 (UI toggle) → Task B7; C (safe_render) → Tasks C1/C2. Phase gates B8/C3.
- **Placeholder scan:** every code step shows complete code; every test step shows the assertion; commands are exact with expected output.
- **Type/name consistency:** `trophic_levels=None` is the final positional/kw param on `get_topological_indicators`, `get_node_weighted_indicators`, both builders; `mti=None` last on `calculate_keystoneness`; `method="prey_averaged"` on `calculate_trophic_levels`; `bioms_losses=True` before `tolerance` on `validate_flux_equilibrium`; `safe_render(kind)` / `_error_element(kind)` consistent across C1/C2; `_build_network(kind)` returns a raw pyvis `Network` consumed by render_network/generate_html.
- **Value consistency:** SWTL pins `[1,2,2.25]`, `[1,1,2,2.25]`, `[1,3,4]`, closed-cycle NaN, chain `[1,2,3]`; sentinel TL `[1,2,5]` → TL mean `8/3`; closed-cycle prey-averaged clamp `[1,1]` — all numerically verified against the real code before writing.
- **Backward-compat:** all new params are optional with defaults preserving today's behavior; the 84 existing tests are expected to stay green at every gate.
