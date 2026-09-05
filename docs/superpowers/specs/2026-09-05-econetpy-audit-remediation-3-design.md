# EconetPy Audit Remediation #3 — Design Spec

**Source:** `docs/superpowers/specs/2026-09-05-econetpy-deep-review-findings.md` (28 confirmed new findings, 18 unverified) plus the out-of-scope items recorded by remediation #2's final review.
**Baseline:** `master` at `bf37c43`, 133 tests passing, 3 known UserWarnings (`network_analysis.py` lines 122, 134, 186).
**Predecessor:** remediation #2 (`audit2-phase1`..`audit2-phase6`), merged. Nothing that branch fixed is re-asked here.

## Goal

Close the confirmed findings that affect correctness, data integrity, or a user's ability to deploy and trust the app, and repair the tests that cannot fail on the bug they claim to guard.

## Already fixed by remediation #2 — do NOT re-do

| Deep-review finding | Where it was closed |
|---|---|
| A9 pickle validator accepts a permuted frame | `app.py:114-115` now `info_pkl['species'].tolist() == list(G_pkl.nodes())` |
| A8 (half) no permuted-pickle test | `test_load_data_alignment.py::test_load_default_data_rejects_permuted_pickle` |
| A24 vacuous validator "perfect balance" fixture | strengthened during Phase 1 |
| Part of A11's cause | non-finite rejection in `fluxing` + validator |
| README license/pyvis/Data-Import tab, deploy `data/` exclude | Phase 5 |

## Decisions (controller rulings, no human available)

1. **Fail loudly at startup over silently serving fake data.** A misalignment or malformed source aborts app import. Serving `Species_1..Species_10` with random biomass while looking like the Baltic web is the worst outcome in a scientific tool.
2. **Data files resolve against `Path(__file__).parent`, never the process cwd.** A `--data-dir` flag is out of scope.
3. **Validate `met.types` at ingestion, not at use.** One validator in `load_data`, reused by the editor apply handler.
4. **The energy-balance verdict becomes user-visible.** Displayed, not merely stored.
5. **Do not restructure `deploy.sh`.** Make it runnable and honest; the allowlist-vs-rsync redesign stays out.
6. **Delete the R-era `deployment/` directory** rather than maintaining two deploy paths. The R app is the historical source, not a shipped artifact.
7. **Feedback stays synchronous in the local-append path and becomes async only for the network call.**
8. **Tests that cannot fail are defects.** Every repaired test must be shown failing against the bug it guards.

## Global constraints

- Python via `micromamba run -n shiny python`; tests `micromamba run -n shiny python -m pytest`.
- Shiny for Python **1.7.0** (`render.DataGrid` has no `editable_columns`; `data_patched()`, `set_patch_fn()` exist).
- Suite starts at **133 passed, 3 known UserWarnings**. Any other warning is a defect.
- `BalticFW.pkl` is gitignored and rebuilt by `micromamba run -n shiny python load_data.py`.
- Every behavior change lands with a test that was seen RED first.
- No pushes, no tags beyond the phase tags named here.

---

## Phase 1 — Data integrity and startup honesty

