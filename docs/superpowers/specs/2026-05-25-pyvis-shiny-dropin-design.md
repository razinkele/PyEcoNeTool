# Drop-in migration to `pyvis.shiny.render_network`

**Date:** 2026-05-25
**Status:** Design — pending implementation
**Scope:** Drop-in iframe cleanup (smallest viable upgrade)

## Problem

`app.py` renders food-web networks by writing a fresh HTML file to `www/` on every reactive render and then embedding it via `<iframe src="/<file>.html">`. This:

- Couples rendering to disk I/O on every input change
- Leaves stale HTML files in `www/` indefinitely
- Misses the `pyvis.shiny` integration shipped in the local fork `pyvis 4.2` (`github.com/razinkele/pyvis`), which provides a cleaner `srcdoc`-based renderer

`requirements.txt` also lists `pyvis>=0.3.2`, which would silently install the *upstream PyPI* package instead of the fork. The current installation came from a local conda-build of `pyvis 4.2`; nothing in the repo records the correct provenance.

## Goal

Replace the save-to-disk → iframe-src pipeline with `pyvis.shiny.render_network(net)` (which returns an `<iframe srcdoc>`), pin `requirements.txt` correctly, and document the conda environment.

Behaviour of the visualisation itself is unchanged: same Network construction, same physics, same node/edge styling, same tooltips.

## Non-goals

The following were explicitly considered and deferred:

- **Native Shiny output binding** (`output_pyvis_network` + `@render_pyvis_network`) — would deliver toolbar/search/export/themes/19 event types and Python→JS control via `PyVisNetworkController`. Real UX upgrade but ~80-150 lines changed and a larger validation surface. Not in this iteration.
- **Module refactor** (`pyvis_network_ui`/`pyvis_network_server`) — only 2 network views currently exist; abstraction is premature.
- **Event wiring** (clicking a node → updating species info panel) — depends on native binding above.
- **Light/dark theme integration** — depends on native binding.

## Architecture

```
BEFORE                                  AFTER
──────────────────────────              ──────────────────────────
build Network                           build Network
  ↓                                       ↓
save_graph(www/<file>.html)             pyvis.shiny.render_network(net)
  ↓                                       ↓
ui.tags.iframe(src=/<file>.html)        <iframe srcdoc="..."> (generated in-memory)
  ↓                                       ↓
Browser fetches static file              Browser receives HTML inline
```

`render_network()` (defined at `pyvis/shiny/wrapper.py:214` in the installed fork) **conditionally** deep-copies the Network and forces `cdn_resources=CDN_INLINE` *only when* the network was constructed with `CDN_LOCAL` (the branch at `wrapper.py:260-264`). Networks built with `CDN_INLINE` or `CDN_REMOTE` are passed through to `generate_html()` directly without modification. It returns `ui.tags.iframe(srcdoc=...)`.

The current builders in `network_viz.py` (`create_topology_network()` at line 56, `create_flux_network()` at line 196) use the default `cdn_resources="local"`, so the conditional override triggers in every current render. **However**, this is fragile: a future refactor that passes `cdn_resources="remote"` in `Network(...)` would silently produce iframes that reference `https://unpkg.com/vis-network@...`, which fail to a blank iframe in offline / firewalled environments with no Python-side exception. The Risks table covers the mitigation.

The Shiny reactive graph is unchanged: both render sites already use `@render.ui` returning a `ui.Tag`, and `render_network()` returns the same.

## File-by-file changes

### `network_viz.py`

| Change | Detail |
|---|---|
| Remove function | `save_network_html()` — dead after migration |
| Remove function | `create_temp_network_html()` — already unused (grep confirms 0 callers) |
| Remove imports | `import tempfile`, `import os` — only used by the deleted functions |
| Keep unchanged | `create_topology_network()`, `create_flux_network()`, `get_functional_group_colors()` — they continue to return `Network` objects |
| Optional re-export | `from pyvis.shiny import render_network` and add to `__all__` (if `network_viz.py` has one) — convenience so callers import everything from one place |

### `app.py`

| Change | Location | Detail |
|---|---|---|
| Add import | top imports | `from pyvis.shiny import render_network` |
| Remove from import | `from network_viz import (...)` | Drop `save_network_html` from the list |
| Rewrite render site 1 | lines 738-748 (Network tab; the `filename`/`www_path`/`save_network_html`/`iframe` block — Network construction at 712-737 is untouched) | Replace with `return render_network(net, height=f"{height}px", width="100%")` |
| Rewrite render site 2 | lines 1024-1035 (Energy Fluxes tab; the `filename`/`www_path`/`save_network_html`/`iframe` block — Network construction at 1014-1023 is untouched) | Same pattern, fixed height `"600px"` |
| Update stale comment | both sites | Delete `# Use iframe to display the network (static_assets serves from root)` |
| Leave alone | line 1186: `app = App(app_ui, server, static_assets=www_dir)` | `www/img/` and any other static assets still need serving; keep `www_dir.mkdir(exist_ok=True)` for the same reason |

### `requirements.txt`

