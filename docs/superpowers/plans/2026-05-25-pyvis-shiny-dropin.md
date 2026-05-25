# pyvis.shiny Drop-In Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `app.py`'s "build Network → save HTML to `www/<file>.html` → embed via `<iframe src=...>`" pipeline with `pyvis.shiny.render_network(net)`, which returns an `<iframe srcdoc=...>` generated in-memory; remove the now-dead `save_network_html()` and `create_temp_network_html()` exports from `network_viz.py`; pin `pyvis` to the `razinkele/pyvis@v4.2` fork via git URL; add `environment.yml`; tighten `.gitignore`.

**Architecture:** No behavioural change to the visualisation. Same `Network` construction, same physics, same node/edge styling, same tooltips. Only the rendering path changes from disk-write to in-memory srcdoc. The Shiny reactive graph is unchanged: render sites already use `@render.ui` returning a `ui.Tag`, and `render_network()` returns the same.

**Tech Stack:** Python 3.13 (micromamba env `shiny`), Shiny for Python 1.x, pyvis 4.2 (razinkele fork — local-only, currently installed via conda-build), NetworkX, pytest, Git (Windows 11).

**Spec:** `docs/superpowers/specs/2026-05-25-pyvis-shiny-dropin-design.md` (commit `b54aa98`).

---

## Pre-conditions

This plan assumes:

1. **Working tree:** the user has uncommitted edits to `app.py`, `network_analysis.py`, `requirements.txt` from a separate "flux feature" (commit `eab25a9` baseline). Those edits are *additive* to this plan's targets and should remain in place. If the executor prefers, the flux feature can be committed first under a separate commit message; either way works because this plan's changes coexist.
2. **Environment:** the `shiny` micromamba env contains `pyvis 4.2` from conda-build (`conda-meta/pyvis-4.2-py_0.json`). All 41 existing pytest tests pass: confirm with the command in Task 0.
3. **Network:** the executor has outbound HTTPS access to `github.com` and `api.github.com` (Task 1 verifies the fork tag).
4. **Branching:** the executor decides whether to do this work on a feature branch or directly on `master`. The plan does not mandate one — but commits are per-task and isolated, so cherry-picking later is straightforward.

If any pre-condition is unmet, stop and report — do not improvise.

---

## File structure

| File | Action | Responsibility after this PR |
|---|---|---|
| `network_viz.py` | Modify | Builds `Network` objects only. No disk I/O. Surface `create_topology_network`, `create_flux_network`, `get_functional_group_colors`. |
| `app.py` | Modify | Render sites call `pyvis.shiny.render_network(net, ...)` directly in `@render.ui`. No `Path("www") / ...` for network HTML. |
| `requirements.txt` | Modify | Pip-installable list. `pyvis` now pinned to `git+https://github.com/razinkele/pyvis.git@v4.2`. |
| `environment.yml` | **Create** | Canonical conda env description for micromamba. Includes `git` so the `pip:` sub-section can resolve the git URL. Carries an `# update with: micromamba env update -n shiny -f environment.yml --prune` header. |
| `.gitignore` | Modify | Append per-render network HTML patterns + Python caches. |
| `tests/test_network_viz_render.py` | **Create** | Regression test that captures the contract `network_viz` builders provide to the renderer (must pass before AND after the migration). |
| `docs/superpowers/plans/2026-05-25-pyvis-shiny-dropin.md` | (this file) | Plan record. |

---

## Phase 1 — Pre-flight verification (no commits)

These tasks gate the rest of the work. **If Task 2 fails, STOP** and report — the fork's packaging needs to be fixed at the fork repo before this plan can complete.

### Task 0: Confirm baseline test pass

**Files:** read-only

- [ ] **Step 1: Run the existing test suite**

Run:
```bash
micromamba run -n shiny python -m pytest test_flux_calculations.py test_network_analysis.py -v
```

Expected: `41 passed` in the summary line.

If anything fails: STOP. The flux feature work is not in a clean state — the user must resolve before this plan proceeds.

---

### Task 1: Verify fork repo and tag are reachable

**Files:** read-only

- [ ] **Step 1: Check the `v4.2` tag exists on GitHub**

Run:
```bash
curl -sIL -o /dev/null -w "%{http_code}\n" https://github.com/razinkele/pyvis/releases/tag/v4.2
curl -sL https://api.github.com/repos/razinkele/pyvis/tags | python -c "import sys, json; tags=json.load(sys.stdin); names=[t['name'] for t in tags]; print('tags:', names); assert 'v4.2' in names, f'v4.2 not found in {names}'"
```

