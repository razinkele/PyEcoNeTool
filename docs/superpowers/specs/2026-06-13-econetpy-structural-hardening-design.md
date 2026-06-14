# EconetPy Structural Hardening — Design Spec

**Date:** 2026-06-13 (revised 2026-06-14 after multi-angle spec review)
**Status:** Approved (design), revised per spec review, pending final user review
**Predecessor:** `docs/superpowers/plans/2026-06-13-econetpy-audit-remediation.md` (the four items below are its "Deferred to follow-up" section)

## Goal

Land the four deferred structural items from the audit remediation, **without changing any validated pin** from that work:

- **(a) Selectable trophic-level method** — expose Williams & Martinez (2004) short-weighted TL alongside the existing prey-averaged TL, defaulting to prey-averaged.
- **(b) `@safe_render` error-handling convention** — analytical render functions surface a clean message instead of a raw traceback; narrow the one bare `except:`.
- **(c) Reactive-CPU refactor** — extend the existing per-session caches and thread their values down, eliminating the remaining redundant linear solves per interaction.
- **(d) Validator `bioms_losses` parameter** — `validate_flux_equilibrium` mirrors the solver's biomass-scaling flag (close the latent footgun).

## Non-Goals (YAGNI)

- No trophic-level metrics beyond prey-averaged and short-weighted.
- No caching beyond TL / MTI / colors.
- `@safe_render` only on renderers that perform computation (not on the trivial count/legend/title text renderers). No `@render.data_frame` kind — none of the 13 targeted renderers use it.
- No change to the prey-averaged default behavior, so all 84 existing tests remain green; new tests are additive.

## Current State (verified against master @ 9d790c9)

- `calculate_trophic_levels(G)` — prey-averaged via `(I − diet) TL = 1` linear solve, with explicit ill-conditioning detection (remediation Task 6) and a documented clamp-to-[1,100] stopgap. Edge direction: `G` edge `i→j` means prey `i` is eaten by predator `j`; **basal species have in-degree 0 in `G`**.
- `get_topological_indicators(G)`, `get_node_weighted_indicators(G, biomass)` — each calls `calculate_trophic_levels(G)` internally.
- `create_topology_network(...)`, `create_flux_network(...)` — each calls `calculate_trophic_levels(G)` internally for y-positioning, normalizing via `np.min`/`np.max` of the TL vector.
- `calculate_keystoneness(G, biomass, impact_quantile=0.75, biomass_quantile=0.25)` — calls `calculate_mti(G)` internally.
- `validate_flux_equilibrium(flux_matrix, losses, efficiencies, biomasses=None, tolerance=1e-6)` — scales `L *= biomasses` whenever `biomasses is not None`; has **no** `bioms_losses` flag (the solver does).
- `network_analysis.py:176` — a bare `except:` in `get_topological_indicators` ShortPath computation.
- **Caches that ALREADY EXIST** (`app.py:560-569`, from remediation memoization): `trophic_levels_cached()`, `mti_cached()`, `keystoneness_cached()` as `@reactive.calc`. They are wired into the TL-consuming renderers (970, 986) and the keystoneness/MTI renderers (1212, 1235, 1282, 1297). **There is no `colors_cached`** — `get_functional_group_colors` is still recomputed at 6 call sites; and the two pyvis builders + `get_topological_indicators`/`get_node_weighted_indicators` still recompute TL internally rather than consuming `trophic_levels_cached`.
- `app.py` analytical renderers (13, all compute → may raise): `topological_indicators`, `trophic_level_histogram`, `node_weighted_indicators`, `biomass_by_group`, `biomass_distribution`, `flux_indicators`, `flux_heatmap`, `flux_network_plot`, `keystoneness_summary`, `keystoneness_scatter`, `mti_heatmap`, `network_plot`, `adjacency_heatmap`. `logger` (`econetpy.app`) is already configured. Shiny version is 1.6.1.

---

## Phase A — Isolated quick wins

### A1. Validator `bioms_losses` parameter (item d)

**Interface change** (new param inserted before `tolerance` — confirmed non-breaking; no caller passes `tolerance` positionally):
```
validate_flux_equilibrium(flux_matrix, losses, efficiencies,
                          biomasses=None, bioms_losses=True, tolerance=1e-6)
```
Scale `L = losses.copy(); if bioms_losses and biomasses is not None: L = L * biomasses` — identical gating to the solver (`flux_calculations.py:117`).