- **1.1 (A1)** `app.py:165-170`: delete the blanket `except Exception` around `load_default_data()`, or narrow it to `(FileNotFoundError, ImportError)` so a misalignment `ValueError` aborts import. A caught fallback must set a module flag `USING_EXAMPLE_NETWORK = True`.
- **1.2 (crit3)** `app.py:101` and `load_data.py:25-33`: resolve `BalticFW.pkl`, the GraphML, the CSV and the JSON against `Path(__file__).parent`. `load_baltic_data` takes an optional `base_dir: Path | None = None` defaulting to its own module directory.
- **1.3 (A1)** When the example network is in use, the dashboard shows a visible banner. Not a stdout print.
- **1.4 (A2)** `flux_calculations.calculate_losses_allometric`: raise `ValueError` naming the unknown values and the accepted set `{"invertebrates", "ectotherm vertebrates", "Other"}` instead of silently mapping to intercept 0. `load_data.load_baltic_data` validates the column at load; the editor apply handler validates edited values and shows an error notification instead of applying.
- **1.5 (A3)** Add `_assert_aligned(G, info)` in `app.py`, called on every `load_default_data` return path and before `current_species_info.set(df)` in the editor handler. Raises on mismatch.
- **1.6 (new, from #2's review)** `flux_calculations.validate_flux_equilibrium`: extend the non-finite guard to `efficiencies`, matching the existing early-return keys and shape.
- **1.7 (new)** After the stale-pickle fall-through, re-save the rebuilt pickle so a stale cache is repaired once rather than bypassed on every start.

## Phase 2 — Flux and keystoneness presentation correctness

- **2.1 (A10)** `app.py:977` and `:1222`: titles become "(Rows = Prey, Columns = Predators)" with explicit `xlabel`/`ylabel`. A render test pins the title string.
- **2.2 (A11)** Surface `validate_flux_equilibrium`'s verdict: a warning notification plus a line in the flux indicators panel when not balanced, and a `logger.warning`.
- **2.3 (A12)** `flux_results.set(None)` before `current_species_info.set(df)` in the editor apply handler, so flux panels cannot render a pre-edit matrix against post-edit labels.
- **2.4 (A13)** `calculate_keystoneness` returns the computed thresholds (`ks_hi`, `bm_lo`); the scatter draws those instead of the hardcoded 1 and 0.05, and the summary reports the top species among `status == "Keystone"` or relabels to "Highest keystoneness index".
- **2.5 (crit1)** `download_network` deep-copies the network and sets inline CDN resources before `generate_html()`, so the downloaded file renders standalone. Test: the download HTML contains no `src="lib/` reference.

## Phase 3 — Test integrity

Each item is repaired by first demonstrating the test passing against the bug.

- **3.1 (A5)** Declare `hypothesis` and `pytest` in `environment.yml` and `requirements.txt` (dev section).
- **3.2 (A23)** `test_fluxing_with_zero_biomass`: replace `isfinite | isnan` with the pinned contract for a consumer whose only prey has zero biomass.
- **3.3 (A22)** `test_keystoneness_ranking_invariant_to_log_base`: compute the reference ranking independently and assert species order.
- **3.4 (A20)** `test_network_viz_render.py`: assert the escaped form present AND the raw form absent.
- **3.5 (A21)** `test_safe_render_below_render_text_order`: actually invoke the stacked renderer, or delete it as a duplicate.
- **3.6 (A25)** Pin `nwC`, `nwG`, `nwV` closed-form on the chain fixture and an omnivory web.
- **3.7 (A26)** The AST cache guard collects attribute calls, asserts every name in `RENDERERS` was visited, and includes the two data-frame renderers.
- **3.8 (A8 remainder)** A same-set/different-order GraphML+CSV pair proving `load_baltic_data`'s reindex branch actually runs.

## Phase 4 — Feedback path

- **4.1 (A4)** The submit effect becomes async; `create_github_issue` runs via `asyncio.to_thread`. The local NDJSON append stays synchronous. Add `http.client.HTTPException` to the caught exceptions.
- **4.2 (A17)** Server-side length caps (title 200, description and steps 5000, browser info 512) enforced before the local save, plus `maxlength` on the inputs. The rate limit becomes process-wide rather than a per-session reactive value.
- **4.3 (crit6)** `get_functional_group_colors` coerces labels with `str()` before sorting; `functional_groups_legend` gets the `@safe_render("ui")` wrapper the other renderers have.

## Phase 5 — Deployment

- **5.1 (A6)** `deploy.sh`: create the log directory before the first log line; add `set -o pipefail`.
- **5.2 (A18)** Pre-flight tests entries with `[ -e ]`; drop `BalticFW.pkl` from the required list.
- **5.3 (A19)** Package install and service restart become fatal unless `--force`; stderr is kept; a non-2xx verification fails the run.
- **5.4 (A7)** Delete `deployment/deploy.sh`, `pre-deploy-check.R`, `install_dependencies.R`, `shiny-server.conf`; point `README.md` at `DEPLOYMENT.md`.
- **5.5 (new)** Add a post-transfer `load_data.py` rebuild step so the server builds its own pickle instead of receiving the developer's.
- **5.6 (crit5)** Remove plotly, great-tables, openpyxl, xlrd, shinywidgets from `requirements.txt` and `environment.yml`; keep the README list in agreement.

## Phase 6 — Remaining UI and latent items

- **6.1 (A14)** Page inputs persist across menu navigation (hidden navset, or values carried in reactive state). `flux_results` records the temperature used and the panel displays it.
- **6.2 (A15)** The built network is cached in a `reactive.calc` keyed on data only; the height slider applies to the iframe, not the network object.
- **6.3 (crit2)** Nodes get `fixed={'y': True}` in both builders so trophic level is readable as vertical position.
- **6.4 (crit4)** Biomass labels read `g/km²`, not `g/km²/day`, in tooltips and both plots.
- **6.5 (A16)** Transpose the example adjacency CSVs to the tracked Baltic convention and correct `examples/README.md`.

---

## Build order and gates

Phases 1 → 6 in order; TDD per task; full suite plus `import app` green at each phase gate; tag `audit3-phase{N}`.

Phase 1 and Phase 2 both touch the editor apply handler; Phase 1 lands first and Phase 2 extends it. Phase 6.3 changes emitted node attributes, so the pinned viz tests from remediation #2 must be updated in the same task.

After Phase 6: a live smoke that drives the Data Editor (the gap remediation #2 never closed), forces a renderer error, and downloads the network HTML.

## Acceptance criteria

- Importing `app` with a deliberately misaligned CSV raises rather than serving the example network; launching from another directory loads the Baltic data.
- An unknown `met.types` value raises with the accepted set named.
- An unbalanced flux solution is visible to the user.
- The downloaded network HTML renders with no local asset references.
- Every repaired test in Phase 3 was shown failing against its bug.
- `./deploy.sh` runs from a fresh clone; a failed install or restart fails the run.
- Suite green; no new warnings.

## Risks

- **Failing loudly at startup** turns a silent degradation into a hard stop. Mitigated by the banner path for the genuinely-absent-sources case, which stays a fallback rather than an abort.
- **Deleting `deployment/`** removes the only R deploy path. It targets an app this repo no longer ships; the R sources themselves stay.
- **Async feedback** changes handler timing. The local append stays synchronous so the user-visible confirmation is unchanged.
- **Phase 6.3 fixed-y** changes rendered layout; the pinned tests must be updated deliberately, not silently.
