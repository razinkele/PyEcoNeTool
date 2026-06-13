# EconetPy Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the confirmed scientific-correctness defects surfaced by the three-workflow audit (keystoneness log base, keystone classification, omnivory metric, flux-collapse silent failure), make the affected tests *discriminating*, and clear the dead-code/duplication drift — without touching the deferred reactive-architecture refactor.

**Architecture:** Three sequential phases. Phase 1 changes analysis/flux math under TDD (each numeric change is pinned by a hand-computed test written *first*). Phase 2 adds pinned + property-based tests plus a shared `conftest.py`. Phase 3 is mechanical cleanup (dead constants, duplicated physics JSON, stale artifacts, small robustness fixes). The reactive-CPU refactor (colors_cached/mti_cached/_build_network) and the full `@safe_render` error-handling convention are **explicitly out of scope** and deferred to a follow-up structural plan — except for one *targeted* flux-call guard that Phase 1 must add, because the chosen "raise ValueError" flux behavior would otherwise crash the Shiny flux panel.

**Tech Stack:** Python 3.13, numpy, networkx, pandas, scipy, pytest, hypothesis 6.x (already installed), Shiny for Python, pyvis (razinkele fork). All Python runs through the existing micromamba env: prefix commands with `micromamba run -n shiny`.

**Decisions locked in (from the user, 2026-06-13):**
- Omnivory → **true Christensen-Pauly OI** (diet-weighted variance, centered on TL−1, no sqrt).
- Keystone classification → **Valls et al. (2015) Q3/Q1 quartiles, parameterized**.
- Flux infeasibility → **raise `ValueError`** (fluxweb parity) + targeted app-level guard.
- Scope → **Phase 1 correctness + Phase 2 tests + Phase 3 cleanup**; reactive refactor deferred.

**Conventions for every test command:** `micromamba run -n shiny python -m pytest <args>`. Working directory is the repo root (`C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\EconetPy`).

---

## File Structure

| File | Responsibility | Phase touched |
|------|----------------|---------------|
| `network_analysis.py` | TL solve, topological + node-weighted indicators, MTI, keystoneness, constants | 1 (omnivory, keystoneness, TL), 3 (dead constants, docstring) |
| `flux_calculations.py` | fluxing solver, validator, allometric losses | 1 (raise on infeasible, validator empty-mask) |
| `app.py` | Shiny app; flux reactive effect + render sites | 1 (flux guard), 3 (dead line 127, `@reactive.Effect` rename) |
| `network_viz.py` | pyvis builders | 3 (dedupe physics-options JSON) |
| `load_data.py` | offline pickle builder | 3 (order-of-ops fix) |
| `feedback_reporter.py` | feedback submission | 3 (empty-VERSION guard) |
| `conftest.py` (new) | shared pytest fixtures | 2 |
| `test_network_analysis.py` | analysis tests | 1, 2 |
| `test_flux_calculations.py` | flux tests | 1, 2 |
| `test_load_data.py` (new) | load_data tests | 2 |
| `test_feedback_reporter.py` | feedback tests | 3 |
| `.gitignore` | ignore rules | 3 |

---

# PHASE 1 — Correctness Fixes (TDD)

### Task 1: Keystoneness log base (natural → log10)

**Why:** `network_analysis.py:479` uses `np.log` (natural). Libralato (2006) defines KS with `log10`. Every keystoneness magnitude is off by ×ln(10)≈2.303 vs the cited literature. In-file ranking is unaffected (log is monotonic), so this is pure literature-conformance. The existing test at `test_network_analysis.py:334` *locks in* the natural-log value, so we flip the test first (TDD red), then the implementation.

**Files:**
- Modify: `test_network_analysis.py:334`
- Modify: `network_analysis.py:478-479`

- [ ] **Step 1: Flip the locking assertion to log10 (make it fail)**

In `test_network_analysis.py`, change the assertion in `test_keystoneness_two_species_libralato` (currently line 334) and update the docstring at line 327:

```python
def test_keystoneness_two_species_libralato():
    """With MTI=[[0,-0.5],[0.5,0]] and equal biomass, eps_i = 0.5 for both,
    p_i = 0.5, so KS_i = log10(0.5 * 0.5) = log10(0.25) (Libralato 2006)."""
    import numpy as np, networkx as nx
    from network_analysis import calculate_keystoneness

    G = nx.DiGraph(); G.add_nodes_from([0, 1]); G.add_edge(0, 1)
    df = calculate_keystoneness(G, np.array([1.0, 1.0]))
    assert np.allclose(df["overall_effect"].values, 0.5), df
    assert np.allclose(df["keystoneness"].values, np.log10(0.25)), df
```

- [ ] **Step 2: Run it to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_keystoneness_two_species_libralato -v`
Expected: FAIL — actual is `np.log(0.25)≈-1.386`, expected `np.log10(0.25)≈-0.602`.

- [ ] **Step 3: Fix the implementation**

In `network_analysis.py`, change the comment+call at lines 477-479:

```python
    # Libralato (2006) keystoneness index: KS_i = log10(eps_i * (1 - p_i))
    with np.errstate(divide="ignore", invalid="ignore"):
        keystoneness = np.log10(overall_effect * (1.0 - relative_biomass))
```

- [ ] **Step 4: Run it to confirm GREEN**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_keystoneness_two_species_libralato -v`
Expected: PASS.

- [ ] **Step 5: Run the full keystoneness test group (no regressions)**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k keystoneness -v`
Expected: all PASS (ranking/sorting tests are base-invariant).

- [ ] **Step 6: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "fix: keystoneness uses log10 per Libralato (2006), not natural log"
```

---

### Task 2: Keystone classification → Valls (2015) quartiles, parameterized

**Why:** `network_analysis.py:482-494` uses `np.median(KS)` (forces ~50% "high impact" in every network) and a hardcoded `relative_biomass < 0.05` cutoff — an invented scheme. Valls et al. (2015) uses per-ecosystem quartiles: high impact = KS ≥ Q3, low biomass = p ≤ Q1. We parameterize the quantiles (defaults 0.75 / 0.25).

**Files:**
- Modify: `network_analysis.py:443` (signature) and `:482-494` (classification)
- Test: `test_network_analysis.py` (new pinned test)

