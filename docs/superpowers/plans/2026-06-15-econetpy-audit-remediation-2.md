# EconetPy Audit Remediation #2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the confirmed inconsistencies and bugs from the deep codebase audit — 3 numeric bugs, the node↔row alignment cluster, robustness guards, test gaps, ops/docs — across six TDD-gated phases.

**Architecture:** Phase 1 fixes numeric correctness (flux inflow diversity, NaN-biomass-as-valid, omnivory center). Phase 2 keys the node↔row join by species name (relabel + assert + regenerate the gitignored `BalticFW.pkl`). Phase 3 adds robustness guards. Phase 4 adds discriminating tests. Phase 5 fixes deploy.sh + README. Phase 6 does two behavior-preserving refactors. Prey-averaged TL stays the default; the 106-test baseline stays green.

**Tech Stack:** Python 3.13, numpy, networkx 3.6.1, pandas, Shiny for Python 1.6.1, pyvis fork. All tests: `micromamba run -n shiny python -m pytest`. Repo root is the working dir. Work on a feature branch (created at execution); do not push/merge unless asked.

**Spec:** `docs/superpowers/specs/2026-06-14-econetpy-audit-remediation-2-design.md` (`752581e`, two review rounds, converged). All pinned values below were re-derived against the real code.

---

## File Structure

| File | Change |
|------|--------|
| `network_analysis.py` | P1: flux-indicator inflow norm (`:382`), omnivory center (`:232`); P3: mti/keystoneness empty+type guards, nwG/nwV divisor, zero-biomass keystoneness |
| `flux_calculations.py` | P1: fluxing raises on non-finite; validator flags non-finite |
| `load_data.py` | P2: relabel by `name`, assert, raise-on-contract, delete dead branch |
| `app.py` | P2: `nodelist=` (`:1119`,`:955`), pickle-load validation, editor `data_patched`; P3: temp/bodymass `req`, logging; P6: page-routing dedup |
| `network_viz.py` | P3: color-overflow warning; P6: `_add_styled_nodes` dedup |
| `deploy.sh` | P5: exclude `data/` |
| `README.md` | P5: GPL-3.0 canonical, deps, drop phantom tab |
| `test_*.py` (+ new `test_load_data.py` additions) | tests per task |

---

# PHASE 1 — Numeric correctness

### Task 1: Flux inflow-diversity transpose (`#1`)

**Files:** Modify `network_analysis.py:382`; Test `test_network_analysis.py`.

- [ ] **Step 1: Write the failing discriminating test**

Add to `test_network_analysis.py`:

```python
def test_flux_indicators_inflow_normalization_multiprey():
    """A predator eating 2 prey with EQUAL flux has effective prey N_res=2, so
    lwG reflects 2 effective prey. The transposed normalization divides by the
    prey's inflow instead of the predator's intake and gets this wrong.
    Web: prey A,B -> predator C, flux 5 each (rows=prey, cols=pred)."""
    from network_analysis import calculate_flux_indicators
    flux = np.array([[0.0, 0.0, 5.0],
                     [0.0, 0.0, 5.0],
                     [0.0, 0.0, 0.0]])  # A->C=5, B->C=5
    ind = calculate_flux_indicators(flux, loop=False)
    # C's inflow is {A:5, B:5} -> Shannon-effective prey = 2.0; lwV unaffected.
    assert np.isclose(ind['lwG'], 2.0), ind['lwG']


def test_flux_indicators_chain_anchor():
    """Non-regression anchor: a single-prey chain gives lwG=lwV=1.0 either way."""
    from network_analysis import calculate_flux_indicators
    flux = np.array([[0.0, 10.0, 0.0], [0.0, 0.0, 5.0], [0.0, 0.0, 0.0]])
    ind = calculate_flux_indicators(flux, loop=False)
    assert np.isclose(ind['lwG'], 1.0) and np.isclose(ind['lwV'], 1.0), ind
```

- [ ] **Step 2: Run to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_flux_indicators_inflow_normalization_multiprey -v`
Expected: FAIL — the transposed normalization yields `lwG != 2.0`.

- [ ] **Step 3: Fix the inflow normalization**

In `network_analysis.py:381-382`, replace:

```python
    with np.errstate(divide='ignore', invalid='ignore'):
        H_in_mat = (W_net.T / sum_in).T * np.log((W_net.T / sum_in).T)
```

with (divide each predator-column by its own intake, mirroring the outflow side at `:394`):

```python
    with np.errstate(divide='ignore', invalid='ignore'):
        P_in = W_net / sum_in[np.newaxis, :]
        H_in_mat = P_in * np.log(P_in)
```

- [ ] **Step 4: Run both tests to confirm GREEN**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k flux_indicators -v`
Expected: both PASS (`lwG=2.0` multi-prey; chain `lwG=lwV=1.0`).

- [ ] **Step 5: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "fix: flux inflow-diversity normalized by predator intake, not prey (lwG)"
```

---

### Task 2: NaN biomass reported as valid (`#2`)

**Files:** Modify `flux_calculations.py` (`fluxing`, `validate_flux_equilibrium`); Test `test_flux_calculations.py`.

- [ ] **Step 1: Write the failing tests**

Add to `test_flux_calculations.py`:

