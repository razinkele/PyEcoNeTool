# EconetPy Audit Remediation #2 — Design Spec

**Date:** 2026-06-14
**Status:** Approved (design), pending spec review
**Source:** Deep multi-angle codebase audit (6 angles + verify + completeness critic; 63 findings → 25 confirmed worthwhile + 8 critic-found). All findings below were adversarially verified against the real code; the load-bearing values were re-derived independently before writing this spec.

## Goal

Fix the confirmed inconsistencies and bugs from the deep audit, in six TDD-gated phases. The 106-test baseline stays green; new tests are additive. The node↔row join becomes key-based (the one design change); everything else preserves current behavior except where it was wrong.

## Decisions (from the user, 2026-06-14)

- **License:** GPL-3.0 is canonical (fix the README footer + badge consistency; the code header already says GPL).
- **Alignment:** deep fix — relabel graph nodes to species names, key the join, regenerate `BalticFW.pkl`.
- **deploy.sh:** fix the privacy/data-loss issue (exclude `data/`, no `--delete` clobber of user data).

## Conventions

- All tests run via `micromamba run -n shiny python -m pytest`. Repo root is the working dir. Work on a feature branch; do not push/merge unless asked.
- Each phase ends green (full suite + `import app`) and is tagged.

---

## Phase 1 — Numeric correctness (do first)