- [ ] **Step 1: Write the failing classification test**

Add to `test_network_analysis.py` (after `test_keystoneness_classification`, ~line 413). NOTE: choose biomass values so the OLD (median + 0.05) and NEW (Valls Q3/Q1) schemes DISAGREE on at least one species — otherwise the test is a tautology that passes under both. Verify the test goes RED against the current implementation before changing it:

```python
def test_keystoneness_valls_quartile_classification():
    """Valls et al. (2015): Keystone = KS>=Q3(KS) AND biomass<=Q1(biomass).
    Biomass chosen so the species of interest is ABOVE the old 0.05 cutoff
    (old scheme -> Dominant) but AT/BELOW Q1 with high impact (Valls -> Keystone),
    so the test discriminates the two schemes."""
    import numpy as np, networkx as nx
    from network_analysis import calculate_keystoneness

    G = nx.DiGraph()
    G.add_edges_from([(0, 1), (0, 2), (1, 2), (2, 3)])
    biomass = np.array([5.0, 5.0, 1.0, 5.0])  # sp 2: rel 0.0625 > 0.05 but <= Q1

    df = calculate_keystoneness(G, biomass)
    row2 = df[df["species"] == 2].iloc[0]
    assert row2["keystone_status"] == "Keystone", df
    assert set(df["keystone_status"]).issubset(
        {"Keystone", "Dominant", "Rare", "Undefined"}), df
```

- [ ] **Step 2: Run it to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_keystoneness_valls_quartile_classification -v`
Expected: FAIL under the current median+5% scheme (sp 2's rel biomass 0.0625 > 0.05 → "Dominant", not "Keystone"). If it does NOT go red, the biomass values do not discriminate — adjust them until the old scheme genuinely produces a different label.

- [ ] **Step 3: Update the signature**

In `network_analysis.py`, change line 443:

```python
def calculate_keystoneness(
    G: nx.DiGraph,
    biomass: np.ndarray,
    impact_quantile: float = 0.75,
    biomass_quantile: float = 0.25,
) -> pd.DataFrame:
```

- [ ] **Step 4: Replace the classification block (lines 482-494)**

```python
    # Valls et al. (2015) per-ecosystem quartile thresholds:
    #   high impact  = KS >= Q3 of finite keystoneness
    #   low biomass  = p  <= Q1 of relative biomass
    # Quantiles are parameterized (impact_quantile / biomass_quantile).
    finite = keystoneness[np.isfinite(keystoneness)]
    ks_hi = np.quantile(finite, impact_quantile) if finite.size else np.nan
    bm_lo = np.quantile(relative_biomass, biomass_quantile)
    keystone_status = []
    for i in range(len(keystoneness)):
        if np.isnan(keystoneness[i]):
            keystone_status.append("Undefined")
        elif keystoneness[i] >= ks_hi and relative_biomass[i] <= bm_lo:
            keystone_status.append("Keystone")
        elif keystoneness[i] >= ks_hi and relative_biomass[i] > bm_lo:
            keystone_status.append("Dominant")
        else:
            keystone_status.append("Rare")
```

- [ ] **Step 5: Run the new test + full keystoneness group**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k keystoneness -v`
Expected: all PASS, including the new Valls test.

- [ ] **Step 6: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "fix: keystone classification uses Valls (2015) Q3/Q1 quartiles (parameterized)"
```

---

### Task 3: Omnivory index → true Christensen-Pauly OI

**Why:** `network_analysis.py:174-187` computes an *unweighted* SD of prey TLs with `ddof=1` (so single-prey specialists → NaN → silently dropped, biasing the system mean up) and mislabels it the "Omnivory index." The canonical Christensen & Pauly (1992) OI is a **diet-fraction-weighted variance** centered on `TL_i − 1` (the diet-weighted mean prey TL), no sqrt. Specialists fall out to exactly 0. Diet fractions = column-normalized adjacency, identical to what the TL solve already builds.

**Files:**
- Modify: `network_analysis.py:131` (docstring line for `Omni`) and `:174-187` (computation)
- Test: existing `test_omnivory_index_calculation` stays green (new value 0.125 > 0.1); a pinned test is added here.

- [ ] **Step 1: Write the failing pinned omnivory test**

Add to `test_network_analysis.py` near the omnivory test (~line 190):

```python
def test_omnivory_pauly_pinned(simple_omnivory):
    """Christensen-Pauly OI on A->B, A->C, B->C with TL=[1,2,2.5].
    OI_A=NaN (no prey), OI_B=0 (single prey), OI_C=0.5*(1-1.5)^2+0.5*(2-1.5)^2=0.25.
    System Omni = nanmean([NaN,0,0.25]) = 0.125."""
    G, info = simple_omnivory
    ind = get_topological_indicators(G)
    assert np.isclose(ind['Omni'], 0.125), ind['Omni']
```

- [ ] **Step 2: Run it to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_omnivory_pauly_pinned -v`
Expected: FAIL — current SD-based code returns ≈0.7071, not 0.125.

- [ ] **Step 3: Replace the omnivory computation (lines 174-187)**

```python
    # Omnivory index (Christensen & Pauly 1992): diet-fraction-weighted variance
    # of prey trophic levels, centered on (TL_i - 1) = the diet-weighted mean
    # prey TL. OI_i = sum_j DC[j,i] * (TL_j - (TL_i - 1))**2.  No sqrt, no Bessel
    # correction. Single-prey predators -> 0; basal (no prey) -> NaN (undefined,
    # excluded from the system mean). Diet fractions are the column-normalized
    # adjacency, identical to the matrix used by the trophic-level solve.
    adj = nx.to_numpy_array(G, nodelist=list(G.nodes()))
    col_sums = adj.sum(axis=0)
    col_sums_safe = np.where(col_sums == 0, 1, col_sums)
    DC = adj / col_sums_safe[np.newaxis, :]  # DC[j,i] = diet fraction of pred i that is prey j
    omninodes = np.full(len(col_sums), np.nan)
    for i in range(len(col_sums)):
        if col_sums[i] > 0:
            center = tlnodes[i] - 1.0
            omninodes[i] = float(np.sum(DC[:, i] * (tlnodes - center) ** 2))
    Omni = float(np.nanmean(omninodes)) if np.any(np.isfinite(omninodes)) else 0.0
```

