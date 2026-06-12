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

### Shell compatibility

The user's primary shell is **PowerShell 7+** on Windows; Bash is also available. To stay cross-shell, this plan follows two rules:

- **Verification commands** are written as `micromamba run -n shiny python -c "..."` one-liners. Python is identical across shells, so the same command works in PowerShell and Bash without modification.
- **Commit message commands** (`git commit -m`) are inherently shell-specific because heredoc syntax differs. Each commit step provides **both variants**: a Bash `git commit -m "$(cat <<'EOF' ... EOF)"` form and a PowerShell `git commit -m @' ... '@` form. Pick the one matching the shell you're running in.

Avoid Bash-only constructs (`/tmp/`, `/dev/null`, `grep`, `tail`, `||` with `echo`, `for ... do ... done`, `curl` flags). They will silently fail or produce wrong results under PowerShell. Where the plan references file paths, use forward slashes (`docs/superpowers/...`) — both shells accept them, and git always normalises to forward slashes internally.

---

## File structure

| File | Action | Responsibility after this PR |
|---|---|---|
| `network_viz.py` | Modify | Builds `Network` objects only. No disk I/O. Surface `create_topology_network`, `create_flux_network`, `get_functional_group_colors`. |
| `app.py` | Modify | Render sites call `pyvis.shiny.render_network(net, ...)` directly in `@render.ui`. No `Path("www") / ...` for network HTML. |
| `requirements.txt` | Modify | Pip-installable list. `pyvis` now pinned to `git+https://github.com/razinkele/pyvis.git@v4.2`. |
| `environment.yml` | **Create** | Canonical conda env description for micromamba. Includes `git` so the `pip:` sub-section can resolve the git URL. Carries an `# update with: micromamba env update -n shiny -f environment.yml --prune` header. |
| `.gitignore` | Modify | Append per-render network HTML patterns + Python caches. |
| `test_network_viz_render.py` | **Create** | Regression test that captures the contract `network_viz` builders provide to the renderer (must pass before AND after the migration). Lives in project root, matching the existing `test_*.py` convention. |
| `docs/superpowers/plans/2026-05-25-pyvis-shiny-dropin.md` | (this file) | Plan record. |

---

## Phase 1 — Pre-flight verification (no commits)

These tasks gate the rest of the work. **If Task 2 fails, STOP** and report — the fork's packaging needs to be fixed at the fork repo before this plan can complete.

### Task 0: Confirm baseline test pass

**Files:** read-only

- [ ] **Step 1: Run the existing test suite**

Run:
```
micromamba run -n shiny python -m pytest test_flux_calculations.py test_network_analysis.py -q
```

Expected: ends with `41 passed` (the `-q` flag prints only summary lines, no `tail` needed).

If anything fails: STOP. The flux feature work is not in a clean state — the user must resolve before this plan proceeds.

---

### Task 1: Verify fork repo and tag are reachable

**Files:** read-only

- [ ] **Step 1: Check the `v4.2` tag exists on GitHub (cross-shell via Python)**

Run:
```
micromamba run -n shiny python -c "import urllib.request, json; r=urllib.request.urlopen('https://api.github.com/repos/razinkele/pyvis/tags'); tags=json.loads(r.read()); names=[t['name'] for t in tags]; print('tags:', names); assert 'v4.2' in names, f'v4.2 not found in {names}'; print('OK: v4.2 tag reachable')"
```

Expected: prints the list of tags including `v4.2`, followed by `OK: v4.2 tag reachable`. Exit code 0.

If `urllib.error.URLError`, `HTTPError`, or `AssertionError`: STOP. The fork tag is unreachable, the repo went private, or `v4.2` was deleted. Re-check with the user before proceeding.

---

### Task 2: Verify fork packaging ships static assets via pip (CRITICAL GATE — acceptance criterion #10)

**Files:** read-only (uses a throwaway scratch env)

This is the single most important pre-flight check. The current installation came from `conda-build` which packages `pyvis/templates/` and `pyvis/shiny/bindings.js` correctly. After we switch to `pip install` from a git URL, those static assets only ship if the fork's `pyproject.toml`/`setup.py`/`MANIFEST.in` declares them. If they don't, `render_network()` will raise Jinja `TemplateNotFound` at first render.

- [ ] **Step 1: Create a scratch micromamba env with git**

Run:
```
micromamba create -n pyvis-scratch -c conda-forge python=3.13 git pip -y
```

Expected: env created, no errors.

- [ ] **Step 2: Pip-install the fork from the git URL into the scratch env**

Run:
```
micromamba run -n pyvis-scratch pip install "pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2"
```

Expected: install completes, ends with `Successfully installed pyvis-4.2`.

If pip errors with "git not found" or similar: STOP — the scratch env is broken, fix and re-run.
If pip errors with build failure: STOP — the fork's `pyproject.toml` has a problem; report and halt.

- [ ] **Step 3: Run the strengthened static-asset assertion (existence + non-empty + content markers + end-to-end render smoke)**

`.exists()` alone is insufficient — empty files would pass, and a `bindings.js` missing the Shiny output binding would still satisfy a bare existence check. This stronger probe asserts: files exist, are non-trivial in size, contain expected markers, and `render_network` itself can produce a srcdoc Tag without raising.