```python
def test_fluxing_raises_on_nan_biomass():
    """A NaN biomass yields all-NaN F; np.any(F < -1e-9) is False for NaN, so the
    negative-F guard misses it. fluxing must reject non-finite inputs/solutions."""
    mat = np.array([[0, 1, 0], [0, 0, 1], [0, 0, 0]])
    losses = np.array([0.1, 0.5, 1.0])
    e = np.array([0.0, 0.6, 0.7])
    bm = np.array([100.0, np.nan, 25.0])
    with pytest.raises(ValueError, match="finite"):
        fluxing(mat=mat, biomasses=bm, losses=losses, efficiencies=e, ef_level="prey")


def test_validate_flux_equilibrium_flags_nonfinite():
    """A non-finite flux must not report balanced=True, max_imbalance=0.0."""
    flux = np.array([[0.0, np.nan, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    losses = np.array([1.0, 1.0, 1.0]); e = np.array([0.5, 0.5, 0.5])
    r = validate_flux_equilibrium(flux, losses, e)
    assert r['balanced'] is False, r
    assert not np.isfinite(r['max_imbalance']), r
```

- [ ] **Step 2: Run to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py -k "nan_biomass or nonfinite" -v`
Expected: both FAIL (no raise; validator returns balanced=True/0.0).

- [ ] **Step 3: Guard fluxing against non-finite**

In `flux_calculations.py`, immediately after the function's input-validation block (near the top of `fluxing`, before the `W` preference matrix is built), add a finite-input check. Then change the negative-F block (`:180-185`) to also reject non-finite `F`. The negative block becomes:

```python
    # Reject non-finite first (np.any(F < -1e-9) is False for NaN, so the
    # negative check alone would silently pass an all-NaN solution).
    if not np.all(np.isfinite(F)):
        raise ValueError(
            "fluxing: non-finite flux solution (check for NaN/inf biomass, "
            "losses, or efficiencies)."
        )
    if np.any(F < -1e-9):
        raise ValueError(
            "fluxing: no non-negative steady-state solution exists for these "
            "inputs (negative ingestion). The food web may contain an infeasible "
            "cycle or inconsistent losses/efficiencies."
        )
```

And add, right after `fluxing`'s existing input validation (where `biomasses`/`losses`/`efficiencies` are checked), an explicit finite-input guard:

```python
    for _name, _arr in (("biomasses", biomasses), ("losses", losses), ("efficiencies", efficiencies)):
        if _arr is not None and not np.all(np.isfinite(np.asarray(_arr, dtype=float))):
            raise ValueError(f"fluxing: {_name} contains non-finite values.")
```

(If the input-validation block's exact location is unclear, place this guard immediately before the `W = mat.copy()...` preference-matrix construction.)

- [ ] **Step 4: Flag non-finite in the validator**

In `validate_flux_equilibrium`, at the very top (before computing inflows/outflows), add:

```python
    if not np.all(np.isfinite(flux_matrix)):
        return {
            'balanced': False,
            'imbalances': np.full(flux_matrix.shape[0], np.nan),
            'max_imbalance': np.inf,
            'mean_imbalance': np.inf,
            'relative_imbalance': np.inf,
        }
```

- [ ] **Step 5: Run both tests + full flux suite**

Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py -v`
Expected: all PASS (new tests green; existing feasible/finite cases unaffected).

- [ ] **Step 6: Commit**

```bash
git add flux_calculations.py test_flux_calculations.py
git commit -m "fix: fluxing rejects non-finite inputs/solutions; validator flags non-finite flux"
```

---

### Task 3: Omnivory center under short-weighted TL (`#3`)

**Files:** Modify `network_analysis.py:219-234`; Test `test_network_analysis.py`.

- [ ] **Step 1: Write the failing + invariance tests**

Add to `test_network_analysis.py`:

```python
def test_omnivory_center_is_method_invariant(simple_omnivory):
    """Omnivory centers on the diet-weighted mean prey TL, which is independent
    of the TL *method* for omnivore_web (prey TLs unchanged). Both methods -> 0.125.
    The buggy center=TL_i-1 gives 0.15625 under short_weighted."""
    G, _ = simple_omnivory
    for method in ("prey_averaged", "short_weighted"):
        tl = calculate_trophic_levels(G, method=method)
        ind = get_topological_indicators(G, trophic_levels=tl)
        assert np.isclose(ind['Omni'], 0.125), (method, ind['Omni'])


def test_omnivory_nan_prey_renormalizes():
    """A predator eating >=2 finite-TL prey plus one NaN-TL prey renormalizes
    over the finite prey (not poisoned to NaN)."""
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'X', 'C'])
    G.add_edges_from([('A', 'C'), ('B', 'C'), ('X', 'C')])  # C eats A,B,X
    tl = np.array([1.0, 2.0, np.nan, 3.0])  # X has NaN TL
    ind = get_topological_indicators(G, trophic_levels=tl)
    # finite prey of C: A(1),B(2) renormalized to 0.5/0.5; center=1.5;
    # OI_C = 0.5*(1-1.5)^2 + 0.5*(2-1.5)^2 = 0.25; basal A,B,X -> NaN; mean = 0.25
    assert np.isclose(ind['Omni'], 0.25), ind['Omni']
```

