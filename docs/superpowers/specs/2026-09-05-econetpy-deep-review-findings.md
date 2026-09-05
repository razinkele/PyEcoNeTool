# EconetPy Deep Codebase Review — Findings (2026-09-05)

**Tree reviewed:** branch `feature/audit-remediation-2`, HEAD `0ad9b00`, clean, 115 tests passing.
**Scope:** the Python app and its ops/docs. R sources (`app.R`, `Script.R`, `EcoNeTool-master.zip`) were used only as the reference for intended semantics.
**Method:** 6 parallel finders (scientific method, Shiny reactivity, data alignment, robustness, test quality, ops/docs) → dedupe → 3 lens-diverse adversarial verifiers per new finding (code-truth, impact, already-covered; a finding survives only if code-truth passes and ≥2 of 3 do not refute) → completeness critic. 97 agents total.
**Counts:** 61 raw findings → 50 after dedupe → 8 re-confirmations of known open items (K2.4, K3.3, K3.4 ×2, K4.1, K4.2, K5.1, K5.2) → 42 new. 30 verified: **28 confirmed, 2 refuted.** 12 lower-ranked new findings were not verified (listed at the end). The critic added 6 more unverified findings.

The known-item IDs (K2.4 … K6.2) refer to the open remediation-#2 plan in `2026-06-14-econetpy-audit-remediation-2-design.md`. Nothing below duplicates those unless stated.

Headline severity is the finder's rating; where verifiers voted to lower it, the adjustment is given in parentheses after the heading.

---

## A. Confirmed new findings (28 findings under 26 headings, ranked)

A8 and A10 each merge two confirmed findings that share one defect.

### A1. Startup blanket `except` silently serves the synthetic example network — HIGH
`app.py:160-165`. The inner fallback at `:116-121` was deliberately narrowed to `(FileNotFoundError, ImportError)`, but the outer `except Exception` around `load_default_data()` swallows the misalignment `ValueError` that commit `4bee51c` added, prints to stdout, and starts the app on `Species_1..Species_10` with random biomass. Same outcome whenever `shiny run` is launched from a cwd other than the repo root (see A-crit3). Verified empirically by importing `app` with one species name changed in the CSV.
**Fix:** drop the outer except (or restrict it to the same tuple); resolve data paths against `Path(__file__).parent`; surface "example network in use" in the UI, not only stdout.

### A2. Unrecognised `met.types` string silently gets intercept 0 — HIGH (impact lens: medium)
`flux_calculations.py:244` `x0 = np.array([losses_param.get(mt, 0) for mt in met_types])`. Any case/whitespace variant, blank, or NaN maps to the `"Other"` intercept, dropping that species' metabolic losses by ~e^17. The Data Editor (`app.py:1367`) makes `met.types` editable, so it is reachable in one edit. The R reference fails loudly on a mismatched name.
**Fix:** raise `ValueError` listing the unknown values and the accepted set; validate in `load_baltic_data` and the editor apply handler.

### A3. Two keying conventions with no boundary assertion — HIGH
`app.py:964` and `:1128` build matrices with `nodelist=info['species'].tolist()` (info order); every consumer (`network_viz.py:134/204`, `network_analysis.py:51/103`, `app.py:618`, `:637-641`, `:1029-1033`, `:1334`) pairs positionally with `list(G.nodes())`. Nothing at the reactive boundary asserts `list(G.nodes()) == info['species'].tolist()`. Empirically, a permuted `info` produces flux edges drawn between the wrong species, an MTI heatmap with wrong labels, and a TL table pairing names with other species' TLs. Reachable via K2.4 (editor sort) or a misordered pickle (A9).
**Fix:** one `_assert_aligned(G, info)` called on every `load_default_data` return path and before `current_species_info.set(df)`; test that a permuted info trips it.

### A4. Feedback submit blocks the asyncio event loop for every session — HIGH (verifiers: medium)
`feedback_reporter.py:138` synchronous `urllib.request.urlopen(req, timeout=10)` inside a sync `reactive.effect` (`app.py:768-815`). py-shiny 1.7 `wrap_async` runs sync effects inline on the loop, so one slow GitHub call freezes all connected sessions. Latent until `ECONETPY_GITHUB_TOKEN` is set (it is set nowhere in `econetool.service`/`DEPLOYMENT.md`, see U11). Also: `http.client.HTTPException` is not in the caught tuple, so a malformed response escapes after the local save already succeeded, leaving the modal open for a duplicate resubmit.
**Fix:** async effect + `await asyncio.to_thread(submit_feedback, …)`; add `HTTPException` to the except.