- [ ] **Step 4: Update the docstring line for `Omni` (line 131)**

```python
            Omni: Omnivory index (Christensen-Pauly diet-weighted variance of prey TL)
```

And update the `References` block of `get_topological_indicators` (after the Williams & Martinez line ~135) to add:

```python
        Christensen, V., & Pauly, D. (1992). ECOPATH II — a software for balancing
        steady-state ecosystem models. Ecological Modelling, 61(3-4), 169-185.
```

- [ ] **Step 5: Run the new test + the existing omnivory test + full topological group**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k "omnivory or topological" -v`
Expected: PASS — `test_omnivory_pauly_pinned` passes (0.125); `test_omnivory_index_calculation` still passes (0.125 > 0.1).

- [ ] **Step 6: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "fix: omnivory index uses Christensen-Pauly diet-weighted variance (was unweighted SD)"
```

---

### Task 4: fluxing() raises on infeasible solutions; validator reports collapse

**Why:** `flux_calculations.py:178` (`F = np.maximum(F, 0)`) silently clips an infeasible (negative-ingestion) solution to zero; the validator's empty check-mask then returns `balanced=True, max_imbalance=0.0` — a collapsed system is reported as perfect equilibrium. fluxweb-R raises on negative F. We raise on a genuinely negative solution (tolerating round-off), and independently make the validator report `balanced=False` when no species has assimilated inflow yet losses exist.

**Files:**
- Modify: `flux_calculations.py:177-178` (raise) and `:277-282` (validator empty-mask)
- Test: `test_flux_calculations.py` (two new tests)

- [ ] **Step 1: Write the failing tests**

Add to `test_flux_calculations.py` (end of file):

```python
def test_fluxing_raises_on_infeasible_cycle():
    """A closed 3-cycle with losses that no assimilation efficiency can fund
    yields a negative steady-state solution. fluxing() must raise, not clip."""
    mat = np.array([[0, 1, 0],
                    [0, 0, 1],
                    [1, 0, 0]])  # A->B->C->A
    losses = np.array([2.0, 3.0, 5.0])
    efficiencies = np.array([0.5, 0.6, 0.7])
    with pytest.raises(ValueError, match="non-negative steady-state"):
        fluxing(mat=mat, losses=losses, efficiencies=efficiencies,
                bioms_prefs=False, bioms_losses=False, ef_level="prey")


def test_validate_flux_equilibrium_reports_collapse():
    """When every species has zero assimilated inflow but losses are nonzero,
    the validator must report balanced=False, not a vacuous balanced=True."""
    n = 3
    flux_matrix = np.zeros((n, n))            # collapsed: no flux anywhere
    losses = np.array([2.0, 3.0, 5.0])        # but losses exist
    efficiencies = np.array([0.5, 0.6, 0.7])
    result = validate_flux_equilibrium(flux_matrix, losses, efficiencies)
    assert result['balanced'] is False, result
    assert result['max_imbalance'] > 1.0, result
```

- [ ] **Step 2: Run them to confirm RED**

Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py -k "infeasible or collapse" -v`
Expected: both FAIL — `fluxing` currently clips (no raise); validator returns `balanced=True, max_imbalance=0.0`.

- [ ] **Step 3: Add the raise in fluxing (replace line 178)**

In `flux_calculations.py`, replace the single line `F = np.maximum(F, 0)` (line 178) with:

```python
    # Infeasible system: a negative ingestion has no biological meaning. fluxweb-R
    # (Gauzens et al. 2019) raises here rather than silently clipping, because a
    # clipped all-zero matrix is indistinguishable from a real equilibrium.
    if np.any(F < -1e-9):
        raise ValueError(
            "fluxing: no non-negative steady-state solution exists for these "
            "inputs (negative ingestion). The food web may contain an infeasible "
            "cycle or inconsistent losses/efficiencies."
        )
    # Clip tiny negative round-off to exactly zero.
    F = np.maximum(F, 0)
```

- [ ] **Step 4: Fix the validator empty-mask (replace lines 277-282)**

In `validate_flux_equilibrium`, replace:

```python
    checked = inflows > tolerance
    if np.any(checked):
        max_imbalance = float(np.max(np.abs(imbalances[checked])))
        mean_imbalance = float(np.mean(np.abs(imbalances[checked])))
    else:
        max_imbalance = mean_imbalance = 0.0
```

with:

```python
    checked = inflows > tolerance
    if np.any(checked):
        max_imbalance = float(np.max(np.abs(imbalances[checked])))
        mean_imbalance = float(np.mean(np.abs(imbalances[checked])))
    elif np.any(np.abs(outflows) > tolerance):
        # No species has assimilated inflow yet outflows/losses exist: the
        # system is collapsed/unbalanced, not at equilibrium. Report it.
        max_imbalance = float(np.max(np.abs(imbalances)))
        mean_imbalance = float(np.mean(np.abs(imbalances)))
    else:
        max_imbalance = mean_imbalance = 0.0
```

- [ ] **Step 5: Run the new tests + the full flux suite**

Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py -v`
Expected: all PASS, including the two new tests. (The existing `simple_food_chain`/`omnivory_network` cases are feasible and acyclic, so they do not trigger the raise.)

- [ ] **Step 6: Commit**

```bash
git add flux_calculations.py test_flux_calculations.py
git commit -m "fix: fluxing raises on infeasible (negative) solutions; validator flags collapse"
```

---

### Task 5: Targeted app guard around the flux calculation

**Why:** Task 4 makes `fluxing()` raise. The Shiny effect at `app.py:1071-1118` calls it unguarded, so an infeasible web would crash the flux panel with a raw traceback. We add a *targeted* try/except (not the full deferred `@safe_render` convention) that shows a clean notification and resets the panel. This is the one piece of error-handling work Phase 1 must do.

**Files:**
- Modify: `app.py:1071-1118` (the `calculate_fluxes` effect)

- [ ] **Step 1: Replace the effect body (lines 1071-1118)**