- [ ] **Step 2: Run to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k "omnivory_center or nan_prey" -v`
Expected: FAIL — short_weighted gives 0.15625; NaN-prey poisons to NaN.

- [ ] **Step 3: Fix the center + NaN-prey handling**

In `network_analysis.py`, replace the omnivory loop body (`:230-233`):

```python
    omninodes = np.full(len(col_sums), np.nan)
    for i in range(len(col_sums)):
        if col_sums[i] > 0:
            center = tlnodes[i] - 1.0
            omninodes[i] = float(np.sum(DC[:, i] * (tlnodes - center) ** 2))
```

with (diet-weighted mean center, renormalized over finite-TL prey):

```python
    omninodes = np.full(len(col_sums), np.nan)
    for i in range(len(col_sums)):
        if col_sums[i] > 0:
            w = DC[:, i].copy()
            finite = np.isfinite(tlnodes) & (w > 0)
            if not finite.any():
                continue  # no finite-TL prey -> undefined (NaN)
            w = w[finite] / w[finite].sum()      # renormalize over finite prey
            tlf = tlnodes[finite]
            center = float(np.sum(w * tlf))       # diet-weighted mean prey TL
            omninodes[i] = float(np.sum(w * (tlf - center) ** 2))
```

Update the docstring (`:219-221`) to read: `# Omnivory index (Christensen & Pauly 1992): diet-fraction-weighted variance of prey trophic levels, centered on the diet-weighted mean prey TL = sum_j DC[j,i]*TL_j (equals TL_i-1 only for prey-averaged TL).`

- [ ] **Step 4: Run the new tests + full topological/omnivory group**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k "omnivory or topological" -v`
Expected: all PASS — `0.125` both methods; NaN-prey → `0.25`; existing prey-averaged `Omni=0.125` pin unchanged.

- [ ] **Step 5: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "fix: omnivory centers on diet-weighted mean prey TL (method-correct, NaN-prey safe)"
```

### Task 4: Phase 1 gate

- [ ] Run: `micromamba run -n shiny python -m pytest -q` → all pass. Then `git tag audit2-phase1`.

---

# PHASE 2 — Alignment (key the node↔row join by name)

> All of Phase 2's library/app changes land across these tasks; the **pickle regen + `nodelist=`** must be in the SAME task (Task 6) so a stale `n0..n33` cache cannot crash the `nodelist=` change.

### Task 5: Relabel graph nodes to species names in load_data (`#6`, `#2.1`)

**Files:** Modify `load_data.py:53-64`; Test new `test_load_data_alignment.py`.

- [ ] **Step 1: Write the failing test**

Create `test_load_data_alignment.py`:

```python
import networkx as nx, pandas as pd, pytest
from pathlib import Path


def test_load_baltic_data_node_ids_are_species_names():
    """After load, node IDs == species names, in the same order."""
    import os
    if not Path("BalticFW_network.graphml").exists():
        pytest.skip("source GraphML not present")
    from load_data import load_baltic_data
    G, info = load_baltic_data()
    assert list(G.nodes()) == info['species'].tolist()


def test_load_baltic_data_raises_on_name_mismatch(tmp_path, monkeypatch):
    """A GraphML/CSV name mismatch must raise, not print-and-continue."""
    # Build a tiny mismatched pair and point load_baltic_data at it via cwd.
    g = nx.DiGraph(); g.add_node('n0', name='Cod'); g.add_node('n1', name='Sprat')
    g.add_edge('n0', 'n1')
    nx.write_graphml(g, tmp_path / "BalticFW_network.graphml")
    pd.DataFrame({'species': ['Cod', 'Herring'], 'fg': ['Fish', 'Fish'],
                  'meanB': [1.0, 2.0], 'bodymasses': [1.0, 2.0],
                  'met.types': ['Other', 'Other'], 'efficiencies': [0.5, 0.5]}
                 ).to_csv(tmp_path / "BalticFW_species_info.csv", index=False)
    monkeypatch.chdir(tmp_path)
    from load_data import load_baltic_data
    with pytest.raises(ValueError, match="match|align"):
        load_baltic_data()
```

- [ ] **Step 2: Run to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_load_data_alignment.py -v`
Expected: the mismatch test FAILs (current code prints, doesn't raise); the names test may already pass *only after* the source is correct — it currently FAILS because nodes stay `n0..n33`.

- [ ] **Step 3: Replace the relabel block**

In `load_data.py`, replace the relabel block (`:53-64`):

```python
    # Ensure species names match network nodes
    # GraphML might have changed node IDs, so we need to map them
    node_mapping = {str(i): name for i, name in enumerate(info['species'])}

    # Check if we need to relabel nodes
    if set(G.nodes()) != set(info['species'].values):
        print("Relabeling nodes to match species names...")
        if all(str(i) in G.nodes() for i in range(len(info))):
            # Nodes are numbered, relabel them
            G = nx.relabel_nodes(G, node_mapping)
        else:
            print("Warning: Node labels don't match. Attempting to align...")