Run:
```
micromamba run -n pyvis-scratch python -c "import pyvis, pathlib, glob; p=pathlib.Path(pyvis.__file__).parent; tpl=p/'templates'/'template.html'; assert tpl.exists() and tpl.stat().st_size>500, f'template.html missing or trivial ({tpl.stat().st_size if tpl.exists() else 0} bytes)'; t=tpl.read_text(encoding='utf-8'); assert '{{' in t and '}}' in t, 'template.html has no Jinja markers'; bj=p/'shiny'/'bindings.js'; assert bj.exists() and bj.stat().st_size>500, f'bindings.js missing or trivial ({bj.stat().st_size if bj.exists() else 0} bytes)'; b=bj.read_text(encoding='utf-8'); assert 'OutputBinding' in b, 'bindings.js present but registers no Shiny OutputBinding'; visjs=glob.glob(str(p/'templates'/'lib'/'vis-*'/'vis-network.min.js')); assert visjs, 'vis-network.min.js missing'; from pyvis.network import Network; from pyvis.shiny import render_network; n=Network(); n.add_node(1,label='x'); n.add_node(2,label='y'); n.add_edge(1,2); tag=render_network(n); assert tag.attrs.get('srcdoc') and len(tag.attrs['srcdoc'])>1000, 'render_network produced no srcdoc'; print('OK: assets present, render_network smoke succeeds')"
```

Expected: `OK: assets present, render_network smoke succeeds` printed; exit code 0.

If any assertion fails: **STOP. Do not proceed to Phase 4 (do not modify `requirements.txt`)**. Report which file is missing or which check failed — the fix is at the fork repo, not in this project. Common causes:
- `pyproject.toml` missing `[tool.setuptools.package-data]` for `pyvis/templates/**` and `pyvis/shiny/*.js`/`*.css`
- `setup.py` missing `include_package_data=True` + corresponding `MANIFEST.in`
- An empty `bindings.js` because a build step was skipped on the fork