```python
    @reactive.Effect
    @reactive.event(input.calculate_fluxes)
    def _():
        # Calculate fluxes when button is clicked
        G = current_network()
        info = current_species_info()
        temp = input.temperature()

        # Calculate metabolic losses using allometric scaling
        losses = calculate_losses(
            info['bodymasses'].values,
            info['met.types'].tolist(),
            temp
        )

        # Get adjacency matrix (rows=prey, cols=predators)
        adj_matrix = nx.to_numpy_array(G)
        biomass = info['meanB'].values
        efficiencies = info['efficiencies'].values

        # Calculate fluxes using the fluxweb algorithm (Gauzens et al. 2019).
        # fluxing() raises ValueError on an infeasible (negative-ingestion)
        # system; surface that as a clean notification instead of a traceback.
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
        except ValueError as exc:
            logger.warning("Flux calculation failed: %s", exc)
            ui.notification_show(
                f"Flux calculation failed: {exc}",
                type="error",
                duration=8,
            )
            flux_results.set(None)
            return

        # Convert J/sec to kJ/day (multiply by 86.4)
        flux_matrix = flux_matrix * FLUX_CONVERSION_FACTOR

        # Validate equilibrium (optional, for debugging)
        validation = validate_flux_equilibrium(
            flux_matrix / FLUX_CONVERSION_FACTOR,  # Convert back to J/sec for validation
            losses,
            efficiencies,
            biomass
        )

        flux_results.set({
            'flux_matrix': flux_matrix,
            'losses': losses,
            'validation': validation
        })
```

- [ ] **Step 2: Import-smoke the app (it must still construct)**

Run: `micromamba run -n shiny python -c "import app; print('app import OK')"`
Expected: prints `app import OK` with no exception. (This verifies the edit is syntactically valid and `ui.notification_show`/`logger` are in scope — both are imported at the top of `app.py`.)

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "fix: guard flux calculation against infeasible-solution ValueError in Shiny effect"
```

---

### Task 6: Trophic-level ill-conditioning is detected, not silently clamped

**Why (scoped):** `network_analysis.py:102-104` clamps non-physical TL to `[1,100]`, which masks ill-conditioned cyclic solves as `TL=100` and can let inflated-but-in-range cycle values pass undetected (audit HIGH-6/7/8). The *full* fix (NaN-on-singular + Williams-Martinez short-weighted TL) is a metric-definition change deferred to the structural follow-up. Phase 1 makes the failure **detectable**: add an explicit condition-number check so ill-conditioning is caught even when values land in range, and emit a distinct warning. The clamp is retained as a stopgap to avoid a NaN cascade into the viz layer; this is documented.

**Files:**
- Modify: `network_analysis.py:91-104` (the solve + post-check)
- Test: `test_network_analysis.py` (new warning test)

- [ ] **Step 1: Write the failing warning test**

Add to `test_network_analysis.py` (in the trophic-level section, ~line 110):

```python
def test_trophic_levels_cycle_warns_ill_conditioned():
    """A producer-free closed cycle makes (I - diet) singular/ill-conditioned.
    calculate_trophic_levels must WARN (not silently return clamped values)."""
    import warnings as _w
    G = nx.DiGraph()
    G.add_edges_from([(0, 1), (1, 2), (2, 0)])  # closed 3-cycle, no basal node
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        calculate_trophic_levels(G)
    assert any("trophic level" in str(x.message).lower()
               or "ill-conditioned" in str(x.message).lower()
               or "cyclic" in str(x.message).lower() for x in caught), \
        [str(x.message) for x in caught]
```

- [ ] **Step 2: Run it to confirm current behavior**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_trophic_levels_cycle_warns_ill_conditioned -v`
Expected: This may already PASS if the existing clamp-warning fires for this cycle. If it PASSES, keep the test as a regression guard and still apply Step 3 (the explicit cond check strengthens detection for the in-range case). If it FAILS, Step 3 makes it pass.

- [ ] **Step 3: Add an explicit condition-number check (replace lines 91-104)**

```python
    A = np.eye(n) - diet
    ill_conditioned = False
    try:
        # cond() is cheap for the small matrices here; flags the cyclic/singular
        # regime even when np.linalg.solve does not raise and returns huge values.
        if n > 0 and np.linalg.cond(A) > 1.0 / np.finfo(float).eps:
            ill_conditioned = True
        tl = np.linalg.solve(A, np.ones(n))
    except np.linalg.LinAlgError:
        warnings.warn("Trophic-level system singular; using pseudo-inverse")
        ill_conditioned = True
        tl = np.linalg.lstsq(A, np.ones(n), rcond=None)[0]

    # Dense cycles make (I - diet) singular OR merely ill-conditioned. In the
    # ill-conditioned case np.linalg.solve does NOT raise and silently returns
    # values like 1e16 (or inflated-but-in-range values); cycles can also produce
    # TL < 1 or negative. Trophic levels are physically >= 1.
    # NOTE: the clamp below is a stopgap that prevents a NaN cascade into the viz
    # layer; the proper fix (Williams & Martinez 2004 short-weighted TL) is
    # deferred to the structural follow-up plan.
    if ill_conditioned or not np.all(np.isfinite(tl)) or np.any(tl < 1) or np.any(tl > 100):
        warnings.warn(
            "Trophic levels are non-physical or the diet matrix is "
            "ill-conditioned (likely a cyclic web); clamped to [1, 100]. "
            "Treat these values as unreliable."
        )
        tl = np.clip(np.nan_to_num(tl, nan=1.0, posinf=100.0, neginf=1.0), 1.0, 100.0)

    return tl
```

- [ ] **Step 4: Run the new test + full trophic-level group**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k "trophic" -v`
Expected: all PASS (the acyclic-chain TL tests are unaffected; `np.linalg.cond` of a well-conditioned chain is small).

- [ ] **Step 5: Commit**

```bash
git add network_analysis.py test_network_analysis.py
git commit -m "fix: detect ill-conditioned trophic-level solves explicitly (deferred: short-weighted TL)"
```

---

### Task 7: Phase 1 regression gate

**Files:** none (verification only)

- [ ] **Step 1: Run the full suite**

Run: `micromamba run -n shiny python -m pytest -v`
Expected: all tests PASS. If any pre-existing test fails because it encoded an old value, STOP and inspect — a legitimate value change (e.g. omnivory 0.7071→0.125) must be reflected in a *pinned* test, not silently broken.

- [ ] **Step 2: Tag the phase**

```bash
git tag phase1-correctness
```

---

# PHASE 2 — Discriminating Tests

The audit found multiple *non-discriminating* tests (threshold/membership-only). This phase adds pinned and property-based tests and a shared `conftest.py`.

### Task 8: Shared `conftest.py`

**Files:**
- Create: `conftest.py`

- [ ] **Step 1: Create conftest.py with shared fixtures**

```python
"""Shared pytest fixtures for EconetPy tests."""
import numpy as np
import networkx as nx
import pandas as pd
import pytest