**Single source of truth at the call site:** in the `calculate_fluxes` effect, hoist `bioms_losses_flag = True` **once** above the try block and pass that *same variable* into both `fluxing(..., bioms_losses=bioms_losses_flag)` and `validate_flux_equilibrium(..., bioms_losses=bioms_losses_flag)`. Do not write two independent `True` literals (that re-creates the asymmetry item d is closing). No UI toggle; do not derive the flag inside the validator.

**Tests:** A→B→C chain, `L=[2,3,5]`, `e=[0.5,0.6,0.7]`, `bm=[10,4,2]`, `flux = fluxing(..., bioms_losses=False)`. Assert `validate_flux_equilibrium(flux, L, e, bm, bioms_losses=False).max_imbalance < tol`; and on the SAME flux, `validate_flux_equilibrium(flux, L, e, bm, bioms_losses=True)` reports a non-trivial imbalance (the flag changes the reported magnitude, since `checked = inflows > tol` is independent of `L`). Default path (`bioms_losses=True`) unchanged.

### A2. Narrow the bare `except:` (part of item b)

`network_analysis.py:176` `except:` → `except (nx.NetworkXError, nx.NetworkXPointlessConcept, ValueError):` followed by `warnings.warn("Mean shortest path undefined; returning NaN", ...)` before `ShortPath = np.nan`. Stops swallowing `KeyboardInterrupt`/`SystemExit`/`NameError` while preserving the disconnected-graph fallback.

**Tests (behavior verified against networkx 3.6.1):** a disconnected graph still yields a finite ShortPath via the largest-component branch; a **single-node** graph yields `ShortPath == 0` and emits **NO** "Mean shortest path undefined" warning (a single-node DiGraph is weakly connected, so `average_shortest_path_length` returns 0 — the only warning is the pre-existing "one or zero species" one); the **null/empty** graph raises `ValueError('Network contains no vertices')` upstream (before ShortPath). To exercise the **narrowed-except path itself**, monkeypatch `nx.average_shortest_path_length` to raise `nx.NetworkXError` and assert `ShortPath` becomes `NaN` with the "Mean shortest path undefined" warning fired — proving the clause catches NetworkX errors yet no longer swallows `KeyboardInterrupt`/`NameError`. Do NOT pin single-node `ShortPath == NaN` (it would fail).

---

## Phase B — TL method + reactive threading (items a + c)

Co-designed: the TL-method toggle only propagates correctly if TL is computed once (with the chosen method) and threaded down — the reactive refactor's mechanism.

### B1. Selectable trophic-level method (item a)

**Interface:** `calculate_trophic_levels(G, method="prey_averaged")` — `method in {"prey_averaged", "short_weighted"}`.

