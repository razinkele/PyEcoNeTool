# EconetPy Structural Hardening — Design Spec

**Date:** 2026-06-13
**Status:** Approved (design), pending spec review
**Predecessor:** `docs/superpowers/plans/2026-06-13-econetpy-audit-remediation.md` (the four items below are its "Deferred to follow-up" section)

## Goal

Land the four deferred structural items from the audit remediation, **without changing any validated pin** from that work:

- **(a) Selectable trophic-level method** — expose Williams & Martinez (2004) short-weighted TL alongside the existing prey-averaged TL, defaulting to prey-averaged.
- **(b) `@safe_render` error-handling convention** — analytical render functions surface a clean message instead of a raw traceback; narrow the one bare `except:`.
- **(c) Reactive-CPU refactor** — compute trophic levels, MTI, and functional-group colors once per change and thread them down, eliminating the 4–6× redundant linear solves per interaction.
- **(d) Validator `bioms_losses` parameter** — `validate_flux_equilibrium` mirrors the solver's biomass-scaling flag (close the latent footgun).

## Non-Goals (YAGNI)

- No trophic-level metrics beyond prey-averaged and short-weighted.
- No caching beyond TL / MTI / colors.
- `@safe_render` only on renderers that perform computation (not on the trivial count/legend/title text renderers).
- No change to the prey-averaged default behavior, so all 84 existing tests remain green; new tests are additive.

## Current State (as of master @ 568226b)

- `calculate_trophic_levels(G)` — prey-averaged via `(I − diet) TL = 1` linear solve, with explicit ill-conditioning detection (Task 6 of the remediation) and a documented clamp-to-[1,100] stopgap. Edge direction: `G` edge `i→j` means prey `i` is eaten by predator `j`; basal species have in-degree 0 in `G`.
- `get_topological_indicators(G)`, `get_node_weighted_indicators(G, biomass)` — each calls `calculate_trophic_levels(G)` internally.
- `create_topology_network(...)`, `create_flux_network(...)` — each calls `calculate_trophic_levels(G)` internally for y-positioning.
- `calculate_keystoneness(G, biomass, impact_quantile=0.75, biomass_quantile=0.25)` — calls `calculate_mti(G)` internally.
- `validate_flux_equilibrium(flux_matrix, losses, efficiencies, biomasses=None, tolerance=1e-6)` — scales `L *= biomasses` whenever `biomasses is not None`; has **no** `bioms_losses` flag (solver does).
- `network_analysis.py:176` — a bare `except:` in `get_topological_indicators` ShortPath computation.
- `app.py` — 13 "analytical" render functions that compute (`topological_indicators`, `trophic_level_histogram`, `node_weighted_indicators`, `biomass_by_group`, `biomass_distribution`, `flux_indicators`, `flux_heatmap`, `flux_network_plot`, `keystoneness_summary`, `keystoneness_scatter`, `mti_heatmap`, `network_plot`, `adjacency_heatmap`) and ~9 trivial text/ui renderers that do not. `logger` is already configured (`econetpy.app`). `get_functional_group_colors` is recomputed in 6 renderers. Three near-identical pyvis build blocks exist (`network_plot`, `download_network`, `flux_network_plot`).

---

## Phase A — Isolated quick wins

### A1. Validator `bioms_losses` parameter (item d)

**Interface change:**
```
validate_flux_equilibrium(flux_matrix, losses, efficiencies,
                          biomasses=None, bioms_losses=True, tolerance=1e-6)
```
Scale `L = losses.copy(); if bioms_losses and biomasses is not None: L = L * biomasses` — identical gating to the solver (`flux_calculations.py:117`). The app's call site passes `bioms_losses=True` explicitly (matches the solver's default in the `calculate_fluxes` effect).

**Why:** Today the validator scales on `biomasses is not None` alone, so a caller using `fluxing(bioms_losses=False)` + biomasses gets a validator that checks a different equation. Mirroring the flag removes the asymmetry.

**Tests:** with `bioms_losses=False` and biomasses supplied, the validator does not scale `L` (pin a case where the old behavior gave a spurious imbalance and the new behavior gives ~0); default path (`bioms_losses=True`) unchanged.