### A5. `hypothesis` is imported but not declared — HIGH (verifiers: medium)
`test_network_analysis.py:15` module-level import; `environment.yml:36` declares only `pytest>=8.0`, `requirements.txt` neither. A fresh env from the repo's own files fails collection of all 42 network-analysis tests. The 115-pass baseline holds only because the dev env happens to have hypothesis installed.
**Fix:** add `hypothesis` and `pytest` to a dev section of both files (or `pytest.importorskip`).

### A6. `deploy.sh` cannot run on a fresh checkout — HIGH
`deploy.sh:635` `log_info` → `tee -a "$LOG_FILE"` runs before `check_prerequisites` creates `deployment_logs/` (`:242`). With `set -e` (`:25`) the script exits right after the banner. Verified empirically.
**Fix:** `mkdir -p "$(dirname "$LOG_FILE")"` right after `LOG_FILE` is defined; add `set -o pipefail`.

### A7. R-era `deployment/deploy.sh` is destructive and then aborts — HIGH (blast radius: the old R deployment)
`deployment/deploy.sh:203` `rm -rf /srv/shiny-server/econetool/*` then `:209` `cp "$APP_DIR/plotfw.R"` — `plotfw.R` does not exist in the repo, so `set -e` exits leaving an empty app dir with no backup. `README.md:192` and `deployment/README.md` still route operators to it.
**Fix:** delete or clearly archive the R deployment folder; point `README.md` at `DEPLOYMENT.md`.

### A8. Pickle-load tests cannot see a permuted pickle — HIGH (verifiers: medium/low)
`test_load_data_alignment.py:31-37` skips on GraphML absence rather than pickle absence and runs only against the developer's fresh local pickle. `test_load_data_alignment.py:5-22`: the tracked GraphML order already equals the CSV order, so the name-keyed reindex branch in `load_data.py:64-66` is never actually exercised; the synthetic test only reaches the set-inequality raise.
**Fix:** tmp_path tests with same-set/different-order GraphML+CSV and a permuted pickle; assert `meanB` follows the species.

### A9. Pickle validator is set-based, not order-based — MEDIUM
`app.py:109-111` `set(info_pkl['species']) == set(G_pkl.nodes())` accepts a row-permuted or duplicated-row info (verified: 35 rows vs 34 nodes passes). Combined with A3, a misordered gitignored pickle silently permutes every table. The impact lens notes the current `save_to_pickle` always writes aligned data, so the vector is a hand-edited or stale pickle. Shares root cause with A8.
**Fix:** `list(G_pkl.nodes()) == info_pkl['species'].tolist()` and fall through to rebuild otherwise.