```

with (relabel by the GraphML `name` attribute, then assert identity):

```python
    # Key the node<->row join by species name. GraphML nodes carry a 'name'
    # attribute (n0->'Synchaeta', ...); relabel the graph to those names so the
    # node IDs ARE the species, not positional 'n0..nN' accidents.
    names = nx.get_node_attributes(G, 'name')
    if names and len(names) == G.number_of_nodes():
        if len(set(names.values())) != len(names):
            raise ValueError("Duplicate species names in GraphML 'name' attrs; "
                             "cannot key the join by name.")
        G = nx.relabel_nodes(G, names)

    # Reindex info to the graph's node order, then require an exact match.
    node_list = list(G.nodes())
    if set(node_list) == set(info['species']):
        info = info.set_index('species').loc[node_list].reset_index()
    if list(G.nodes()) != info['species'].tolist():
        raise ValueError(
            "Network nodes do not align with species rows by name "
            f"(nodes={node_list[:3]}..., species={info['species'].tolist()[:3]}...)."
        )
```

Also change the missing-columns branch (`:77-78`) from `print(...)` to `raise ValueError(f"Missing required columns: {missing_cols}")`.

- [ ] **Step 4: Run the alignment tests + full suite**

Run: `micromamba run -n shiny python -m pytest test_load_data_alignment.py -v && micromamba run -n shiny python -m pytest -q`
Expected: both alignment tests PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add load_data.py test_load_data_alignment.py
git commit -m "fix: load_data keys node<->row join by species name; raises on mismatch"
```

---

### Task 6: Regenerate the pickle + thread nodelist= + validate the load (`#2.2`, `#2.3`, `#11`)

**Files:** Modify `app.py` (`:1119`, `:955`, pickle-load `~64-80`); regenerate `BalticFW.pkl`.

> `BalticFW.pkl` is **gitignored** (per-machine cache). This task rebuilds it AND adds `nodelist=` together so a stale cache cannot crash.

- [ ] **Step 1: Write the failing pickle-validation test**

Add to `test_load_data_alignment.py`:

```python
def test_load_default_data_pickle_is_name_keyed():
    """The on-disk pickle path must yield name-keyed nodes (catches a stale pkl)."""
    if not Path("BalticFW_network.graphml").exists():
        pytest.skip("source not present")
    import app
    G, info = app.load_default_data()
    assert list(G.nodes()) == info['species'].tolist()
```

- [ ] **Step 2: Regenerate the pickle from the fixed loader (RED → GREEN hinge)**

Run: `micromamba run -n shiny python -m pytest "test_load_data_alignment.py::test_load_default_data_pickle_is_name_keyed" -v`
Expected: FAIL — the cached `BalticFW.pkl` still has `n0..n33`. Then rebuild:

Run: `rm -f BalticFW.pkl && micromamba run -n shiny python load_data.py`
This regenerates `BalticFW.pkl` with species-named nodes (data values identical).

- [ ] **Step 3: Add pickle-load validation in app.py**

In `app.py`, in `load_default_data` (the `if data_file.exists():` pickle branch, `~:66-72`), after `data = pickle.load(f)`, validate before returning:

```python
        if not (isinstance(data, dict) and {'network', 'info'} <= set(data.keys())):
            print("BalticFW.pkl missing 'network'/'info'; rebuilding from sources.")
        else:
            G_pkl, info_pkl = data['network'], data['info']
            required = ['species', 'fg', 'meanB', 'bodymasses', 'met.types', 'efficiencies']
            if (all(c in info_pkl.columns for c in required)
                    and set(info_pkl['species']) == set(G_pkl.nodes())):
                return G_pkl, info_pkl
            print("BalticFW.pkl stale/misaligned; rebuilding from sources.")
    # fall through to reconstruction
```

(Adjust to wrap the existing `return data['network'], data['info']` so a bad/stale pickle falls through to the `load_baltic_data()` reconstruction path instead of returning.)

- [ ] **Step 4: Thread nodelist= into the two adjacency builders**

In `app.py`, the flux effect (`:1119`): change `adj_matrix = nx.to_numpy_array(G)` to:

```python
        adj_matrix = nx.to_numpy_array(G, nodelist=info['species'].tolist())
```

And in `adjacency_heatmap` (`~:955`, the `nx.to_numpy_array(G)` call there): pass `nodelist=info['species'].tolist()` using the `info` in that renderer's scope (read the renderer first to match the local variable name).

- [ ] **Step 5: Run the pickle test + full suite + import smoke**

Run: `micromamba run -n shiny python -m pytest test_load_data_alignment.py -v && micromamba run -n shiny python -m pytest -q && micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: all PASS; `app OK`. The keystoneness `species` column now holds real names (verified live later).

- [ ] **Step 6: Commit** (the pkl is gitignored, so it won't be staged — that's expected)

```bash
git add app.py test_load_data_alignment.py
git commit -m "fix: regenerate name-keyed pickle; nodelist= on adjacency builders; validate pickle load"
```

---

### Task 7: Data Editor reorder-safety (`#5`, `#2.4`)

**Files:** Modify `app.py:1356-1383`; Test `test_app_structure.py`.

- [ ] **Step 1: Write the failing/structural test**

Add to `test_app_structure.py` (AST-level, since the Shiny render flow is hard to drive without a harness):