### A2. Narrow the bare `except:` (part of item b)

`network_analysis.py:176` `except:` → `except (nx.NetworkXError, nx.NetworkXPointlessConcept, ValueError):` followed by `warnings.warn("Mean shortest path undefined; returning NaN", ...)` before `ShortPath = np.nan`. This stops the clause swallowing `KeyboardInterrupt`/`SystemExit`/`NameError` while preserving the disconnected-graph fallback.

**Tests:** a disconnected graph still yields a finite ShortPath via the largest-component branch; a single-node graph yields `NaN` and emits the warning (not a silent swallow).

---

## Phase B — TL method + reactive threading (items a + c)

These are co-designed: the TL-method toggle only propagates correctly if TL is computed once and threaded down, which is the reactive refactor's mechanism.

### B1. Selectable trophic-level method (item a)

**Interface:**
```
calculate_trophic_levels(G, method="prey_averaged")   # method in {"prey_averaged", "short_weighted"}
```

- `method="prey_averaged"` (default): **current implementation verbatim** — linear solve + ill-conditioning detection + clamp stopgap. No behavior change.
- `method="short_weighted"`: Williams & Martinez (2004) short-weighted TL:
  ```
  SWTL_i = (shortest_TL_i + prey_averaged_TL_i) / 2
  ```
  where:
  - `prey_averaged_TL` = the existing solve result.
  - `shortest_TL_i = 1 + d_i`, with `d_i` = the shortest prey-chain length from species `i` to any basal node. Compute via multi-source BFS: basal nodes (in-degree 0 in `G`) get `d=0`; relax along the prey→predator edges (a predator's `d` = 1 + min over its prey's `d`). Basal-unreachable nodes (e.g. members of a closed cycle with no basal path) → `shortest_TL = NaN`, hence `SWTL = NaN`.

  `shortest_TL` is finite for every basal-reachable node regardless of cycles, so SWTL is bounded where the metric is defined and degrades to NaN (not a misleading clamp) only for genuinely unreachable nodes.

**Invariant:** for acyclic webs, `shortest_TL == prey_averaged_TL` along single chains, so `linear_chain` SWTL == prey-averaged `[1,2,3]`. They diverge only on multi-prey (omnivorous) species: `omnivore_web` (C eats A@1 and B@2) → prey-averaged `TL_C=2.5`, shortest `TL_C=2` (via C→A), so `SWTL_C=2.25`.

**Tests:** `method="prey_averaged"` identical to today (regression). `method="short_weighted"`: `linear_chain` → `[1,2,3]`; `omnivore_web` → `[1,2,2.25]` (pinned); a producer-anchored web containing a 2-cycle returns finite SWTL where prey-averaged clamps; a basal-unreachable closed cycle returns NaN for those nodes.

### B2. Optional precomputed arguments (item c, library side)

All backward-compatible — `None` (or omitted) preserves today's behavior by computing internally.

```
get_topological_indicators(G, trophic_levels=None)
get_node_weighted_indicators(G, biomass, trophic_levels=None)
create_topology_network(..., trophic_levels=None)
create_flux_network(..., trophic_levels=None)
calculate_keystoneness(G, biomass, impact_quantile=0.75, biomass_quantile=0.25, mti=None)
```
Each function: `tl = trophic_levels if trophic_levels is not None else calculate_trophic_levels(G)` (and analogously `mti`).