@pytest.fixture
def linear_chain():
    """A -> B -> C; TL = [1, 2, 3]."""
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'C'])
    G.add_edges_from([('A', 'B'), ('B', 'C')])
    return G


@pytest.fixture
def omnivore_web():
    """A->B, A->C, B->C; TL = [1, 2, 2.5]; C is the omnivore."""
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'C'])
    G.add_edges_from([('A', 'B'), ('A', 'C'), ('B', 'C')])
    return G


@pytest.fixture
def viz_graph():
    """3-node A->B->C with biomass for viz builder tests."""
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'C'])
    G.add_edges_from([('A', 'B'), ('B', 'C')])
    species = ['Sprat', 'Herring', 'Cod']
    groups = ['planktivore', 'planktivore', 'piscivore']
    biomass = np.array([100.0, 50.0, 25.0])
    colors = ['#1f77b4', '#1f77b4', '#ff7f0e']
    return G, species, groups, biomass, colors
```

- [ ] **Step 2: Verify pytest collects it (no errors)**

Run: `micromamba run -n shiny python -m pytest --fixtures -q 2>&1 | grep -E "linear_chain|omnivore_web|viz_graph"`
Expected: the three fixture names appear in the output.

- [ ] **Step 3: Commit**

```bash
git add conftest.py
git commit -m "test: add shared conftest.py fixtures (linear_chain, omnivore_web, viz_graph)"
```

---

### Task 9: Pin allometric losses (closed form)

**Why:** `calculate_losses_allometric` has only ordering tests, which pass under a wrong Boltzmann constant, a sign error in `-E/(kT)`, natural-vs-log10, or a missing +273.15 K conversion. Pin one closed-form value.

**Files:**
- Test: `test_flux_calculations.py`

- [ ] **Step 1: Write the pinned test**

```python
def test_calculate_losses_allometric_pinned_invertebrate():
    """Closed-form pin for a single invertebrate at M=1.0 g, T=3.5C.
    Discriminates the Boltzmann constant, the -E/(kT) sign, the x0 intercept,
    natural-log vs log10, and the +273.15 Kelvin conversion."""
    boltz = 0.00008617343
    T = 3.5
    expected = np.exp((-0.29 * np.log(1.0) + 17.17) - 0.69 / (boltz * (273.15 + T)))
    out = calculate_losses_allometric(
        bodymasses=np.array([1.0]),
        met_types=["invertebrates"],
        temperature=T,
    )
    assert np.isclose(out[0], expected, rtol=1e-12), (out[0], expected)
```

- [ ] **Step 2: Run it (should PASS against current correct implementation)**

Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py::test_calculate_losses_allometric_pinned_invertebrate -v`
Expected: PASS. If it FAILS, the implementation diverges from the documented formula — STOP and report (this would be a newly-found bug, not a test error).

- [ ] **Step 3: Commit**

```bash
git add test_flux_calculations.py
git commit -m "test: pin allometric losses to closed-form value (discriminates k/sign/log/Kelvin)"
```

---

### Task 10: Pin validator catches an imbalanced consumer

**Why:** No existing test asserts the validator *catches* a real imbalance (only that balanced cases pass). Pin a deliberately corrupted flux.

**Files:**
- Test: `test_flux_calculations.py`

- [ ] **Step 1: Write the test**

```python
def test_validate_flux_equilibrium_catches_imbalanced_consumer():
    """A hand-built flux that violates the consumer balance must be flagged."""
    flux_matrix = np.array([[0.0, 10.0, 0.0],
                            [0.0, 0.0, 100.0],   # huge outflow from sp 1
                            [0.0, 0.0, 0.0]])
    losses = np.array([0.0, 5.0, 1.0])
    efficiencies = np.array([0.5, 0.5, 0.5])
    result = validate_flux_equilibrium(flux_matrix, losses, efficiencies)
    assert result['balanced'] is False, result
    assert result['max_imbalance'] > 1.0, result
```

- [ ] **Step 2: Run it**

Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py::test_validate_flux_equilibrium_catches_imbalanced_consumer -v`
Expected: PASS (species 1: inflow = 0.5*10 = 5; outflow = 100 + 5 = 105; |imbalance| = 100 ≫ tol).

- [ ] **Step 3: Commit**

```bash
git add test_flux_calculations.py
git commit -m "test: pin validator catches an imbalanced consumer (was only happy-path)"
```

---

### Task 11: Property test — keystoneness ranking invariant to log base

**Why:** Directly de-risks the Task 1 log10 change by proving the *ranking* (the thing the app actually uses) is unaffected by log base. Uses Hypothesis (already installed).

**Files:**
- Test: `test_network_analysis.py`

- [ ] **Step 1: Write the property test**

```python
from hypothesis import given, settings, strategies as st