```python
def test_editor_uses_data_patched_not_data_view():
    """The species-info update must read data_patched() (original node order +
    edits), not data_view() (display/sorted order) which permutes rows."""
    src = APP.read_text(encoding="utf-8")
    assert ".data_patched()" in src, "editor must use data_patched()"
    assert "species_info_editor.data_view()" not in src, "data_view() reorders rows"
```

- [ ] **Step 2: Run to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_editor_uses_data_patched_not_data_view -v`
Expected: FAIL — current code uses `species_info_editor.data_view()`.

- [ ] **Step 3: Switch to data_patched + non-editable species/fg + length assert**

In `app.py`, change the editor render (`:1360`) to make `species`/`fg` non-editable:

```python
        return render.DataGrid(info, editable=True, width="100%",
                               editable_columns=["meanB", "bodymasses", "efficiencies"])
```

(If `editable_columns` is unsupported in this Shiny version, instead leave `editable=True` and rely on the post-edit re-coercion; verify against the installed Shiny and adjust.)

And in `_apply_species_info_edits` (`:1365`), change:

```python
        edited = species_info_editor.data_view()  # returns original + user edits
```

to:

```python
        edited = species_info_editor.data_patched()  # original node order + edits
```

After the numeric-coercion block, before `current_species_info.set(df)` (`:1382`), add a length guard:

```python
        if len(df) != current_network().number_of_nodes():
            ui.notification_show(
                "Edited table row count does not match the network; not applied.",
                type="error", duration=6,
            )
            return
```

- [ ] **Step 4: Run the test + import smoke + full suite**

Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -c "import app; print('app OK')" && micromamba run -n shiny python -m pytest -q`
Expected: PASS; `app OK`.

- [ ] **Step 5: Commit**

```bash
git add app.py test_app_structure.py
git commit -m "fix: Data Editor reads data_patched (node order + edits); guards row count"
```

---

### Task 8: Keystoneness name-keying regression test (`#4`)

**Files:** Test `test_network_analysis.py`.

- [ ] **Step 1: Write the regression test (node IDs ≠ insertion order)**

```python
def test_keystoneness_species_column_is_name_keyed():
    """The returned 'species' column must hold the graph's node labels (names),
    paired correctly with each node's relative_biomass even after the descending
    sort. Use node labels that are NOT in sorted/insertion order."""
    G = nx.DiGraph()
    G.add_nodes_from(['Cod', 'Sprat', 'Herring'])
    G.add_edges_from([('Sprat', 'Cod'), ('Herring', 'Cod')])
    biomass = np.array([5.0, 100.0, 50.0])  # Cod, Sprat, Herring (node order)
    df = calculate_keystoneness(G, biomass)
    assert set(df['species']) == {'Cod', 'Sprat', 'Herring'}
    total = biomass.sum()
    for name, bm in zip(['Cod', 'Sprat', 'Herring'], biomass):
        row = df[df['species'] == name].iloc[0]
        assert np.isclose(row['relative_biomass'], bm / total), (name, row['relative_biomass'])
```

- [ ] **Step 2: Run it**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_keystoneness_species_column_is_name_keyed -v`
Expected: PASS (the `(species, relative_biomass)` pairing is zipped before the sort). This is a guard, not a fix — if it fails, the join is broken.

- [ ] **Step 3: Commit**

```bash
git add test_network_analysis.py
git commit -m "test: keystoneness species column is name-keyed and survives the sort"
```

### Task 9: Phase 2 gate

- [ ] Run full suite + import smoke + the on-disk pickle test; then `git tag audit2-phase2`.

```bash
micromamba run -n shiny python -m pytest -q && micromamba run -n shiny python -c "import app; print('app OK')" && git tag audit2-phase2
```

---

# PHASE 3 — Robustness guards

### Task 10: Empty-graph + type guards (`#7`, `#8`)

**Files:** Modify `network_analysis.py` (`calculate_mti`, `calculate_keystoneness`); Test `test_network_analysis.py`.

- [ ] **Step 1: Write the failing tests**

```python
def test_mti_empty_graph_raises():
    with pytest.raises(ValueError, match="no vertices"):
        calculate_mti(nx.DiGraph())


def test_keystoneness_empty_graph_raises():
    with pytest.raises(ValueError, match="no vertices"):
        calculate_keystoneness(nx.DiGraph(), np.array([]))


def test_keystoneness_type_guard_on_cached_path():
    """With mti= passed, calculate_mti is never called, so the type guard must
    live in calculate_keystoneness itself."""
    with pytest.raises(ValueError, match="DiGraph"):
        calculate_keystoneness(["not", "a", "graph"], np.array([1.0]), mti=np.zeros((1, 1)))
```

- [ ] **Step 2: Run to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k "empty_graph or type_guard_on_cached" -v`
Expected: FAIL (mti returns/raises differently; keystoneness lacks its own guards).

- [ ] **Step 3: Add the guards**

In `calculate_mti`, after `n = len(G.nodes())` (`:451`), add:

```python
    if n == 0:
        raise ValueError("Network contains no vertices")
```

In `calculate_keystoneness`, at the very top of the body (before `MTI = mti if mti...`, `:521`), add:

```python
    if not isinstance(G, nx.DiGraph):
        raise ValueError("Input 'G' must be a NetworkX DiGraph object")
    if len(G.nodes()) == 0:
        raise ValueError("Network contains no vertices")