### A10. Heatmap axis titles are transposed — MEDIUM (two sites, one defect)
`app.py:977` and `:1222` say "Rows = Predators, Columns = Prey"; the matrices are rows = prey, columns = predators (edges are prey→predator; verified on the Baltic data: cod's row is all zeros). Every diet/predation reading from the heatmaps is inverted.
**Fix:** "(Rows = Prey, Columns = Predators)" plus explicit `xlabel`/`ylabel`; pin the title in a render test.

### A11. Energy-balance validation is computed and never shown — MEDIUM
`app.py:1159-1172` stores `validation` in `flux_results` under a comment admitting it is unused; no reader anywhere. A collapsed solution (zero-biomass prey → zeroed column → `D_e` grounded) is reported through lwC/lwG/lwV and the flux network as a valid equilibrium. Related: any non-`ValueError` escaping the flux effect closes the whole session (K3.4 territory).
**Fix:** `ui.notification_show(type='warning')` and a line in `flux_indicators()` when not balanced; `logger.warning`.

### A12. `flux_results` never invalidated on Data Editor apply — MEDIUM
`app.py:1391` sets `current_species_info` but `flux_results` (only set at `:1153`/`:1168` inside the button effect) keeps the pre-edit matrix, now rendered with post-edit labels, sizes and tooltips.
**Fix:** `flux_results.set(None)` before `current_species_info.set(df)` (the flux panels already handle `None`).

### A13. Keystoneness plot thresholds and summary contradict the classification — MEDIUM
`app.py:1306-1307` draws lines at KS=1 and rel. biomass=0.05 (old fixed thresholds) while `network_analysis.py:549-557` classifies with Libralato log10 KS and per-web Q3/Q1 quantiles. On the Baltic data KS ranges about −1.2..0.16, so the y=1 line is above every point; `app.py:1252-1262` labels `Gadus morhua` "Top Keystone Species" while its status is Dominant.
**Fix:** return `ks_hi`/`bm_lo` from `calculate_keystoneness` and draw those; report the top species among status=="Keystone".

### A14. Page inputs are destroyed on every menu click — MEDIUM
`app.py:852-870` `main_content` rebuilds each page from a lambda, so `temperature` resets to 3.5 and `network_type`/`network_height` to defaults while `flux_results` persists: the sidebar shows 3.5 °C next to a 20 °C solution, and nothing records which temperature was used.
**Fix:** `ui.navset_hidden` with static panels, or persist inputs in `reactive.Value`s and pass them as `value=`; store `temperature` in `flux_results` and display it.

### A15. Height slider rebuilds the whole pyvis network — MEDIUM
`app.py:940-947` bakes `network_height` into the `Network` object, so every debounced slider step deep-copies and re-inlines vis.js (MBs of srcdoc), reloads the iframe and restarts physics, losing the user's layout.
**Fix:** cache the built network in a `reactive.calc` keyed on data only; apply height to the iframe style.

### A16. Example adjacency CSVs use the opposite orientation from the Baltic export — MEDIUM (latent)
`examples/Simple_3Species_network.csv` is row-eats-column (`create_example_datasets.R:18`), `BalticFW_adjacency.csv` is rows = prey (igraph `as_adjacency_matrix`). Verified: `nx.from_pandas_adjacency` on the example makes Fish basal and Phytoplankton the top predator. No loader reads either today, so latent until a CSV upload feature lands.
**Fix:** transpose the tracked examples to the Baltic convention and fix `examples/README.md:56`, or give any future loader an explicit orientation flag.

### A17. Feedback endpoint: no size caps, per-session rate limit — MEDIUM
`app.py:649` `last_feedback_submit = reactive.Value(None)` is per session; `feedback_reporter.save_feedback_local` has no length check. A script opening N sessions can grow `data/user_feedback_log.ndjson` without bound on a public, unauthenticated `0.0.0.0:8000` service, and open unlimited GitHub issues if the token is set. The finder's code-fence-breakout sub-claim was refuted by two verifiers.
**Fix:** server-side max lengths; process-wide limiter; size-cap/rotate the NDJSON.

### A18. `deploy.sh` pre-check always fails without `--force` — MEDIUM
`deploy.sh:299-304` tests each `FILES` entry with `[ -f ]`, but `FILES` (`:62-74`) holds `www/`, `examples/` and the gitignored `BalticFW.pkl`. Operators learn to always pass `--force`, which also waives the ssh/rsync checks. Distinct from K5.1.
**Fix:** `[ -e ]`; drop the pickle from the list; make `FILES` the real transfer allowlist.

### A19. `deploy.sh` reports success unconditionally — MEDIUM
`deploy.sh:487-498`, `:533`, `:662`: pip install failure and `systemctl restart` failure (stderr discarded) downgrade to `log_warn` and the green banner prints. A server without git fails the `git+https` pyvis line, the old code keeps running, and systemd's `Restart=always` loops if pyvis is missing.
**Fix:** make install and restart fatal unless `--force`; keep stderr; fail on non-2xx from the curl check; document git as a prerequisite.

### A20–A28. Test-quality gaps (all MEDIUM unless noted)
- **A20** `test_network_viz_render.py:107,112` accept the raw un-escaped `<i>`/`&` as passing alternatives, so the escaping test passes in the state it guards against; `:84` passes if tooltips are dropped entirely. Assert the escaped form present and the raw form absent.
- **A21** `test_app_structure.py:76-90` defines the `@render.text`/`@safe_render` stacked `boom` but never calls it; only `raw_boom` is asserted. Tests nothing about decorator order.
- **A22** `test_network_analysis.py:634-645` "log-base invariance" only asserts the frame is sorted descending, which `sort_values` guarantees by construction. Compute the reference ranking independently.
- **A23** `test_flux_calculations.py:445` `isfinite | isnan` is false only for ±inf, so it cannot fail on any value `fluxing` returns. Zero-biomass prey silently yields an all-zero matrix (verified). Pin the contract.
- **A24** `test_flux_calculations.py:349-369` "perfect balance" fixture is unbalanced (`max_imbalance = 100`, verified) and asserts only key presence. Fix the fixture and assert `balanced is True`.
- **A25** `test_network_analysis.py:315-317` nwC/nwG/nwV only `> 0`; the `2·B·(S−1)` denominator is unpinned. Pin `225/700`, `1.0`, `1.0` on the chain fixture and `4/3` on an omnivory web.
- **A26** `test_app_structure.py:19-34` AST cache guard matches only bare-name calls, never asserts the `RENDERERS` set was visited (rename passes), and omits the two data-frame renderers.
- (The remaining two confirmed findings are the alignment-test gaps merged into A8, and the second heatmap-title site merged into A10.)

---

## B. Refuted (2)
- `flux_calculations.py:211` "app discards the shipped `losses` column / exponent −0.29 vs 0.71". Facts confirmed (ratio is exactly M_i) but the conclusion was refuted: `a=−0.29` is the mass-specific rate required because `fluxing` multiplies by biomass, and `app.R` (the port's actual reference) does the same. Worth a one-line docstring note, nothing more.
- `test_app_structure.py:38` "structural tests depend on cwd/pickle". Mechanism real, but the structural tests are data-insensitive and the one affected test already guards itself. Superseded by A-crit3.

## C. Known items re-confirmed (8)
K2.4 (`app.py:1374`), K3.3 (`test_network_analysis.py:328` — nwV NaN unasserted), K3.4 (`app.py:1118` and `:1136` — `calculate_losses` and `to_numpy_array` run outside the `ValueError`-only try), K4.1 (`test_network_analysis.py:717` — `lwC`/`loop=True`/`get_functional_group_colors` uncovered), K4.2 (`test_flux_calculations.py:244`), K5.1 (`deploy.sh:61`), K5.2 (`README.md:3`). All still open on this HEAD; no known item was found to be already fixed.

---

## D. Unverified — completeness-critic additions (6)
Not put through the refuter panel. Treat as plausible, evidence quoted.
- **crit1 HIGH** `app.py:949-955` `download_network` yields `net.generate_html()` from a `cdn_resources='local'` network, so the downloaded standalone HTML references `lib/vis-10.0.2/…` next to a file that has no `lib/`, and renders blank. Verified the emitted `<script src="lib/…">` refs; not opened in a browser. Fix: deep-copy and set `cdn_resources = CDN_INLINE` as `pyvis/shiny/wrapper.py:260-264` does; test that the download contains no `src="lib/`.
- **crit2 MEDIUM** `network_viz.py:143-154` nodes have `physics=True` and no `fixed={'y': True}`, so the trophic-level y is only a seed and barnesHut stabilisation interleaves levels; the R reference fixes y. Also the seed grows with TL while vis.js y grows downward.
- **crit3 MEDIUM** `app.py:96-98`, `load_data.py:25-33` resolve data files against the process cwd while `www/` and `VERSION` use `__file__`; launching from any other directory silently serves the example network (combine with A1).
- **crit4 LOW** `network_viz.py:138,244`, `app.py:1077,1101` label biomass "g/km²/day"; `meanB` is a stock (g/km²) per `app.R:1718` and the metadata.
- **crit5 LOW** `requirements.txt:20-28`, `environment.yml:29-35` declare plotly, great-tables, openpyxl, xlrd, shinywidgets; none is imported anywhere.
- **crit6 LOW** `network_viz.py:307` `sorted(set(functional_groups))` raises `TypeError` on a NaN `fg`; `functional_groups_legend` (`app.py:888`) is the one renderer without `@safe_render`, so the dashboard shows a raw error.

## E. Unverified — finder findings below the verification cap (12)
Ranked out of the 30-slot verification budget. Three are medium; nine low.
- **MEDIUM** `deploy.sh:456` rsync mirrors `./` (not `$PROJECT_ROOT`) with `--delete` and a denylist, so `.remember/`, `.hypothesis/`, `lib/`, `docs/superpowers/`, stale `www/*.html` and `data/` are pushed and served. Overlaps K5.1; fix together (allowlist or `git archive`).
- **MEDIUM** `feedback_reporter.py:113` `ECONETPY_GITHUB_TOKEN` is documented nowhere (`econetool.service`, `DEPLOYMENT.md`), its absence logs at INFO (dropped, K3.6), and the modal does not say submissions may become public issues.
- **MEDIUM** `README.md:119` READMEs contradict code and each other on data file names, which deploy guide applies, repo name, flux status, deps and Python version. Extends K5.2.
- **LOW** `requirements.txt:11` pyvis fork pinned by mutable tag, no commit SHA; hard-imports a fork-only module.
- **LOW** `network_analysis.py:240` system omnivory index is Christensen–Pauly variance, `Script.R` uses mean SD over consumers with ≥2 prey; roughly half the tutorial's value under the same label.
- **LOW** `network_analysis.py:133` clamped-to-[1,100] "unreliable" TLs feed mean TL, nwTL, omnivory and node y with no UI indication.
- **LOW** `network_analysis.py:467` MTI/keystoneness use the binary adjacency, not flux-weighted diet fractions as in Libralato 2006; document.
- **LOW** `app.py:75` `safe_render` catches bare `Exception`, which includes py-shiny's `SilentException`, so `req()` inside a wrapped renderer shows an error panel instead of deferring. Blocks the K3.4 `req()` fix; re-raise those two.
- **LOW** `app.py:1281` "Undefined" keystoneness species are omitted from the scatter and summary counts.
- **LOW** `app.py:667` footer "Last updated" has no reactive dependency; rendered once.
- **LOW** `app.py:523` client-side menu highlighter marks "Feedback" active though it only opens a modal.
- **LOW** `network_viz.py:138` tooltip `<b>`/`<br>` markup is rendered literally by vis-network 10 `innerText`; the existing test asserts the opposite contract.

---

## F. Coverage
Read in full by at least one finder and re-read by the critic: `app.py`, `network_analysis.py`, `flux_calculations.py`, `network_viz.py`, `load_data.py`, `feedback_reporter.py`, `conftest.py`, `test_load_data*.py`, `test_app_structure.py`, `test_network_viz_render.py`, `requirements.txt`, `environment.yml`, `econetool.service`, `.gitignore`. Read in full by one finder only: `test_network_analysis.py`, `test_flux_calculations.py`, `test_feedback_reporter.py`, `deploy.sh`, `deployment/*`, all README/DEPLOYMENT/FIXES docs. Not assessed: browser-side rendering (no app launch), the R `fluxweb` package internals, Ehnes 2011 rate units.

Verified correct and deliberately not reported: prey-averaged TL solve orientation, short-weighted TL BFS, Bersier indicators (identical to R `fluxind`, scale-invariant), Ulanowicz `Q = DC − PD^T`, Libralato `KS = log10(ε(1−p))`, prey-level fluxweb solve (energy balance to 1e-17 on the bundled data), Kelvin conversion and the 86.4 J/s→kJ/day factor, nwC/nwG/nwV/nwTL formulas, MTI conditioning (det 20 on the Baltic web), every `input.<id>()` has a matching `ui.input_*`, no per-session file writes under `www/`, figures are closed by `render.plot`, DataGrid patches do not mutate the module-level frame.

## G. Suggested grouping for remediation #3
1. **Alignment invariant** (A1, A3, A9, A8, crit3): one `_assert_aligned` at the boundaries, order-based pickle check, `__file__`-relative paths, no blanket except, permuted-order tests. Do together with K2.4/K2.5.
2. **Flux path** (A2, A11, A12, A23, A24, K3.4): validate `met.types`, surface validation, invalidate `flux_results`, fix the two vacuous tests.
3. **Presentation correctness** (A10, A13, A14, crit1, crit2, crit4): axis titles, keystoneness thresholds/summary, persistent page inputs, downloadable HTML, fixed y, biomass unit.
4. **Deploy** (A6, A7, A18, A19, rsync `:456`, K5.1, K5.2, README `:119`, crit5): make `deploy.sh` runnable and honest, archive the R deployment, allowlist transfer, prune deps.
5. **Test hardening** (A5, A20–A26, K3.3, K4.x): declare hypothesis, replace the tautological/vacuous assertions, pin nw* values.
6. **Feedback path** (A4, A17, `:113`): async submit, size caps, process-wide limiter, document the token.