- `method="prey_averaged"` (default): **current implementation verbatim** — linear solve + ill-conditioning detection + clamp stopgap. No behavior change.
- `method="short_weighted"`: Williams & Martinez (2004) `SWTL_i = (shortest_TL_i + prey_averaged_TL_i) / 2`, where:
  - `prey_averaged_TL` = the existing solve result.
  - `shortest_TL_i = 1 + d_i`, `d_i` = shortest prey-chain length from `i` to any basal node, via multi-source BFS: basal nodes (in-degree 0 in `G`) get `d=0`; a predator's `d = 1 + min over its prey's d`. **Basal-unreachable nodes** (e.g. a closed cycle with no basal path) → `shortest_TL = NaN`, hence `SWTL = NaN`.

  Verified: BFS has no off-by-one; basal definition matches the edge direction. `shortest_TL` is finite for every basal-reachable node regardless of cycles, so SWTL is bounded where defined and is NaN (never a misleading clamp) only for genuinely unreachable nodes.

**Invariant:** for acyclic single chains `shortest_TL == prey_averaged_TL`; they diverge on multi-prey (omnivorous) species.

**Tests (numerically pre-verified):**
- `prey_averaged` identical to today (regression over existing fixtures).
- `short_weighted` headline pins: `linear_chain` → `[1,2,3]` (≡ prey-averaged); `omnivore_web` (C eats A@1, B@2) → `[1,2,2.25]` (the discriminating pin).
- `short_weighted` invariants: `np.allclose(SWTL(linear_chain), prey_averaged(linear_chain))`; every in-degree-0 node has `SWTL == 1.0`; multi-basal — **build node order explicitly**: `G.add_nodes_from(['A','B','C','D'])` BEFORE `G.add_edges_from([('A','C'),('B','C'),('B','D'),('C','D')])` so `list(G.nodes()) == [A,B,C,D]`, then `SWTL = [1, 1, 2, 2.25]` (A,B basal; D top omnivore). NOTE: if built edge-first, `list(G.nodes()) == [A,C,B,D]` and the array is `[1, 2, 1, 2.25]` — assert per-node (or against an explicit sorted nodelist), never the bare positional array.
- **Cycle behavior — TWO separate graphs (do NOT conflate "finite SWTL" with "prey-averaged clamps"; they are mutually exclusive):**
  1. **Basal-reachable cycle** `0→1, 1→2, 2→1` (node 0 basal): `prey_averaged = [1, 4, 5]` (finite, no clamp); assert `SWTL` is all-finite and shorter-chain-biased — `SWTL = [1, 3, 4]`, so `SWTL[1]=3 < prey_averaged[1]=4`. Do NOT assert clamping here.
  2. **Closed 2-cycle** `(0,1), (1,0)` (no basal): assert the clamp path fires (`pytest.warns(match="clamped to")`, the singular-matrix lstsq branch) and `prey_averaged` of the cycle nodes `== [1.0, 1.0]` **exactly** (the sub-1 lstsq output ≈`[0,0]` is pulled UP to the clamp floor 1.0 — indistinguishable from a real basal node, hence unreliable), while `SWTL` of those nodes is `NaN`. Do NOT assert a `[1,100]` range; the clamped values sit at the floor, not near 100.

### B2. Optional precomputed arguments (item c, library side)

All backward-compatible — `None`/omitted preserves today's behavior by computing internally.

```
get_topological_indicators(G, trophic_levels=None)
get_node_weighted_indicators(G, biomass, trophic_levels=None)
create_topology_network(..., height="600px", trophic_levels=None)      # FINAL param, after height
create_flux_network(..., flux_matrix, height="600px", trophic_levels=None)  # FINAL param, after height
calculate_keystoneness(G, biomass, impact_quantile=0.75, biomass_quantile=0.25, mti=None)
```
Each function: `tl = trophic_levels if trophic_levels is not None else calculate_trophic_levels(G)` (analogously `mti`). **`trophic_levels=None` is appended as the final parameter** in both builders (after `height`) to preserve the existing `width`/`height` positional contract and avoid a string-into-`np.min` footgun; optionally made keyword-only via a `*` separator. Verified non-breaking: no existing test or call site passes these positionally.

**Omni tracks the chosen method (by design):** `get_topological_indicators` computes the omnivory index from the threaded `trophic_levels`, so under `short_weighted` it changes consistently with TL — this is correct (omnivory is a function of trophic level, so the metric choice must propagate). For `omnivore_web` under `short_weighted` (`TL=[1,2,2.25]`): `Omni = nanmean([NaN, 0, 0.3125]) = 0.15625` (pinned). The default prey-averaged `Omni=0.125` pin is unchanged.

**NaN-safe aggregation (short_weighted may inject NaN TL):**
- `get_topological_indicators` system `TL` **must be changed** from `np.mean(tlnodes)` to `np.nanmean(tlnodes)` (the current code at network_analysis.py:181 is `np.mean`, which a NaN short-weighted TL would poison); the omnivory `nanmean` guard is already present.
- `get_node_weighted_indicators` **must mask non-finite TL** in the weighted `nwTL` sum (a `nanmean` does not fix a biomass-weighted sum): `m = np.isfinite(tl); nwTL = np.sum((tl*biomass)[m]) / np.sum(biomass[m])`.

**Tests — SENTINEL equivalence (a known-TL equality test is trivial: passed-in and internal are the *same* function on the *same* graph and prove nothing):**
For each threaded function, inject a `trophic_levels`/`mti` that **differs** from the internally-computed value (e.g. `[1,2,5]` for a chain whose real TL is `[1,2,3]`; a perturbed MTI for keystoneness) and assert the output **reflects the injected value** (`nwTL`/system-TL shift; topology and flux-network node y-positions shift; keystoneness reflects the injected MTI). Pair each with a `None`-path assertion reproducing the real computed value. Keep all sentinels finite and in-range so they don't trip the short-weighted NaN path.

**Viz NaN handling (network_viz.py) — required so short_weighted NaN TL does not silently flatten the web:**
`create_topology_network`/`create_flux_network` currently normalize y via `np.min`/`np.max(trophic_levels)`, which return NaN if any TL is NaN, collapsing every node to one row. Change to: `min_tl = np.nanmin(tl)`, `max_tl = np.nanmax(tl)`; guard the per-node y formula with `np.isfinite(tl[i])`; place NaN-TL nodes at a sentinel y **outside the [0,100] band** (e.g. `−15`, so they are visually distinct from the basal/min-TL row at y=0 — do NOT use 0, which collides with real min-TL nodes) with a tooltip note and render their TL as `"n/a"` (not the literal `"nan"`). **Test:** pass a `trophic_levels` array containing a NaN and assert the finite nodes still spread across 0–100 (not all-zero), no node `y` is NaN, AND the NaN node's `y` differs from every finite node's `y` (especially the basal/min-TL node at 0).

### B3. Extend the existing reactive layer + build-network helper (item c, app side)

The caches `trophic_levels_cached`/`mti_cached`/`keystoneness_cached` **already exist** (`app.py:560-569`). This phase **extends and fully threads** them — it does not redefine them.

- **Extend** `trophic_levels_cached` to honor the toggle: `return calculate_trophic_levels(current_network(), method=input.tl_method())`.
- **Add** the missing `colors_cached`: `@reactive.calc def colors_cached(): return get_functional_group_colors(current_species_info()['fg'].tolist())`.
- **Thread** the existing caches into the call sites that still recompute: `get_topological_indicators(G, trophic_levels=trophic_levels_cached())`, `get_node_weighted_indicators(G, biomass, trophic_levels=trophic_levels_cached())`, both builders via the helper, `calculate_keystoneness(..., mti=mti_cached())` (so `keystoneness_cached` does not double-compute MTI), and replace the remaining `get_functional_group_colors(...)` call sites (6 in `app.py`) with `colors_cached()`.
- A private helper `_build_network(kind, height="600px")` (`kind in {"topology", "flux"}`) consolidates the three near-identical pyvis build blocks (`network_plot`, `download_network`, `flux_network_plot`), reading `current_network`/`current_species_info`/`colors_cached`/`trophic_levels_cached` (and `flux_results` for the flux kind — no reactive-context issue, confirmed) and **returning the built pyvis `Network` object** (NOT an iframe — `download_network` needs `net.generate_html()`, which an iframe cannot supply). Each caller wraps it: `render_network(net, height=..., width="100%")` for `network_plot` (dynamic height) and `flux_network_plot` (600px); `net.generate_html()` for `download_network`. The per-caller guards (the two distinct None-flux/empty `ui.p` messages and the download topology fallback) stay in the callers around the `_build_network` call. The helper only reads caches, so the AST dedup guard remains satisfiable.

**Dedup is structural, not eyeballed — enforce it with a test:** add an AST/grep regression test asserting that after B3 **no analytical-renderer function body** references `calculate_trophic_levels(`, `calculate_mti(`, or `get_functional_group_colors(` directly (they must go through the caches). **The guard MUST exclude the cache-definition functions themselves** (`trophic_levels_cached`/`mti_cached`/`colors_cached` legitimately call these) — scope the AST check to the analytical-renderer nodes only (whitelist the cache defs, or filter by enclosing-function name), and verify it passes on a clean tree before landing. This is the cheapest insurance against a silent cache bypass. Do not claim runtime call-count verifiability (no `TestClient` flow here); an optional Playwright e2e could prove single-compute at runtime but is not required.

### B4. UI toggle (item a, app side)

A sidebar control (global, so the metric is consistent across all analysis tabs):
```
ui.input_radio_buttons("tl_method", "Trophic level method",
    {"prey_averaged": "Prey-averaged", "short_weighted": "Short-weighted (W&M 2004)"},
    selected="prey_averaged")
```
`input.tl_method()` feeds `trophic_levels_cached`. (Verified: this dependency recomputes on toggle change without over-invalidating.)

---

## Phase C — `@safe_render` convention (main of item b)

**Module-scope** decorator factory + helper in `app.py`:
```
def safe_render(kind):  # kind in {"text", "plot", "ui"}
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
`_error_element(kind)`: `"text"` → a uniform error string; `"plot"` → a matplotlib `Figure` whose axes text holds the message; `"ui"` → a `ui.div`/`ui.Tag` with a stable CSS class. Both `safe_render` and `_error_element` are module-scope (importable/testable in isolation).

**Decorator order (verified correct on Shiny 1.6.1):** `@safe_render` goes **below** `@output`/`@render.*` — i.e. `render.*` wraps the `safe_render`-wrapped function. `functools.wraps` preserves what Shiny needs; this stacking is confirmed to work.
```
@output
@render.text
@safe_render("text")
def topological_indicators(): ...
```
Applied to all 13 analytical renderers; the flux effect's existing targeted try/except (remediation Task 5) remains — `@safe_render` covers the *render* path, the effect covers the *compute-on-click* path (complementary).

**Tests (no full Shiny harness needed):** decorate a plain dummy function (no `@output`/`@render`) that raises, and assert: `"text"` → exact error marker string; `"plot"` → a `Figure` whose axes text contains the marker; `"ui"` → a `ui.Tag` carrying the stable class; and that `logger.exception` fired (via `caplog`). One order guard: wrap a raising dummy in `@render.text` + `@safe_render("text")` and assert `.render()` returns the marker (not a propagated exception).

---

## Build Order & Phase Gates

1. **Phase A** (A1, A2) — isolated; full suite green + tag.
2. **Phase B** — B1 (method + cycle/invariant tests) → B2 (optional args + sentinel equivalence + NaN-safe aggregation + viz NaN handling) → B3 (extend/thread caches + `_build_network` + AST guard) → B4 (toggle). **B2 and B3 land atomically** (a partially-threaded renderer would bypass the cache). Full suite green + manual toggle smoke + tag.
3. **Phase C** — decorator + apply to 13 renderers; full suite green + forced-failure smoke + tag.

Each task follows TDD; frequent commits; `micromamba run -n shiny python -m pytest` for all runs.

## Acceptance Criteria

- All 84 existing tests pass unchanged (prey-averaged default preserved; `Omni=0.125`, `log10(0.25)`, flux pins all hold).
- New: short-weighted pins (`omnivore_web=[1,2,2.25]`, multi-basal `[1,1,2,2.25]`, chain≡prey-averaged, basal-reachable cycle `SWTL=[1,3,4]`, closed 2-cycle SWTL=NaN); `Omni=0.15625` under short_weighted; SENTINEL equivalence tests for every threaded function; viz NaN-TL render test; `nwTL` NaN-mask test; validator `bioms_losses` symmetry pin; narrowed-except warning; `@safe_render` uniform error element + `logger.exception` + order guard; AST dedup guard.
- App imports clean; the TL toggle switches the metric across all analysis tabs; a forced renderer failure shows a clean message, not a traceback.
- The AST guard passes: no analytical renderer recomputes TL/MTI/colors directly.

## Risks & Mitigations

- **Short-weighted NaN cascade** into (1) system TL mean — fixed by changing `np.mean`→`np.nanmean` at network_analysis.py:181 (B2); (2) `nwTL` weighted sum — fixed by the `np.isfinite` mask (B2); (3) **viz y-normalization** — fixed by `np.nanmin`/`np.nanmax` + per-node `isfinite` guard + sentinel y (B2). These are the three real sinks; all addressed.
- **Threading divergence** (a function uses a different TL than passed) → SENTINEL equivalence tests (B2), not trivial equality.
- **Silent cache bypass** (a renderer keeps recomputing) → AST/grep dedup guard test (B3).
- **`@safe_render` masking real bugs** → logs full traceback via `logger.exception`; affects only the display path; tests assert the log fired.
- **Param-position footgun** → `trophic_levels=None` appended as the final builder param (optionally keyword-only).
