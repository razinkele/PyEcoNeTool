# EconetPy Correctness & Quality Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the verified scientific-correctness bugs (energy flux, MTI, keystoneness, omnivory), revive the two dead UI features (data editor, network download), memoize expensive solves, and close honesty/hygiene gaps surfaced by the multi-angle review.

**Architecture:** Pure-function fixes in `network_analysis.py` / `flux_calculations.py` are locked in with analytic regression tests (hand-computed answers) so a future transpose/axis bug can't pass green again. Shiny wiring fixes go in `app.py`. Each scientific fix is TDD: write the failing analytic test first, then the minimal correction.

**Tech Stack:** Python 3.13, numpy, networkx, pandas, pytest, Shiny for Python (posit), pyvis (razinkele fork v4.2). Env: micromamba env `shiny` — run everything as `micromamba run -n shiny <cmd>`.

**Convention used throughout:** adjacency `adj[i,j]=1` means species *i* (prey) is eaten by *j* (predator) — **rows = prey, columns = predators**. This is already consistent across the codebase; do not change it.

> ## ⚠️ Execution-order rule (read before dispatching parallel workers)
> Tasks that edit the **same file MUST run strictly sequentially** — line-number anchors in later tasks go stale once an earlier task changes the file. Group accordingly:
> - **Group A → `network_analysis.py`:** Tasks 2 → 3 → 4 (in this order; 3 depends on 2).
> - **Group B → `app.py`:** Tasks 5 → 6 → 7 → 9 → 10 (in this order).
> - **Independent lanes (safe to parallelize with the groups):** Task 1 + Task 4b → `flux_calculations.py`; Task 8 → `VERSION`/`requirements.txt`/`environment.yml` (also touches `app.py:543`, so coordinate with Group B — do Task 8's app.py edit within the Group-B sequence).
> **Before every edit, re-grep the anchor** (function name / unique string) rather than trusting the printed line number — numbers shift as the file is edited within a group.

---

## Phase 1 — Scientific correctness (highest value)

### Task 1: Fix `fluxing()` linear system

The steady-state energy balance for prey-level efficiency is `F_i·(Wᵀe)_i = L_i + (W·F)_i`, so the matrix is `(diag(Wᵀe) − W)`. The current code uses the wrong diagonal axis **and** an erroneous transpose (`− W.T`), violating energy balance by orders of magnitude on real data.

**Files:**
- Test: `test_flux_calculations.py` (add new test)
- Modify: `flux_calculations.py:131-139` (prey branch) and `:158-163` (pred branch)

- [ ] **Step 1: Write the failing analytic test**

Add to `test_flux_calculations.py`:

```python
def test_fluxing_prey_level_satisfies_energy_balance():
    """On an A->B->C chain the solved fluxes must satisfy the prey-level
    steady-state balance F_i*(W.T@e)_i - (W@F)_i - L_i == 0 for consumers."""
    import numpy as np
    from flux_calculations import fluxing

    mat = np.array([[0, 1, 0], [0, 0, 1], [0, 0, 0]], float)  # 0->1->2
    L = np.array([2.0, 3.0, 5.0])
    e = np.array([0.5, 0.6, 0.7])

    flux = fluxing(mat, losses=L, efficiencies=e, ef_level="prey")

    W = mat.copy()
    cs = W.sum(0); cs[cs == 0] = 1; W = W / cs
    F = flux.sum(axis=0)                      # per-node intake = column sums
    residual = F * (W.T @ e) - (W @ F) - L
    # Consumer nodes (1, 2) must balance to ~0; node 0 is basal (excluded).
    assert abs(residual[1]) < 1e-9, residual
    assert abs(residual[2]) < 1e-9, residual
```

- [ ] **Step 2: Run test to verify it fails**

Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py::test_fluxing_prey_level_satisfies_energy_balance -v`
Expected: FAIL — residual ≈ `[-13.8, 5.0]`, assertion error.

- [ ] **Step 3: Fix the prey branch**

In `flux_calculations.py`, replace lines 131-139 (the `D_e = ...` through `A = np.diag(D_e) - W.T`) with:

```python
        # Calculate D_e: d_i = sum_j W_ji * e_j = (W.T @ e)_i
        # (efficiency-weighted column combination, NOT row-sum * e_i)
        D_e = W.T @ efficiencies

        # Handle basal species (no prey -> column sums to 0) to avoid singularity
        D_e[D_e == 0] = 1

        # Coefficient matrix: (diag(D_e) - W) @ F = L   (no transpose on W)
        A = np.diag(D_e) - W
```

- [ ] **Step 4: Fix the pred branch (transpose AND basal grounding)**

In `flux_calculations.py`, replace lines 158-163 (the `eff_adj = ...` through `A = np.diag(eff_adj) - W.T`) with:

```python
        # Basal species (no prey -> normalized column sums to 0) get diagonal 1.
        # fluxweb grounds basal species by no-prey (colSums(adj)==0), NOT by
        # efficiency==0 (which leaves a real basal species ungrounded and scales
        # its solved intake by 1/e_basal).
        eff_adj = efficiencies.copy().astype(float)
        eff_adj[W.sum(axis=0) == 0] = 1
        A = np.diag(eff_adj) - W
```

> **Review note (fluxweb fidelity):** the original `eff_adj[eff_adj == 0] = 1` is the wrong grounding criterion — verified against the canonical fluxweb R source. Its effect is confined to the *internal* solved intake `F` of basal species (which fluxweb scales by `1/e_basal` when mis-grounded); because `fluxing()` returns the between-species flux *matrix* and basal production is not a between-species flux, the returned matrix is unchanged for acyclic webs. The fix is applied for fidelity/robustness (and to avoid a singular matrix if a basal species ever has efficiency 0). No separate test is added because the defect is not observable from the returned matrix.

- [ ] **Step 5: Run the new test + full flux suite to verify pass**

Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py -v`
Expected: the new test PASSES; pre-existing tests still pass (they only assert shape/finiteness, so they remain green).

- [ ] **Step 6: Commit**

```bash
git add flux_calculations.py test_flux_calculations.py
git commit -m "fix: correct fluxing() steady-state linear system (wrong transpose + diagonal)"
```

---

### Task 2: Fix Mixed Trophic Impact (axis + missing predation term)

The current `DC` is row-normalized (a prey's predator distribution) and the model omits the predation-mortality term. The correct net direct impact is `Q = DC − PDᵀ`, where `DC[i,j]` = fraction of predator *j*'s diet that is prey *i* (column-normalized), and `PD[i,j]` = fraction of prey *i*'s mortality due to predator *j* (row-normalized). The total-impact matrix is `(I − Q)⁻¹ @ Q`. We preserve the existing return convention `MTI[i,j] = impact of j on i` by returning the transpose, so `app.py`'s heatmap is unaffected.

**Files:**
- Test: `test_network_analysis.py` (add new test)
- Modify: `network_analysis.py:412-443`

- [ ] **Step 1: Write the failing analytic test**

Add to `test_network_analysis.py`:

```python
def test_mti_two_species_predator_prey():
    """1 prey (0) eaten by 1 predator (1). Hand-computed total impacts:
    MTI[0,1] = impact of species 1 (predator) on 0 (prey) = -0.5
    MTI[1,0] = impact of species 0 (prey) on 1 (predator) = +0.5"""
    import numpy as np, networkx as nx
    from network_analysis import calculate_mti

    G = nx.DiGraph()
    G.add_nodes_from([0, 1])
    G.add_edge(0, 1)  # 0 (prey) -> 1 (predator)
    MTI = calculate_mti(G)
    assert np.isclose(MTI[0, 1], -0.5), MTI
    assert np.isclose(MTI[1, 0], 0.5), MTI
    assert np.allclose(np.diag(MTI), 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_mti_two_species_predator_prey -v`
Expected: FAIL (current code returns different/zero values; no predation term).

- [ ] **Step 3: Replace the MTI computation**

In `network_analysis.py`, replace lines 412-443 (from `# Create Diet Composition (DC) matrix` through `return MTI`) with:

```python
    # Diet composition: DC[i,j] = fraction of predator j's diet that is prey i
    # (column-normalized; columns are predators)
    col_sums = np.sum(adj_matrix, axis=0)
    col_sums_safe = np.where(col_sums == 0, 1, col_sums)
    DC = adj_matrix / col_sums_safe[np.newaxis, :]

    # Predation distribution: PD[i,j] = fraction of prey i's mortality
    # due to predator j (row-normalized; rows are prey)
    row_sums = np.sum(adj_matrix, axis=1)
    row_sums_safe = np.where(row_sums == 0, 1, row_sums)
    PD = adj_matrix / row_sums_safe[:, np.newaxis]

    # Net direct impact of i on j: positive as food (DC) minus negative as
    # predator (PD transposed):  Q[i,j] = DC[i,j] - PD[j,i]
    Q = DC - PD.T

    I = np.eye(n)
    I_minus_Q = I - Q
    if np.abs(np.linalg.det(I_minus_Q)) < 1e-10:
        warnings.warn("(I - Q) is singular or near-singular. Using pseudo-inverse.")
        inv_I_minus_Q = np.linalg.pinv(I_minus_Q)
    else:
        inv_I_minus_Q = inv(I_minus_Q)

    # Total (direct + indirect) impact of i on j
    M = inv_I_minus_Q @ Q
    np.fill_diagonal(M, 0)

    # Preserve existing convention: MTI[i,j] = impact of j on i
    return M.T
```

(The replacement block above already supplies the corrected `DC` comment — do not separately edit the old line 413; it no longer exists after the block replace.)

- [ ] **Step 4: Run test to verify it passes**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_mti_two_species_predator_prey -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "fix: MTI uses column-normalized diet + predation term (Ulanowicz/Puccia)"
```

---

### Task 3: Fix keystoneness to the Libralato (2006) index

`KS_i = log(ε_i · (1 − p_i))` with `ε_i` the **L2** norm of species *i*'s impacts (not the L1 sum), and `p_i` relative biomass. Replace the ratio-of-logs and the ad-hoc thresholds.

**Files:**
- Test: `test_network_analysis.py` (add new test)
- Modify: `network_analysis.py:476-500`

- [ ] **Step 1: Write the failing analytic test**

Add to `test_network_analysis.py`:

```python
def test_keystoneness_two_species_libralato():
    """With MTI=[[0,-0.5],[0.5,0]] and equal biomass, eps_i = 0.5 for both,
    p_i = 0.5, so KS_i = log(0.5 * 0.5) = log(0.25)."""
    import numpy as np, networkx as nx
    from network_analysis import calculate_keystoneness

    G = nx.DiGraph(); G.add_nodes_from([0, 1]); G.add_edge(0, 1)
    df = calculate_keystoneness(G, np.array([1.0, 1.0]))
    assert np.allclose(df["overall_effect"].values, 0.5), df
    assert np.allclose(df["keystoneness"].values, np.log(0.25)), df
```

- [ ] **Step 2: Run test to verify it fails**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_keystoneness_two_species_libralato -v`
Expected: FAIL (current code uses L1 sum and log-ratio).

- [ ] **Step 3: Replace overall-effect, index, and classification**

In `network_analysis.py`, replace lines 476-500 (from `# Calculate overall effect` through the classification `for` loop) with:

```python
    # Overall effect epsilon_i = L2 norm of species i's impacts.
    # MTI[i,j] = impact of j on i, so species i's impacts are column i.
    overall_effect = np.sqrt(np.sum(MTI ** 2, axis=0))

    # Relative biomass p_i
    total_biomass = np.sum(biomass)
    relative_biomass = biomass / total_biomass if total_biomass > 0 else biomass

    # Libralato (2006) keystoneness index: KS_i = log(eps_i * (1 - p_i))
    with np.errstate(divide="ignore", invalid="ignore"):
        keystoneness = np.log(overall_effect * (1.0 - relative_biomass))
    keystoneness[~np.isfinite(keystoneness)] = np.nan

    # Classify relative to the median KS (high impact) and a biomass threshold.
    finite = keystoneness[np.isfinite(keystoneness)]
    ks_threshold = np.median(finite) if finite.size else np.nan
    keystone_status = []
    for i in range(len(keystoneness)):
        if np.isnan(keystoneness[i]):
            keystone_status.append("Undefined")
        elif keystoneness[i] >= ks_threshold and relative_biomass[i] < 0.05:
            keystone_status.append("Keystone")
        elif keystoneness[i] >= ks_threshold and relative_biomass[i] >= 0.05:
            keystone_status.append("Dominant")
        else:
            keystone_status.append("Rare")
```

- [ ] **Step 4: Run test + the existing keystoneness tests**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k keyston -v`
Expected: new test PASSES. (Verified: no existing keystoneness/MTI test asserts the old numeric values — `test_keystoneness_*` only check ordering and valid status, `test_mti_*` only shape/diagonal/sign/finiteness — so the formula change breaks **no** existing test.)

- [ ] **Step 5: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "fix: keystoneness uses Libralato (2006) log(eps*(1-p)) with L2 impact norm"
```

---

### Task 4: Omnivory sample-SD + cycle-robust trophic levels

Two independent corrections. (a) Omnivory must use ddof=1 (R's `sd`) so single-prey predators yield NaN (excluded) instead of 0. (b) Replace the divergent fixed-point TL loop with a linear solve that is identical for acyclic binary webs but stable on cycles.

**Files:**
- Test: `test_network_analysis.py` (add two tests)
- Modify: `network_analysis.py:190` (omnivory) and `:89-114` (TL loop)

- [ ] **Step 1: Write failing tests**

Add to `test_network_analysis.py`:

```python
def test_trophic_levels_finite_on_cycles():
    """Cyclic / dense webs must yield finite, physical (1 <= TL <= 100) levels,
    never huge (~1e16) or negative values. Covers the dangerous ill-conditioned
    (not exactly singular) case where np.linalg.solve silently returns 1e16."""
    import numpy as np, networkx as nx
    from network_analysis import calculate_trophic_levels
    cases = [
        [(0, 1), (1, 0)],                                            # 2-cycle
        [(0, 1), (1, 2), (2, 0)],                                    # 3-cycle
        [(i, j) for i in range(4) for j in range(4) if i != j],     # fully connected
    ]
    for edges in cases:
        G = nx.DiGraph(); G.add_nodes_from(range(4)); G.add_edges_from(edges)
        tl = calculate_trophic_levels(G)
        assert np.all(np.isfinite(tl)), (edges, tl)
        assert np.all(tl >= 1) and np.all(tl <= 100), (edges, tl)

def test_trophic_levels_chain_unchanged():
    """Linear chain 0->1->2 still gives 1,2,3 (no regression vs old loop)."""
    import numpy as np, networkx as nx
    from network_analysis import calculate_trophic_levels
    G = nx.DiGraph(); G.add_nodes_from([0,1,2]); G.add_edge(0,1); G.add_edge(1,2)
    assert np.allclose(calculate_trophic_levels(G), [1, 2, 3])
```

- [ ] **Step 2: Run to verify failure**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k trophic_levels_finite_on_cycles -v`
Expected: FAIL — current loop returns `[~200, ~201]` for the cycle (and the un-guarded linear solve would return `~1e16` for the fully-connected case, also failing).

- [ ] **Step 3: Replace the TL iteration with a linear solve**

In `network_analysis.py`, replace lines 89-114 (the `converged = False` loop through `return tl`) with:

```python
    # Short-weighted / prey-averaged trophic level via linear solve.
    # For binary adjacency, diet fractions are uniform (1/#prey), so this is
    # identical to "1 + mean(TL of prey)" for acyclic webs but is stable on cycles.
    col_sums = adj.sum(axis=0)
    col_sums_safe = np.where(col_sums == 0, 1, col_sums)
    # diet[i,j] = fraction of predator i's diet that is prey j
    diet = (adj / col_sums_safe[np.newaxis, :]).T
    A = np.eye(n) - diet
    try:
        tl = np.linalg.solve(A, np.ones(n))
    except np.linalg.LinAlgError:
        warnings.warn("Trophic-level system singular; using pseudo-inverse")
        tl = np.linalg.lstsq(A, np.ones(n), rcond=None)[0]

    # Dense cycles make (I - diet) singular OR merely ill-conditioned. In the
    # ill-conditioned case np.linalg.solve does NOT raise and silently returns
    # values like 1e16; cycles can also produce TL < 1 or negative. Trophic
    # levels are physically >= 1, so flag and clamp non-physical results.
    if not np.all(np.isfinite(tl)) or np.any(tl < 1) or np.any(tl > 100):
        warnings.warn("Trophic levels non-physical (likely a cyclic web); clamped to [1, 100]")
        tl = np.clip(np.nan_to_num(tl, nan=1.0, posinf=100.0, neginf=1.0), 1.0, 100.0)

    return tl
```

(The now-unused `TROPHIC_LEVEL_MAX_ITER` / `TROPHIC_LEVEL_CONVERGENCE` constants may be left in place or removed if grep shows no other users.)

- [ ] **Step 4: Fix omnivory ddof**

In `network_analysis.py`, change line 190 from `omninodes = np.nanstd(webtl, axis=0)` to:

```python
    with warnings.catch_warnings():
        # ddof=1 makes single-prey predators yield NaN (intended exclusion);
        # that emits a benign "Degrees of freedom <= 0" RuntimeWarning.
        warnings.simplefilter("ignore", RuntimeWarning)
        omninodes = np.nanstd(webtl, axis=0, ddof=1)
```

(`warnings` is already imported in `network_analysis.py`. This keeps the suite clean for any future `pytest.warns`/`-W error` gate without hiding the NaN itself — `np.nanmean` still excludes the single-prey predators as intended.)

- [ ] **Step 5: Run TL + topological tests**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -v`
Expected: new tests PASS; existing topological tests still PASS (BalticFW TLs unchanged).

- [ ] **Step 6: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "fix: cycle-stable trophic-level solve + sample-SD omnivory (ddof=1)"
```

---

### Task 4b: Fix `validate_flux_equilibrium` to the solver's balance (retire false reassurance)

`validate_flux_equilibrium` (`flux_calculations.py:259-283`) currently checks `rowSum(flux)·e − colSum(flux) − L`, which is a **different** equation from the prey-level steady state the solver enforces. After Task 1 it will report the now-correct fluxes as `balanced=False` (verified: max_imbalance ~0.057, still above tolerance). It must validate the same balance the solver targets — assimilated incoming flux `= Σ_k e_k·flux[k,i]` equals outflow-to-predators `+ L` for each consumer (basal/grounded species excluded).

**Files:**
- Test: `test_flux_calculations.py` (add new test)
- Modify: `flux_calculations.py:259-283`

- [ ] **Step 1: Write the failing test**

```python
def test_validate_flux_equilibrium_passes_on_correct_fluxes():
    """After the fluxing fix, the validator must report balanced=True on the
    solver's own output (consumer nodes balanced to ~0)."""
    import numpy as np
    from flux_calculations import fluxing, validate_flux_equilibrium
    mat = np.array([[0, 1, 0], [0, 0, 1], [0, 0, 0]], float)
    L = np.array([2.0, 3.0, 5.0]); e = np.array([0.5, 0.6, 0.7])
    flux = fluxing(mat, losses=L, efficiencies=e, ef_level="prey")
    v = validate_flux_equilibrium(flux, losses=L, efficiencies=e)
    assert v["balanced"] is True, v
    assert v["max_imbalance"] < 1e-9, v
```

- [ ] **Step 2: Run to verify it fails**

Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py::test_validate_flux_equilibrium_passes_on_correct_fluxes -v`
Expected: FAIL — the current validator encodes a different balance and reports `balanced=False` (`max_imbalance` ≈ 20.7 for this toy chain; on BalticFW it drops from ~2602 to ~0.057 but still trips the tolerance).

- [ ] **Step 3: Rewrite the balance check**

In `flux_calculations.py`, replace lines 261-283 (from `# Calculate inflows` through the closing `}` of the `return {...}` dict) with:

```python
    # Prey-level steady state: assimilated incoming flux to consumer i equals
    # its outflow to predators plus losses.
    #   assimilated_in_i = sum_k e_k * flux[k,i]  =  (flux.T @ e)_i
    #   outflow_i        = sum_j flux[i,j] + L_i
    inflows = flux_matrix.T @ efficiencies

    L = losses.copy()
    if biomasses is not None:
        L = L * biomasses
    outflows = np.sum(flux_matrix, axis=1) + L

    imbalances = inflows - outflows
    # Only species with nonzero ASSIMILATED inflow are subject to this balance.
    # This consistently excludes (a) basal species (no prey) and (b) consumers
    # whose prey are all zero-efficiency producers — both are grounded by the
    # solver's `D_e[D_e==0]=1` step and enforce a different (F = L + outflow)
    # equation, so checking them here would raise a false alarm.
    checked = inflows > tolerance
    if np.any(checked):
        max_imbalance = float(np.max(np.abs(imbalances[checked])))
        mean_imbalance = float(np.mean(np.abs(imbalances[checked])))
    else:
        max_imbalance = mean_imbalance = 0.0

    return {
        'balanced': max_imbalance < tolerance,
        'imbalances': imbalances,
        'max_imbalance': max_imbalance,
        'mean_imbalance': mean_imbalance,
        'relative_imbalance': max_imbalance / np.mean(outflows) if np.mean(outflows) > 0 else np.inf,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py -v`
Expected: new test PASSES. Note: an existing "perfect balance" test that builds fluxes by hand may now legitimately report `balanced=False` if those hand-built fluxes don't satisfy the prey-level balance — if so, replace its hand-built matrix with `fluxing(...)` output (it was never asserting `balanced` before, per the original review T5).

- [ ] **Step 5: Commit**

```bash
git add flux_calculations.py test_flux_calculations.py
git commit -m "fix: validate_flux_equilibrium checks the solver's prey-level balance"
```

---

## Phase 2 — Revive dead UI features

### Task 5: Wire the Data Editor "Update" button

The editable grid's edits are never read back. Add an event handler that reads the edited frame and updates `current_species_info` (and rebuilds the network if the functional-group/species set changed).

**Files:**
- Modify: `app.py` — add handler near the `species_info_editor` render (`app.py:1296-1300`)

- [ ] **Step 1: Add the update handler**

**Insertion point (important):** insert this **immediately after line 1300** (the `return render.DataGrid(...)` line) — i.e. as the *last* block inside the `server()` function, at **4-space indentation**, BEFORE the blank line 1301 and the module-level `# CREATE APP` comment at line 1303 / `app = App(...)` at line 1311. If placed after the blank lines it lands at module scope where `input`, `species_info_editor`, and `current_species_info` are undefined → `NameError`.

```python
    @reactive.effect
    @reactive.event(input.update_species_info)
    def _apply_species_info_edits():
        edited = species_info_editor.data_view()  # returns original + user edits
        if edited is None or edited.empty:
            ui.notification_show("No edited data to apply.", type="warning", duration=4)
            return
        df = edited.copy()
        # DataGrid returns edited cells as strings; coerce numeric columns back.
        for col in ("meanB", "bodymasses", "efficiencies"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        # Reject malformed edits rather than letting NaN crash downstream renders
        # (R6: renders have no error surfacing; this handler is the gate).
        numeric_cols = [c for c in ("meanB", "bodymasses", "efficiencies") if c in df.columns]
        if numeric_cols and df[numeric_cols].isna().any().any():
            ui.notification_show(
                "Some numeric cells are invalid (non-numeric or blank). Fix them and retry.",
                type="error", duration=6,
            )
            return
        current_species_info.set(df)
        ui.notification_show("Species info updated.", type="message", duration=4)
```

> Colors are derived per-session from `current_species_info()` inside the render functions (see Task 10 Step 1), so updating `current_species_info` is sufficient — there is no separate color map to rebuild here.

- [ ] **Step 2: Verify the app imports and the handler is registered**

Run: `micromamba run -n shiny python -c "import app; print('ok')"`
Expected: prints `ok` with no exception.

- [ ] **Step 3: Manual verification note**

Launch `micromamba run -n shiny shiny run app.py`, open the Data Editor tab, change a `meanB` value, click "Update Species Info", confirm the dashboard value boxes / biomass plots reflect the change. (No automated Shiny test harness is set up; this is a manual check. Document the result.)

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: wire Data Editor update button to current_species_info"
```

---

### Task 6: Implement the `download_network` handler

**Files:**
- Modify: `app.py` — add a download handler; the button is at `app.py:206`.

- [ ] **Step 1: Add the handler inside `server()`**

Add near the network render functions (after `network_plot`):

```python
    @render.download(filename="econetool_network.html")
    def download_network():
        G = current_network()
        info = current_species_info()
        node_colors, _ = get_functional_group_colors(info['fg'].tolist())
        if input.network_type() == "Flux-Weighted" and flux_results() is not None:
            net = create_flux_network(
                G,
                species_names=info['species'].tolist(),
                functional_groups=info['fg'].tolist(),
                biomass=info['meanB'].values,
                colors=node_colors,
                flux_matrix=flux_results()['flux_matrix'],
            )
        else:
            net = create_topology_network(
                G,
                species_names=info['species'].tolist(),
                functional_groups=info['fg'].tolist(),
                biomass=info['meanB'].values,
                colors=node_colors,
            )
        yield net.generate_html()
```

> **Review correction:** the builders are keyword-heavy — `create_topology_network(G, species_names, functional_groups, biomass, colors, ...)` and `create_flux_network(..., flux_matrix=...)`. The earlier shorthand `create_topology_network(G, info, colors)` would raise `TypeError`. The code above mirrors the existing `network_plot` call at `app.py:851-885` exactly; `flux_results()` is a dict, so the matrix is `flux_results()['flux_matrix']`. `Network.generate_html()` is verified present in pyvis v4.2 and returns a full HTML string.

- [ ] **Step 2: Verify import**

Run: `micromamba run -n shiny python -c "import app; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Manual verification note**

In the running app, click "Download Network HTML" on the Network tab; confirm an HTML file downloads and opens to the current network. Document result.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: implement download_network handler (serve generated pyvis HTML)"
```

---

## Phase 3 — Performance / reactivity

### Task 7: Memoize expensive solves with `@reactive.calc`

Trophic levels, MTI, and keystoneness are recomputed in many renders. Cache them so they recompute only when `current_network` / `current_species_info` change.

**Files:**
- Modify: `app.py` — add reactive calcs near the other per-session reactives (~line 559); update render call sites to read them.

- [ ] **Step 1: Add the cached reactives**

After the `current_network` / `current_species_info` reactive values (~line 560), add:

```python
    @reactive.calc
    def trophic_levels_cached():
        return calculate_trophic_levels(current_network())

    @reactive.calc
    def mti_cached():
        return calculate_mti(current_network())

    @reactive.calc
    def keystoneness_cached():
        return calculate_keystoneness(current_network(), current_species_info()["meanB"].values)
```

(Note: `calculate_mti` and `calculate_keystoneness` are **already imported** at `app.py:31-32` — no import change needed.)

- [ ] **Step 2: Update render call sites (verified counts)**

The line numbers below are against the *current* file; Tasks 5 and 6 insert handlers earlier in `app.py`, so **grep for each call immediately before editing** and use the grep output, not these numbers. Repoint these call sites to the cached reactives:
- `calculate_keystoneness(...)` → `keystoneness_cached()` at **app.py:1172, 1198, 1248** (3 sites).
- `calculate_mti(...)` → `mti_cached()` at **app.py:1264** (1 site — `mti_heatmap`).
- `calculate_trophic_levels(...)` → `trophic_levels_cached()` at **app.py:939, 956** (2 sites — `trophic_level_histogram`, `trophic_levels_table`). **Do not skip these** — otherwise `trophic_levels_cached()` is created but unused and the TL perf goal is unmet. (Note: `get_topological_indicators` / `get_node_weighted_indicators` / the viz builders compute TL internally; leave those as-is for this task.)

Re-grep `calculate_mti(`, `calculate_keystoneness(`, `calculate_trophic_levels(` in `app.py` after editing to confirm no stray direct call remains in a render. The `pytest -q` gate will NOT catch a missed replacement (an unused cache doesn't fail), so verify by grep, not tests.

- [ ] **Step 3: Verify import + tests still pass**

Run: `micromamba run -n shiny python -c "import app; print('ok')"` then `micromamba run -n shiny python -m pytest -q`
Expected: `ok`; 70+ passed (the new analytic tests included).

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "perf: memoize trophic-level/MTI/keystoneness solves in reactive.calc"
```

---

## Phase 4 — Honesty & hygiene

### Task 8: Add `VERSION` file + reconcile numpy pins

**Files:**
- Create: `VERSION`
- Modify: `app.py:543` (hardcoded version), `requirements.txt`, `environment.yml`

- [ ] **Step 1: Create `VERSION`**

```
1.0.0
```

- [ ] **Step 2: Read it in `app.py`**

The current line is `app.py:543` = `ui.HTML("Version 1.0.0 | Python Shiny")` (a `ui.HTML`, with the `| Python Shiny` suffix). Preserve the element type and suffix, only sourcing the version from the file:

```python
        ui.HTML(f"Version {(Path(__file__).parent / 'VERSION').read_text(encoding='utf-8').strip() if (Path(__file__).parent / 'VERSION').exists() else 'unknown'} | Python Shiny"),
```

- [ ] **Step 3: Align numpy floor**

Set both files to the same floor. In `requirements.txt` change `numpy>=1.24.0` and in `environment.yml` change `numpy>=2.4.0` so both read `numpy>=2.0.0` (realistic for python 3.13). Verify the installed version satisfies it: `micromamba run -n shiny python -c "import numpy; print(numpy.__version__)"`.

- [ ] **Step 4: Verify + commit**

Run: `micromamba run -n shiny python -m pytest -q` → still green.
```bash
git add VERSION app.py requirements.txt environment.yml
git commit -m "fix: add VERSION single-source + reconcile numpy version floors"
```

---

### Task 9: Feedback honesty — fix GDPR text + stop leaking exceptions

**Files:**
- Modify: `app.py:664-665` (UI text), `app.py:739-741` (exception notification)

- [ ] **Step 1: Reconcile the "no personal data" claim**

Change the modal note at `app.py:664-665` to state what is actually attached:

```python
                ui.tags.small(
                    {"class": "text-muted", "style": "display:block; margin-top:8px;"},
                    "System info (app version, current tab, browser User-Agent, species and edge counts) "
                    "will be attached automatically to help diagnose issues.",
                ),
```

- [ ] **Step 2: Add the module logger (REQUIRED — app.py has none)**

`app.py` has no `logging` import or module logger (verified). The Step-3 replacement calls `logger.exception(...)`, so this is mandatory, not optional. Near the top of `app.py` (after the existing imports), add:

```python
import logging
logger = logging.getLogger("econetpy.app")
```

- [ ] **Step 3: Stop echoing raw exceptions**

Replace the catch-all at `app.py:739-741`:

```python
        except Exception as exc:
            logger.exception("feedback submission failed")
            ui.notification_show("Submission failed, please try again.", type="error", duration=6)
            return
```

- [ ] **Step 4: Verify + commit**

Run: `micromamba run -n shiny python -c "import app; print('ok')"`
```bash
git add app.py
git commit -m "fix: accurate feedback data-collection notice; don't leak exception text to users"
```

---

### Task 10: Low-risk cleanups (one commit)

**Files:** `app.py`, `network_analysis.py`, `network_viz.py`

- [ ] **Step 1: Per-session colors in biomass plots**

In `app.py`, in `biomass_by_group` (~998) and `biomass_distribution` (~1020), replace reads of the module-global `color_map` with a per-session derivation:

```python
        _, color_map = get_functional_group_colors(current_species_info()["fg"].tolist())
```

- [ ] **Step 2: Seed the example network**

In `app.py:create_example_network` replace the `np.random.uniform(...)` calls with a seeded generator:

```python
    rng = np.random.default_rng(0)
    # ... rng.uniform(10, 100, 10), rng.uniform(0.001, 10, 10), rng.uniform(0.1, 0.85, 10)
```

- [ ] **Step 3: Delete dead code**

- `app.py:867` and `:883` — remove the unused `filename = "...network.html"` assignments.
- `network_analysis.py:365` — remove the unused `pos_ind` computation.
- Prune pyflakes-confirmed unused imports: `app.py:11` `ImgData`, `:19` `json`, `:21` `Dict, List, Tuple, Optional`, `:25` `COLOR_SCHEME`; `network_analysis.py:16` `Tuple`, `:20` `fluxing, validate_flux_equilibrium`; `network_viz.py:10` `pandas as pd`, `:12` `Optional`. Run `micromamba run -n shiny python -m pyflakes app.py network_analysis.py network_viz.py` to confirm clean.

- [ ] **Step 4: Factor the duplicated pyvis physics options**

In `network_viz.py`, extract the ~45-line `set_options(...)` JSON shared by `create_topology_network` (64-109) and `create_flux_network` (204-249) into a helper `_base_physics_options() -> str` and call it from both, overriding only the edge-specific differences. Verify the render tests still pass.

- [ ] **Step 5: Verify everything green + commit**

Run: `micromamba run -n shiny python -m pytest -q`
Expected: all tests pass.
```bash
git add app.py network_analysis.py network_viz.py
git commit -m "chore: per-session colors, seed example net, prune dead code, dedup physics options"
```

---

## Self-Review checklist (done while writing)

- **Spec coverage:** the scientific core and the two dead UI features are fully covered — flux (#1), validator (#4b), MTI (#2), keystoneness (#3), omnivory+TL (#4), data editor (#5), download (#6), reactive.calc perf (#7), VERSION+numpy (#8), feedback notice+exception leak (#9), color_map/seed/dead-code/dup-physics (#10). The shallow-test theme is addressed by the analytic tests in #1–#4 and #4b. **This plan does NOT cover every review finding** — see "Deferred findings" below for the items intentionally left out and why.
- **Convention consistency:** `MTI[i,j] = impact of j on i` preserved across Task 2 (return `M.T`) and Task 3 (overall_effect `axis=0`). `current_species_info` / `current_network` reactive names used consistently in Tasks 5–7.
- **No placeholders:** every code step contains runnable code and an exact command with expected output.

## Deferred findings (from the original review, intentionally NOT in this plan)

Tracked here for honesty; each is a deliberate scope call, to be handled in a separate PR:

- **Security (defense-in-depth / scaling):** Bearer-token redirect stripping (`feedback_reporter.py:128-141`); per-session-resettable rate limit (`app.py:563,686`); unbounded NDJSON growth + no concurrent-write lock (`feedback_reporter.py:87-99`). Low risk for an internal single-worker tool.
- **Data minimization (S1):** Task 9 makes the feedback notice *honest* about User-Agent capture but does not stop collecting it or remove it from the public GitHub issue body. If GDPR minimization is required, follow up by coarsening `browser_info` to browser family only.
- **Reactivity/UX:** frozen `footer_info` clock (`app.py:579-585`); no error surfacing in the heavier render functions beyond the editor gate added in Task 5 (R6 — broader render-level try/except deferred); 1300-line monolith / per-tab `lambda` UI rebuild (R7, structural).
- **Quality:** `pyvis` git-URL pin onboarding trap (Q3 — the fork is required, so no change, just document in README); `calculate_losses` pass-through wrapper vs `calculate_losses_allometric` used by the app (Q7 — verify intended before changing, borderline correctness); magic numbers vs the `network_analysis` constants (Q9); residual `print()`→logging sweep in `load_data.py` (Q6); misc Q11 (bare `except`, loose typing, stale module docstring, `met.types` R-ism).
- **Tests:** feedback handler / rate-limit / `submit_feedback` body unit tests (T1/T7 — pure-logic-testable even without a Shiny harness; worth adding alongside #9 to lock the S1 disclosure to the actual issue body); `load_default_data` fallback chain (T2); `calculate_flux_indicators` (T3); strengthen weak edge-case assertions and `pytest.warns` the 8 warnings (T6/T9); `network_viz` builder numeric logic (T8).

## Downstream effects to expect (note in the PR description)

- **Flux magnitudes drop ~6 orders of magnitude** on BalticFW (prey total ≈ 3387 → ≈ 0.0057) — the old numbers were wrong; the new ones satisfy energy balance to ~1e-17. The `flux_heatmap` log epsilon (`+1e-10`, ~`app.py:1119`) was sized for the old ~1000-scale fluxes; check the heatmap still renders meaningfully and lower the epsilon if it flattens the scale.
- **Keystoneness re-classification churn:** on BalticFW ~half the species change status under the Libralato formula + median threshold (old `{Keystone:28,...}` → new `{Rare:17, Keystone:15, Dominant:2}`). Any narrative keyed on the old "28 keystone species" must be re-read. Intended, but call it out.
- **Omnivory shifts +~0.11** (0.418 → 0.524 on BalticFW) from ddof=1; **mean TL is unchanged** (binary acyclic web). Both as predicted.

## Notes / risks for the implementer

- Tasks 1–4 are independent and can be done/reviewed in any order; 3 depends on 2 (keystoneness uses the corrected MTI) — do 2 before 3.
- Tasks 5–7 touch `app.py`; do them sequentially to avoid edit conflicts. Task 7 depends on the imports added there.
- The MTI/keystoneness conventions were hand-derived against a 2-species case (no R reference exists for these in `Script.R`). If the original MarineSABRES R source is later located, cross-check the BalticFW output against it and adjust the classification thresholds if needed.
- No Shiny test harness exists, so Tasks 5–6 rely on manual verification — capture a screenshot or note the observed behavior in the commit/PR.

## Plan review (2026-06-13, 4-angle adversarial pass) — corrections applied

A 4-angle review (math / codebase-accuracy / framework-API / executability) was run against this plan. The Phase-1 math was independently re-derived and run on throwaway copies (full suite stayed 67 passed; the 5 new tests passed) — **all four scientific fixes and every analytic expected-value are correct**. Corrections folded in above:
- **Task 6** handler rewritten to the real keyword builder signatures (the shorthand would have raised `TypeError`).
- **Task 7** call-site counts corrected (1 `calculate_mti`, not 4) and the 2 missed `calculate_trophic_levels` sites (939, 956) added.
- **Task 8** version edit corrected to preserve `ui.HTML(... | Python Shiny)`.
- **Task 3** test-break hedge replaced with the verified fact that no existing test asserts the changed numbers.

Two non-blocking caveats from the math review (no action required, noted for the implementer):
- **Task 4 cycle test** passes because an unanchored 2-cycle hits the `LinAlgError`→`lstsq` fallback and returns `[0, 0]` — that satisfies "doesn't diverge" but isn't an ecologically meaningful TL. To assert something stronger, anchor the cycle with a basal feeder (e.g. add edge `2→0`) and check the basal node's TL `== 1`.
- **Task 1 test**: node 0's balance residual is intentionally nonzero (it's the grounded basal/producer row, which has no assimilation-balance equation); only consumer nodes 1 and 2 are asserted. The inline test comment already states this.