### 1.1 Flux inflow-diversity is transposed (`network_analysis.py:382`)
`calculate_flux_indicators` normalizes inflows with `(W_net.T / sum_in).T`, which divides `W_net[i,j]` by `sum_in[i]` (the *prey's* total inflow) instead of `sum_in[j]` (the *predator's* intake). The outflow side (`:394`) is correct. Result: `lwG` is computed on the wrong distribution; `lwV` is fine.
- **Fix:** `:382` → `H_in_mat = (W_net / sum_in[np.newaxis, :]) * np.log(W_net / sum_in[np.newaxis, :])` (mirror the outflow form, divide each column by its predator's intake).
- **Test (must be discriminating):** a web with a **multi-prey predator** — the 3-chain gives `lwG=lwV=1.0` under *both* buggy and fixed code (single-prey predators hide the transpose). Use e.g. predator C eating prey A and B with **equal** flux so its effective number of prey `N_res=2.0`; assert `lwG`/`N_res` reflects 2 effective prey (the buggy transpose gives a different value). Pin the 3-chain `lwG=lwV=1.0` as a non-regression anchor, and assert `lwV` is byte-identical before/after the fix (the fix touches only the inflow path).

### 1.2 NaN biomass reported as perfect equilibrium (`flux_calculations.py:~180-187, ~287`)
A single NaN biomass → all-NaN `F`; `np.any(F < -1e-9)` is `False` for NaN, so `fluxing` does not raise; `validate_flux_equilibrium` then returns `balanced=True, max_imbalance=0.0`. Broken == valid.
- **Fix:** in `fluxing`, before the negative-F check, raise `ValueError` if inputs are non-finite OR `not np.all(np.isfinite(F))` (after solve). In `validate_flux_equilibrium`, if `flux_matrix`/inputs contain non-finite values, return `balanced=False` with `max_imbalance=inf` (or `nan`) rather than `0.0`.
- **Test:** `fluxing` with one `np.nan` biomass raises; `validate_flux_equilibrium` on a non-finite flux returns `balanced=False`.

### 1.3 Omnivory center wrong under short-weighted TL (`network_analysis.py:232`)
`center = tlnodes[i] - 1.0` equals the diet-weighted mean prey TL **only for prey-averaged TL**. The app now threads short-weighted TL into `get_topological_indicators`, where the identity breaks, so the omnivory variance is taken about the wrong center.
- **Fix:** `:232` → `center = float(np.sum(DC[:, i] * tlnodes))` (the actual diet-weighted mean prey TL). Update the docstring (`:219-221`) to stop asserting `center == TL_i - 1`.
- **NaN-prey rule (precise):** if any prey of predator `i` has a NaN TL, renormalize `DC[:, i]` over the finite-TL prey only — `w = DC[mask, i] / DC[mask, i].sum()` — then `center = sum(w * TL[mask])` and `OI_i = sum(w * (TL[mask] - center)**2)`. If no finite-TL prey remain, `OI_i = NaN`. (This keeps a predator with some short-weighted-NaN prey from poisoning to NaN.)
- **Verified invariance:** the prey-averaged `Omni=0.125` pin is unchanged (for prey-averaged the new center *equals* `TL_i-1`). For `omnivore_web`, corrected `Omni=0.125` under **both** methods (re-derived). *(There is no `0.247` regression pin today; the Baltic `0.247` value was observed live, not pinned — if a second invariant is wanted, add the post-regen BalticFW system Omni as a NEW pin, clearly labeled.)*
- **Test:** assert `Omni == 0.125` for `omnivore_web` under both `prey_averaged` and `short_weighted` (was wrong under short-weighted before the fix).

---

## Phase 2 — Alignment, deep (key the node↔row join by name)

Root cause: node IDs are `n0..n33`; species names live in `info['species']`; everything aligns by load-order accident. **Verified:** the GraphML carries a `name` attribute on every node (`n0→'Synchaeta'`), and it matches `info['species']` positionally.

### 2.1 Relabel + key the join (`load_data.py`)
- In `load_baltic_data`: after reading the GraphML, `names = nx.get_node_attributes(G, 'name')`; if complete, `G = nx.relabel_nodes(G, names)`. Then **`assert list(G.nodes()) == info['species'].tolist()`** (reindex `info` to node order first if needed). Delete the dead `str(i)` relabel branch (`:55-64`) — it never fires (`n`-prefixed IDs).
- `load_baltic_data` **raises** on contract violations instead of `print`-and-continue (missing columns, length mismatch, name/order mismatch).
- **Regenerate `BalticFW.pkl`** (run the fixed `load_data.py`); node IDs become species names, data values identical. **Note: `BalticFW.pkl` is gitignored — it is NOT committed.** It is a per-machine cache rebuilt from the tracked GraphML/CSV/JSON. So there is no "commit the pickle" step; instead, every dev/CI machine must rebuild it (see build order). **Verified: the 34 species names are unique** (no `relabel_nodes` merge risk).

### 2.2 Key the matrix builders (`app.py`, `network_analysis.py`, `network_viz.py`)
Pass `nodelist=info['species'].tolist()` (== `list(G.nodes())` after 2.1) to **both** `nx.to_numpy_array(G)` call sites where per-species alignment matters: `app.py:955` (`adjacency_heatmap`) **and `app.py:1119`** (the `calculate_fluxes` effect — the actual flux-solve `mat=` fed to `fluxing()`, the more important one), plus the MTI/omnivory/keystoneness builders. After 2.1 this is belt-and-suspenders, but it makes the contract explicit and survives a future reorder. **This change must land in the same task as the pickle regen (2.1), before that task's gate** — adding `nodelist=info['species']` against a stale `n0..n33` pickle throws `NetworkXError`.

### 2.3 Pickle fast-path validation (`app.py:~96-104`)
On the pickle load, validate `{'network','info'}` keys, the required columns, **AND `set(info['species']) == set(G.nodes())`**; on any failure, fall through to reconstruction from the tracked sources (don't crash deep in a renderer with an opaque `KeyError`, and don't silently use a stale n-prefixed pickle after 2.1).

### 2.4 Data Editor reorder-safety (`app.py:~1356-1383`)
`current_species_info.set(species_info_editor.data_view())` (`app.py:1365`) returns *display-order* rows **with edits**; a user sort silently permutes biomass/efficiency against unchanged node order. **Fix: read from `species_info_editor.data_patched()`** — original node order WITH user cell edits — *not* `.data()` (drops edits) and *not* `.data_view()` (display order). Alternatively, reindex `data_view()` back to node order before `set`. `assert len == G.number_of_nodes()`; make `species`/`fg` non-editable in the editor. (Also correct the stale `app.py:1365` comment.)

### 2.5 Keystoneness names (`#4`, resolved by 2.1)
After 2.1, `calculate_keystoneness`'s `species` column holds real names. Add a **regression test** with a fixture whose node IDs are **non-trivial vs insertion order** (so the descending sort reorders rows), asserting BOTH: (a) the returned `species` column holds the mapped **names**, not raw IDs; and (b) per row, `relative_biomass == biomass[that node] / total` — i.e. the `(species, relative_biomass)` pairing survives the descending sort. A node==name fixture cannot catch the original bug.

---

## Phase 3 — Robustness guards

- **3.1 (`#7`)** Empty graph: `calculate_mti` and `calculate_keystoneness` raise `ValueError("Network contains no vertices")` on `len(G.nodes()) == 0` (mti silently returns `[]`; keystoneness raises a cryptic `IndexError`).
- **3.2 (`#8`)** `calculate_keystoneness` type-guard: add `if not isinstance(G, nx.DiGraph): raise ValueError(...)` at the top — currently skipped on the cached `mti=` path (the app's path).
- **3.3 (`#9`)** `nwG`/`nwV` (`network_analysis.py:~301,305`): the guards test node *count* but divide by biomass *sum* → all-zero-biomass prey gives silent NaN. Guard the divisor like `nwTL`/`nwC` (`... if denom > 0 else 0`).
- **3.4 (`#10`)** Flux effect (`app.py:~1103-1145`): cleared `input.temperature()` → `None` → `TypeError` escapes the `ValueError`-only `except`; `bodymasses <= 0` → inf/NaN loss. Add `req()` guards (and a finite-bodymass guard) around `calculate_losses`.
- **3.5 (`#13`)** Zero-biomass keystoneness (`network_analysis.py:~528-553`): the `total_biomass > 0` guard makes `relative_biomass` all-**ZERO** (not NaN) when `total_biomass == 0`; the quartile classification then still labels a degenerate web (a 4-node web yields e.g. `['Keystone','Rare','Rare','Rare']`, driven entirely by the impact quartile — meaningless). Fix: special-case `total_biomass == 0`/empty → all `"Undefined"` (or raise); guard `np.quantile` on empty finite/relative-biomass arrays. **Test: assert `"Undefined"` under zero biomass** (not "all NaN" / not "all Keystone").
- **3.6 (`#16`)** Logging: add one `logging.basicConfig(level=..., format=...)` at app start, honoring `ECONETPY_LOG_LEVEL` (default INFO). Currently the root logger has no handler, so `logger.info` is dropped and ERROR reaches stderr with no timestamp/level.

---

## Phase 4 — Test coverage additions (pure additions)

- **4.1 (`#12`)** Bersier `calculate_flux_indicators` is runtime-untested (`:375-414` 0% covered). Add parametrized pins using **multi-prey** webs (so they're discriminating), computed from the *corrected* formula (post-1.1).
- **4.2 (`#14`)** Pred-level efficiency grounding (`test_flux_calculations.py:~230`): make the basal-`e=0` case primary — chain `0→1→2`, pin `flux[0,1]`; wrong grounding makes the matrix singular.
- **4.3 (`#15`)** Disconnected-graph ShortPath largest-cc branch (`network_analysis.py:~204-213`); color-collision when a 6th functional group reuses `COLOR_SCHEME[0]` (`network_viz.py:~297-321`) + a `logging.warning` on color overflow.

---

## Phase 5 — Ops + docs

- **5.1 (`#17`)** `deploy.sh`: add `data/` to `EXCLUDE_PATTERNS`; ensure the rsync never `--delete`s user-data dirs (`data/user_feedback_log.ndjson` carries prior feedback + User-Agent strings and is currently pushed to the public server *and* clobbered). The curated `FILES` allowlist is dead — note it.
- **5.2 (`#18`)** README: make **GPL-3.0** canonical (fix the CC BY-SA footer); regenerate the dependency list to match reality (`pyvis` is a git fork, not `>=0.3.2`); remove the documented "Data Import" file-upload tab that doesn't exist.

---

## Phase 6 — Refactors (last, behavior-preserving)

- **6.1** Page routing: replace the 8 menu effects + `main_content` if/elif with one ordered `PAGES` dict (`page_key → (menu_input_id, ui_builder)`), loop-registered effects, dict-lookup dispatch. Keep the `*_ui` builders as named module attributes (`test_app_structure.py` calls `app.dashboard_ui()`). Leave `menu_feedback` as its own modal effect.
- **6.2** Viz dedup: extract `_add_styled_nodes(net, G, names, groups, biomass, colors, tl, physics_opts)` shared by `create_topology_network`/`create_flux_network`; hoist `NAN_TL_Y = -15.0` to module scope. Add a flux-side node size/y test (currently topology-only).

---

## Build order & gates

Phases 1→6 in order. Each phase: TDD per task (failing test first for behavior changes; pinned/regression tests), full suite + `import app` green at the phase gate, tag `audit2-phase{N}`.

**Phase 2 pickle handling (load-bearing):** `BalticFW.pkl` is **gitignored**, so it is regenerated, never committed. The 2.1 relabel + 2.2 `nodelist=` + the pickle regen must land **together** (one task), and that task's gate must **`rm -f BalticFW.pkl` then rebuild from source** (`micromamba run -n shiny python load_data.py`) so a stale `n0..n33` cache cannot mask the `nodelist=` crash. Add a test that loads via `load_default_data()` so the gate exercises the on-disk pickle path (not just in-memory graphs).

After all phases, a **live Playwright smoke**: keystoneness panel shows species names (not `n23`); TL toggle still recomputes; a forced renderer error still shows the clean panel.

## Acceptance criteria

- All 106 existing tests pass unchanged; new tests for each fix.
- `lwG` correct (multi-prey discriminating pin); NaN biomass raises / validator flags it; omnivory `0.125` under both TL methods.
- Node IDs == species names after load; `assert` guards the join; `BalticFW.pkl` regenerated; editor reorder-safe; keystoneness panel name-keyed (regression test with node≠name).
- Empty/zero-biomass/non-DiGraph/cleared-input paths raise or degrade cleanly (no silent NaN); logging configured.
- `deploy.sh` excludes `data/`; README internally consistent (GPL-3.0), deps accurate, no phantom tab.
- App imports; live smoke green.

## Risks & mitigations

- **Regenerating `BalticFW.pkl`** — it is *gitignored* (per-machine cache), so the real risk is a **stale cache** on a dev/CI machine still holding `n0..n33` IDs, which would make the 2.2 `nodelist=info['species']` change crash with `NetworkXError`. Mitigated by rebuilding (`rm -f` + `load_data.py`) inside the Phase-2 gate, the `set(species)==set(nodes)` pickle-load validation (2.3), and the `assert list(G.nodes())==info['species']` at load. Species names are unique (verified), so `relabel_nodes` cannot merge nodes; data values are unchanged.
- **`nodelist=` changes** could reorder a matrix if misused → the post-relabel identity assert makes `nodelist` a no-op for the real data; tests pin per-species outputs.
- **Phase 6 refactors** are behavior-preserving → the AST guard + full suite + the `app.dashboard_ui()` structural test catch regressions.