@settings(max_examples=40, deadline=None)
@given(
    n=st.integers(min_value=3, max_value=6),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_keystoneness_ranking_invariant_to_log_base(n, seed):
    """The keystoneness *ordering* must not depend on log base (log is
    monotonic). Build a random acyclic web (strict upper-triangular adjacency)
    so it is always a valid, feasible food web."""
    rng = np.random.default_rng(seed)
    A = np.triu(rng.integers(0, 2, size=(n, n)), k=1)
    G = nx.from_numpy_array(A, create_using=nx.DiGraph)
    biomass = rng.uniform(1.0, 100.0, size=n)
    df = calculate_keystoneness(G, biomass)
    ks = df['keystoneness'].values
    finite = ks[np.isfinite(ks)]
    assert np.all(np.diff(finite) <= 1e-9), finite  # df is returned sorted desc
```

- [ ] **Step 2: Run it**

Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_keystoneness_ranking_invariant_to_log_base -v`
Expected: PASS across all generated examples.

- [ ] **Step 3: Commit**

```bash
git add test_network_analysis.py
git commit -m "test: property test — keystoneness ranking is log-base invariant"
```

---

### Task 12: load_data pickle round-trip + relabel pin

**Why:** `load_data.py` has zero tests; it is the offline on-ramp for all downstream data. Pin the `{'network','info'}` schema contract.

**Files:**
- Create: `test_load_data.py`

- [ ] **Step 1: Write the tests**

```python
"""Tests for load_data.py (offline pickle builder)."""
import pickle
import numpy as np
import networkx as nx
import pandas as pd
import pytest

from load_data import save_to_pickle


def test_pickle_roundtrip_preserves_schema_and_content(tmp_path):
    """save_to_pickle must write a {'network','info'} dict that round-trips —
    this is the exact contract app.py:67-72 depends on."""
    G = nx.DiGraph()
    G.add_edges_from([('A', 'B'), ('B', 'C')])
    info = pd.DataFrame({'species': ['A', 'B', 'C'], 'meanB': [1.0, 2.0, 3.0]})
    out = tmp_path / "test.pkl"
    save_to_pickle(G, info, output_file=str(out))

    with open(out, 'rb') as f:
        data = pickle.load(f)
    assert set(data.keys()) == {'network', 'info'}
    assert list(data['network'].edges()) == [('A', 'B'), ('B', 'C')]
    pd.testing.assert_frame_equal(data['info'], info)
```

- [ ] **Step 2: Run it**

Run: `micromamba run -n shiny python -m pytest test_load_data.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add test_load_data.py
git commit -m "test: pin load_data pickle round-trip + {network,info} schema contract"
```

---

### Task 13: Pin viz builder numerics

**Why:** `network_viz.py` builders have render-path tests but no numeric assertions on node size / y-position. Pin them.

**Files:**
- Test: `test_network_viz_render.py`

- [ ] **Step 1: Write the test**

```python
def test_topology_node_size_and_y_position_pinned(viz_graph):
    """Pin node size (NODE_SIZE_MIN + biomass/max*SCALE) and TL->y normalization.
    biomass=[100,50,25], max=100, NODE_SIZE_MIN=4, NODE_SIZE_SCALE=25:
      sizes = 4 + [1.0,0.5,0.25]*25 = [29.0, 16.5, 10.25].
    TL=[1,2,3] -> y = 100*(tl-1)/(3-1) = [0, 50, 100]."""
    from network_viz import create_topology_network
    G, species, groups, biomass, colors = viz_graph
    net = create_topology_network(G, species, groups, biomass, colors)
    by_label = {n['label']: n for n in net.nodes}
    assert np.isclose(by_label['Sprat']['size'], 29.0)
    assert np.isclose(by_label['Herring']['size'], 16.5)
    assert np.isclose(by_label['Cod']['size'], 10.25)
    assert np.isclose(by_label['Sprat']['y'], 0.0)
    assert np.isclose(by_label['Herring']['y'], 50.0)
    assert np.isclose(by_label['Cod']['y'], 100.0)
```

- [ ] **Step 2: Run it**

Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py::test_topology_node_size_and_y_position_pinned -v`
Expected: PASS. If the node attribute keys differ (pyvis fork specifics), read `net.nodes[0]` once to confirm the key names and adjust, then re-run.

- [ ] **Step 3: Commit**

```bash
git add test_network_viz_render.py
git commit -m "test: pin topology builder node size + TL->y normalization"
```

---

### Task 14: Phase 2 gate

- [ ] **Step 1: Full suite**

Run: `micromamba run -n shiny python -m pytest -v`
Expected: all PASS.

- [ ] **Step 2: Tag**

```bash
git tag phase2-tests
```

---

# PHASE 3 — Mechanical Cleanup & Small Robustness Fixes

### Task 15: Delete dead constants

**Why:** Grep-confirmed zero Python consumers (audit). `TROPHIC_LEVEL_MAX_ITER/CONVERGENCE` (TL now uses direct solve), `FLUX_LOG_EPSILON` (app hardcodes `1e-10`), `EDGE_ARROW_SIZE_TOPOLOGY/FLUX` (viz hardcodes 0.5/0.3, contradicting these).

**Files:**
- Modify: `network_analysis.py:31-45`

- [ ] **Step 1: Re-confirm dead before deleting**

Run: `micromamba run -n shiny python - <<'PY'
import subprocess
for name in ["TROPHIC_LEVEL_MAX_ITER","TROPHIC_LEVEL_CONVERGENCE","FLUX_LOG_EPSILON","EDGE_ARROW_SIZE_TOPOLOGY","EDGE_ARROW_SIZE_FLUX"]:
    r = subprocess.run(["grep","-rnw","--include=*.py",name,"."],capture_output=True,text=True)
    print(name, "->", [l for l in r.stdout.splitlines() if "network_analysis.py:3" not in l and "network_analysis.py:4" not in l])
PY`
Expected: each name maps to an empty list (only its definition line, which is filtered). If any name has a real consumer, do NOT delete it — report instead.

- [ ] **Step 2: Delete the dead constant lines (32-33, 37, 44-45)**

Remove lines 32-33 (`TROPHIC_LEVEL_MAX_ITER`, `TROPHIC_LEVEL_CONVERGENCE`), line 37 (`FLUX_LOG_EPSILON`), and lines 44-45 (`EDGE_ARROW_SIZE_TOPOLOGY`, `EDGE_ARROW_SIZE_FLUX`). Keep `FLUX_CONVERSION_FACTOR` (line 36, still imported by app.py) and the `NODE_SIZE_*`/`EDGE_WIDTH_*` constants (used by network_viz). Leave section headers intact.

- [ ] **Step 3: Import-smoke both consumers**

Run: `micromamba run -n shiny python -c "import network_analysis, app; print('imports OK')"`
Expected: `imports OK`.

- [ ] **Step 4: Full suite**

Run: `micromamba run -n shiny python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add network_analysis.py
git commit -m "chore: remove dead constants (iter params, FLUX_LOG_EPSILON, EDGE_ARROW_SIZE_*)"
```

---

### Task 16: Delete dead module-level color assignment

**Why:** `app.py:127` (`node_colors, color_map = get_functional_group_colors(...)`) runs at import but every consumer recomputes locally (grep-confirmed: 819, 869, 902, 1025, 1048, 1183 are all fresh calls). Pyflakes never flags unused module globals.

**Files:**
- Modify: `app.py:126-127`

- [ ] **Step 1: Confirm no read of the module-level names**

Run: `micromamba run -n shiny python - <<'PY'
import subprocess
r = subprocess.run(["grep","-nE",r"\b(node_colors|color_map)\b","app.py"],capture_output=True,text=True)
print(r.stdout)
PY`
Expected: line 127 (the assignment) appears; every other hit is a *local* reassignment inside a render function, never a bare read of the module-level value. Confirm visually before deleting.

- [ ] **Step 2: Delete line 127 and its comment (line 126)**

Remove:
```python
# Get functional group colors
node_colors, color_map = get_functional_group_colors(species_info['fg'].tolist())
```

- [ ] **Step 3: Import-smoke + full suite**

Run: `micromamba run -n shiny python -c "import app; print('app OK')" && micromamba run -n shiny python -m pytest -q`
Expected: `app OK` then all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "chore: drop dead module-level node_colors/color_map (all consumers recompute)"
```

---

### Task 17: Deduplicate the physics-options JSON

**Why:** `network_viz.py:63-108` (topology) and `:203-248` (flux) are ~40 identical lines differing only in arrow `scaleFactor` (0.5 vs 0.3) and edge `scaling` (`{min:1,max:1}` vs `{min:0.1,max:15}`).

**Files:**
- Modify: `network_viz.py`

- [ ] **Step 1: Add a module-level helper (after the imports, ~line 20)**

```python
def _physics_options(arrow_scale: float, edge_scale_min: float, edge_scale_max: float) -> str:
    """Return the shared Barnes-Hut physics options JSON for a pyvis Network,
    parameterized by the two fields that differ between the topology and flux
    builders (arrow scaleFactor and edge scaling range)."""
    return """
    {
        "physics": {
            "enabled": true,
            "solver": "barnesHut",
            "barnesHut": {
                "gravitationalConstant": -2000,
                "centralGravity": 0.1,
                "springLength": 200,
                "springConstant": 0.02,
                "damping": 0.7,
                "avoidOverlap": 0.2
            },
            "stabilization": {
                "enabled": true,
                "iterations": 1000,
                "updateInterval": 50,
                "onlyDynamicEdges": false,
                "fit": true
            },
            "minVelocity": 0.5,
            "maxVelocity": 20
        },
        "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true
        },
        "edges": {
            "smooth": {
                "type": "curvedCW",
                "roundness": 0.2
            },
            "arrows": {
                "to": {
                    "enabled": true,
                    "scaleFactor": %s
                }
            },
            "scaling": {
                "min": %s,
                "max": %s
            }
        }
    }
    """ % (arrow_scale, edge_scale_min, edge_scale_max)
```

- [ ] **Step 2: Replace the topology `set_options(...)` call (was lines 63-108)**

```python
    net.set_options(_physics_options(arrow_scale=0.5, edge_scale_min=1, edge_scale_max=1))
```

- [ ] **Step 3: Replace the flux `set_options(...)` call (was lines 203-248)**

```python
    net.set_options(_physics_options(arrow_scale=0.3, edge_scale_min=0.1, edge_scale_max=15))
```

- [ ] **Step 4: Run the render regression tests (they assert `barnesHut` is in the HTML)**

Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py -v`
Expected: all PASS — the emitted options JSON is equivalent for both builders.

- [ ] **Step 5: Commit**

```bash
git add network_viz.py
git commit -m "refactor: dedupe physics-options JSON via _physics_options helper"
```

---

### Task 18: Rename deprecated `@reactive.Effect`

**Why:** `app.py:1071` uses the deprecated capitalized `@reactive.Effect`; everywhere else uses lowercase `@reactive.effect`.

**Files:**
- Modify: `app.py:1071`

- [ ] **Step 1: Rename**

Change `@reactive.Effect` to `@reactive.effect` on line 1071 (the `calculate_fluxes` effect from Task 5).

- [ ] **Step 2: Import-smoke**

Run: `micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: `app OK`.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "chore: use lowercase @reactive.effect (deprecated capitalized form)"
```

---

### Task 19: load_data order-of-ops + feedback empty-VERSION guard

**Why:** Two small robustness fixes the audit confirmed. (a) `load_data.py:79` calls `info['fg'].nunique()` *before* the missing-column check at `:83`, so a missing `fg` column raises `KeyError` instead of the intended warning. (b) `feedback_reporter.collect_system_context` raises an uncaught `IndexError` when `VERSION` is empty (escapes the `except OSError`).

**Files:**
- Modify: `load_data.py:74-85`
- Modify: `feedback_reporter.py` (the VERSION read in `collect_system_context`)
- Test: `test_feedback_reporter.py`

- [ ] **Step 1: Reorder the load_data column check before the fg summary**

In `load_data.py`, move the required-columns check (currently lines 81-85) to *before* the data-summary print that references `info['fg']` (line 79). Concretely, replace lines 74-85 with:

```python
    # Check for required columns BEFORE referencing any of them.
    required_cols = ['species', 'fg', 'meanB', 'bodymasses', 'met.types', 'efficiencies']
    missing_cols = [col for col in required_cols if col not in info.columns]
    if missing_cols:
        print(f"\nWarning: Missing required columns: {missing_cols}")

    # Verify data integrity
    print(f"\nData Summary:")
    print(f"  Network nodes: {len(G.nodes())}")
    print(f"  Network edges: {len(G.edges())}")
    print(f"  Species info rows: {len(info)}")
    if 'fg' in info.columns:
        print(f"  Functional groups: {info['fg'].nunique()}")
```

- [ ] **Step 2: Read the feedback VERSION block, then guard it**

Open `feedback_reporter.py`, find where `collect_system_context` reads the `VERSION` file (the `version_path` argument). Wrap the read so an empty file yields `'unknown'` instead of an `IndexError`:

```python
    try:
        lines = Path(version_path).read_text(encoding="utf-8").splitlines()
        app_version = lines[0].strip() if lines else "unknown"
    except (OSError, IndexError):
        app_version = "unknown"
```

(Adjust variable names to match the existing function; the key change is `lines[0] if lines else "unknown"` plus `IndexError` in the `except`.)

- [ ] **Step 3: Write a test for the empty-VERSION case**

Add to `test_feedback_reporter.py`:

```python
def test_collect_system_context_empty_version_file(tmp_path):
    """An empty VERSION file must yield 'unknown', not raise IndexError."""
    from feedback_reporter import collect_system_context
    vfile = tmp_path / "VERSION"
    vfile.write_text("", encoding="utf-8")
    ctx = collect_system_context(
        current_tab="x", browser_info="x", user_level="x", language="x",
        species_count=0, edge_count=0, version_path=str(vfile),
    )
    assert ctx["app_version"] == "unknown", ctx
```

(Match the exact `collect_system_context` keyword arguments to its real signature; adjust the asserted key if the version is stored under a different name.)

- [ ] **Step 4: Run the feedback tests**

Run: `micromamba run -n shiny python -m pytest test_feedback_reporter.py -v`
Expected: all PASS, including the new empty-VERSION test.

- [ ] **Step 5: Commit**

```bash
git add load_data.py feedback_reporter.py test_feedback_reporter.py
git commit -m "fix: load_data checks columns before fg summary; feedback handles empty VERSION"
```

---

### Task 20: Tidy stale artifacts + gitignore

**Why:** The save-to-file→srcdoc pyvis migration is complete; stale `temp_*.html` and obsolete `www/*_network.html` ignore rules remain. Also guard against future scratch `_*.py` files.

**Files:**
- Modify: `.gitignore`
- Delete: stale root HTML files if present

- [ ] **Step 1: Remove stale root HTML if present**

Run: `micromamba run -n shiny python - <<'PY'
from pathlib import Path
for n in ["temp_network.html","temp_flux_network.html","test_network.html"]:
    p = Path(n)
    if p.exists():
        p.unlink(); print("removed", n)
    else:
        print("absent", n)
PY`
Expected: prints removed/absent per file (no error).

- [ ] **Step 2: Add a scratch-file ignore rule to `.gitignore`**

Append (if not already present):

```
# Scratch / repro files
_*.py
```

Confirm the existing `BalticFW.pkl` and per-render network HTML rules remain; do not remove ignore rules for files that may still exist locally.

- [ ] **Step 3: Confirm working tree is clean of junk**

Run: `git status --porcelain`
Expected: shows only the intended `.gitignore` (and any deleted HTML) changes.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore scratch _*.py; remove stale pre-migration HTML artifacts"
```

---

### Task 21: Final gate + documentation note

- [ ] **Step 1: Full suite, final**

Run: `micromamba run -n shiny python -m pytest -v`
Expected: all PASS.

- [ ] **Step 2: App import-smoke, final**

Run: `micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: `app OK`.

- [ ] **Step 3: Record the deferred items**

Append a `## Deferred to follow-up` section to this plan listing: (a) Williams & Martinez (2004) short-weighted trophic level (replace the TL clamp stopgap), (b) the full `@safe_render` error-handling convention for all analytical render functions + narrowing the bare `except:` at `network_analysis.py:167`, (c) the reactive-CPU refactor (colors_cached/mti_cached/_build_network), (d) the `bioms_losses` validator-asymmetry parameter (latent footgun; live app uses the default so it is non-urgent).

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-06-13-econetpy-audit-remediation.md
git commit -m "docs: record deferred follow-up items in remediation plan"
```

---

## Deferred to follow-up

The following items were identified during the audit/remediation but are intentionally
out of scope for this plan. They are recorded here so the structural follow-up plan can
pick them up. None of them block the live app on its default inputs.

- **(a) Williams & Martinez (2004) short-weighted trophic level — replace the TL clamp stopgap.**
  `network_analysis.py:91-104` currently detects an ill-conditioned `(I - diet)` solve and
  *clamps* non-physical trophic levels to `[1, 100]` to avoid a NaN cascade into the viz layer
  (Task 6). This is a stopgap. The proper fix is to compute the short-weighted trophic level
  (Williams & Martinez 2004) — the average of the shortest and prey-averaged paths to a basal
  node — which is well-defined on cyclic webs and removes the need for the clamp. Replacing the
  clamp is a metric-definition change and must be done under TDD with hand-computed pins on
  cyclic and acyclic webs.

- **(b) Full `@safe_render` error-handling convention + narrow the bare `except:` at `network_analysis.py:167`.**
  Phase 1 added only a single *targeted* try/except around the flux calculation (Task 5). The
  broader convention — a `@safe_render` decorator wrapping every analytical render function so a
  failure shows a clean notification instead of a raw traceback — is deferred. As part of this,
  narrow the bare `except:` at `network_analysis.py:167` to the specific exception type(s) it is
  meant to catch (a bare `except:` also swallows `KeyboardInterrupt`/`SystemExit`).

- **(c) Reactive-CPU refactor (`colors_cached` / `mti_cached` / `_build_network`).**
  Several render functions recompute functional-group colors, the MTI matrix, and the pyvis
  network from scratch on every reactive invalidation. Hoisting these into memoized reactive
  calcs (`colors_cached`, `mti_cached`, `_build_network`) would cut redundant CPU work. This is a
  structural reactive-architecture change explicitly held out of the current plan's scope.

- **(d) `bioms_losses` validator-asymmetry parameter (latent footgun; non-urgent).**
  `fluxing()` and `validate_flux_equilibrium()` can disagree about whether losses are scaled by
  biomass (`bioms_losses`). The live app always uses the default, so the two are consistent in
  production, but the parameter is a latent footgun if a caller ever overrides it on one side and
  not the other. Thread the flag through (or otherwise enforce agreement) in the follow-up.

- **(e) Remove the unused `import pandas as pd` in `conftest.py`.**
  `conftest.py:4` imports pandas (`import pandas as pd`) but no fixture references `pd`. Drop the
  unused import. Trivial; deferred only to keep this plan's commits scoped.