```

- [ ] **Step 4: Run + full suite**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k "empty_graph or type_guard" -v && micromamba run -n shiny python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "fix: empty-graph + cached-path type guards in mti/keystoneness"
```

---

### Task 11: nwG/nwV divisor guard + zero-biomass keystoneness (`#9`, `#13`)

**Files:** Modify `network_analysis.py` (`get_node_weighted_indicators:~265,269`; `calculate_keystoneness:~529`); Test `test_network_analysis.py`.

- [ ] **Step 1: Write the failing tests**

```python
def test_node_weighted_zero_biomass_no_nan():
    """All-zero biomass must not yield silent NaN nwG/nwV."""
    G = nx.DiGraph(); G.add_edges_from([('A', 'B'), ('B', 'C')])
    ind = get_node_weighted_indicators(G, np.array([0.0, 0.0, 0.0]))
    assert ind['nwG'] == 0 and ind['nwV'] == 0, ind


def test_keystoneness_zero_biomass_is_undefined():
    """All-zero biomass -> every species 'Undefined', not 'Keystone'."""
    G = nx.DiGraph(); G.add_edges_from([(0, 1), (0, 2), (2, 3)])
    df = calculate_keystoneness(G, np.array([0.0, 0.0, 0.0, 0.0]))
    assert set(df['keystone_status']) == {'Undefined'}, df['keystone_status'].tolist()
```

- [ ] **Step 2: Run to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k "zero_biomass" -v`
Expected: FAIL (nwG/nwV → NaN; keystoneness → `['Keystone','Rare',...]`).

- [ ] **Step 3: Guard nwG/nwV divisors**

In `get_node_weighted_indicators`, change the `nwG` and `nwV` lines (`:265`, `:269`) to test the biomass-sum divisor (mirroring `nwTL`/`nwC`):

```python
    nwG = (np.sum((in_degrees * biomass)[predators]) / np.sum(biomass[predators])) \
        if np.sum(predators) > 0 and np.sum(biomass[predators]) > 0 else 0
```
```python
    nwV = (np.sum((out_degrees * biomass)[prey]) / np.sum(biomass[prey])) \
        if np.sum(prey) > 0 and np.sum(biomass[prey]) > 0 else 0
```

- [ ] **Step 4: Special-case zero-biomass keystoneness**

In `calculate_keystoneness`, immediately after `relative_biomass = ...` (`:530`), add:

```python
    if total_biomass <= 0:
        return pd.DataFrame({
            'species': list(G.nodes()),
            'overall_effect': overall_effect,
            'relative_biomass': relative_biomass,
            'keystoneness': np.full(len(overall_effect), np.nan),
            'keystone_status': ['Undefined'] * len(overall_effect),
        })
```

- [ ] **Step 5: Run + full suite**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k "zero_biomass" -v && micromamba run -n shiny python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "fix: nwG/nwV zero-biomass divisor guard; zero-biomass keystoneness -> Undefined"
```

---

### Task 12: Flux-effect input guards + logging config (`#10`, `#16`)

**Files:** Modify `app.py` (flux effect `:1109-1116`; logging `~:47-49`).

- [ ] **Step 1: Add `req` guards around calculate_losses**

In `app.py`, ensure `from shiny import req` is imported (or use `shiny.req`). In the flux effect, before `losses = calculate_losses(...)` (`:1112`), guard the inputs:

```python
        from shiny import req
        req(temp is not None)
        bodymasses = info['bodymasses'].values
        req(np.all(np.isfinite(bodymasses)) and np.all(bodymasses > 0))
        losses = calculate_losses(bodymasses, info['met.types'].tolist(), temp)
```

(Replace the existing `losses = calculate_losses(info['bodymasses'].values, info['met.types'].tolist(), temp)` with the guarded version.)

- [ ] **Step 2: Add logging config at module level**

In `app.py`, replace the logger setup (`~:47-48`):

```python
import logging
logger = logging.getLogger("econetpy.app")
```

with:

```python
import logging
logging.basicConfig(
    level=os.environ.get("ECONETPY_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("econetpy.app")
```

Add `import os` to the imports if not present.

- [ ] **Step 3: Import smoke + structural test**

Add to `test_app_structure.py`:

```python
def test_logging_configured():
    src = APP.read_text(encoding="utf-8")
    assert "logging.basicConfig(" in src
    assert "ECONETPY_LOG_LEVEL" in src
```

Run: `micromamba run -n shiny python -c "import app; print('app OK')" && micromamba run -n shiny python -m pytest test_app_structure.py -v`
Expected: `app OK`; tests pass.

- [ ] **Step 4: Commit**

```bash
git add app.py test_app_structure.py
git commit -m "fix: req guards for temperature/bodymass; configure root logging"
```

### Task 13: Phase 3 gate

- [ ] Full suite + import smoke; `git tag audit2-phase3`.

---

# PHASE 4 — Test coverage additions

### Task 14: Bersier flux-indicator pins + pred-grounding + disconnected/color (`#12`, `#14`, `#15`)

**Files:** Test `test_network_analysis.py`, `test_flux_calculations.py`, `test_network_viz_render.py`; Modify `network_viz.py` (color warning).