Replace:

```
pyvis>=0.3.2
```

with:

```
pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2
```

The `v4.2` tag exists on the GitHub repo (verified via `https://api.github.com/repos/razinkele/pyvis/tags`). Tag was chosen over commit SHA for readability; if force-push reproducibility becomes a concern later, switch to SHA.

### `environment.yml` (new file)

Generated from `micromamba env export -n shiny --from-history` and trimmed to direct dependencies. The pyvis fork goes under a `pip:` sub-section since it is not on conda-forge.

Skeleton:

```yaml
name: shiny
channels:
  - conda-forge
dependencies:
  - python=3.13.*
  - git                          # required so pip can fetch the pyvis fork via git+https
  - shiny>=1.0.0
  - htmltools>=0.5.0
  - shinyswatch>=0.4.0
  - networkx>=3.0
  - pandas>=2.0.0
  - numpy>=1.24.0
  - scipy>=1.10.0
  - great-tables>=0.1.0
  - openpyxl>=3.1.0
  - xlrd>=2.0.0
  - matplotlib>=3.7.0
  - seaborn>=0.12.0
  - plotly>=5.14.0
  - pytest>=8.0
  - pip
  - pip:
    - pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2
```

Exact version pins to be filled in at implementation time from the actual env export. `git` is listed explicitly because `pip` invoked inside the env needs a `git` binary on PATH to resolve the `git+https` URL — the current `shiny` env has no `git` package, so a fresh `micromamba env create` would otherwise fail at the pip step.

**How to apply this file:**

```bash
# update the existing env in place (recommended for current users):
micromamba env update -n shiny -f environment.yml --prune

# OR recreate fresh under a different name (clean install for new contributors):
micromamba create -n shiny-fresh -f environment.yml
```

Running `micromamba env create -f environment.yml` against the existing `shiny` env errors with "prefix already exists" — use one of the two forms above.

### `.gitignore`

Append to the existing `.gitignore`:

```
# Python
__pycache__/
*.pyc

# Per-render network HTML (auto-generated by Shiny app)
www/topology_network.html
www/flux_network.html
www/flux_network_energy_tab.html
temp_*.html
test_network.html
```

Existing untracked files (`www/topology_network.html`, etc.) are left in place — they will simply stop being regenerated. User may delete manually if desired.

### Files NOT touched by this design

- `flux_calculations.py`, `network_analysis.py` — unrelated to rendering
- `test_*.py` — 41 tests remain authoritative for calculations
- `_ul` (stray 72-byte ASCII file in repo root) — unknown content, untouched; recommend the user inspect and decide separately
- Untracked large binaries (`BalticFW.*`, `EcoNeTool-master.zip`, `coast 2011-04-10 10.00.ewemdb`) — separate concern from this design

## Data flow

Single reactive render → returns `ui.Tag` (iframe with srcdoc embedding the full vis.js + network HTML).

**Side-effect removal:** the old code wrote a fresh HTML file to `www/` on every render. With reactives firing on input changes (network type switch, dataset changes, slider adjustments), that meant per-interaction disk churn. After this change: zero disk writes during rendering.

**Payload size:** vis.js (~418 KB JS + ~215 KB CSS ≈ 633 KB inlined per render — measured against `pyvis/templates/lib/vis-10.0.2/`) is embedded inline in the srcdoc on every reactive render. For a single network view this is acceptable; the srcdoc HTML passes through Shiny's UI patch over websocket on every render, so heavy slider drags will move ~633 KB per tick. If profiling shows this dominates response time, the fix is to construct `Network(..., cdn_resources="remote")` and let vis.js load from CDN — but that requires internet at runtime. The fork's `render_network` only overrides `cdn_resources` to `CDN_INLINE` when the source network used `CDN_LOCAL` (see Architecture section); other values pass through unchanged, which is how a `CDN_REMOTE` opt-in would work.

## Testing

### Automated

41 existing unit tests (`test_network_analysis.py` + `test_flux_calculations.py`) cover the calculation pipeline and are untouched by this change. Re-run after the migration to confirm no regression:

```
micromamba run -n shiny python -m pytest test_flux_calculations.py test_network_analysis.py -v
```

Expected: `41 passed`.

### Manual smoke (cannot be automated without Playwright investment)

1. `micromamba run -n shiny shiny run app.py`
2. Open `http://localhost:8000` in browser
3. Load default dataset (BalticFW)
4. Navigate to **Food Web Network** tab → confirm Topology renders, drag/zoom work, hover tooltips show species/TL/biomass
5. Switch network type to **Flux** → confirm flux network renders, edge widths reflect flux, hover shows flux values
6. Navigate to **Energy Fluxes** tab → confirm flux network renders there too
7. While interacting: `ls www/*.html` should NOT show any new files appearing (the three existing ones may still be there from prior runs but should not be modified)
8. Confirm no console errors in browser devtools

### Out of scope for this iteration

- Playwright-based render assertions (pytest-playwright is installed but a real test harness for vis.js render is a separate investment)
- Visual regression on tooltips/colors (manual inspection only)

## Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `srcdoc` HTML-encoding breaks special characters in tooltips | Low | Tooltip text garbled | Tooltips already use HTML in `title=` attr; srcdoc uses identical HTML. Smoke test covers it. |
| `CDN_INLINE` bloats response payload | Medium-Low | Slower first paint | ~600 KB per network render. Acceptable for analytical app. Switch to `CDN_REMOTE` if profiling shows it matters. |
| Future builder change passes `cdn_resources="remote"` → silent blank iframe offline | Low (now) / Medium (over time) | Blank iframe, no error | `render_network`'s conditional `CDN_LOCAL → CDN_INLINE` override only triggers for the default. Either (a) pass `cdn_resources="in_line"` explicitly in both `Network(...)` constructions in `network_viz.py` so behaviour is unconditional, or (b) add a code comment near each `Network(...)` warning against switching to `"remote"`. Deferred to implementation plan; spec flags as known fragility. |
| Unknown caller relies on `save_network_html` | Low | Import error at runtime | Grep confirms only 2 call sites, both in `app.py` and both being rewritten. |
| `environment.yml` drifts from `requirements.txt` | Medium | Confused contributors | Treat `environment.yml` as canonical for conda users; `requirements.txt` for pip users. Both must be updated together when deps change. Document this in the file headers. Long-term: consolidate to a single source of truth (deferred to a follow-up). |
| Fork tag `v4.2` is force-pushed | Low | Silent behaviour change in fresh installs | Mitigated by tagging discipline on the fork. If this becomes a concern, switch to commit SHA in the pin. |
| Pip-from-git install fails for missing `git` binary inside the env | Was HIGH; now mitigated | `micromamba env create` errors at the pip step | `environment.yml` lists `- git` under conda deps so a fresh env recreation has `git` on PATH before pip runs. Verified the current `shiny` env had no `git` package. |
| Conda→pip provenance switch drops static assets (`templates/`, `shiny/bindings.js`) if fork's `pyproject.toml` lacks `include_package_data` / `MANIFEST.in` | Unknown (fork packaging not verified) | `render_network` raises Jinja `TemplateNotFound` at first render | Acceptance criterion 10 enforces a scratch-env install check that asserts the files exist. If the check fails, fix is at the fork repo — pin must not land until corrected. |

## Rollback

Single revert commit. No data migrations, no schema changes, no state to clean up. Stale HTML files in `www/` are pre-existing and untouched.

## Acceptance criteria

1. `git grep save_network_html` returns no results
2. `git grep create_temp_network_html` returns no results
3. `requirements.txt` has `pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2` (no PyPI `pyvis>=0.3.2` line)
4. `environment.yml` exists, includes `- git` under conda dependencies, and lists the pyvis fork under `pip:`
5. `.gitignore` covers `__pycache__/`, per-render `www/*.html` files, `temp_*.html`, `test_network.html`
6. `pytest test_flux_calculations.py test_network_analysis.py` → 41 passed
7. Manual smoke checklist (steps 1-8 above) all green
8. No new files appear in `www/` during normal app interaction
9. `network_viz.py` no longer contains `import tempfile` or `import os` (orphaned by the deleted functions)
10. **Static-asset shipping check** — in a scratch env, after `pip install "pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2"`, the following must exit 0:
    ```bash
    python -c "import pyvis, pathlib; p = pathlib.Path(pyvis.__file__).parent; \
      assert (p / 'templates' / 'template.html').exists(), 'template.html missing'; \
      assert (p / 'shiny' / 'bindings.js').exists(), 'bindings.js missing'; \
      import glob; \
      assert glob.glob(str(p / 'templates' / 'lib' / 'vis-*' / 'vis-network.min.js')), 'vis-network.min.js missing'"
    ```
    The current installation came from `conda-build` which packages these directories correctly. After switching to `pip install` from a git URL, the same assets must still ship — they will only do so if the fork's `pyproject.toml` / `setup.py` declares `include_package_data=True` with a `MANIFEST.in`, OR uses `[tool.setuptools.package-data]` to explicitly include `pyvis/templates/**` and `pyvis/shiny/*.js`/`*.css`. If this check fails, the fix is at the fork repository (not in this project), and the pin in `requirements.txt` must not land until the fork is updated.

## References

- Installed fork: `C:\Users\arturas.baziukas\micromamba\envs\shiny\Lib\site-packages\pyvis`
- Fork repo: https://github.com/razinkele/pyvis (tag `v4.2`)
- Render function: `pyvis/shiny/wrapper.py:214` (`render_network`); conditional `CDN_INLINE` override at `wrapper.py:260-264`
- Current render sites being rewritten: `app.py:738-748` (Network tab save+iframe block), `app.py:1024-1035` (Energy Fluxes tab save+iframe block). Network object construction at `app.py:712-737` and `app.py:1014-1023` is **not** modified.
- Static asset mount: `app.py:1186` (`static_assets=www_dir`); `www_dir.mkdir(exist_ok=True)` at `app.py:1184` retained for `www/img/`