Phases 2 and 3 can still proceed (they don't depend on `requirements.txt`), but the dependency declaration phase blocks until the fork is fixed.

- [ ] **Step 4: Clean up the scratch env**

Run:
```
micromamba env remove -n pyvis-scratch -y
```

Expected: env removed.

---

## Phase 2 — Capture render baseline (regression safety)

Adds a render-path test that must pass on the current code AND after the migration. Catches drift in tooltip escaping, generate_html() output structure, species-name round-tripping, the CDN_LOCAL assumption, and the actual `render_network()` Tag structure — none of which the existing 41 calculation tests cover.

### Task 3: Add a render-path regression test

**Files:**
- Create: `test_network_viz_render.py` (project root, alongside the other `test_*.py` files — matches existing convention)

- [ ] **Step 1: Write the new test file**

Create `test_network_viz_render.py` with this content:

```python
"""
Render-Path Regression Tests for network_viz

These tests assert the contract that network_viz builders provide
to the rendering layer:
  - Each builder returns a pyvis.network.Network instance
  - generate_html() produces a string containing species names,
    physics solver markers, and (for flux) the Flux: tooltip marker
  - Special characters in species names (quotes, ampersands, angle
    brackets) round-trip without being silently dropped or
    double-escaped
  - Builders use cdn_resources=CDN_LOCAL so render_network's
    CDN_INLINE conditional override triggers (otherwise the iframe
    srcdoc would reference external JS that browsers block)
  - render_network itself returns an iframe Tag with srcdoc set
    (not src) and embeds the species names

They must pass both BEFORE and AFTER the pyvis.shiny.render_network
migration. The migration changes how the HTML is delivered to the
browser, not what generate_html() produces.

To run: pytest test_network_viz_render.py -v
"""

import pytest
import networkx as nx
import numpy as np
from pyvis.network import Network, CDN_LOCAL
from pyvis.shiny import render_network
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


def test_topology_tooltip_bold_marker_round_trips(simple_test_network):
    """The <b>...</b> wrapper around species names in tooltips must reach
    the browser as a tag, not as double-escaped &lt;b&gt; literal text.
    Catches a Jinja autoescape regression on the fork."""
    G, species, groups, biomass, colors = simple_test_network
    net = create_topology_network(G, species, groups, biomass, colors)
    html = net.generate_html()
    # <b>Sprat</b> must appear either raw or as JSON-escaped <
    # forms — but NOT as the double-escaped HTML &amp;lt;b&amp;gt;
    # which would render as literal text in the tooltip.
    assert '&amp;lt;b&amp;gt;' not in html, "tooltip bold markup got double-escaped — Jinja autoescape regression"


def test_topology_html_safe_for_special_chars():
    """Special characters in species names must round-trip — not just
    appear as substrings, but actually be present in valid escaped form
    and NOT double-escaped."""
    G = nx.DiGraph()
    G.add_nodes_from(['X', 'Y', 'Z'])
    G.add_edges_from([('X', 'Y'), ('Y', 'Z')])
    species = ['Salmo "trutta"', 'Mytilus & Co.', 'Genus <i>italicus</i>']
    groups = ['fish', 'shellfish', 'other']
    biomass = np.array([10.0, 5.0, 2.0])
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
    net = create_topology_network(G, species, groups, biomass, colors)
    html = net.generate_html()
    # The double-quote in 'Salmo "trutta"' must round-trip to a valid
    # encoded form: either JSON-escaped \" or HTML-entity &quot;.
    assert '\\"trutta\\"' in html or '&quot;trutta&quot;' in html, \
        "double-quote in species name was dropped or wrongly escaped"
    # The literal & in 'Mytilus & Co.' must appear (raw or &amp;).
    assert 'Mytilus &amp; Co.' in html or 'Mytilus & Co.' in html, \
        "ampersand in species name was dropped"
    # The angle brackets in 'Genus <i>italicus</i>' must appear in some
    # escaped form (not silently stripped).
    assert '&lt;i&gt;' in html or '<i>' in html, \
        "angle bracket in species name was dropped"
    # Most important: nothing got double-escaped to literal display.
    assert '&amp;amp;' not in html, "double-escaped ampersand"


def test_builders_use_cdn_local_so_render_network_inlines_assets(simple_test_network):
    """render_network's CDN_INLINE conditional override only triggers
    when the network was constructed with CDN_LOCAL (wrapper.py:260-264).
    If a future builder change switches to CDN_REMOTE, the iframe srcdoc
    will reference external JS that browsers may block — silently to a
    blank iframe with no Python exception. This test guards that
    assumption."""
    G, species, groups, biomass, colors = simple_test_network
    net = create_topology_network(G, species, groups, biomass, colors)
    assert net.cdn_resources == CDN_LOCAL, \
        f"builder changed cdn_resources to {net.cdn_resources!r} — render_network's CDN_INLINE branch is now skipped, iframe srcdoc will request external JS"


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


def test_render_network_returns_iframe_with_srcdoc(simple_test_network):
    """render_network must produce an iframe Tag with srcdoc populated
    (not src), and the srcdoc must embed the species names. This is the
    only test that exercises the actual NEW code path the migration
    introduces — all earlier tests bypass render_network and call
    generate_html() directly."""
    G, species, groups, biomass, colors = simple_test_network
    net = create_topology_network(G, species, groups, biomass, colors)
    tag = render_network(net, height="600px", width="100%")
    assert tag.name == 'iframe', f"expected iframe Tag, got {tag.name!r}"
    assert 'srcdoc' in tag.attrs, "render_network must use srcdoc"
    assert 'src' not in tag.attrs, "render_network must NOT use src attribute"
    srcdoc = tag.attrs['srcdoc']
    assert len(srcdoc) > 1000, f"srcdoc trivially small: {len(srcdoc)} chars"
    for name in species:
        assert name in srcdoc, f"species {name!r} not in srcdoc"
```

- [ ] **Step 2: Run the new tests against current code (baseline)**

Run:
```
micromamba run -n shiny python -m pytest test_network_viz_render.py -v
```

Expected: 8 tests collected, all pass.

If any fail: STOP. The current `network_viz` builders are already broken in a way the test detected — investigate before continuing with the migration, since you'd be moving a broken baseline.

- [ ] **Step 3: Commit (Bash variant)**

```
git add test_network_viz_render.py
git commit -m "$(cat <<'EOF'
test: add render-path regression tests for network_viz

Captures the contract network_viz builders provide to the rendering
layer: each returns a pyvis Network whose generate_html() contains
species names, the physics solver, and (for flux) the Flux: tooltip
marker. Also asserts:
  - <b>...</b> markup in tooltips is not double-escaped (Jinja
    autoescape regression guard)
  - special chars (", &, <) in species names round-trip without
    being dropped or double-escaped
  - builders use cdn_resources=CDN_LOCAL so render_network's
    CDN_INLINE conditional override triggers (otherwise the iframe
    srcdoc references external JS browsers block)
  - render_network itself returns an iframe Tag with srcdoc set
    (not src) and embeds the species names — the only test of the
    actual NEW code path introduced by the migration

8 tests, all pass against current iframe(src=) path; will continue
to pass after the migration to render_network(srcdoc).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3 (PowerShell variant): same commit, PowerShell here-string syntax**

```
git add test_network_viz_render.py
git commit -m @'
test: add render-path regression tests for network_viz

Captures the contract network_viz builders provide to the rendering
layer: each returns a pyvis Network whose generate_html() contains
species names, the physics solver, and (for flux) the Flux: tooltip
marker. Also asserts:
  - <b>...</b> markup in tooltips is not double-escaped (Jinja
    autoescape regression guard)
  - special chars (", &, <) in species names round-trip without
    being dropped or double-escaped
  - builders use cdn_resources=CDN_LOCAL so render_network's
    CDN_INLINE conditional override triggers (otherwise the iframe
    srcdoc references external JS browsers block)
  - render_network itself returns an iframe Tag with srcdoc set
    (not src) and embeds the species names — the only test of the
    actual NEW code path introduced by the migration

8 tests, all pass against current iframe(src=) path; will continue
to pass after the migration to render_network(srcdoc).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

> Note: In PowerShell here-strings, the closing `'@` MUST be at column 0 (no leading whitespace) on its own line — indentation is a parse error.

---

## Phase 3 — Code migration

**Safer execution order than the obvious one.** The naive order ("remove dead exports first, then update callers") would leave `app.py` referencing a deleted symbol between tasks, breaking the app if execution is interrupted. This phase updates `app.py` FIRST so it no longer references the soon-to-be-removed symbol, then removes the dead code from `network_viz.py`. At every inter-task pause the working tree is in a runnable state.

### Task 4: Update `app.py` to call `render_network` at both render sites

**Files:**
- Modify: `app.py` line 45 (drop `save_network_html` from the `from network_viz import (...)` block)
- Modify: `app.py` line 47 (insert `from pyvis.shiny import render_network` immediately after the closing `)` of the network_viz import block)
- Modify: `app.py` lines 738-749 (Network tab: replace the save+iframe block with `render_network(...)` call)
- Modify: `app.py` lines 1024-1035 (Energy Fluxes tab: same replacement)

- [ ] **Step 1: Verify line targets and call-site count**

Run:
```
micromamba run -n shiny python -c "import re; t=open('app.py').read(); assert 'save_network_html' in t, 'save_network_html no longer imported in app.py?'; assert 'from pyvis.shiny import render_network' not in t, 'render_network already imported?'; m=list(re.finditer(r'save_network_html\(net, str\(www_path\)\)', t)); assert len(m)==2, f'expected 2 save_network_html call sites, found {len(m)}'; print('OK: 2 call sites found, render_network not yet imported')"
```

Expected: `OK: 2 call sites found, render_network not yet imported`.

- [ ] **Step 2: Update the `from network_viz import (...)` block**

The current block (lines 41-46) imports:
```python
from network_viz import (
    create_topology_network,
    create_flux_network,
    get_functional_group_colors,
    save_network_html
)
```

Use the Edit tool to remove `save_network_html` (and the trailing comma on the preceding line if applicable). After edit, the block reads:
```python
from network_viz import (
    create_topology_network,
    create_flux_network,
    get_functional_group_colors,
)
```

- [ ] **Step 3: Add the `render_network` import at line 47**

Immediately after the closing `)` of the `from network_viz import (...)` block (which sits on line 46), insert a new line:
```python
from pyvis.shiny import render_network
```

There is no other `from pyvis...` import in `app.py` today; this is the canonical location for new pyvis-area imports.

- [ ] **Step 4: Replace render site 1 (Network tab) at lines 738-749**

The current block (find it by the `save_network_html(net, str(www_path))` call followed by the iframe return):
```python
        # Save to www directory for static serving
        www_path = Path("www") / filename
        save_network_html(net, str(www_path))

        # Use iframe to display the network (static_assets serves from root)
        return ui.tags.iframe(
            src=f"/{filename}",
            width="100%",
            height=f"{height}px",
            frameborder="0",
            style="border: none;"
        )
```

Replace with the single line (preserve the same level of indentation — 8 spaces):
```python
        return render_network(net, height=f"{height}px", width="100%")
```

The `filename` variable computed in the `if/else` above (lines 711-736) becomes unused after this edit — that is intentional; leave the `filename =` assignments in place since they live inside conditional branches and removing them is out of scope.

> **Important:** the old block contains `frameborder="0",` between `height=` and `style=`. If you do an exact-match Edit, that line MUST be present in the "old text" string for the replacement to succeed. The Edit tool will silently fail to match if you omit it.

- [ ] **Step 5: Replace render site 2 (Energy Fluxes tab) at lines 1024-1035**

The current block:
```python
        # Save to www directory for static serving
        www_path = Path("www") / "flux_network_energy_tab.html"
        save_network_html(net, str(www_path))

        # Use iframe to display the network (static_assets serves from root)
        return ui.tags.iframe(
            src="/flux_network_energy_tab.html",
            width="100%",
            height="600px",
            frameborder="0",
            style="border: none;"
        )
```

Replace with (preserve indentation — 8 spaces):
```python
        return render_network(net, height="600px", width="100%")
```

Same `frameborder="0",` caveat as Step 4 — it MUST be in the "old text" for exact-match Edit to succeed.

- [ ] **Step 6: Sanity check — file parses, all references resolved**

Run:
```
micromamba run -n shiny python -c "import ast; ast.parse(open('app.py').read()); t=open('app.py').read(); assert 'save_network_html' not in t, 'save_network_html still referenced in app.py'; assert 'from pyvis.shiny import render_network' in t, 'render_network import missing'; assert t.count('render_network(net') == 2, f'expected 2 render_network call sites, found {t.count(chr(39)+chr(34)+chr(34)+chr(40)+chr(110)+chr(101)+chr(116))}'; print('OK: app.py parses, save_network_html removed, 2 render_network call sites present')"
```

Expected: `OK: app.py parses, save_network_html removed, 2 render_network call sites present`.

If `SyntaxError` from `ast.parse`: indentation broke — fix before continuing.
If any assert fails: an edit was incomplete — investigate.

- [ ] **Step 7: Confirm the module still imports without error**

At this point `network_viz.py` still defines `save_network_html` (Task 5 removes it). `app.py` no longer imports or calls it. The app is in a valid intermediate state where both the old API (still defined in `network_viz`) and the new API (used in `app.py`) coexist. Confirm:

Run:
```
micromamba run -n shiny python -c "import importlib.util; spec=importlib.util.spec_from_file_location('app','app.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); print('OK: app.py imports without error')"
```

Expected: `OK: app.py imports without error`.

**Do not commit yet** — Task 5 removes the now-dead `save_network_html` and `create_temp_network_html` from `network_viz.py`, and the whole refactor lands as one commit in Task 6.

---

### Task 5: Remove dead exports from `network_viz.py`

At this point nothing in the codebase references `save_network_html` or `create_temp_network_html`. They can be removed cleanly without breaking anything.

**Files:**
- Modify: `network_viz.py` lines 13-14 (drop `import tempfile`, `import os`)
- Modify: `network_viz.py` lines 314-326 (delete `save_network_html`)
- Modify: `network_viz.py` lines 329-343 (delete `create_temp_network_html`)

- [ ] **Step 1: Verify targets are still present**

Run:
```
micromamba run -n shiny python -c "t=open('network_viz.py').read(); assert 'import tempfile' in t, 'import tempfile not found'; assert 'import os' in t, 'import os not found'; assert 'def save_network_html' in t, 'save_network_html not found'; assert 'def create_temp_network_html' in t, 'create_temp_network_html not found'; print('OK: all delete targets present')"
```

Expected: `OK: all delete targets present`. If anything's missing, the file has drifted — re-grep and adjust line numbers.

- [ ] **Step 2: Delete `import tempfile` and `import os` from the import block**

Use the Edit tool to remove these two lines (lines 13 and 14). The surrounding imports (`networkx as nx`, `from scipy.linalg import inv`, etc.) stay.

After edit, the import block of `network_viz.py` should read (no tempfile, no os):

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

Leave exactly one blank line between adjacent function defs after the deletion.

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
```
micromamba run -n shiny python -c "import network_viz; assert hasattr(network_viz, 'create_topology_network'); assert hasattr(network_viz, 'create_flux_network'); assert hasattr(network_viz, 'get_functional_group_colors'); assert not hasattr(network_viz, 'save_network_html'), 'save_network_html still exported'; assert not hasattr(network_viz, 'create_temp_network_html'), 'create_temp_network_html still exported'; assert not hasattr(network_viz, 'tempfile'), 'tempfile still imported'; assert not hasattr(network_viz, 'os'), 'os still imported'; print('OK: dead symbols removed, builders intact')"
```

Expected: `OK: dead symbols removed, builders intact`.

---

### Task 6: Run full test suite and commit the migration

**Files:** read-only test run, then commits two files.

- [ ] **Step 1: Run all tests (existing + new)**

Run:
```
micromamba run -n shiny python -m pytest test_flux_calculations.py test_network_analysis.py test_network_viz_render.py -q
```

Expected: ends with `49 passed` (41 existing calculation tests + 8 new render-path tests).

If anything fails: investigate. Do not paper over with a skip or assertion change — the failures indicate a real behaviour drift introduced by the refactor.

- [ ] **Step 2: Commit the migration (Bash variant)**

```
git add network_viz.py app.py
git commit -m "$(cat <<'EOF'
refactor: replace iframe(src=) render path with pyvis.shiny.render_network

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
existing 41 calculation tests all pass: 49/49.

Spec: docs/superpowers/specs/2026-05-25-pyvis-shiny-dropin-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2 (PowerShell variant): same commit, PowerShell here-string**

```
git add network_viz.py app.py
git commit -m @'
refactor: replace iframe(src=) render path with pyvis.shiny.render_network

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
existing 41 calculation tests all pass: 49/49.

Spec: docs/superpowers/specs/2026-05-25-pyvis-shiny-dropin-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

## Phase 4 — Dependency declaration

**Pre-condition:** Phase 1 Task 2 must have succeeded (fork pip-installs and ships static assets correctly). If it failed, halt here and do not proceed until the fork repo is fixed and Task 2 re-passes.

### Task 7: Update `requirements.txt` and create `environment.yml` (single commit)

These two files belong together — a `requirements.txt` pinning the fork URL without a matching `environment.yml` describing the conda env (with `git` installed) leaves new contributors unable to reproduce the env. Land both in one commit.

**Files:**
- Modify: `requirements.txt`
- Create: `environment.yml`

- [ ] **Step 1: Locate and verify the current pyvis line in requirements.txt**

Run:
```
micromamba run -n shiny python -c "t=open('requirements.txt').read(); [print(f'{i}: {l!r}') for i,l in enumerate(t.splitlines(),1) if 'pyvis' in l.lower()]"
```

Expected: a single line containing `pyvis>=0.3.2` (line number depends on user's pending edits to requirements.txt — both reviewers found it at line 11 at audit time, but the executor should not hard-code it).

- [ ] **Step 2: Replace the pyvis line**

Use the Edit tool to replace the line containing `pyvis>=0.3.2` (and any inline comment on the same line) with:

```
pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2  # razinkele fork; not on PyPI. Requires git on PATH at install time.
```

- [ ] **Step 3: Verify requirements.txt change**

Run:
```
micromamba run -n shiny python -c "t=open('requirements.txt').read(); assert 'pyvis>=0.3.2' not in t, 'old PyPI pin still present'; assert 'pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2' in t, 'fork pin not present'; print('OK: requirements.txt updated')"
```

Expected: `OK: requirements.txt updated`.

- [ ] **Step 4: Export the actual env's direct dependencies (for version pinning reference)**

Write the export to a project-relative path (NOT `/tmp/` — doesn't exist on Windows):

```
micromamba env export -n shiny --from-history > env-export.yml
```

Then read it:
```
micromamba run -n shiny python -c "print(open('env-export.yml').read())"
```

Expected: a YAML listing of user-installed packages. Use this as the version-pinning reference for Step 5. Add `env-export.yml` to `.gitignore` in Task 8 (or just delete it after Step 5).

- [ ] **Step 5: Write `environment.yml`**

Create `environment.yml`. Use the version strings from Step 4's export where present, or keep the `>=` defaults shown below for anything the export doesn't list. Keep `python=3.13.*` literal (it pins to the 3.13 minor series).

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
  - shinywidgets>=0.3.0
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

> Note: `shinywidgets` is included to match the current `requirements.txt`. If the user's flux-feature edits removed it from `requirements.txt`, remove it here too.

- [ ] **Step 6: Validate environment.yml**

Run:
```
micromamba run -n shiny python -c "import yaml; d=yaml.safe_load(open('environment.yml')); assert d['name']=='shiny'; assert 'git' in d['dependencies']; pip=[x for x in d['dependencies'] if isinstance(x,dict) and 'pip' in x][0]['pip']; assert any('pyvis' in p and 'razinkele' in p for p in pip), 'pyvis fork URL not in pip: section'; print('OK: environment.yml is valid')"
```

Expected: `OK: environment.yml is valid`.

- [ ] **Step 7: Delete the throwaway env-export.yml**

Run (cross-shell):
```
micromamba run -n shiny python -c "import os; os.remove('env-export.yml') if os.path.exists('env-export.yml') else None; print('OK: env-export.yml cleaned up')"
```

- [ ] **Step 8: Commit both files together (Bash variant)**

```
git add requirements.txt environment.yml
git commit -m "$(cat <<'EOF'
deps: pin pyvis to razinkele fork v4.2, add environment.yml

requirements.txt: replace 'pyvis>=0.3.2' (which would silently install
the wrong upstream PyPI package) with the git URL pin:
  pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2

environment.yml (new): canonical micromamba env description, listing
'git' under conda deps so the pip-from-git step has the git binary on
PATH inside the env (the existing shiny env had no git package). The
pyvis fork lives under the pip: sub-section since it's not on conda-forge.

Both files must be kept in sync manually until a single source of truth
is adopted. The file header documents the env update/create commands.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 8 (PowerShell variant)**

```
git add requirements.txt environment.yml
git commit -m @'
deps: pin pyvis to razinkele fork v4.2, add environment.yml

requirements.txt: replace 'pyvis>=0.3.2' (which would silently install
the wrong upstream PyPI package) with the git URL pin:
  pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2

environment.yml (new): canonical micromamba env description, listing
'git' under conda deps so the pip-from-git step has the git binary on
PATH inside the env (the existing shiny env had no git package). The
pyvis fork lives under the pip: sub-section since it's not on conda-forge.

Both files must be kept in sync manually until a single source of truth
is adopted. The file header documents the env update/create commands.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

## Phase 5 — Hygiene

### Task 8: Tighten `.gitignore`

**Files:**
- Modify: `.gitignore` (append new patterns; existing content untouched)

- [ ] **Step 1: Read current `.gitignore`**

Run:
```
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

# Throwaway micromamba env export file (Task 7 Step 4)
env-export.yml
```

If `__pycache__/` or `*.pyc` is already there, skip those two lines — don't duplicate.

- [ ] **Step 3: Verify entries are present**

Run:
```
micromamba run -n shiny python -c "t=open('.gitignore').read(); missing=[n for n in ['__pycache__/','*.pyc','www/topology_network.html','www/flux_network.html','www/flux_network_energy_tab.html','temp_*.html','test_network.html','env-export.yml'] if n not in t]; assert not missing, f'missing patterns: {missing}'; print('OK: all .gitignore patterns present')"
```

Expected: `OK: all .gitignore patterns present`.

- [ ] **Step 4: Commit (Bash variant)**

```
git add .gitignore
git commit -m "$(cat <<'EOF'
chore: gitignore per-render network HTML and Python caches

Post pyvis.shiny.render_network migration, the app no longer writes
HTML files to www/ on each render — but legacy artifacts may still
exist locally, and __pycache__/*.pyc were never ignored. Add explicit
patterns to keep git status focused on real changes. Also ignore the
throwaway env-export.yml produced by `micromamba env export` during
plan execution.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4 (PowerShell variant)**

```
git add .gitignore
git commit -m @'
chore: gitignore per-render network HTML and Python caches

Post pyvis.shiny.render_network migration, the app no longer writes
HTML files to www/ on each render — but legacy artifacts may still
exist locally, and __pycache__/*.pyc were never ignored. Add explicit
patterns to keep git status focused on real changes. Also ignore the
throwaway env-export.yml produced by `micromamba env export` during
plan execution.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
'@
```

---

## Phase 6 — Verification

Two complementary tasks: an automated app-start probe that exercises the new render path end-to-end without a human in the loop, and a manual smoke checklist for the things a human eye catches better than a probe (visual styling, tooltip rendering, drag/zoom interactivity).

### Task 9: Automated app-start probe

This task gives the executor (subagent or human) confidence that the app actually starts and serves the migrated render path before declaring the migration complete. Without it, a syntax-clean refactor could still raise at first reactive render and the executor would miss it.

**Files:** read-only

- [ ] **Step 1: Run the probe (cross-shell Python)**

Run:
```
micromamba run -n shiny python -c "import subprocess, sys, time, urllib.request, urllib.error, os, signal; port=8765; env=os.environ.copy(); proc=subprocess.Popen(['micromamba','run','-n','shiny','shiny','run','app.py','--port',str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env); print(f'started shiny PID {proc.pid} on port {port}', flush=True); resp=None
for i in range(30):
    if proc.poll() is not None:
        out, err = proc.communicate(timeout=5)
        sys.stderr.write('SHINY PROCESS EXITED EARLY\\nSTDOUT:\\n'+out.decode(errors='replace')+'\\nSTDERR:\\n'+err.decode(errors='replace'))
        sys.exit(1)
    try:
        resp = urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2).read().decode('utf-8','replace')
        print(f'GET /: {len(resp)} bytes received after {i+1}s'); break
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        time.sleep(1)
assert resp, 'app did not respond on /'
assert 'shiny' in resp.lower() or 'html' in resp.lower(), 'response does not look like a Shiny page'
print('OK: app started and served /')
proc.terminate()
try: proc.wait(timeout=10)
except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
out, err = proc.communicate()
err_text = err.decode(errors='replace')
if 'Traceback' in err_text:
    sys.stderr.write('APP STDERR CONTAINS TRACEBACK:\\n'+err_text); sys.exit(2)
print('OK: app stopped cleanly, no tracebacks in stderr')
"
```

Expected output ending with:
```
OK: app started and served /
OK: app stopped cleanly, no tracebacks in stderr
```

If the process exits early, the probe prints the captured stdout/stderr — read them to diagnose. Common causes:
- Port 8765 already in use → change `port=8765` to an unused port
- Missing import in `app.py` → fix and re-run from Task 4
- The fork's `render_network` raised at first import → re-run Task 2 to verify packaging

**No commit for this task** — produces no file changes.

---

### Task 10: Manual smoke checklist

The probe in Task 9 confirms the app starts. This task confirms it *works visually*. Cannot be skipped — it's the only thing that exercises the actual browser-side render path with real user interaction.

**Files:** read-only

- [ ] **Step 1: Launch the Shiny app**

Run (in a terminal you'll keep open):
```
micromamba run -n shiny shiny run app.py
```

Expected: console output showing `Uvicorn running on http://127.0.0.1:8000` (or similar). Leave running.

- [ ] **Step 2: Load the default dataset (BalticFW) in a browser**

Open `http://127.0.0.1:8000`. Confirm the app loads without errors. Browser devtools console (F12) should be free of red errors.

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

- [ ] **Step 6: Smoke item 4 — Special-character species names (sanity)**

The strengthened `test_topology_html_safe_for_special_chars` in Task 3 asserts round-trip correctness in the HTML. This step confirms the *visual* render matches. If the default dataset has no special-character species names, mark this step as "not directly tested in app — covered by unit test." Otherwise, hover over the affected species and confirm tooltips render correctly (bold + species name, no literal `&lt;b&gt;` text).

- [ ] **Step 7: Smoke item 5 — Disk hygiene (cross-shell file listing)**

After several minutes of interaction (switching tabs, sliding parameters, recalculating):

```
micromamba run -n shiny python -c "import glob, os, time; files=[(f, os.path.getmtime(f)) for f in glob.glob('www/*.html')]; [print(f'{f}: mtime={time.ctime(t)}') for f,t in sorted(files, key=lambda x: x[1])]; print(f'NOTE: any file with mtime AFTER app launch indicates render still writes to disk')"
```

Expected: only the three pre-existing files (`topology_network.html`, `flux_network.html`, `flux_network_energy_tab.html`) with mtimes BEFORE the time the app was launched. No new files. No mtimes younger than launch time.

If new files appear or existing files were modified: the migration is incomplete — a render path is still calling the old `save_network_html`. Re-grep `app.py`.

- [ ] **Step 8: Smoke item 6 — Browser console hygiene**

In the browser devtools (F12) → Console tab. After exercising the app, confirm no errors (red lines). Warnings are acceptable.

- [ ] **Step 9: Stop the app**

Ctrl+C in the terminal running `shiny run app.py`.

**No commit for this task** — smoke verification produces no file changes.

---

## Phase 7 — Final acceptance gate

### Task 11: Run all 10 acceptance criteria from the spec

**Files:** read-only

For each criterion, run the listed Python command (cross-shell) and confirm the expected output. Record any failure and stop the plan there.

- [ ] **Criterion 1: `save_network_html` no longer in code (only in docs)**

Run:
```
micromamba run -n shiny python -c "import subprocess; r=subprocess.run(['git','grep','save_network_html','--',':!docs/'], capture_output=True, text=True); print('matches:', r.stdout.strip() or '(none)'); assert not r.stdout.strip(), 'save_network_html still in code'; print('OK: no code references')"
```
Expected: `OK: no code references`.

- [ ] **Criterion 2: `create_temp_network_html` no longer in code (only in docs)**

Run:
```
micromamba run -n shiny python -c "import subprocess; r=subprocess.run(['git','grep','create_temp_network_html','--',':!docs/'], capture_output=True, text=True); print('matches:', r.stdout.strip() or '(none)'); assert not r.stdout.strip(), 'create_temp_network_html still in code'; print('OK: no code references')"
```
Expected: `OK: no code references`.

- [ ] **Criterion 3: `requirements.txt` has the fork pin**

Run:
```
micromamba run -n shiny python -c "t=open('requirements.txt').read(); assert 'pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2' in t, 'fork pin missing'; assert 'pyvis>=0.3.2' not in t, 'old PyPI pin still present'; print('OK: requirements.txt has fork pin, no PyPI pin')"
```
Expected: `OK: requirements.txt has fork pin, no PyPI pin`.

- [ ] **Criterion 4: `environment.yml` exists, has `- git`, has fork URL under `pip:`**

Run:
```
micromamba run -n shiny python -c "import yaml, os; assert os.path.exists('environment.yml'), 'environment.yml missing'; d=yaml.safe_load(open('environment.yml')); assert d['name']=='shiny'; assert 'git' in d['dependencies'], 'git not in conda deps'; pip=[x for x in d['dependencies'] if isinstance(x,dict) and 'pip' in x][0]['pip']; assert any('razinkele/pyvis' in p for p in pip), 'fork URL not under pip:'; print('OK: environment.yml conformant')"
```
Expected: `OK: environment.yml conformant`.

- [ ] **Criterion 5: `.gitignore` has the expected patterns**

Run:
```
micromamba run -n shiny python -c "t=open('.gitignore').read(); patterns=['__pycache__/','*.pyc','www/topology_network.html','www/flux_network.html','www/flux_network_energy_tab.html','temp_*.html','test_network.html']; missing=[p for p in patterns if p not in t]; assert not missing, f'missing: {missing}'; print(f'OK: all {len(patterns)} patterns present')"
```
Expected: `OK: all 7 patterns present`.

- [ ] **Criterion 6: All tests pass (calculation + render-path)**

Run:
```
micromamba run -n shiny python -m pytest test_flux_calculations.py test_network_analysis.py test_network_viz_render.py -q
```
Expected: ends with `49 passed`.

- [ ] **Criterion 7: Manual smoke checklist green**

Refer to Task 10 above. Mark this criterion green only if every smoke item passed.

- [ ] **Criterion 8: No new files in `www/` during interaction**

Already covered by Task 10 Step 7. Mark green if that step passed.

- [ ] **Criterion 9: `network_viz.py` no longer imports `tempfile` or `os`**

Run:
```
micromamba run -n shiny python -c "t=open('network_viz.py').read(); bad=[l for l in t.splitlines() if l.strip() in ('import tempfile','import os')]; assert not bad, f'stale imports present: {bad}'; print('OK: tempfile/os not imported')"
```
Expected: `OK: tempfile/os not imported`.

- [ ] **Criterion 10: Static-asset shipping verified in scratch env**

Already covered by Task 2. Mark green only if that task passed. If Task 2 was deferred (the fork's packaging needed fixing), this criterion remains blocked and the requirements.txt landing in Task 7 should be considered provisional.

- [ ] **Step: Report**

Summarise: which criteria passed, which failed (if any), which are blocked on out-of-project work (the fork repo). If all 10 pass, the plan is complete — the migration is done.

---

## Commit history at end of plan

```
* (HEAD) chore: gitignore per-render network HTML and Python caches
* deps: pin pyvis to razinkele fork v4.2, add environment.yml
* refactor: replace iframe(src=) render path with pyvis.shiny.render_network
* test: add render-path regression tests for network_viz
* (existing) docs: implementation plan for pyvis.shiny drop-in migration
* (existing) docs: address multi-agent review findings on pyvis spec
* (existing) docs: design spec for drop-in pyvis.shiny migration
* (existing) Initial commit: PyEcoNeTool — Python Shiny food web analysis tool
```

Four new commits, all isolated to the pyvis migration. The user's separate flux-feature edits in `app.py`, `network_analysis.py`, `requirements.txt` are not touched by this plan and remain uncommitted in the working tree (or already committed if the user committed them before starting).

---

## Out-of-scope (deferred to future work — captured from multi-agent reviews)

These items were flagged by reviewers but the user explicitly chose drop-in scope:

1. **Delete the three stale `www/*_network*.html` files.** Still served via `static_assets=www_dir`; stale data could be loaded via direct URL. Trivial follow-up (one `git rm` + commit).
2. **Add explicit `cdn_resources="in_line"` to `Network(...)` calls in `network_viz.py`.** Would make CDN_INLINE unconditional AND skip the per-render deepcopy (perf win on slider drags).
3. **Wrap `render_network(net, ...)` calls in try/except** returning a user-friendly error UI instead of Shiny's default red error box.
4. **Add Playwright-based render assertions to CI** (pytest-playwright is already installed in the `shiny` env).
5. **Consolidate `requirements.txt` and `environment.yml` to a single source of truth** (currently they must be hand-synced).
6. **Document multi-machine reproducibility** (the `DELL` profile path mystery in the original conda-build provenance).
7. **Add a note in `econetool.service`** about systemd restart-loop risk if render fails at startup probe.