Expected:
- First command: `200`
- Second command: prints a list of tags including `v4.2`, no AssertionError

If either fails: STOP. The fork tag is unreachable or has moved. Re-check with the user before proceeding.

---

### Task 2: Verify fork packaging ships static assets via pip (CRITICAL GATE — acceptance criterion #10)

**Files:** read-only (uses a throwaway scratch env)

This is the single most important pre-flight check. The current installation came from `conda-build` which packages `pyvis/templates/` and `pyvis/shiny/bindings.js` correctly. After we switch to `pip install` from a git URL, those static assets only ship if the fork's `pyproject.toml`/`setup.py`/`MANIFEST.in` declares them. If they don't, `render_network()` will raise Jinja `TemplateNotFound` at first render.

- [ ] **Step 1: Create a scratch micromamba env with git**

Run:
```bash
micromamba create -n pyvis-scratch -c conda-forge python=3.13 git pip -y
```

Expected: env created, no errors.

- [ ] **Step 2: Pip-install the fork from the git URL into the scratch env**

Run:
```bash
micromamba run -n pyvis-scratch pip install "pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2"
```

Expected: install completes, ends with `Successfully installed pyvis-4.2`.

If pip errors with "git not found" or similar: STOP — the scratch env is broken, fix and re-run.
If pip errors with build failure: STOP — the fork's `pyproject.toml` has a problem; report and halt.

- [ ] **Step 3: Run the static-asset assertion**

Run:
```bash
micromamba run -n pyvis-scratch python -c "import pyvis, pathlib, glob; p=pathlib.Path(pyvis.__file__).parent; assert (p/'templates'/'template.html').exists(), 'template.html missing'; assert (p/'shiny'/'bindings.js').exists(), 'bindings.js missing'; assert glob.glob(str(p/'templates'/'lib'/'vis-*'/'vis-network.min.js')), 'vis-network.min.js missing'; print('OK: all static assets present')"
```

Expected: `OK: all static assets present` printed; exit code 0.

If any assertion fails: **STOP. Do not proceed to Phase 4 (do not modify `requirements.txt`)**. Report which file is missing — the fix is at the fork repo, not in this project. Common causes:
- `pyproject.toml` missing `[tool.setuptools.package-data]` for `pyvis/templates/**` and `pyvis/shiny/*.js`/`*.css`
- `setup.py` missing `include_package_data=True` + corresponding `MANIFEST.in`