- [ ] **Step 1: Bersier flux-indicator pins (multi-prey, discriminating)**

Add to `test_network_analysis.py` (values computed from the corrected formula):

```python
def test_flux_indicators_pinned_diamond():
    """Diamond: A->C, B->C (5 each), C->D (8). Pins lwG/lwV/lwC."""
    from network_analysis import calculate_flux_indicators
    flux = np.array([[0., 0., 5., 0.],
                     [0., 0., 5., 0.],
                     [0., 0., 0., 8.],
                     [0., 0., 0., 0.]])
    ind = calculate_flux_indicators(flux, loop=False)
    # Recompute the exact expected lwG/lwV/lwC from the corrected formula in the
    # test body so the pin is self-checking:
    W = flux; si = W.sum(0); so = W.sum(1)
    import numpy as _np
    with _np.errstate(divide='ignore', invalid='ignore'):
        Pi = W / si[None, :]; Hin = -_np.nansum(_np.where(Pi > 0, Pi*_np.log(Pi), 0), 0)
        Po = W / so[:, None]; Hout = -_np.nansum(_np.where(Po > 0, Po*_np.log(Po), 0), 1)
    Nres = _np.where(si == 0, Hin, _np.exp(Hin)); Ncon = _np.where(so == 0, Hout, _np.exp(Hout))
    tot = W.sum()
    assert _np.isclose(ind['lwG'], (si*Nres).sum()/tot)
    assert _np.isclose(ind['lwV'], (so*Ncon).sum()/tot)
```

- [ ] **Step 2: Pred-level grounding test**

Add to `test_flux_calculations.py`:

```python
def test_fluxing_pred_level_basal_grounding():
    """Pred-level efficiency with a basal e=0 must ground the basal node (no
    singular matrix). Chain 0->1->2, e=[0,0.6,0.7]."""
    mat = np.array([[0, 1, 0], [0, 0, 1], [0, 0, 0]])
    losses = np.array([0.1, 0.5, 1.0]); e = np.array([0.0, 0.6, 0.7])
    flux = fluxing(mat=mat, losses=losses, efficiencies=e, ef_level="pred")
    assert np.all(np.isfinite(flux)) and flux[0, 1] > 0, flux
```

- [ ] **Step 3: Disconnected ShortPath + color-overflow warning**

Add to `test_network_analysis.py`:

```python
def test_shortpath_disconnected_uses_largest_component():
    G = nx.DiGraph(); G.add_edges_from([('A', 'B'), ('B', 'C'), ('X', 'Y')])
    ind = get_topological_indicators(G)
    assert np.isfinite(ind['ShortPath']) and ind['ShortPath'] > 0
```

Add a color-overflow warning in `network_viz.py` (`get_functional_group_colors`, where a group index exceeds `len(COLOR_SCHEME)`): emit `import warnings; warnings.warn(...)` (or `logger.warning`) when more groups than colors. Add to `test_network_viz_render.py`:

```python
def test_color_overflow_warns():
    import warnings as _w
    from network_viz import get_functional_group_colors
    groups = [f"g{i}" for i in range(len(__import__('network_analysis').COLOR_SCHEME) + 2)]
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        get_functional_group_colors(groups)
    assert any("color" in str(x.message).lower() for x in caught), [str(x.message) for x in caught]
```

- [ ] **Step 4: Run all + full suite**

Run: `micromamba run -n shiny python -m pytest -q`
Expected: all PASS. (If a pin's self-computed expected value differs from the implementation, that's a real discrepancy — STOP and report.)

- [ ] **Step 5: Commit**

```bash
git add test_network_analysis.py test_flux_calculations.py test_network_viz_render.py network_viz.py
git commit -m "test: Bersier indicators, pred-grounding, disconnected ShortPath, color-overflow warn"
```

### Task 15: Phase 4 gate

- [ ] Full suite; `git tag audit2-phase4`.

---

# PHASE 5 — Ops + docs

### Task 16: deploy.sh excludes data/ (`#17`)

**Files:** Modify `deploy.sh`.

- [ ] **Step 1: Read deploy.sh, find the rsync + EXCLUDE_PATTERNS**

Run: `grep -n "rsync\|EXCLUDE\|--delete\|data/" deploy.sh`
Identify the `EXCLUDE_PATTERNS` array (or the `--exclude` flags) and the `rsync` invocation.

- [ ] **Step 2: Add `data/` to the excludes**

Add `data/` (and `data/user_feedback_log.ndjson`) to `EXCLUDE_PATTERNS` / add `--exclude 'data/'` to the rsync, so the local feedback log (with User-Agent strings) is never pushed and `--delete` cannot clobber server-collected feedback. Leave a comment: `# never sync or --delete server-collected user data`.

- [ ] **Step 3: Syntax-check**

Run: `bash -n deploy.sh && echo "deploy.sh syntax OK"`
Expected: `deploy.sh syntax OK`.

- [ ] **Step 4: Commit**

```bash
git add deploy.sh
git commit -m "fix(ops): exclude data/ from deploy rsync (privacy + no --delete clobber)"
```

---

### Task 17: README — GPL-3.0 canonical, deps, drop phantom tab (`#18`)

**Files:** Modify `README.md`.