**Tests (equivalence):** for each function, output is identical whether the value is passed in or computed internally (using a fixture's known TL/MTI). This guards the threading against subtle divergence.

### B3. App reactive layer + build-network helper (item c, app side)

In `app.py`, add per-session caches:
```
@reactive.calc
def trophic_levels_cached():
    return calculate_trophic_levels(current_network(), method=input.tl_method())

@reactive.calc
def mti_cached():
    return calculate_mti(current_network())

@reactive.calc
def colors_cached():
    return get_functional_group_colors(current_species_info()['fg'].tolist())
```
Every analytical renderer reads these and passes them down (e.g. `get_topological_indicators(G, trophic_levels=trophic_levels_cached())`, `create_topology_network(..., trophic_levels=trophic_levels_cached())`, the keystoneness renderers reuse `keystoneness_cached` which threads `mti_cached()`). The 6 `get_functional_group_colors` call sites use `colors_cached()`.

A private helper `_build_network(kind, height="600px")` (`kind in {"topology", "flux"}`) consolidates the 3 near-identical pyvis build blocks, reading `current_network`/`current_species_info`/`colors_cached`/`trophic_levels_cached` (and `flux_results` for the flux kind) and returning the `render_network(...)` iframe. `network_plot`, `download_network`, and `flux_network_plot` delegate to it.

**Tests:** the cached TL respects `input.tl_method()` (covered via the library equivalence tests + a focused test that `calculate_trophic_levels(G, method=...)` is what flows through); no functional change to rendered outputs for the default method (the existing render regression tests stay green).

### B4. UI toggle (item a, app side)

A sidebar control:
```
ui.input_radio_buttons("tl_method", "Trophic level method",
    {"prey_averaged": "Prey-averaged", "short_weighted": "Short-weighted (W&M 2004)"},
    selected="prey_averaged")
```
Placed in the sidebar (global to all analysis tabs, so the metric is consistent across topology/indicators/viz). `input.tl_method()` feeds `trophic_levels_cached`.

---

## Phase C — `@safe_render` convention (main of item b)

A decorator factory in `app.py`:
```
def safe_render(kind):  # kind in {"text", "plot", "ui"}
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                logger.exception("Render %s failed", fn.__name__)
                return _error_element(kind)   # text -> str; plot -> mpl Figure with message; ui -> ui.div
        return wrapper
    return decorator
```
Applied **below** the Shiny `@output`/`@render.*` decorators on each of the 13 analytical renderers, e.g.:
```
@output
@render.text
@safe_render("text")
def topological_indicators(): ...
```
`_error_element(kind)` returns a uniform, friendly message ("This panel could not be computed — see logs.") rendered appropriately per kind. The flux effect's existing targeted try/except (remediation Task 5) remains; `@safe_render` covers the *render* path, the effect covers the *compute-on-click* path — they are complementary.

**Tests:** a renderer monkeypatched to raise returns the uniform error element (assert type/marker), not a propagated exception; `logger.exception` is called. Trivial renderers are untouched.

---

## Build Order & Phase Gates

1. **Phase A** (A1, A2) — isolated, no cross-dependencies; full suite green + tag.
2. **Phase B** (B1 → B2 → B3 → B4) — library first (method + optional args + equivalence tests), then app wiring (caches + helper + toggle); full suite green + manual smoke of the toggle + tag.
3. **Phase C** — decorator + apply to 13 renderers; full suite green + a forced-failure smoke + tag.

Each task follows TDD (failing test first for new behavior; equivalence/regression tests for threading); frequent commits; `micromamba run -n shiny python -m pytest` for all test runs.

## Acceptance Criteria

- All 84 existing tests still pass unchanged (prey-averaged default preserved).
- New: short-weighted TL pinned (`omnivore_web` → `TL_C=2.25`), equivalence tests for every threaded function, validator `bioms_losses` symmetry, narrowed-except warning, `@safe_render` uniform error element.
- App imports clean; the TL toggle switches the metric across all analysis tabs; a forced renderer failure shows a clean message, not a traceback.
- No redundant TL/MTI/color recomputation: each is computed once per `current_network`/`tl_method` change (verifiable by the single `reactive.calc` definitions feeding all consumers).

## Risks & Mitigations

- **Threading divergence** (a function computes TL differently than the passed value) → equivalence tests per function (B2).
- **TL toggle not propagating** to a renderer that still computes internally → the `_build_network` helper + explicit pass-down at every call site; a grep check in the plan that no analytical renderer calls `calculate_trophic_levels`/`get_functional_group_colors` directly after B3.
- **`@safe_render` masking real bugs** → it logs `logger.exception` (full traceback to logs) and only affects the *display* path; tests assert the log call fires.
- **Short-weighted NaN cascade** into `np.mean(TL)` for unreachable cycles → use `np.nanmean` in the system-level TL aggregation when method is short_weighted, mirroring the omnivory NaN handling.