Phases 2 and 3 can still proceed (they don't depend on `requirements.txt`), but the dependency declaration phase blocks until the fork is fixed.

- [ ] **Step 4: Clean up the scratch env**

Run:
```bash
micromamba env remove -n pyvis-scratch -y
```

Expected: env removed.

---

## Phase 2 — Capture render baseline (regression safety)

Adds a small render-path test that must pass on the current code AND after the migration. Catches drift in tooltip escaping, generate_html() output structure, and species-name round-tripping that the existing 41 calculation tests don't cover.

### Task 3: Add a render-path regression test

**Files:**
- Create: `test_network_viz_render.py` (project root, alongside the other `test_*.py` files — matches existing convention)

- [ ] **Step 1: Write the new test file**

Create `test_network_viz_render.py` with this content:

```python
"""
Render-Path Regression Tests for network_viz

These tests assert the contract that network_viz builders provide
to the rendering layer: each builder must return a pyvis.network.Network
instance whose generate_html() produces a string containing the species
names, the physics solver name, and structural markers.

They must pass both BEFORE and AFTER the pyvis.shiny.render_network
migration (the migration changes how the HTML is delivered to the browser,
not what generate_html() produces).

To run: pytest test_network_viz_render.py -v
"""

import pytest
import networkx as nx
import numpy as np
from pyvis.network import Network
from network_viz import create_topology_network, create_flux_network


@pytest.fixture
def simple_test_network():
    """Minimal 3-species food chain for render testing."""
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'C'])
    G.add_edges_from([('A', 'B'), ('B', 'C')])
    species_names = ['Sprat', 'Herring', 'Cod']
    functional_groups = ['planktivore', 'planktivore', 'piscivore']
    biomass = np.array([100.0, 50.0, 25.0])
    colors = ['#1f77b4', '#1f77b4', '#ff7f0e']
    return G, species_names, functional_groups, biomass, colors


@pytest.fixture
def simple_flux_network(simple_test_network):
    """Same network plus a 3x3 flux matrix with non-zero edge fluxes."""
    G, species_names, functional_groups, biomass, colors = simple_test_network
    flux_matrix = np.array([
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 5.0],
        [0.0, 0.0, 0.0],
    ])
    return G, species_names, functional_groups, biomass, colors, flux_matrix


def test_topology_builder_returns_pyvis_network(simple_test_network):
    G, species, groups, biomass, colors = simple_test_network
    net = create_topology_network(G, species, groups, biomass, colors)
    assert isinstance(net, Network), f"expected pyvis Network, got {type(net).__name__}"


def test_topology_html_contains_species_and_solver(simple_test_network):
    G, species, groups, biomass, colors = simple_test_network
    net = create_topology_network(G, species, groups, biomass, colors)
    html = net.generate_html()
    assert isinstance(html, str) and len(html) > 1000, "generate_html() returned empty or trivially small output"
    assert 'barnesHut' in html, "physics solver options not embedded in HTML"
    for name in species:
        assert name in html, f"species name {name!r} not present in rendered HTML"


def test_topology_html_safe_for_special_chars():
    """Species names with quotes/ampersands must not break generate_html()."""
    G = nx.DiGraph()
    G.add_nodes_from(['X', 'Y'])
    G.add_edge('X', 'Y')
    species = ['Salmo "trutta"', 'Mytilus & Co.']
    groups = ['fish', 'shellfish']
    biomass = np.array([10.0, 5.0])
    colors = ['#1f77b4', '#ff7f0e']
    net = create_topology_network(G, species, groups, biomass, colors)
    html = net.generate_html()
    assert 'Salmo' in html
    assert 'Mytilus' in html


def test_flux_builder_returns_pyvis_network(simple_flux_network):
    G, species, groups, biomass, colors, flux_matrix = simple_flux_network
    net = create_flux_network(G, species, groups, biomass, colors, flux_matrix)
    assert isinstance(net, Network)


def test_flux_html_contains_species_and_flux_values(simple_flux_network):
    G, species, groups, biomass, colors, flux_matrix = simple_flux_network
    net = create_flux_network(G, species, groups, biomass, colors, flux_matrix)
    html = net.generate_html()
    assert isinstance(html, str) and len(html) > 1000
    assert 'barnesHut' in html
    for name in species:
        assert name in html
    # Edge tooltips reference "Flux:" string from network_viz.py
    assert 'Flux:' in html
```

- [ ] **Step 2: Run the new tests against current code (baseline)**

Run:
```bash
micromamba run -n shiny python -m pytest test_network_viz_render.py -v
```

Expected: 5 tests collected, all pass.

If any fail: STOP. The current `network_viz` builders are already broken in a way the test detected — investigate before continuing with the migration, since you'd be moving a broken baseline.

- [ ] **Step 3: Commit**

```bash
git add test_network_viz_render.py
git commit -m "test: add render-path regression tests for network_viz

Captures the contract network_viz builders provide to the rendering
layer: each returns a pyvis Network whose generate_html() contains
species names, the physics solver, and (for flux) the Flux: tooltip
marker. Passes against current iframe(src=) path; will continue to
pass after the migration to render_network(srcdoc).

Covers special-char species names (quotes, ampersands) which were
flagged as a potential silent-failure mode for srcdoc.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — Code migration

Refactor the render path. Each task ends with a test run to confirm no regression.

### Task 4: Remove dead exports from `network_viz.py`

**Files:**
- Modify: `network_viz.py` lines 13-14 (drop `import tempfile`, `import os`)
- Modify: `network_viz.py` lines 314-326 (delete `save_network_html`)
- Modify: `network_viz.py` lines 329-343 (delete `create_temp_network_html`)

- [ ] **Step 1: Verify the targeted lines are still what the spec described**

Run:
```bash
micromamba run -n shiny python -c "
import re
text = open('network_viz.py').read()
assert 'import tempfile' in text, 'import tempfile not found'
assert 'import os' in text, 'import os not found'
assert 'def save_network_html' in text, 'save_network_html not found'
assert 'def create_temp_network_html' in text, 'create_temp_network_html not found'
print('OK: all targets present')
"
```

Expected: `OK: all targets present`. If anything's missing, the file has drifted — re-grep and adjust.

- [ ] **Step 2: Delete `import tempfile` and `import os` from the import block**

Use the Edit tool to remove these two lines (currently lines 13 and 14). The surrounding imports (`networkx as nx`, `from scipy.linalg import inv`, etc.) stay.

After edit, the import block of `network_viz.py` should look like (no tempfile, no os):

```python
import networkx as nx
import numpy as np
import pandas as pd
from pyvis.network import Network
from typing import Dict, List, Tuple, Optional
from network_analysis import (
    calculate_trophic_levels,
    COLOR_SCHEME,
    NODE_SIZE_SCALE,
    NODE_SIZE_MIN,
    EDGE_WIDTH_SCALE,
    EDGE_WIDTH_MIN
)
```

- [ ] **Step 3: Delete the `save_network_html` function**

Use the Edit tool to delete this entire block:

```python
def save_network_html(net: Network, output_path: str) -> str:
    """
    Save a PyVis network to an HTML file.

    Args:
        net: PyVis Network object
        output_path: Path to save the HTML file

    Returns:
        Path to the saved HTML file
    """
    net.save_graph(output_path)
    return output_path
```

(plus the blank lines immediately before and after to preserve spacing — leave exactly one blank line between adjacent function defs)

- [ ] **Step 4: Delete the `create_temp_network_html` function**

Use the Edit tool to delete this entire block:

```python
def create_temp_network_html(net: Network) -> str:
    """
    Create a temporary HTML file for the network visualization.

    Args:
        net: PyVis Network object

    Returns:
        Path to the temporary HTML file
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
        temp_path = f.name

    net.save_graph(temp_path)
    return temp_path
```

- [ ] **Step 5: Confirm `network_viz.py` is still importable and no orphaned symbols remain**

Run:
```bash
micromamba run -n shiny python -c "
import network_viz
assert hasattr(network_viz, 'create_topology_network')
assert hasattr(network_viz, 'create_flux_network')
assert hasattr(network_viz, 'get_functional_group_colors')
assert not hasattr(network_viz, 'save_network_html'), 'save_network_html still exported'
assert not hasattr(network_viz, 'create_temp_network_html'), 'create_temp_network_html still exported'
assert not hasattr(network_viz, 'tempfile'), 'tempfile still imported'
assert not hasattr(network_viz, 'os'), 'os still imported'
print('OK: dead symbols removed, builders intact')
"
```

Expected: `OK: dead symbols removed, builders intact`.

- [ ] **Step 6: Re-run the render-path tests**

Run:
```bash
micromamba run -n shiny python -m pytest test_network_viz_render.py -v
```

Expected: 5 passed. Builders still produce valid `Network` objects.

**Do not commit yet** — `app.py` still imports the deleted symbol. Task 5 follows immediately.

---

### Task 5: Replace render site 1 in `app.py` (Network tab)

**Files:**
- Modify: `app.py` line 45 (drop `save_network_html` from the `from network_viz import (...)` block)
- Modify: `app.py` (after line 39 or wherever the pyvis-related imports sit) — add `from pyvis.shiny import render_network`
- Modify: `app.py` lines 738-748 — replace the save+iframe block with one `render_network(...)` call

- [ ] **Step 1: Verify line targets**

Run:
```bash
micromamba run -n shiny python -c "
text = open('app.py').read()
assert 'save_network_html' in text, 'save_network_html no longer imported in app.py?'
assert 'from pyvis.shiny import render_network' not in text, 'render_network already imported?'
import re
matches = list(re.finditer(r'save_network_html\(net, str\(www_path\)\)', text))
assert len(matches) == 2, f'expected 2 save_network_html call sites, found {len(matches)}'
print('OK: 2 call sites found, render_network not yet imported')
"
```

Expected: `OK: 2 call sites found, render_network not yet imported`.

- [ ] **Step 2: Update the `from network_viz import (...)` block**

The current block (around line 41-46) imports:
```python
from network_viz import (
    create_topology_network,
    create_flux_network,
    get_functional_group_colors,
    save_network_html
)
```

Remove `save_network_html`. After edit:
```python
from network_viz import (
    create_topology_network,
    create_flux_network,
    get_functional_group_colors,
)
```

- [ ] **Step 3: Add the `render_network` import**

Immediately after the `from network_viz import (...)` block (or grouped with the other pyvis-area imports — pick the spot that matches the file's existing style), add:

```python
from pyvis.shiny import render_network
```

- [ ] **Step 4: Replace the save+iframe block at lines 738-748 (Network tab)**

The current block (after the `if input.network_type() == "Topology": ... else: ...` Network construction):

```python
        filename = "topology_network.html" if input.network_type() == "Topology" else "flux_network.html"
        www_path = Path("www") / filename
        save_network_html(net, str(www_path))

        # Use iframe to display the network (static_assets serves from root)
        return ui.tags.iframe(
            src=f"/{filename}",
            width="100%",
            height=f"{height}px",
            style="border: none;"
        )
```

Replace with the single line (preserve the same level of indentation):

```python
        return render_network(net, height=f"{height}px", width="100%")
```

If the exact `filename`/`www_path`/`save_network_html`/`ui.tags.iframe` block has drifted from these exact lines, identify it by the `save_network_html(net, str(www_path))` call and replace from that call up through the closing `)` of the iframe — do not leave any of those lines behind.

- [ ] **Step 5: Quick sanity check — file still parses**

Run:
```bash
micromamba run -n shiny python -c "import ast; ast.parse(open('app.py').read()); print('OK: app.py parses')"
```

Expected: `OK: app.py parses`. If SyntaxError, the edit broke indentation — fix before continuing.

**Do not commit yet** — the Energy Fluxes site (Task 6) still calls `save_network_html` which no longer exists. App would fail at runtime if it hit the second render path.

---

### Task 6: Replace render site 2 in `app.py` (Energy Fluxes tab)

**Files:**
- Modify: `app.py` lines 1024-1035

- [ ] **Step 1: Locate the second site**

It's the second of the two `save_network_html(net, str(www_path))` calls. Confirm with:

```bash
micromamba run -n shiny python -c "
import re
text = open('app.py').read()
matches = [m.start() for m in re.finditer(r'save_network_html\(net, str\(www_path\)\)', text)]
print(f'remaining call sites: {len(matches)}')
# Should be 1 (Task 5 removed one)
"
```

Expected: `remaining call sites: 1`.

- [ ] **Step 2: Replace the save+iframe block at lines 1024-1035 (Energy Fluxes tab)**

The current block:

```python
        www_path = Path("www") / "flux_network_energy_tab.html"
        save_network_html(net, str(www_path))

        # Use iframe to display the network (static_assets serves from root)
        return ui.tags.iframe(
            src="/flux_network_energy_tab.html",
            width="100%",
            height="600px",
            style="border: none;"
        )
```

Replace with (preserve indentation):

```python
        return render_network(net, height="600px", width="100%")
```

- [ ] **Step 3: Confirm no remaining references to `save_network_html` in `app.py`**

Run:
```bash
micromamba run -n shiny python -c "
text = open('app.py').read()
assert 'save_network_html' not in text, 'save_network_html still referenced in app.py'
print('OK: save_network_html fully removed from app.py')
"
```

Expected: `OK: save_network_html fully removed from app.py`.

- [ ] **Step 4: Confirm the app module still imports cleanly**

Run:
```bash
micromamba run -n shiny python -c "
import importlib.util
spec = importlib.util.spec_from_file_location('app', 'app.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('OK: app.py imports without error')
"
```

Expected: `OK: app.py imports without error`. If `ImportError` or `NameError`, inspect the traceback and fix before continuing.

---

### Task 7: Confirm full test suite still passes

**Files:** read-only

- [ ] **Step 1: Run all tests**

Run:
```bash
micromamba run -n shiny python -m pytest test_flux_calculations.py test_network_analysis.py test_network_viz_render.py -v
```

Expected: `46 passed` (41 existing + 5 new render-path tests).

If anything fails: investigate. Do not paper over with a skip or an assertion change — the failures indicate a real behaviour drift introduced by the refactor.

- [ ] **Step 2: Commit the migration**

```bash
git add network_viz.py app.py
git commit -m "refactor: replace iframe(src=) render path with pyvis.shiny.render_network

Both network render sites in app.py (Network tab and Energy Fluxes tab)
now call pyvis.shiny.render_network(net, ...) directly inside @render.ui,
returning ui.tags.iframe(srcdoc=...) generated in-memory. The previous
'save HTML to www/ then embed via iframe src=' pipeline is gone, along
with the now-dead exports save_network_html() and create_temp_network_html()
(and their tempfile/os imports) from network_viz.py.

No behavioural change to the visualisation itself: same Network
construction, same physics, same node/edge styling, same tooltips.
What changes is where the HTML lives — in the Shiny response payload
instead of on disk, eliminating per-render disk I/O.

Render-path regression tests (test_network_viz_render.py) and the
existing 41 calculation tests all pass: 46/46.

Spec: docs/superpowers/specs/2026-05-25-pyvis-shiny-dropin-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Dependency declaration

**Pre-condition:** Phase 1 Task 2 must have succeeded (fork pip-installs and ships static assets correctly). If it failed, halt here and do not proceed until the fork repo is fixed and Task 2 re-passes.

### Task 8: Update `requirements.txt` to pin pyvis to the fork

**Files:**
- Modify: `requirements.txt` line 9 (currently `igraph>=0.11.0` was already removed by the user; verify the pyvis line and replace)

- [ ] **Step 1: Read the current pyvis line in requirements.txt**

Run:
```bash
micromamba run -n shiny python -c "
text = open('requirements.txt').read()
for i, line in enumerate(text.splitlines(), 1):
    if 'pyvis' in line.lower():
        print(f'{i}: {line!r}')
"
```

Expected: a line like `12: 'pyvis>=0.3.2'` (line number may vary depending on user's pending requirements.txt edits).

- [ ] **Step 2: Replace the pyvis line**

Edit `requirements.txt`. Replace the `pyvis>=0.3.2` line (and any inline comment on the same line) with:

```
pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2  # razinkele fork; not on PyPI. Requires git on PATH at install time.
```

- [ ] **Step 3: Verify the change is correct**

Run:
```bash
micromamba run -n shiny python -c "
text = open('requirements.txt').read()
assert 'pyvis>=0.3.2' not in text, 'old PyPI pin still present'
assert 'pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2' in text, 'fork pin not present'
print('OK: requirements.txt updated')
"
```

Expected: `OK: requirements.txt updated`.

**Do not commit yet** — environment.yml in Task 9 should land in the same commit.

---

### Task 9: Create `environment.yml`

**Files:**
- Create: `environment.yml`

- [ ] **Step 1: Export the actual env's direct dependencies to use as the source of truth for versions**

Run:
```bash
micromamba env export -n shiny --from-history > /tmp/shiny-env-export.yml 2>&1
cat /tmp/shiny-env-export.yml
```

Expected: a YAML listing of the user-installed packages (not the full solve). Use this as the basis for the `environment.yml` you write — but trim out anything unrelated to this project (e.g., GIS deps the user happens to have for a different project should not be hard-pinned here unless they're actually used).

The spec's skeleton in section "`environment.yml` (new file)" is the authoritative shape — start from that and fill in versions from the export.

- [ ] **Step 2: Write `environment.yml`**

Create `environment.yml` with this content (replace `<X.Y.Z>` placeholders with the exact versions from Step 1's export; keep `python=3.13.*` literal):

```yaml
# environment.yml — canonical conda env for EconetPy
#
# To apply this file:
#   - Update existing env in place:    micromamba env update -n shiny -f environment.yml --prune
#   - Or recreate fresh under new name: micromamba create -n shiny-fresh -f environment.yml
#
# Running `micromamba env create -f environment.yml` against an existing
# `shiny` env errors with "prefix already exists" — use one of the two
# forms above.
#
# Pair: requirements.txt (for `pip install -r requirements.txt` users).
# Both files must be kept in sync manually until a single source of truth
# is adopted (see spec docs/superpowers/specs/2026-05-25-pyvis-shiny-dropin-design.md
# Risks table).

name: shiny
channels:
  - conda-forge
dependencies:
  - python=3.13.*
  - git                          # required so pip can resolve git+https URLs at install time
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

- [ ] **Step 3: Validate the YAML parses**

Run:
```bash
micromamba run -n shiny python -c "
import yaml
with open('environment.yml') as f:
    d = yaml.safe_load(f)
assert d['name'] == 'shiny'
assert 'git' in d['dependencies']
pip_section = [x for x in d['dependencies'] if isinstance(x, dict) and 'pip' in x][0]['pip']
assert any('pyvis' in p and 'razinkele' in p for p in pip_section), 'pyvis fork URL not in pip: section'
print('OK: environment.yml is valid')
"
```

Expected: `OK: environment.yml is valid`.

- [ ] **Step 4: Commit dependency changes**

```bash
git add requirements.txt environment.yml
git commit -m "deps: pin pyvis to razinkele fork v4.2, add environment.yml

requirements.txt: replace 'pyvis>=0.3.2' (which would silently install
the wrong upstream PyPI package) with the git URL pin:
  pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2

environment.yml (new): canonical micromamba env description, listing
'git' under conda deps so the pip-from-git step has the git binary on
PATH inside the env (the existing shiny env had no git package). The
pyvis fork lives under the pip: sub-section since it's not on conda-forge.

Both files must be kept in sync manually until a single source of truth
is adopted. The file header documents the env update/create commands.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 5 — Hygiene

### Task 10: Tighten `.gitignore`

**Files:**
- Modify: `.gitignore` (append new patterns; existing content untouched)

- [ ] **Step 1: Read current `.gitignore`**

Run:
```bash
micromamba run -n shiny python -c "print(open('.gitignore').read())"
```

Note what's already there so the new patterns don't duplicate existing entries.

- [ ] **Step 2: Append new patterns**

Append (with a blank line before the new section if the file doesn't already end with one):

```
# Python bytecode caches
__pycache__/
*.pyc

# Per-render network HTML produced by Shiny app (post pyvis.shiny migration these stop being written, but legacy artifacts remain)
www/topology_network.html
www/flux_network.html
www/flux_network_energy_tab.html
temp_*.html
test_network.html
```

If `__pycache__/` or `*.pyc` is already there, skip those two lines — don't duplicate.

- [ ] **Step 3: Verify entries are present**

Run:
```bash
micromamba run -n shiny python -c "
text = open('.gitignore').read()
for needle in ['__pycache__/', '*.pyc', 'www/topology_network.html', 'www/flux_network.html', 'www/flux_network_energy_tab.html', 'temp_*.html', 'test_network.html']:
    assert needle in text, f'missing: {needle}'
print('OK: all .gitignore patterns present')
"
```

Expected: `OK: all .gitignore patterns present`.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore per-render network HTML and Python caches

Post pyvis.shiny.render_network migration, the app no longer writes
HTML files to www/ on each render — but legacy artifacts may still
exist locally, and __pycache__/*.pyc were never ignored. Add explicit
patterns to keep git status focused on real changes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 6 — Manual smoke verification

This phase is the only un-automated work in the plan. The user (or an executor with a display) runs the app and walks the checklist. Cannot be skipped — it's the only thing that exercises the actual browser-side render path.

### Task 11: Run the app and walk the smoke checklist

**Files:** read-only

- [ ] **Step 1: Launch the Shiny app**

Run (in a terminal you'll keep open):
```bash
micromamba run -n shiny shiny run app.py
```

Expected: console output showing `Uvicorn running on http://127.0.0.1:8000` (or similar). Leave running.

- [ ] **Step 2: In a browser, open http://127.0.0.1:8000 and load the default dataset (BalticFW)**

Confirm the app loads without errors. The browser devtools console should be free of red errors.

- [ ] **Step 3: Smoke item 1 — Network tab, Topology**

Navigate to **Food Web Network** tab. Set network type to **Topology**.

Confirm:
- Network renders within ~3 seconds
- Nodes are coloured by functional group
- Hover over any node — tooltip shows species name in bold, Functional Group, Trophic Level, Biomass
- Drag a node — physics simulation moves connected nodes
- Scroll to zoom — view scales correctly

- [ ] **Step 4: Smoke item 2 — Network tab, Flux**

Switch network type to **Flux** (after calculating fluxes in the Energy Fluxes tab if needed).

Confirm:
- Network renders
- Edge widths visibly vary with flux magnitude
- Hover over an edge — tooltip shows `Flux: <value> kJ/day/km²`

- [ ] **Step 5: Smoke item 3 — Energy Fluxes tab**

Navigate to **Energy Fluxes** tab.

Confirm:
- Flux network renders here as well
- Same interactive behaviour

- [ ] **Step 6: Smoke item 4 — Special-character species names (acceptance gate from silent-failure review)**

If the default dataset has species names containing `<`, `>`, `&`, `"`, or `'` — confirm tooltips render correctly (no literal `&lt;b&gt;` text visible). If no such species exist in BalticFW, load a custom dataset where at least one species name contains one of these characters (or add one temporarily via the data input UI).

If no path exists to load a special-char species name, note this as "not directly tested in app" — the unit test `test_topology_html_safe_for_special_chars` is the fallback assertion.

- [ ] **Step 7: Smoke item 5 — Disk hygiene**

After several minutes of interaction (switching tabs, sliding parameters, recalculating):
```bash
ls -la www/*.html
```

Expected: only the three pre-existing files (`topology_network.html`, `flux_network.html`, `flux_network_energy_tab.html`) with their original timestamps from before the migration. No newly written files. No timestamps younger than the time the app was launched.

If new files appear: the migration is incomplete — a render path is still calling the old save_network_html. Re-grep for it.

- [ ] **Step 8: Smoke item 6 — Console hygiene**

In the browser devtools (F12) → Console tab. After exercising the app, confirm no errors (red lines). Warnings are acceptable.

- [ ] **Step 9: Stop the app**

Ctrl+C in the terminal running `shiny run app.py`.

**No commit for this task** — smoke verification produces no file changes.

---

## Phase 7 — Final acceptance gate

### Task 12: Run all 10 acceptance criteria from the spec

**Files:** read-only

For each criterion below, run the listed command (or perform the listed check) and confirm the expected output. Record any failure and stop the plan there.

- [ ] **Criterion 1: `git grep save_network_html` returns no results**

```bash
git grep save_network_html || echo "OK: no results"
```
Expected: `OK: no results` (only printed if grep finds nothing). Spec/plan documents will match — that's fine for git-grep, which only searches tracked files. If they appear, they're in docs only.

To strictly exclude docs/spec/plan matches:
```bash
git grep save_network_html -- ':!docs/' || echo "OK: no code results"
```
Expected: `OK: no code results`.

- [ ] **Criterion 2: `git grep create_temp_network_html` returns no results**

```bash
git grep create_temp_network_html -- ':!docs/' || echo "OK: no code results"
```
Expected: `OK: no code results`.

- [ ] **Criterion 3: `requirements.txt` has the fork pin**

```bash
grep 'pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2' requirements.txt
grep -v 'pyvis>=0.3.2' requirements.txt > /dev/null && echo "OK: no PyPI pin remains" || echo "FAIL: PyPI pin still present"
```
Expected: the fork pin line is printed; `OK: no PyPI pin remains` follows.

- [ ] **Criterion 4: `environment.yml` exists, has `- git`, has fork URL under `pip:`**

```bash
test -f environment.yml && echo "OK: file exists"
grep -E '^\s*-\s*git\s*(#|$)' environment.yml && echo "OK: git listed under conda deps"
grep 'pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2' environment.yml && echo "OK: fork URL under pip:"
```
Expected: all three `OK:` lines.

- [ ] **Criterion 5: `.gitignore` has the expected patterns**

```bash
for p in __pycache__/ '*.pyc' 'www/topology_network.html' 'www/flux_network.html' 'www/flux_network_energy_tab.html' 'temp_*.html' 'test_network.html'; do
  grep -F "$p" .gitignore > /dev/null && echo "OK: $p" || echo "FAIL: missing $p"
done
```
Expected: 7 `OK:` lines.

- [ ] **Criterion 6: 41 calculation tests pass**

```bash
micromamba run -n shiny python -m pytest test_flux_calculations.py test_network_analysis.py -v 2>&1 | tail -3
```
Expected: `41 passed`.

- [ ] **Criterion 7: Manual smoke checklist green**

Refer to Task 11 above. Mark this criterion green only if every smoke item passed.

- [ ] **Criterion 8: No new files in `www/` during interaction**

Already covered by Task 11 Step 7. Mark green if that step passed.

- [ ] **Criterion 9: `network_viz.py` no longer imports `tempfile` or `os`**

```bash
grep -E '^import tempfile|^import os' network_viz.py && echo "FAIL: stale imports present" || echo "OK: tempfile/os not imported"
```
Expected: `OK: tempfile/os not imported`.

- [ ] **Criterion 10: Static-asset shipping verified in scratch env**

Already covered by Task 2. Mark green only if that task passed. If Task 2 was deferred (the fork's packaging needed fixing), this criterion remains blocked and the requirements.txt landing in Task 8 should be considered provisional.

- [ ] **Step: Report**

Summarise: which criteria passed, which failed (if any), and which are blocked on out-of-project work (the fork repo). If all 10 pass, the plan is complete — the migration is done.

---

## Commit history at end of plan

```
* (HEAD) chore: gitignore per-render network HTML and Python caches
* deps: pin pyvis to razinkele fork v4.2, add environment.yml
* refactor: replace iframe(src=) render path with pyvis.shiny.render_network
* test: add render-path regression tests for network_viz
* (existing) docs: address multi-agent review findings on pyvis spec
* (existing) docs: design spec for drop-in pyvis.shiny migration
* (existing) Initial commit: PyEcoNeTool — Python Shiny food web analysis tool
```

Four new commits, all isolated to the pyvis migration. The user's separate flux-feature edits in `app.py`, `network_analysis.py`, `requirements.txt` are not touched by this plan and remain uncommitted in the working tree (or already committed if the user committed them before starting).

---

## Out-of-scope (deferred to future work — captured from multi-agent review)

These were in the "should-fix" and "nice-to-have" buckets of the multi-agent review; the user chose to keep this plan focused on must-fixes. They live here as a backlog:

1. Delete the three stale `www/*_network*.html` files (currently orphaned but still served via `static_assets=www_dir`)
2. Add explicit `cdn_resources="in_line"` to `Network(...)` calls in `network_viz.py` to make CDN_INLINE unconditional AND skip the per-render deepcopy (perf win)
3. Wrap `render_network(net, ...)` calls in try/except returning a user-friendly error UI instead of Shiny's default red error box
4. Add Playwright-based render assertions to CI
5. Consolidate `requirements.txt` and `environment.yml` to a single source of truth
6. Document multi-machine reproducibility (the `DELL` profile path mystery in the original conda-build provenance)
7. Add a note in `econetool.service` about systemd restart-loop risk if render fails at startup probe