- [ ] **Step 1: Read README, locate the contradictions**

Run: `grep -n "CC BY-SA\|GPL\|License\|pyvis\|Data Import\|upload" README.md`

- [ ] **Step 2: Make GPL-3.0 canonical**

Replace the CC BY-SA 4.0 footer (and any CC reference) with GPL-3.0 so the license is consistent with the badge/body. Update the dependency list: replace `pyvis>=0.3.2` with the actual git-fork requirement (`pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2`, matching `requirements.txt`). Remove the documented "Data Import" / file-upload tab/workflow (it does not exist in the app).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README license=GPL-3.0 consistent; deps accurate; drop phantom Data Import tab"
```

### Task 18: Phase 5 gate

- [ ] Full suite + import smoke; `git tag audit2-phase5`.

---

# PHASE 6 — Refactors (behavior-preserving)

### Task 19: Page-routing dedup (`#6.1`)

**Files:** Modify `app.py` (`:668-701` menu effects, `:841-861` main_content).

- [ ] **Step 1: Read the 8 menu effects + main_content**

Run: `grep -n "current_page.set\|def main_content\|menu_" app.py | head -40` — confirm the page keys, menu input ids, and the `*_ui` builders.

- [ ] **Step 2: Introduce one ordered PAGES registry + loop-register**

Define (near the page UI lambdas) `PAGES = {"dashboard": ("menu_dashboard", dashboard_ui), "network": ("menu_network", network_ui), ...}` for the 7 navigable pages (NOT feedback, which is a modal). Replace the 7 individual `@reactive.effect`/`@reactive.event(input.menu_X)` blocks that call `current_page.set("X")` with a loop that registers one effect per `(key, (menu_id, _builder))`. Replace the `main_content` if/elif chain with `builder = PAGES.get(current_page(), ("", dashboard_ui))[1]; return builder()`. Keep `menu_feedback`'s modal effect as-is. Keep all `*_ui` builders as named module attributes (a test calls `app.dashboard_ui()`).

- [ ] **Step 3: Verify behavior unchanged**

Run: `micromamba run -n shiny python -c "import app; print('app OK')" && micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -m pytest -q`
Expected: `app OK`; the `app.dashboard_ui()` structural test still passes; full suite green.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "refactor: page routing via one PAGES registry + loop-registered effects"
```

---

### Task 20: Viz builder dedup (`#6.2`)

**Files:** Modify `network_viz.py`.

- [ ] **Step 1: Extract `_add_styled_nodes`**

Hoist `NAN_TL_Y = -15.0` to module scope. Extract a helper `_add_styled_nodes(net, G, species_names, functional_groups, biomass, colors, trophic_levels)` that builds the Network, computes the NaN-safe y-positions, and adds the styled nodes (the block currently duplicated in `create_topology_network` and `create_flux_network`). Each builder calls it, then runs only its own physics options + edge loop (the flux builder keeps using the returned node list for `G_weighted`).

- [ ] **Step 2: Run the render regression + a flux-side numeric pin**

Add to `test_network_viz_render.py` a flux-builder node size/y pin (mirroring the existing topology one). Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py -v`
Expected: all PASS (the emitted HTML/positions are unchanged for both builders).

- [ ] **Step 3: Commit**

```bash
git add network_viz.py test_network_viz_render.py
git commit -m "refactor: dedupe pyvis builders via _add_styled_nodes; flux-side size/y test"
```

### Task 21: Final gate + live smoke

- [ ] **Step 1: Full suite + import smoke**

Run: `micromamba run -n shiny python -m pytest -v && micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: all pass; `app OK`. Tag `audit2-phase6`.

- [ ] **Step 2: Live Playwright smoke (controller-run)**

Launch the app; verify: the **Keystoneness panel shows species names** (e.g. `Gadus morhua`), not `n23`; the TL-method toggle still recomputes; a forced renderer error shows the clean panel; flux calculation works. (Controller performs this; not a subagent task.)

---

## Self-Review (completed during authoring)

- **Spec coverage:** P1 → Tasks 1-3; P2 (2.1-2.5) → Tasks 5-8; P3 (#7-#10,#13,#16) → Tasks 10-12; P4 (#12,#14,#15) → Task 14; P5 (#17,#18) → Tasks 16-17; P6 → Tasks 19-20. Phase gates 4/9/13/15/18/21.
- **Placeholder scan:** every code step shows the code; every test step the assertion; two steps (Task 6 adjacency local var, Task 7 `editable_columns` support, Task 16/17 read-then-edit) say "verify against the file/installed Shiny" — intentional, the *change* is fully specified.
- **Value/type consistency:** `nodelist=info['species'].tolist()` used consistently; omnivory center `sum(DC[:,i]*tlnodes)` matches the re-derived `0.125`/`0.25` pins; keystoneness `total_biomass <= 0` guard returns the same DataFrame schema; `fluxing`/validator non-finite handling consistent; pickle validation matches `load_baltic_data`'s `required` columns.
- **Verified pins:** flux multi-prey `lwG=2.0` (chain `1.0`); omnivory `0.125` both methods, NaN-prey `0.25`; keystoneness zero-biomass all-`Undefined`; GraphML `name` complete + unique (34).
