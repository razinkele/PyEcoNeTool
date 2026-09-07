# EconetPy Audit Remediation #3 Implementation Plan

## STATUS: COMPLETE (verified 2026-09-07)

**All 45 tasks landed. The `- [ ]` checkboxes below were never ticked during
execution — do not read them as outstanding work.** The commit map here and the
`audit3-*` tags are the source of truth for what was done.

Verified at `audit3-complete-2-g72aea3f`: full suite **182 passed, 1 skipped**
(the live smoke is opt-in via `ECONETOOL_LIVE_SMOKE=1`); `import app` OK;
`deploy/*.sh` parse. Separately re-run against the production interpreter
(pandas 3.0.3 / numpy 2.3.5) — core suite 89/89 — and against the *pinned*
`pyvis-optimized 4.3.1` — viz + structure suite 58/58. That last check matters
because local dev sits on 4.4.0 while the pin and the server are on 4.3.1.

| Phase | Tasks | Landed in | Tag |
|---|---|---|---|
| 1 — Data integrity & startup honesty | 1–8 | `ef59542` `fab7c3b` `8e3a3ee` `e92dd12` `eb5865a` `f3cadd5` `c587e6b` `a9ceaf6` `ba1d651` | `audit3-phase1` |
| 2 — Flux & keystoneness presentation | 10–14 | `c04b7a4` `6cfcd25` `f0f3822` `fb49148` `6997e00` `dcbe3d0` | `audit3-phase2` |
| 3 — Test integrity | 16–23 | `f9327c0` `4f71a3a` `b43d7ab` `569eb2c` `fc85f21` `a2586d2` `940b578` `dd28170` | `audit3-phase3` |
| 4 — Feedback path | 25–29 | `7e347b0` `aab7d63` `b5df547` `a6b5ee1` `974ba1b` | `audit3-phase4` |
| 5 — Deployment | 31–36 | `2bbd49c` `65b2de2` `64c2f8b` `460194b` `7e474be` `6116796` `d38b7e7` | `audit3-phase5` |
| 6 — Remaining UI & latent items | 38–43 | `e142674` `8ccbdd4` `5370c53` `5858b0d` `cc0ece4` `366aa80` `3bd8366` `e0ed602` | `audit3-phase6` |
| Post-Phase-6 live smoke | 45 | `7d403e7` `c965a93` | `audit3-complete` |

Tasks 9, 15, 24, 30, 37 and 44 are the per-phase gates; each is recorded by the
corresponding tag rather than by a code commit.

**Superseded since completion.** Phase 5 (Tasks 31–36) hardened a `deploy.sh`
that targeted a systemd unit on port 8000 — an arrangement that did not exist on
the server. That script was replaced wholesale in `72aea3f` by the Shiny Server
deployment under `deploy/`; see `DEPLOYMENT.md`. Phase 5's tasks are historically
complete but the artifact they modified is gone.

---


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the confirmed deep-review findings that remediation #2 left open — startup honesty and data integrity, flux/keystoneness presentation correctness, tests that cannot fail on the bug they guard, the feedback path, deployment, and the remaining UI and latent items.

**Architecture:** Six TDD-gated phases in order. Phase 1 makes the data path honest (module-relative paths, no swallowed misalignment, an accepted-set `met.types` validator, an alignment assert, a self-repairing pickle). Phase 2 makes what the user sees match what was computed. Phase 3 repairs tests that pass in the state they claim to guard against. Phase 4 unblocks the event loop and bounds the feedback endpoint. Phase 5 makes deployment runnable and honest. Phase 6 finishes the UI and latent fixture items.

**Tech Stack:** Python 3.13, numpy, networkx, pandas, Shiny for Python **1.7.0**, pyvis fork, matplotlib/seaborn. Tests: `micromamba run -n shiny python -m pytest`. Repo root is the working directory.

**Spec:** `docs/superpowers/specs/2026-09-05-econetpy-audit-remediation-3-design.md`
**Findings source:** `docs/superpowers/specs/2026-09-05-econetpy-deep-review-findings.md`

## Global Constraints

- Python only via `micromamba run -n shiny python`; never create a venv.
- Shiny for Python is **1.7.0**: `render.DataGrid` has NO `editable_columns`; `data_patched()`, `data_view()`, `set_patch_fn()` all exist.
- Baseline at plan start: **133 passed, 3 known UserWarnings** (`network_analysis.py` lines 122, 134, 186). Any other warning in test output is a defect.
- `BalticFW.pkl` is gitignored and rebuilt with `micromamba run -n shiny python load_data.py`.
- Every behavior change lands with a test that was seen RED first. Where a Shiny reactive closure cannot be driven without a live session, an AST/source-structural test is acceptable but must still be shown RED first.
- Never use shell heredocs on this machine (cmd.exe mangles them) — write scratch scripts with the Write tool.
- No pushes. Tags only: `audit3-phase1` .. `audit3-phase6`.
- Work on a feature branch off `master` (`27086de` or later), created at execution time.

## Cross-phase dependencies (read before starting any phase)

- **Task 1 (`1.2`) is load-bearing for the whole plan.** It moves data-file resolution from the process cwd to `Path(__file__).parent`, which BREAKS two existing remediation-#2 tests that use `monkeypatch.chdir` (`test_load_baltic_data_raises_on_name_mismatch`, `test_load_default_data_rejects_permuted_pickle`). Task 1 rewrites both onto `base_dir=` / `monkeypatch.setattr(app, "DATA_DIR", ...)` in the same task. Task 23 (`3.8`, the synthetic same-set/different-order reindex proof) also consumes `load_baltic_data(base_dir=...)`.
- **Phase 2 assumes Phase 1 has landed**: `_assert_aligned` exists in `app.py` and the editor apply handler already validates `met.types`. Phase 2's Task 12 extends that same handler.
- **Task 41 (`6.3`) changes emitted node attributes**, so the pinned viz tests `test_topology_node_size_and_y_position_pinned` and `test_flux_node_size_and_y_position_pinned` are updated in that same task, deliberately.
- **Task 13 (`2.4`) returns thresholds via the DataFrame's `.attrs`**, chosen because every existing caller unpacks `calculate_keystoneness` as a single DataFrame; a second return value would break all of them.
- **Task 45 is the acceptance gate for the whole plan.** It is the spec-required post-Phase-6 live smoke (design doc L105) — the first and only step that starts the real app and drives it: a Data Editor round-trip through `data_patched()`/`set_patch_fn`, a forced renderer error checked against `safe_render`'s clean panel, and a self-contained network-HTML download. It runs after Task 44's `audit3-phase6` tag and depends on Task 14 (inlined download assets), Task 20 (`safe_render`), and Phase 1's editor validations having all landed. The plan is not complete until Task 45 is green.

---

# PHASE 1 — Data integrity and startup honesty

### Task 1: Resolve data files against the module directory, not cwd (`1.2`)

**Files:**
- Modify: `load_data.py:17-71` (`load_baltic_data`)
- Modify: `app.py:91-126` (`load_default_data` — add `DATA_DIR`, fix `data_file`, pass `base_dir`)
- Test: `test_load_data_alignment.py`

**Interfaces:**
- Consumes: nothing
- Produces: `load_data.load_baltic_data(base_dir: Path | None = None)`; module constant `app.DATA_DIR = Path(__file__).parent`, used later by Tasks 4, 5, 8.

- [ ] **Step 1: Write the failing test**
```python
# Add to test_load_data_alignment.py
def test_load_baltic_data_resolves_against_base_dir_not_cwd(tmp_path, monkeypatch):
    """load_baltic_data(base_dir=tmp_path) must read tmp_path's files even
    though cwd points somewhere else entirely — proves resolution is no
    longer cwd-relative."""
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    g = nx.DiGraph()
    g.add_node('n0', name='Cod'); g.add_node('n1', name='Sprat')
    g.add_edge('n0', 'n1')
    nx.write_graphml(g, tmp_path / "BalticFW_network.graphml")
    pd.DataFrame({'species': ['Cod', 'Sprat'], 'fg': ['Fish', 'Fish'],
                  'meanB': [1.0, 2.0], 'bodymasses': [1.0, 2.0],
                  'met.types': ['Other', 'Other'], 'efficiencies': [0.5, 0.5]}
                 ).to_csv(tmp_path / "BalticFW_species_info.csv", index=False)

    from load_data import load_baltic_data
    G, info = load_baltic_data(base_dir=tmp_path)
    assert list(G.nodes()) == info['species'].tolist() == ['Cod', 'Sprat']
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_load_data_alignment.py::test_load_baltic_data_resolves_against_base_dir_not_cwd -v`
Expected: FAIL — `TypeError: load_baltic_data() got an unexpected keyword argument 'base_dir'` (today's signature is `load_baltic_data()` with no parameters, `load_data.py:17`).
- [ ] **Step 3: Add `base_dir` to `load_baltic_data`**
```python
# load_data.py:17-27, replace:
def load_baltic_data():
    """
    Load Baltic Food Web data from converted files.

    Returns:
        tuple: (network, species_info)
    """
    # Check if converted files exist
    network_file = Path("BalticFW_network.graphml")
    info_file = Path("BalticFW_species_info.csv")
    metadata_file = Path("BalticFW_metadata.json")

# with:
def load_baltic_data(base_dir: Path | None = None):
    """
    Load Baltic Food Web data from converted files.

    Args:
        base_dir: Directory holding the tracked GraphML/CSV/JSON sources.
                  Defaults to this module's own directory (never the cwd).

    Returns:
        tuple: (network, species_info)
    """
    base_dir = Path(base_dir) if base_dir is not None else Path(__file__).parent
    # Check if converted files exist
    network_file = base_dir / "BalticFW_network.graphml"
    info_file = base_dir / "BalticFW_species_info.csv"
    metadata_file = base_dir / "BalticFW_metadata.json"
```
- [ ] **Step 4: Add `DATA_DIR` in `app.py` and route the pickle + fallback call through it**
```python
# app.py:91-101, replace:
def load_default_data():
    """Load the default Baltic Food Web data.

    Resolution order:
    1. BalticFW.pkl — fast prebuilt cache (gitignored; present on dev machines).
    2. Tracked text sources (BalticFW_network.graphml + _species_info.csv +
       _metadata.json) via load_data.load_baltic_data() — used on a fresh clone
       where the pickle is absent.
    3. A small synthetic example network, only if neither is available.
    """
    data_file = Path("BalticFW.pkl")

# with:
DATA_DIR = Path(__file__).parent


def load_default_data():
    """Load the default Baltic Food Web data.

    Resolution order:
    1. BalticFW.pkl — fast prebuilt cache (gitignored; present on dev machines).
    2. Tracked text sources (BalticFW_network.graphml + _species_info.csv +
       _metadata.json) via load_data.load_baltic_data() — used on a fresh clone
       where the pickle is absent.
    3. A small synthetic example network, only if neither is available.

    All sources resolve against DATA_DIR (this file's own directory), never
    the process cwd, so `shiny run /path/to/app.py` from another directory
    still finds the Baltic data.
    """
    data_file = DATA_DIR / "BalticFW.pkl"
```
and at `app.py:120-123`, replace:
```python
    # No pickle cache — reconstruct from the tracked GraphML/CSV/JSON sources.
    try:
        from load_data import load_baltic_data
        return load_baltic_data()
```
with:
```python
    # No pickle cache — reconstruct from the tracked GraphML/CSV/JSON sources.
    try:
        from load_data import load_baltic_data
        return load_baltic_data(base_dir=DATA_DIR)
```
- [ ] **Step 5: Update the two existing tests that relied on cwd resolution**
```python
# test_load_data_alignment.py: test_load_baltic_data_raises_on_name_mismatch
# replace the two lines:
    monkeypatch.chdir(tmp_path)
    from load_data import load_baltic_data
    with pytest.raises(ValueError, match="match|align"):
        load_baltic_data()
# with:
    from load_data import load_baltic_data
    with pytest.raises(ValueError, match="match|align"):
        load_baltic_data(base_dir=tmp_path)
```
```python
# test_load_data_alignment.py: test_load_default_data_rejects_permuted_pickle
# replace:
    monkeypatch.chdir(tmp_path)

    sentinel_g = nx.DiGraph(); sentinel_g.add_node('Sentinel')
# with:
    import app
    monkeypatch.setattr(app, 'DATA_DIR', tmp_path)

    sentinel_g = nx.DiGraph(); sentinel_g.add_node('Sentinel')
```
and further down in the same test, replace:
```python
    monkeypatch.setattr('load_data.load_baltic_data',
                         lambda: (sentinel_g, sentinel_info))

    import app
    G, info = app.load_default_data()
```
with (the sentinel lambda must accept the `base_dir` keyword — `load_default_data` now calls `load_baltic_data(base_dir=DATA_DIR)`; the redundant second `import app` is dropped since `app` is now imported once, above):
```python
    monkeypatch.setattr('load_data.load_baltic_data',
                         lambda base_dir=None: (sentinel_g, sentinel_info))

    G, info = app.load_default_data()
```
- [ ] **Step 6: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_load_data_alignment.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS — new test green; `test_load_baltic_data_raises_on_name_mismatch` and `test_load_default_data_rejects_permuted_pickle` still pass under the new resolution mechanism; 133+ passed, only the 3 known UserWarnings.
- [ ] **Step 7: Commit**
```bash
git add load_data.py app.py test_load_data_alignment.py
git commit -m "fix: resolve Baltic data sources against module dir, not cwd"
```

---

### Task 2: Accepted-set validator for `met.types`, used at the allometric-loss and ingestion sites (`1.4` part A)

**Files:**
- Modify: `flux_calculations.py:207-251` (`calculate_losses_allometric`), add `validate_met_types` + `ACCEPTED_MET_TYPES`
- Modify: `load_data.py:81-85` (`load_baltic_data` required-columns check)
- Test: `test_flux_calculations.py`, `test_load_data_alignment.py`

**Interfaces:**
- Consumes: nothing
- Produces: `flux_calculations.validate_met_types(met_types, context="") -> None` (raises `ValueError`), `flux_calculations.ACCEPTED_MET_TYPES` — imported by Task 7 (editor handler).

- [ ] **Step 1: Write the failing tests**
```python
# Add to test_flux_calculations.py
def test_calculate_losses_allometric_rejects_unknown_met_type():
    """An unknown met.types value must raise ValueError naming the bad value
    and the accepted set, not silently fall back to intercept 0 via .get(mt, 0)."""
    bodymasses = np.array([1.0, 1.0])
    met_types = ['invertebrates', 'mammal']  # 'mammal' is not an accepted value
    with pytest.raises(ValueError, match="mammal"):
        calculate_losses_allometric(bodymasses, met_types, temperature=10.0)
```
```python
# Add to test_load_data_alignment.py
def test_load_baltic_data_rejects_unknown_met_type(tmp_path):
    """load_baltic_data must validate met.types at ingestion, not defer to
    calculate_losses_allometric at first use."""
    g = nx.DiGraph()
    g.add_node('n0', name='Cod'); g.add_node('n1', name='Sprat')
    g.add_edge('n0', 'n1')
    nx.write_graphml(g, tmp_path / "BalticFW_network.graphml")
    pd.DataFrame({'species': ['Cod', 'Sprat'], 'fg': ['Fish', 'Fish'],
                  'meanB': [1.0, 2.0], 'bodymasses': [1.0, 2.0],
                  'met.types': ['Other', 'mammal'], 'efficiencies': [0.5, 0.5]}
                 ).to_csv(tmp_path / "BalticFW_species_info.csv", index=False)
    from load_data import load_baltic_data
    with pytest.raises(ValueError, match="mammal"):
        load_baltic_data(base_dir=tmp_path)
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py::test_calculate_losses_allometric_rejects_unknown_met_type test_load_data_alignment.py::test_load_baltic_data_rejects_unknown_met_type -v`
Expected: FAIL — `calculate_losses_allometric` today does `losses_param.get(mt, 0)` (`flux_calculations.py:244`), silently mapping `'mammal'` to intercept 0 instead of raising, so no `ValueError` is raised in either test.
- [ ] **Step 3: Add the validator and call it from `calculate_losses_allometric`**
```python
# flux_calculations.py, insert before `def calculate_losses_allometric(` at line 207:
ACCEPTED_MET_TYPES = frozenset({"invertebrates", "ectotherm vertebrates", "Other"})


def validate_met_types(met_types, context: str = "") -> None:
    """Raise ValueError naming any met.types value outside ACCEPTED_MET_TYPES.

    Used at three sites so the check happens exactly once, in one place:
    calculate_losses_allometric, load_data.load_baltic_data, and the editor
    apply handler in app.py.
    """
    unknown = sorted(set(met_types) - ACCEPTED_MET_TYPES)
    if unknown:
        where = f" in {context}" if context else ""
        raise ValueError(
            f"Unknown met.types value(s) {unknown}{where}; "
            f"accepted values are {sorted(ACCEPTED_MET_TYPES)}."
        )
```
```python
# flux_calculations.py:234, inside calculate_losses_allometric, replace:
    boltz = 0.00008617343  # Boltzmann constant

    # Normalization constants (intercept of body-mass metabolism scaling)
    losses_param = {
        "invertebrates": 17.17,
        "ectotherm vertebrates": 18.47,
        "Other": 0
    }

    # Get x0 for each species
    x0 = np.array([losses_param.get(mt, 0) for mt in met_types])
# with:
    validate_met_types(met_types, context="calculate_losses_allometric")

    boltz = 0.00008617343  # Boltzmann constant

    # Normalization constants (intercept of body-mass metabolism scaling)
    losses_param = {
        "invertebrates": 17.17,
        "ectotherm vertebrates": 18.47,
        "Other": 0
    }

    # Get x0 for each species (all values are now known to be in the accepted set)
    x0 = np.array([losses_param[mt] for mt in met_types])
```
- [ ] **Step 4: Call it from `load_baltic_data` at ingestion**
```python
# load_data.py:81-85, replace:
    # Check for required columns BEFORE referencing any of them.
    required_cols = ['species', 'fg', 'meanB', 'bodymasses', 'met.types', 'efficiencies']
    missing_cols = [col for col in required_cols if col not in info.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
# with:
    # Check for required columns BEFORE referencing any of them.
    required_cols = ['species', 'fg', 'meanB', 'bodymasses', 'met.types', 'efficiencies']
    missing_cols = [col for col in required_cols if col not in info.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    from flux_calculations import validate_met_types
    validate_met_types(info['met.types'].tolist(), context="load_baltic_data")
```
- [ ] **Step 5: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py test_load_data_alignment.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS — both new tests green; every existing caller uses only `invertebrates`/`ectotherm vertebrates`/`Other` (verified: `test_network_analysis.py:45,71,356,371,384`, `test_flux_calculations.py:274,286,299,312,339,458`, `create_example_network` in `app.py:155`), so no existing test is affected; 133+ passed.
- [ ] **Step 6: Commit**
```bash
git add flux_calculations.py load_data.py test_flux_calculations.py test_load_data_alignment.py
git commit -m "fix: raise on unknown met.types instead of silently zeroing intercept"
```

---

### Task 3: Extend `validate_flux_equilibrium`'s non-finite guard to `efficiencies` (`1.6`)

**Files:**
- Modify: `flux_calculations.py:281` (`validate_flux_equilibrium`'s non-finite guard; verified at line 281 pre-Task-2 — Task 2 inserts `ACCEPTED_MET_TYPES`/`validate_met_types` above this function, so by the time this task runs the same guard line sits ~17 lines lower; locate it by the `if not np.all(np.isfinite(flux_matrix))` text shown below, not by line number alone)
- Test: `test_flux_calculations.py`

**Interfaces:**
- Consumes: nothing
- Produces: nothing (internal robustness fix; the function's returned dict shape is unchanged)

- [ ] **Step 1: Write the failing test**
```python
# Add to test_flux_calculations.py, after test_validate_flux_equilibrium_flags_nonfinite_losses
def test_validate_flux_equilibrium_flags_nonfinite_efficiencies():
    """A NaN in efficiencies with an all-zero flux_matrix and zero losses must
    also trip the guard.

    Same vacuous-else-branch shape as the flux_matrix/losses NaN cases above:
    inflows = flux_matrix.T @ efficiencies is NaN in every entry (0*nan=nan
    propagates through the sum), so `inflows > tolerance` is False everywhere
    (checked all-False); outflows = sum(flux, axis=1) + losses is all-zero, so
    `abs(outflows) > tolerance` is also False. Pre-guard code falls into the
    else branch and would silently report balanced=True / max_imbalance=0.0.
    Extending the guard to cover `efficiencies` must catch it.
    """
    flux = np.zeros((3, 3))
    losses = np.array([0.0, 0.0, 0.0])
    e = np.array([0.5, np.nan, 0.5])
    r = validate_flux_equilibrium(flux, losses, e)
    assert r['balanced'] is False, r
    assert not np.isfinite(r['max_imbalance']), r
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py::test_validate_flux_equilibrium_flags_nonfinite_efficiencies -v`
Expected: FAIL — `flux_calculations.py:281` only checks `np.isfinite(flux_matrix)` and `np.isfinite(losses)`, not `efficiencies`; both flux_matrix and losses are finite here, so the early return is skipped, `inflows` computes to all-NaN, `checked` is all-False, `outflows` is all-zero, and the function falls into the `else: max_imbalance = mean_imbalance = 0.0` branch, returning `balanced=True`.
- [ ] **Step 3: Extend the guard**
```python
# flux_calculations.py:281, replace:
    if not np.all(np.isfinite(flux_matrix)) or not np.all(np.isfinite(losses)):
# with:
    if (not np.all(np.isfinite(flux_matrix))
            or not np.all(np.isfinite(losses))
            or not np.all(np.isfinite(efficiencies))):
```
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS — new test green; `test_validate_flux_equilibrium_flags_nonfinite` and `test_validate_flux_equilibrium_flags_nonfinite_losses` still pass (their `efficiencies` arrays are already all-finite); 133+ passed.
- [ ] **Step 5: Commit**
```bash
git add flux_calculations.py test_flux_calculations.py
git commit -m "fix: validate_flux_equilibrium also flags non-finite efficiencies"
```

---

### Task 4: `_assert_aligned` guard on every `load_default_data` return path (`1.5` part A)

**Files:**
- Modify: `app.py:91-126` (`load_default_data`)
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: `app.DATA_DIR` (Task 1)
- Produces: `app._assert_aligned(G, info) -> None` (raises `ValueError`) — imported/used by Task 7 (editor handler).

- [ ] **Step 1: Write the failing test**
```python
# Add to test_app_structure.py
def test_assert_aligned_raises_on_node_row_mismatch():
    """_assert_aligned must raise ValueError when node order and species-row
    order have diverged (the exact contract load_default_data's three return
    paths and the editor apply handler depend on)."""
    import networkx as nx
    import pandas as pd
    import pytest
    app = importlib.import_module("app")
    G = nx.DiGraph()
    G.add_node('Cod'); G.add_node('Sprat')
    info = pd.DataFrame({'species': ['Sprat', 'Cod'], 'fg': ['Fish', 'Fish']})
    with pytest.raises(ValueError, match="misalign|align"):
        app._assert_aligned(G, info)


def test_load_default_data_raises_on_pickle_bypassing_misaligned_reconstruction(tmp_path, monkeypatch):
    """If load_baltic_data's own reindex/raise contract were ever bypassed
    (e.g. a future refactor returns misaligned data directly), _assert_aligned
    inside load_default_data must still catch it rather than returning
    misaligned data silently."""
    app = importlib.import_module("app")
    monkeypatch.setattr(app, 'DATA_DIR', tmp_path)  # no BalticFW.pkl here

    import networkx as nx
    import pandas as pd
    import pytest
    bad_g = nx.DiGraph(); bad_g.add_node('Cod'); bad_g.add_node('Sprat')
    bad_info = pd.DataFrame({'species': ['Sprat', 'Cod'], 'fg': ['Fish', 'Fish'],
                             'meanB': [1.0, 2.0], 'bodymasses': [1.0, 2.0],
                             'met.types': ['Other', 'Other'], 'efficiencies': [0.5, 0.5]})
    monkeypatch.setattr('load_data.load_baltic_data', lambda base_dir=None: (bad_g, bad_info))

    with pytest.raises(ValueError, match="misalign|align"):
        app.load_default_data()
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_assert_aligned_raises_on_node_row_mismatch test_app_structure.py::test_load_default_data_raises_on_pickle_bypassing_misaligned_reconstruction -v`
Expected: FAIL — `AttributeError: module 'app' has no attribute '_assert_aligned'` for the first test; for the second, `load_default_data` (`app.py:120-123`) returns whatever `load_baltic_data()` gives it with no alignment check of its own, so the monkeypatched misaligned pair is returned as-is instead of raising.
- [ ] **Step 3: Add `_assert_aligned` and call it on every return path**
```python
# app.py, insert immediately before `def load_default_data():` (after the new
# DATA_DIR = Path(__file__).parent from Task 1):
def _assert_aligned(G, info):
    """Raise ValueError if the network's node order and species_info's row
    order have diverged. Called on every load_default_data() return path and
    before current_species_info.set(df) in the editor apply handler."""
    nodes = list(G.nodes())
    species = info['species'].tolist()
    if nodes != species:
        raise ValueError(
            "Network nodes and species_info rows are misaligned: "
            f"nodes={nodes[:3]}..., species={species[:3]}..."
        )
```
```python
# app.py:111-126, replace:
        else:
            G_pkl, info_pkl = data['network'], data['info']
            required = ['species', 'fg', 'meanB', 'bodymasses', 'met.types', 'efficiencies']
            if (all(c in info_pkl.columns for c in required)
                    and info_pkl['species'].tolist() == list(G_pkl.nodes())):
                return G_pkl, info_pkl
            print("BalticFW.pkl stale/misaligned; rebuilding from sources.")
        # fall through to reconstruction

    # No pickle cache — reconstruct from the tracked GraphML/CSV/JSON sources.
    try:
        from load_data import load_baltic_data
        return load_baltic_data(base_dir=DATA_DIR)
    except (FileNotFoundError, ImportError) as exc:
        print(f"Baltic sources unavailable ({exc}); using example network.")
        return create_example_network()
# with:
        else:
            G_pkl, info_pkl = data['network'], data['info']
            required = ['species', 'fg', 'meanB', 'bodymasses', 'met.types', 'efficiencies']
            if (all(c in info_pkl.columns for c in required)
                    and info_pkl['species'].tolist() == list(G_pkl.nodes())):
                _assert_aligned(G_pkl, info_pkl)
                return G_pkl, info_pkl
            print("BalticFW.pkl stale/misaligned; rebuilding from sources.")
        # fall through to reconstruction

    # No pickle cache — reconstruct from the tracked GraphML/CSV/JSON sources.
    try:
        from load_data import load_baltic_data
        G, info = load_baltic_data(base_dir=DATA_DIR)
        _assert_aligned(G, info)
        return G, info
    except (FileNotFoundError, ImportError) as exc:
        print(f"Baltic sources unavailable ({exc}); using example network.")
        G, info = create_example_network()
        _assert_aligned(G, info)
        return G, info
```
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS — both new tests green; 133+ passed.
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "fix: assert node/row alignment on every load_default_data return path"
```

---

### Task 5: Stop swallowing a misalignment `ValueError` at startup; set `USING_EXAMPLE_NETWORK` (`1.1`)

**Files:**
- Modify: `app.py:91-126` (`load_default_data`'s internal except — the operative fallback path, as left by Task 4) and `app.py:164-170` (module-level startup try/except — the backstop)
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: `app.load_default_data`, `app.create_example_network`, `app._assert_aligned` (Task 4), `app.DATA_DIR` (Task 1)
- Produces: module flag `app.USING_EXAMPLE_NETWORK: bool`, set `True` on both the internal and the module-level fallback — consumed by Task 6 (`dashboard_ui` banner).

- [ ] **Step 1: Write the failing test**
```python
# Add to test_app_structure.py
def test_startup_except_clause_is_narrow_not_bare_exception():
    """The module-level `try: load_default_data()` guard must not catch a
    bare Exception — a ValueError from a real data misalignment (Task 4's
    _assert_aligned) must abort import, not be silently swallowed into the
    example network."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    module_level_tries = [
        n for n in tree.body if isinstance(n, ast.Try)
    ]
    assert module_level_tries, "expected a module-level try/except around load_default_data()"
    handlers = module_level_tries[0].handlers
    assert len(handlers) == 1
    caught = handlers[0].type
    # ast.Tuple of Name nodes for `except (FileNotFoundError, ImportError):`
    assert isinstance(caught, ast.Tuple), ast.dump(caught)
    names = {elt.id for elt in caught.elts if isinstance(elt, ast.Name)}
    assert names == {"FileNotFoundError", "ImportError"}, names


def test_using_example_network_flag_set_when_sources_absent(tmp_path, monkeypatch):
    """USING_EXAMPLE_NETWORK must flip to True via the actual code path taken
    when DATA_DIR holds neither a pickle nor tracked GraphML/CSV/JSON sources
    — this is the path load_default_data() takes on 99% of fresh clones
    without a prebuilt BalticFW.pkl, NOT the (mostly dead) module-level
    startup except clause."""
    app = importlib.import_module("app")
    monkeypatch.setattr(app, 'DATA_DIR', tmp_path)  # empty: no .pkl, no sources
    # monkeypatch (not a bare assignment) so the module flag is restored at
    # teardown — same reason DATA_DIR above uses it. A bare assignment would
    # leak USING_EXAMPLE_NETWORK=True into every later test in the session.
    monkeypatch.setattr(app, 'USING_EXAMPLE_NETWORK', False)

    G, info = app.load_default_data()

    assert app.USING_EXAMPLE_NETWORK is True
    assert list(G.nodes()) == info['species'].tolist()  # example network self-aligned
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_startup_except_clause_is_narrow_not_bare_exception test_app_structure.py::test_using_example_network_flag_set_when_sources_absent -v`
Expected: FAIL — first test: `app.py:167` is `except Exception as e:`, so `caught` is an `ast.Name` (`Exception`), not an `ast.Tuple`; the assertion `isinstance(caught, ast.Tuple)` fails. Second test: `USING_EXAMPLE_NETWORK` does not exist as a module attribute at all yet — nothing in `load_default_data` (`app.py:91-126`, as left by Task 4) ever assigns it — so `monkeypatch.setattr(app, 'USING_EXAMPLE_NETWORK', False)` raises `AttributeError: <module 'app'> has no attribute 'USING_EXAMPLE_NETWORK'` before the call is even reached. (Once Step 3 defines the module-level flag, the same test re-runs and then fails on `assert app.USING_EXAMPLE_NETWORK is True` if the fallback path does not set it — both are the RED this test is for.)
- [ ] **Step 3: Narrow the module-level except clause AND set the flag on the actual fallback path inside `load_default_data`**

The flag must be set where `create_example_network()` is actually invoked. That is overwhelmingly `load_default_data`'s own internal `except (FileNotFoundError, ImportError)` (as left by Task 4) — the module-level except at `app.py:167` only fires if `load_default_data()` itself propagates one of those two exception types. It does not propagate `FileNotFoundError`/`ImportError` today, because the reconstruction path catches both internally, so that clause is a defensive backstop rather than the operative path.

Note what is NOT guarded, and do not assume it is: the `pickle.load(f)` at `app.py:107-108` and the dict-shape check below it sit outside every `try` in `load_default_data`, so a corrupt cache raises `UnpicklingError`/`EOFError` straight out of the function (and out of `import app`). That hole is closed in **Task 8, Step 4** — do not try to fix it here.

Insert `USING_EXAMPLE_NETWORK = False` directly **below the `DATA_DIR = Path(__file__).parent` line** added by Task 1. Anchor on `DATA_DIR`, NOT on adjacency to `def load_default_data():` — Task 4 has already inserted the whole `_assert_aligned` function between `DATA_DIR` and `load_default_data`, so they are no longer neighbours:
```python
# app.py, immediately after the `DATA_DIR = Path(__file__).parent` line added
# by Task 1, and ABOVE Task 4's `_assert_aligned`:
DATA_DIR = Path(__file__).parent
USING_EXAMPLE_NETWORK = False


def _assert_aligned(G, info):   # <- added by Task 4; unchanged, shown only as the anchor
    ...


def load_default_data():
```
```python
# app.py, inside load_default_data (the internal except, as left by Task 4), replace:
    except (FileNotFoundError, ImportError) as exc:
        print(f"Baltic sources unavailable ({exc}); using example network.")
        G, info = create_example_network()
        _assert_aligned(G, info)
        return G, info
# with:
    except (FileNotFoundError, ImportError) as exc:
        global USING_EXAMPLE_NETWORK
        print(f"Baltic sources unavailable ({exc}); using example network.")
        USING_EXAMPLE_NETWORK = True
        G, info = create_example_network()
        _assert_aligned(G, info)
        return G, info
```
```python
# app.py:164-170, replace:
# Load data at startup
try:
    network, species_info = load_default_data()
except Exception as e:
    print(f"Warning: Could not load default data: {e}")
    print("Using example network instead.")
    network, species_info = create_example_network()
# with:
# Load data at startup. Narrowed to the two cases load_default_data() itself
# does not already resolve into the example network internally (this except
# is a defensive backstop in case load_default_data ever propagates one of
# these two): a data ValueError (misalignment, unknown met.types, ...) is a
# bug to fix, not a fallback, and must abort import.
try:
    network, species_info = load_default_data()
except (FileNotFoundError, ImportError) as e:
    print(f"Warning: Could not load default data: {e}")
    print("Using example network instead.")
    network, species_info = create_example_network()
    USING_EXAMPLE_NETWORK = True
```
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS — both new tests green; 133+ passed; `micromamba run -n shiny python -c "import app; print('app OK')"` still succeeds since the tracked Baltic sources are aligned, `load_default_data()` takes the pickle or reconstruction success path, and `USING_EXAMPLE_NETWORK` stays `False`.
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "fix: let a data ValueError abort import instead of masking it as example-network fallback"
```

---

### Task 6: Visible banner when the example network is in use (`1.3`)

**Files:**
- Modify: `app.py:176-228` (`dashboard_ui` lambda; verified: `dashboard_ui = lambda:` at 176, `width=1/3` at 226, closing `)` at 227 and 228, `network_ui` begins at 230)
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: `app.USING_EXAMPLE_NETWORK` (Task 5)
- Produces: nothing further consumed this phase (Phase 2/6 do not depend on this banner)

- [ ] **Step 1: Write the failing test**
```python
# Add to test_app_structure.py
def test_dashboard_banner_shown_when_using_example_network(monkeypatch):
    """dashboard_ui() must render a visible banner element when the module
    flag says the example network is in use — not merely a stdout print.

    NOTE: dashboard_ui() returns a shiny.ui._card.CardItem; bare str() on it
    yields its object repr ('<shiny.ui._card.CardItem object at 0x...>'), NOT
    rendered HTML (this is why the existing test_tl_method_is_single_topbar_select
    at test_app_structure.py:104 only ever checks *absence* of a substring — it
    would pass whether or not the string is really rendered). Render properly
    via htmltools.TagList(...) so the assertion actually inspects markup.
    """
    import htmltools
    app = importlib.import_module("app")
    monkeypatch.setattr(app, 'USING_EXAMPLE_NETWORK', True)
    html = str(htmltools.TagList(app.dashboard_ui()))
    assert "example network" in html.lower()


def test_dashboard_banner_absent_when_using_real_data(monkeypatch):
    import htmltools
    app = importlib.import_module("app")
    monkeypatch.setattr(app, 'USING_EXAMPLE_NETWORK', False)
    html = str(htmltools.TagList(app.dashboard_ui()))
    assert "example network" not in html.lower()
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_dashboard_banner_shown_when_using_example_network -v`
Expected: FAIL — `dashboard_ui` (`app.py:176`) is a fixed `lambda: ui.layout_sidebar(...)` with no reference to `USING_EXAMPLE_NETWORK` and no banner text anywhere in its output; rendering it with `htmltools.TagList(...)` gives the real markup (confirmed manually: today it is ~5400 chars of card/sidebar HTML with no "example network" text anywhere), so `"example network" in html.lower()` is False.
- [ ] **Step 3: Make `dashboard_ui` a function that reads the flag and prepends a banner**

The whole current definition is `app.py:176-228`:
```python
dashboard_ui = lambda: ui.layout_sidebar(
        ui.sidebar(
            ui.h4("EcoNeTool"),
            ui.p("Interactive Food Web Analysis"),
            ui.hr(),
            ui.h5("Dataset Info"),
            ui.output_text_verbatim("dataset_summary"),
            ui.hr(),
            ui.h5("Functional Groups"),
            ui.output_ui("functional_groups_legend"),
            width=300
        ),
        ui.card(
            ui.card_header("Welcome to EcoNeTool"),
            ui.markdown(
                """
                ### Food Web Explorer
                ...
                """
            )
        ),
        ui.layout_column_wrap(
            ui.value_box(
                "Species",
                ui.output_text("n_species"),
                theme="primary"
            ),
            ui.value_box(
                "Links",
                ui.output_text("n_links"),
                theme="success"
            ),
            ui.value_box(
                "Functional Groups",
                ui.output_text("n_groups"),
                theme="info"
            ),
            width=1/3
        )
    )
```
Replace only the first line (`dashboard_ui = lambda: ui.layout_sidebar(` at `app.py:176`) and the last three lines (`            width=1/3\n        )\n    )` at `app.py:226-228`) so the body in between is unchanged:
```python
# app.py:176, replace:
dashboard_ui = lambda: ui.layout_sidebar(
        ui.sidebar(
# with:
def dashboard_ui():
    banner = (
        ui.div(
            "Showing a synthetic example network — the Baltic data sources "
            "were unavailable at startup. See server logs for details.",
            class_="econetpy-example-network-banner",
            style=(
                "background:#fff3cd; color:#664d03; border:1px solid #ffecb5; "
                "border-radius:6px; padding:10px 16px; margin-bottom:12px; "
                "font-weight:600;"
            ),
        )
        if USING_EXAMPLE_NETWORK else None
    )
    layout = ui.layout_sidebar(
        ui.sidebar(
```
```python
# app.py:226-228, replace:
            width=1/3
        )
    )
# with:
            width=1/3
        )
    )
    return ui.div(banner, layout) if banner is not None else layout
```
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS — both new tests green; `PAGES["dashboard"]` (`app.py:373`) still holds a zero-arg callable (`dashboard_ui` is now a `def` instead of a `lambda`, same call signature `dashboard_ui()` used at `app.py:846`); 133+ passed.
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "fix: show a visible dashboard banner when serving the example network"
```

---

### Task 7: Validate edits before applying them — `met.types` accepted set and node/row alignment (`1.4` part B, `1.5` part B)

**Files:**
- Modify: `app.py:1364-1390` (`_apply_species_info_edits`; verified: `@reactive.effect` at 1364, `def _apply_species_info_edits():` at 1366, function body ends at 1390 with the `"Species info updated."` notification)
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: `flux_calculations.validate_met_types` (Task 2), `app._assert_aligned` (Task 4)
- Produces: nothing (terminal handler; Phase 2's editor changes extend this same function)

- [ ] **Step 1: Write the failing test (structural — this is a `@reactive.effect` body, not independently callable)**

The apply handler only runs inside a live Shiny reactive graph and cannot be invoked directly in-process without a running session, so this is pinned with an AST guard, following the pattern already used for `test_analytical_renderers_use_caches_not_direct_compute` in this file.
```python
# Add to test_app_structure.py
def test_apply_species_info_edits_validates_met_types_and_alignment():
    """The editor apply handler must reject an edited met.types value outside
    the accepted set and must re-check node/row alignment before
    current_species_info.set(df) — both via app-level helpers, not ad hoc."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_apply_species_info_edits":
            target = node
            break
    assert target is not None, "could not find _apply_species_info_edits"
    calls = _calls_in(target)
    assert "validate_met_types" in calls, calls
    assert "_assert_aligned" in calls, calls
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_apply_species_info_edits_validates_met_types_and_alignment -v`
Expected: FAIL — `_apply_species_info_edits` (`app.py:1364-1390`) today only coerces numeric columns and checks `len(df) != current_network().number_of_nodes()`; it calls neither `validate_met_types` nor `_assert_aligned`, so both membership assertions fail.
- [ ] **Step 3: Add the two validations before `current_species_info.set(df)`**
```python
# app.py:1364-1390, replace:
    @reactive.effect
    @reactive.event(input.update_species_info)
    def _apply_species_info_edits():
        edited = species_info_editor.data_patched()  # original node order + edits
        if edited is None or edited.empty:
            ui.notification_show("No edited data to apply.", type="warning", duration=4)
            return
        df = edited.copy()
        # DataGrid returns edited cells as strings; coerce numeric columns back.
        for col in ("meanB", "bodymasses", "efficiencies"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        # Reject malformed edits rather than letting NaN crash downstream renders.
        numeric_cols = [c for c in ("meanB", "bodymasses", "efficiencies") if c in df.columns]
        if numeric_cols and df[numeric_cols].isna().any().any():
            ui.notification_show(
                "Some numeric cells are invalid (non-numeric or blank). Fix them and retry.",
                type="error", duration=6,
            )
            return
        if len(df) != current_network().number_of_nodes():
            ui.notification_show(
                "Edited table row count does not match the network; not applied.",
                type="error", duration=6,
            )
            return
        current_species_info.set(df)
        ui.notification_show("Species info updated.", type="message", duration=4)
# with:
    @reactive.effect
    @reactive.event(input.update_species_info)
    def _apply_species_info_edits():
        edited = species_info_editor.data_patched()  # original node order + edits
        if edited is None or edited.empty:
            ui.notification_show("No edited data to apply.", type="warning", duration=4)
            return
        df = edited.copy()
        # DataGrid returns edited cells as strings; coerce numeric columns back.
        for col in ("meanB", "bodymasses", "efficiencies"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        # Reject malformed edits rather than letting NaN crash downstream renders.
        numeric_cols = [c for c in ("meanB", "bodymasses", "efficiencies") if c in df.columns]
        if numeric_cols and df[numeric_cols].isna().any().any():
            ui.notification_show(
                "Some numeric cells are invalid (non-numeric or blank). Fix them and retry.",
                type="error", duration=6,
            )
            return
        if len(df) != current_network().number_of_nodes():
            ui.notification_show(
                "Edited table row count does not match the network; not applied.",
                type="error", duration=6,
            )
            return
        if 'met.types' in df.columns:
            try:
                validate_met_types(df['met.types'].tolist(), context="edited species info")
            except ValueError as exc:
                ui.notification_show(f"Cannot apply edits: {exc}", type="error", duration=6)
                return
        try:
            _assert_aligned(current_network(), df)
        except ValueError as exc:
            ui.notification_show(f"Cannot apply edits: {exc}", type="error", duration=6)
            return
        current_species_info.set(df)
        ui.notification_show("Species info updated.", type="message", duration=4)
```
```python
# app.py:35-37, add validate_met_types to the flux_calculations import:
from flux_calculations import (
    fluxing,
    validate_flux_equilibrium
)
# with:
from flux_calculations import (
    fluxing,
    validate_flux_equilibrium,
    validate_met_types,
)
```
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS — new test green; 133+ passed.
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "fix: editor apply handler validates met.types and node/row alignment before applying"
```

---

### Task 8: Repair the stale pickle once instead of bypassing it on every start (`1.7`)

**Files:**
- Modify: `app.py:91-131` (`load_default_data`, extends Tasks 4-5's version) — two edits: re-save after a stale-cache fallthrough (Step 3) and a guard around the `pickle.load` at `app.py:107-108` (Step 4)
- Test: `test_app_structure.py` (two new tests)

**Interfaces:**
- Consumes: `app.DATA_DIR` (Task 1), `app.USING_EXAMPLE_NETWORK` (Task 5, untouched by this task), `load_data.save_to_pickle` (existing, unchanged signature `save_to_pickle(network, species_info, output_file="BalticFW.pkl")`)
- Produces: nothing further consumed this phase

- [ ] **Step 1: Write the failing test**
```python
# Add to test_app_structure.py
def test_load_default_data_resaves_pickle_after_stale_fallthrough(tmp_path, monkeypatch):
    """After the pickle is found stale/misaligned and load_default_data falls
    through to reconstruction, it must re-save the rebuilt pickle to DATA_DIR
    so the next start uses the fast path instead of rebuilding every time."""
    import pickle as pkl
    import networkx as nx
    import pandas as pd
    app = importlib.import_module("app")
    monkeypatch.setattr(app, 'DATA_DIR', tmp_path)

    # A stale pickle: valid schema, but info/node order do not match.
    stale_g = nx.DiGraph(); stale_g.add_node('Cod'); stale_g.add_node('Sprat')
    stale_info = pd.DataFrame({'species': ['Sprat', 'Cod'], 'fg': ['Fish', 'Fish'],
                               'meanB': [1.0, 2.0], 'bodymasses': [1.0, 2.0],
                               'met.types': ['Other', 'Other'], 'efficiencies': [0.5, 0.5]})
    with open(tmp_path / "BalticFW.pkl", 'wb') as f:
        pkl.dump({'network': stale_g, 'info': stale_info}, f)

    rebuilt_g = nx.DiGraph(); rebuilt_g.add_node('Cod'); rebuilt_g.add_node('Sprat')
    rebuilt_info = pd.DataFrame({'species': ['Cod', 'Sprat'], 'fg': ['Fish', 'Fish'],
                                 'meanB': [1.0, 2.0], 'bodymasses': [1.0, 2.0],
                                 'met.types': ['Other', 'Other'], 'efficiencies': [0.5, 0.5]})
    monkeypatch.setattr('load_data.load_baltic_data',
                         lambda base_dir=None: (rebuilt_g, rebuilt_info))

    G, info = app.load_default_data()
    assert list(G.nodes()) == info['species'].tolist() == ['Cod', 'Sprat']

    with open(tmp_path / "BalticFW.pkl", 'rb') as f:
        resaved = pkl.load(f)
    assert list(resaved['network'].nodes()) == resaved['info']['species'].tolist() == ['Cod', 'Sprat']
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_load_default_data_resaves_pickle_after_stale_fallthrough -v`
Expected: FAIL — `load_default_data` (`app.py:120-123` post-Task-4) reconstructs from `load_baltic_data` and returns, but never calls `save_to_pickle`; re-reading `tmp_path / "BalticFW.pkl"` after the call still yields the original stale `stale_info` (`['Sprat', 'Cod']`), so the final assertion fails.
- [ ] **Step 3: Re-save after a successful stale-fallthrough reconstruction**
```python
# app.py (as left by Tasks 4-5), replace only the `try:` success branch —
# the except branch below is shown for anchoring only and is NOT changed:
    # No pickle cache — reconstruct from the tracked GraphML/CSV/JSON sources.
    try:
        from load_data import load_baltic_data
        G, info = load_baltic_data(base_dir=DATA_DIR)
        _assert_aligned(G, info)
        return G, info
    except (FileNotFoundError, ImportError) as exc:
        global USING_EXAMPLE_NETWORK
        print(f"Baltic sources unavailable ({exc}); using example network.")
        USING_EXAMPLE_NETWORK = True
        G, info = create_example_network()
        _assert_aligned(G, info)
        return G, info
# with (only the try body changes; the except branch is untouched):
    # No pickle cache (or a stale one) — reconstruct from the tracked
    # GraphML/CSV/JSON sources.
    try:
        from load_data import load_baltic_data
        G, info = load_baltic_data(base_dir=DATA_DIR)
        _assert_aligned(G, info)
        # Repair a stale/absent cache once, so the next start takes the fast
        # pickle path instead of rebuilding on every run.
        # NOTE the handler is (OSError, ImportError), not just OSError: this
        # `from load_data import save_to_pickle` sits INSIDE the outer
        # `try: ... except (FileNotFoundError, ImportError)`. A narrower handler
        # would let an ImportError from this line escape to the outer clause and
        # silently drop the app onto the example network even though the Baltic
        # data loaded fine. Catching it here keeps the failure local to the cache.
        try:
            from load_data import save_to_pickle
            save_to_pickle(G, info, output_file=str(DATA_DIR / "BalticFW.pkl"))
        except (OSError, ImportError) as exc:
            print(f"Could not re-save BalticFW.pkl ({exc}); continuing without cache.")
        return G, info
    except (FileNotFoundError, ImportError) as exc:
        global USING_EXAMPLE_NETWORK
        print(f"Baltic sources unavailable ({exc}); using example network.")
        USING_EXAMPLE_NETWORK = True
        G, info = create_example_network()
        _assert_aligned(G, info)
        return G, info
```
- [ ] **Step 4: Guard the pickle read itself against a corrupt file**

Same defect class, same function, so it lands here rather than in its own task. `pickle.load` at
`app.py:107-108` and the dict-shape check just below it sit **outside** any `try`/`except`: a
truncated or otherwise corrupt `BalticFW.pkl` raises `UnpicklingError`/`EOFError` straight out of
`load_default_data()` — and, because that happens at module import, straight out of `import app`.
Nothing catches it: `load_default_data`'s only handler is the reconstruction `except
(FileNotFoundError, ImportError)`, which is further down and does not cover the pickle read. Wrap
the read + shape check so a corrupt cache falls through to reconstruction exactly like a stale one.

The corrupt-pickle test (add to `test_app_structure.py` alongside the Step 1 test):
```python
def test_load_default_data_survives_a_corrupt_pickle(tmp_path, monkeypatch):
    """A truncated/corrupt BalticFW.pkl must fall through to reconstruction,
    not raise UnpicklingError out of load_default_data() (and hence out of
    `import app`)."""
    import networkx as nx
    import pandas as pd
    app = importlib.import_module("app")
    monkeypatch.setattr(app, 'DATA_DIR', tmp_path)
    (tmp_path / "BalticFW.pkl").write_bytes(b"\x80\x04garbage-not-a-pickle")

    rebuilt_g = nx.DiGraph(); rebuilt_g.add_node('Cod'); rebuilt_g.add_node('Sprat')
    rebuilt_info = pd.DataFrame({'species': ['Cod', 'Sprat'], 'fg': ['Fish', 'Fish'],
                                 'meanB': [1.0, 2.0], 'bodymasses': [1.0, 2.0],
                                 'met.types': ['Other', 'Other'], 'efficiencies': [0.5, 0.5]})
    monkeypatch.setattr('load_data.load_baltic_data',
                         lambda base_dir=None: (rebuilt_g, rebuilt_info))

    G, info = app.load_default_data()
    assert list(G.nodes()) == info['species'].tolist() == ['Cod', 'Sprat']
```
Run it first to confirm RED:
`micromamba run -n shiny python -m pytest test_app_structure.py::test_load_default_data_survives_a_corrupt_pickle -v`
Expected: FAIL — `_pickle.UnpicklingError: pickle data was truncated` propagates out of
`app.load_default_data()`; nothing in the function catches it. (Verified: `pickle.loads(b"\x80\x04garbage-not-a-pickle")`
raises exactly that. `EOFError` is kept in the handler tuple below for other truncation points, and
`\xff\xff` — `invalid load key` — is an equally valid corrupt-file fixture if you prefer one.)

Then wrap the read (locate by the `with open(data_file, 'rb') as f:` text; `data_file` is
`DATA_DIR / "BalticFW.pkl"` as of Task 1):
```python
# app.py, replace:
    if data_file.exists():
        with open(data_file, 'rb') as f:
            data = pickle.load(f)
        if not (isinstance(data, dict) and {'network', 'info'} <= set(data.keys())):
            print("BalticFW.pkl missing 'network'/'info'; rebuilding from sources.")
        else:
            ...
# with (same body, now inside a guard that falls through on a corrupt file):
    if data_file.exists():
        try:
            with open(data_file, 'rb') as f:
                data = pickle.load(f)
            if not (isinstance(data, dict) and {'network', 'info'} <= set(data.keys())):
                print("BalticFW.pkl missing 'network'/'info'; rebuilding from sources.")
            else:
                ...   # unchanged: required-columns + alignment check, `return G_pkl, info_pkl`
        except (EOFError, pickle.UnpicklingError, AttributeError, ModuleNotFoundError) as exc:
            print(f"BalticFW.pkl is unreadable ({exc}); rebuilding from sources.")
        # fall through to reconstruction
```
(`AttributeError`/`ModuleNotFoundError` cover a pickle written by a since-renamed class or module —
the same "cache no longer matches the code" failure, surfaced by the unpickler rather than by the
shape check. Do NOT widen this to bare `Exception`: a `ValueError` from `_assert_aligned` further
down must still propagate, per Task 5.)
- [ ] **Step 5: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS — both new tests green; the 133-test baseline plus every test added so far (cumulative; do not expect an exact number), no new warnings (the real dev-machine `BalticFW.pkl` at repo root is untouched by these tests since they monkeypatch `DATA_DIR` to `tmp_path`).
- [ ] **Step 6: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "fix: re-save the rebuilt pickle after a stale-cache fallthrough; survive a corrupt pickle"
```

---

### Task 9: Phase 1 gate

- [ ] **Step 1: Full suite**
Run: `micromamba run -n shiny python -m pytest`
Expected: all tests pass — the 133-test baseline plus every test added in Tasks 1-8 and all preceding phases (cumulative; do not expect an exact number). Only the 3 known `network_analysis.py` UserWarnings (lines 122, 134, 186); any other warning is a defect.
- [ ] **Step 2: Import smoke test**
Run: `micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: prints `app OK` with no traceback (the tracked `BalticFW_network.graphml`/`BalticFW_species_info.csv` are aligned, so `_assert_aligned` does not raise on this machine; `USING_EXAMPLE_NETWORK` is `False`).
- [ ] **Step 3: Tag**
```bash
git tag audit3-phase1
```

---

# PHASE 2 — Flux and keystoneness presentation correctness

Baseline for this phase is `master` at `27086de` plus Phase 1 (data integrity/startup)
landed first. Two Phase-1 facts this phase's tasks build on:

- `app.py` gains `_assert_aligned(G, info)` and calls it before `current_species_info.set(df)`
  in `_apply_species_info_edits` (the editor apply handler).
- `_apply_species_info_edits` already validates `met.types` before applying edits.

Task 12 below inserts `flux_results.set(None)` into that same handler; land it after those
Phase-1 calls in source order (the ordering *between* Phase-1's checks and Phase-1's
`current_species_info.set(df)` is Phase 1's concern — this phase only needs
`flux_results.set(None)` to run before `current_species_info.set(df)`, wherever that call ends up).

---

### Task 10: Heatmap titles state the correct matrix orientation (`2.1`)

**Files:**
- Modify: `app.py:941-959` (`adjacency_heatmap`), `app.py:1185-1207` (`flux_heatmap`)
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: nothing new (uses existing `nx.to_numpy_array(G, nodelist=info['species'].tolist())` matrices already built at `app.py:941` and read from `flux_results()['flux_matrix']` at `app.py:1185`)
- Produces: nothing later tasks depend on

Both heatmaps build their matrix with `nodelist=info['species'].tolist()`, so
`nx.to_numpy_array(...)[i, j]` is the weight of the edge `species[i] -> species[j]`.
The flux effect's own comment at `app.py:1107` (`# Get adjacency matrix (rows=prey, cols=predators)`)
and `create_example_network`'s comment at `app.py:139` (`# Add some edges (prey -> predator direction)`)
both confirm edges run prey→predator, so row `i` is the prey and column `j` is the predator — but
the two heatmap titles currently say the opposite:
- `app.py:954`: `ax.set_title("Food Web Adjacency Matrix\n(Rows = Predators, Columns = Prey)")`
- `app.py:1202`: `ax.set_title("Energy Flux Matrix (log-transformed)\n(Rows = Predators, Columns = Prey)")`

Neither renderer sets `xlabel`/`ylabel` today (only `mti_heatmap` at `app.py:1333-1334` does, with
its own "Impacting/Impacted Species" text, which is a different matrix convention and is untouched).

- [ ] **Step 1: Write the failing test**
```python
def test_adjacency_and_flux_heatmap_titles_state_correct_matrix_orientation():
    """A10: nx.to_numpy_array(G, nodelist=species)[i,j] is the edge species[i]->species[j],
    and edges run prey->predator (app.py:1107's own comment, app.py:139's own comment), so
    row i is prey and column j is predator. Both heatmap titles currently say the opposite,
    and neither sets an explicit xlabel/ylabel."""
    src = APP.read_text(encoding="utf-8")
    assert "Food Web Adjacency Matrix\\n(Rows = Prey, Columns = Predators)" in src
    assert "Energy Flux Matrix (log-transformed)\\n(Rows = Prey, Columns = Predators)" in src
    assert "(Rows = Predators, Columns = Prey)" not in src
    assert src.count('ax.set_xlabel("Predator")') == 2
    assert src.count('ax.set_ylabel("Prey")') == 2
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_adjacency_and_flux_heatmap_titles_state_correct_matrix_orientation -v`
Expected: FAIL on the first assertion — the source contains `"(Rows = Predators, Columns = Prey)"` (inverted) at both `app.py:954` and `app.py:1202`, and neither `ax.set_xlabel("Predator")` nor `ax.set_ylabel("Prey")` appears anywhere in `app.py`.
- [ ] **Step 3: Fix both titles and add axis labels**
```python
        ax.set_title("Food Web Adjacency Matrix\n(Rows = Prey, Columns = Predators)")
        ax.set_xlabel("Predator")
        ax.set_ylabel("Prey")
        plt.xticks(rotation=90, ha='right')
```
(replacing `app.py:954`'s title line, inserted before the existing `plt.xticks(rotation=90, ha='right')` at `app.py:955`), and
```python
        ax.set_title("Energy Flux Matrix (log-transformed)\n(Rows = Prey, Columns = Predators)")
        ax.set_xlabel("Predator")
        ax.set_ylabel("Prey")
        plt.xticks(rotation=90, ha='right')
```
(replacing `app.py:1202`'s title line, inserted before the existing `plt.xticks(rotation=90, ha='right')` at `app.py:1203`).
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest -q`
Expected: PASS, suite green, no new warnings
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "fix: adjacency/flux heatmap titles match prey-row/predator-column matrix convention"
```

---

### Task 11: Surface the flux-equilibrium verdict to the user (`2.2`)

**Files:**
- Modify: `app.py:1140-1170` (flux effect + `flux_indicators`)
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: `validate_flux_equilibrium(...)` return dict (keys `balanced`, `max_imbalance`, per `flux_calculations.py:275-283,319-324`); `flux_results.set({...})` shape from `app.py:1148-1152` (unchanged: still has a `'validation'` key)
- Produces: nothing later tasks depend on

Today `validation = validate_flux_equilibrium(...)` is computed at `app.py:1140-1146` and stashed
in `flux_results.set({... 'validation': validation})` at `app.py:1151`, but nothing ever reads
`validation['balanced']` — grep confirms no occurrence of `balanced` outside `flux_calculations.py`
itself. `flux_indicators` (`app.py:1154-1170`) only prints lwC/lwG/lwV.

- [ ] **Step 1: Write the failing test**
```python
def test_flux_effect_warns_on_unbalanced_equilibrium():
    """A11: validate_flux_equilibrium's verdict must reach the user - a
    logger.warning plus a warning notification when validation['balanced'] is
    False - not sit unused in flux_results()['validation']."""
    src = APP.read_text(encoding="utf-8")
    assert "if not validation['balanced']:" in src, \
        "flux effect never branches on the equilibrium verdict"
    branch = src.split("if not validation['balanced']:", 1)[1][:400]
    assert "logger.warning(" in branch
    assert 'type="warning"' in branch


def test_flux_indicators_panel_reports_balance_status():
    """The flux indicators text panel must show the equilibrium verdict, not
    just the lwC/lwG/lwV numbers."""
    src = APP.read_text(encoding="utf-8")
    assert "Equilibrium:" in src
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_flux_effect_warns_on_unbalanced_equilibrium test_app_structure.py::test_flux_indicators_panel_reports_balance_status -v`
Expected: FAIL — `app.py` contains no `"if not validation['balanced']:"` and no `"Equilibrium:"` string anywhere (confirmed by grep of the current file); `validation['balanced']` is never read.
- [ ] **Step 3: Branch on the verdict in the flux effect, and show it in the panel**
```python
        # Validate equilibrium (optional, for debugging)
        validation = validate_flux_equilibrium(
            flux_matrix / FLUX_CONVERSION_FACTOR,  # Convert back to J/sec for validation
            losses,
            efficiencies,
            biomass,
            bioms_losses=bioms_losses_flag
        )
        if not validation['balanced']:
            logger.warning(
                "Flux equilibrium not balanced: max_imbalance=%.6g",
                validation['max_imbalance'],
            )
            ui.notification_show(
                f"Flux solution is not fully balanced (max imbalance "
                f"{validation['max_imbalance']:.4g}). Results may be approximate.",
                type="warning",
                duration=8,
            )

        flux_results.set({
            'flux_matrix': flux_matrix,
            'losses': losses,
            'validation': validation
        })
```
(this replaces `app.py:1139-1152` in place — same call, new branch inserted before the existing `flux_results.set({...})`)
```python
    def flux_indicators():
        if flux_results() is None:
            return "Click 'Calculate Fluxes' to compute energy fluxes."

        flux_matrix = flux_results()['flux_matrix']
        validation = flux_results()['validation']
        indicators = calculate_flux_indicators(flux_matrix, loop=False)
        balance_line = (
            "  Equilibrium: BALANCED" if validation['balanced']
            else f"  Equilibrium: NOT BALANCED (max imbalance {validation['max_imbalance']:.4g})"
        )

        return f"""
Flux-Based Indicators:

  Link-Weighted Connectance (lwC): {indicators['lwC']:.4f}
  Link-Weighted Generality (lwG): {indicators['lwG']:.4f}
  Link-Weighted Vulnerability (lwV): {indicators['lwV']:.4f}
{balance_line}
        """
```
(replacing `app.py:1157-1170`)
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest -q`
Expected: PASS, suite green, no new warnings
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "fix: surface flux-equilibrium verdict via warning notification and panel line"
```

---

### Task 12: Clear stale flux results before applying species-info edits (`2.3`)

**Files:**
- Modify: `app.py` inside `_apply_species_info_edits` (currently `app.py:1364-1391`; Phase 1 inserts `_assert_aligned` and a `met.types` check into this same function first, so the exact line numbers will have shifted by the time this task lands — locate the function by name, not by line)
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: `flux_results` (`reactive.Value`, `app.py:624`), `current_species_info` (`reactive.Value`, `app.py:623`) — both already in scope inside `_apply_species_info_edits`
- Produces: nothing later tasks depend on

Today `_apply_species_info_edits` (`app.py:1364-1391`) validates and coerces `df`, then calls
`current_species_info.set(df)` at `app.py:1390` and shows a success notification. It never touches
`flux_results`. If a user has already calculated fluxes (`flux_results()` holding a
`flux_matrix`/`labels` pair sized to the pre-edit species list) and then edits the table — e.g.
changes the row count, or reorders/renames species — `flux_heatmap` and `flux_network_plot` would
go on rendering the stale `flux_matrix` against the new `current_species_info()` labels.

- [ ] **Step 1: Write the failing test**
```python
def test_editor_apply_clears_flux_results_before_updating_info():
    """A12: flux_results must be cleared before current_species_info is updated, so a
    flux panel already rendered can't display a pre-edit flux matrix against
    post-edit species labels/order."""
    src = APP.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_apply_species_info_edits")
    body = ast.get_source_segment(src, fn)
    assert body is not None
    assert "flux_results.set(None)" in body, \
        "editor apply handler must clear flux_results"
    assert body.index("flux_results.set(None)") < body.index("current_species_info.set(df)"), \
        "flux_results must be cleared BEFORE current_species_info is updated"
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_editor_apply_clears_flux_results_before_updating_info -v`
Expected: FAIL — `_apply_species_info_edits`'s body contains no `"flux_results.set(None)"` today (confirmed by reading `app.py:1364-1391`), so the first assertion raises.
- [ ] **Step 3: Clear flux_results immediately before applying the edit**
```python
        flux_results.set(None)
        current_species_info.set(df)
        ui.notification_show("Species info updated.", type="message", duration=4)
```
(insert `flux_results.set(None)` as the statement directly before the existing `current_species_info.set(df)` line, wherever Phase 1's edits to this same function leave it)
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest -q`
Expected: PASS, suite green, no new warnings
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "fix: clear flux_results before applying species-info edits (A12)"
```

---

### Task 13: `calculate_keystoneness` exposes its quartile thresholds; app.py stops hardcoding them (`2.4`)

**Files:**
- Modify: `network_analysis.py:504-593` (`calculate_keystoneness`)
- Modify: `app.py:1222-1244` (`keystoneness_summary`), `app.py:1246-1292` (`keystoneness_scatter`)
- Test: `test_network_analysis.py`, `test_app_structure.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `calculate_keystoneness(...)` return value now also carries `.attrs['ks_hi']` (float, the `impact_quantile` cutoff on finite keystoneness) and `.attrs['bm_lo']` (float, the `biomass_quantile` cutoff on relative biomass) on the returned `DataFrame` — every existing caller in `app.py` (`app.py:636`) and `test_network_analysis.py` (12 call sites, e.g. `test_network_analysis.py:439,470,491,511,530,561,589,601,608,614,636,689`) keeps working unmodified because the return type is still a plain `DataFrame`; only readers who want the thresholds need touch `.attrs`.

`calculate_keystoneness` (`network_analysis.py:504-593`) computes `ks_hi`/`bm_lo` internally at
`network_analysis.py:568-569` and uses them only to build `keystone_status` — they are discarded
before `return results` at `network_analysis.py:593`. There is also an early-return branch at
`network_analysis.py:549-556` (`total_biomass <= 0`) that returns a `DataFrame` before `ks_hi`/`bm_lo`
are ever computed. `DataFrame.attrs` (a plain dict attached to the object, unaffected by the
`.sort_values(...).reset_index(drop=True)` at `network_analysis.py:591`) is the right vehicle: it
keeps every one of the ~12 existing call sites — all of which do `df = calculate_keystoneness(...)`
and treat the result as a single `DataFrame` — working with zero changes.

Downstream, `app.py`'s `keystoneness_scatter` (`app.py:1286-1287`) hardcodes
`ax.axhline(y=1, ...)` / `ax.axvline(x=0.05, ...)` instead of drawing the real thresholds, and
`keystoneness_summary` (`app.py:1232-1233`) reports `keystoneness_df.iloc[0]` (the single highest-KS
row after the `sort_values` at `network_analysis.py:591`) as `"Top Keystone Species"` even when that
row's `keystone_status` is `"Dominant"`, not `"Keystone"` (high impact, but biomass above `bm_lo`).

- [ ] **Step 1: Write the failing test**
```python
def test_keystoneness_returns_thresholds_as_attrs(simple_linear_chain):
    """2.4: calculate_keystoneness must expose the Q3(KS)/Q1(biomass) thresholds
    it computes internally so the scatter plot can draw the real cutoffs instead
    of hardcoded 1 and 0.05. Every existing caller unpacks the return value as a
    single DataFrame, so the thresholds ride as .attrs, not a second return value."""
    G, info = simple_linear_chain
    biomass = info['meanB'].values
    df = calculate_keystoneness(G, biomass)
    assert 'ks_hi' in df.attrs, df.attrs
    assert 'bm_lo' in df.attrs, df.attrs
    finite_ks = df['keystoneness'].to_numpy()
    finite_ks = finite_ks[np.isfinite(finite_ks)]
    q3 = float(np.quantile(finite_ks, 0.75))
    q1 = float(np.quantile(df['relative_biomass'].to_numpy(), 0.25))
    assert np.isclose(df.attrs['ks_hi'], q3)
    assert np.isclose(df.attrs['bm_lo'], q1)


def test_keystoneness_zero_biomass_attrs_are_present_and_nan():
    """The total_biomass<=0 early-return path must still set ks_hi/bm_lo (as
    NaN) so a caller reading df.attrs unconditionally doesn't KeyError."""
    G = nx.DiGraph(); G.add_edges_from([(0, 1), (0, 2), (2, 3)])
    df = calculate_keystoneness(G, np.array([0.0, 0.0, 0.0, 0.0]))
    assert 'ks_hi' in df.attrs and 'bm_lo' in df.attrs
    assert np.isnan(df.attrs['ks_hi'])
    assert np.isnan(df.attrs['bm_lo'])


def test_keystoneness_scatter_uses_computed_thresholds_not_hardcoded():
    """A13: draw the real Q3(KS)/Q1(biomass) cutoffs from calculate_keystoneness's
    df.attrs, not the hardcoded axhline(y=1)/axvline(x=0.05)."""
    src = APP.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "keystoneness_scatter")
    body = ast.get_source_segment(src, fn)
    assert "attrs['ks_hi']" in body or 'attrs["ks_hi"]' in body
    assert "attrs['bm_lo']" in body or 'attrs["bm_lo"]' in body
    assert "axhline(y=1," not in body
    assert "axvline(x=0.05," not in body


def test_keystoneness_summary_only_labels_true_keystone_species():
    """A13: 'Top Keystone Species' must come from a status=='Keystone' row, not
    just row 0 (which can be 'Dominant' - high impact but not low biomass)."""
    src = APP.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "keystoneness_summary")
    body = ast.get_source_segment(src, fn)
    assert "keystone_status'] == 'Keystone'" in body or 'keystone_status"] == "Keystone"' in body
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_keystoneness_returns_thresholds_as_attrs test_network_analysis.py::test_keystoneness_zero_biomass_attrs_are_present_and_nan test_app_structure.py::test_keystoneness_scatter_uses_computed_thresholds_not_hardcoded test_app_structure.py::test_keystoneness_summary_only_labels_true_keystone_species -v`
Expected: FAIL — `calculate_keystoneness` never assigns to `results.attrs` today (`network_analysis.py:582-593`), so `df.attrs` is `{}` and both `network_analysis.py` tests fail on `assert 'ks_hi' in df.attrs`; `keystoneness_scatter`'s body still contains `axhline(y=1,`/`axvline(x=0.05,` with no `attrs[` reference, and `keystoneness_summary`'s body contains no `keystone_status'] == 'Keystone'` comparison, so both `app.py` tests fail too.
- [ ] **Step 3a: Attach thresholds as DataFrame.attrs in calculate_keystoneness**
Replace the early-return branch at `network_analysis.py:549-556`:
```python
    if total_biomass <= 0:
        undefined = pd.DataFrame({
            'species': list(G.nodes()),
            'overall_effect': overall_effect,
            'relative_biomass': relative_biomass,
            'keystoneness': np.full(len(overall_effect), np.nan),
            'keystone_status': ['Undefined'] * len(overall_effect),
        })
        undefined.attrs['ks_hi'] = np.nan
        undefined.attrs['bm_lo'] = np.nan
        return undefined
```
and, replacing `network_analysis.py:581-593`:
```python
    # Create results dataframe
    results = pd.DataFrame({
        'species': list(G.nodes()),
        'overall_effect': overall_effect,
        'relative_biomass': relative_biomass,
        'keystoneness': keystoneness,
        'keystone_status': keystone_status
    })

    # Sort by keystoneness (descending)
    results = results.sort_values('keystoneness', ascending=False).reset_index(drop=True)
    # DataFrame.attrs survives sort_values/reset_index and every existing caller
    # still treats the return value as a plain DataFrame.
    results.attrs['ks_hi'] = float(ks_hi)
    results.attrs['bm_lo'] = float(bm_lo)

    return results
```
- [ ] **Step 3b: Use the real thresholds in keystoneness_scatter**
```python
        ax.axhline(y=keystoneness_df.attrs['ks_hi'], color='k', linestyle='--', alpha=0.3)
        ax.axvline(x=keystoneness_df.attrs['bm_lo'], color='k', linestyle='--', alpha=0.3)
```
(replacing `app.py:1286-1287`)
- [ ] **Step 3c: Report the top true-Keystone species in keystoneness_summary**
```python
    def keystoneness_summary():
        keystoneness_df = keystoneness_cached()

        n_keystone = (keystoneness_df['keystone_status'] == 'Keystone').sum()
        n_dominant = (keystoneness_df['keystone_status'] == 'Dominant').sum()
        n_rare = (keystoneness_df['keystone_status'] == 'Rare').sum()

        keystone_only = keystoneness_df[keystoneness_df['keystone_status'] == 'Keystone']
        if len(keystone_only) > 0:
            top_label = "Top Keystone Species"
            top_species = keystone_only.iloc[0]['species']
            top_ks = keystone_only.iloc[0]['keystoneness']
        else:
            top_label = "Highest Keystoneness Index (no Keystone-status species)"
            top_species = keystoneness_df.iloc[0]['species']
            top_ks = keystoneness_df.iloc[0]['keystoneness']

        return f"""
Keystoneness Analysis Summary:

  Keystone Species: {n_keystone}
  Dominant Species: {n_dominant}
  Rare Species: {n_rare}

  {top_label}: {top_species}
  Keystoneness Index: {top_ks:.4f}
        """
```
(replacing `app.py:1225-1244`; `keystoneness_df` is still sorted descending by `network_analysis.py:591`, so `keystone_only.iloc[0]` is the highest-KS row among `Keystone`-status rows)
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest -q`
Expected: PASS, suite green, no new warnings
- [ ] **Step 5: Commit**
```bash
git add network_analysis.py app.py test_network_analysis.py test_app_structure.py
git commit -m "fix: calculate_keystoneness exposes Q3/Q1 thresholds via attrs; scatter/summary use them (A13)"
```

---

### Task 14: Downloaded network HTML is self-contained (`2.5`)

**Files:**
- Modify: `app.py:17` (imports), `app.py:85` (new helper), `app.py:926-932` (`download_network`)
- Test: `test_network_viz_render.py`

**Interfaces:**
- Consumes: `pyvis.network.Network` instances as already returned by `_build_network(...)` (`app.py:644-665`, itself calling `create_topology_network`/`create_flux_network` from `network_viz.py`, both of which construct `Network(...)` without a `cdn_resources=` argument, so `net.cdn_resources` defaults to `"local"` per `pyvis/network.py:72` — confirmed also by the existing `test_network_viz_render.py:118-128` (`test_builders_use_cdn_local_so_render_network_inlines_assets`))
- Produces: `_network_download_html(net) -> str`, a module-level function in `app.py` that later tasks/tests may reuse for any other download path

`download_network` (`app.py:926-932`) currently does `yield net.generate_html()` directly. With
`net.cdn_resources == "local"` (`pyvis/network.py:36` `CDN_LOCAL = "local"`), `generate_html()`
(`pyvis/network.py:934-957`) references `src="lib/vis-9.1.2/vis-network.min.js"` etc — paths that
only resolve relative to the running app's own template directory, not a file the user saved to
disk and reopened. `pyvis/shiny/wrapper.py:254-266` (`render_network`, the function `app.py`
already imports at `app.py:45` and uses for on-screen rendering) solves exactly this for the iframe
path: it deep-copies the network and flips `cdn_resources` to `CDN_INLINE`
(`pyvis/network.py:37` `CDN_INLINE = "in_line"`) before calling `generate_html()`, so the emitted
HTML embeds the JS/CSS instead of referencing `lib/`. `download_network` needs the same treatment,
factored into its own helper so it is unit-testable without a running Shiny session.

- [ ] **Step 1: Write the failing test**
```python
def test_download_network_html_has_no_local_asset_references(simple_test_network):
    """crit1: the downloaded network HTML must be self-contained - no
    src="lib/..." reference a saved-and-reopened file's browser can't resolve.
    Mirrors pyvis.shiny.wrapper.render_network's CDN_LOCAL -> CDN_INLINE
    deep-copy override (pyvis/shiny/wrapper.py:260-266), applied to the
    generate_html() path used for downloads instead of the iframe path."""
    import importlib
    app = importlib.import_module("app")
    G, species, groups, biomass, colors = simple_test_network
    net = create_topology_network(G, species, groups, biomass, colors)
    assert net.cdn_resources == CDN_LOCAL  # precondition: builder still defaults to local

    html = app._network_download_html(net)

    assert 'src="lib/' not in html, "download HTML references local lib/ assets"
    assert net.cdn_resources == CDN_LOCAL, \
        "helper must not mutate the caller's network in place"
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py::test_download_network_html_has_no_local_asset_references -v`
Expected: FAIL — `AttributeError: module 'app' has no attribute '_network_download_html'` (no such function exists in `app.py` today; `download_network` at `app.py:926-932` calls `net.generate_html()` directly with no CDN override).
- [ ] **Step 3: Add the helper and use it from download_network**
```python
import pickle
import time
import functools
import os
import copy
import shinyswatch
```
(add `import copy` to the import block at `app.py:17-21`)
```python
def _network_download_html(net):
    """Render a pyvis Network to a standalone HTML string for file download.
    Mirrors pyvis.shiny.wrapper.render_network's CDN_LOCAL -> CDN_INLINE
    deep-copy override (used there for the iframe srcdoc path): a network
    built with cdn_resources='local' (network_viz.py's default) embeds
    src="lib/..." references that only resolve inside this app's own
    template directory, so a saved-and-reopened file would render blank.
    Deep-copies before mutating cdn_resources to avoid altering the caller's
    network (which _build_network's caches may still be holding)."""
    from pyvis.network import CDN_LOCAL, CDN_INLINE
    if net.cdn_resources == CDN_LOCAL:
        net_copy = copy.deepcopy(net)
        net_copy.cdn_resources = CDN_INLINE
        return net_copy.generate_html()
    return net.generate_html()
```
(insert after `safe_render`'s definition, `app.py:72-84`)
```python
    @render.download(filename="econetool_network.html")
    def download_network():
        if input.network_type() == "Flux-Weighted" and flux_results() is not None:
            net = _build_network("flux")
        else:
            net = _build_network("topology")
        yield _network_download_html(net)
```
(replacing `app.py:926-932`)
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest -q`
Expected: PASS, suite green, no new warnings
- [ ] **Step 5: Commit**
```bash
git add app.py test_network_viz_render.py
git commit -m "fix: downloaded network HTML inlines CDN resources instead of referencing lib/ (crit1)"
```

---

### Task 15: Phase 2 gate

- [ ] **Step 1: Full suite**
Run: `micromamba run -n shiny python -m pytest -q`
Expected: all tests pass — the 133-test baseline plus every test added in Tasks 10-14 and all preceding phases (cumulative; do not expect an exact number). Only the 3 known `network_analysis.py` UserWarnings (lines 122, 134, 186); any other warning is a defect.
- [ ] **Step 2: Import check**
Run: `micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: prints `app OK` with no exception.
- [ ] **Step 3: Tag**
```bash
git tag audit3-phase2
```

---

# PHASE 3 — Test integrity

Every task below repairs a test that **cannot fail on the bug it claims to guard** (spec Decision 8). Because the production code is already correct in each case, the RED step is not "run the new test against today's code and watch it fail" — it is one of:

- **(A)** show the CURRENT (weak) test still PASSES against a deliberately broken/simulated production behavior, described as an exact temporary edit (or a synthetic string standing in for `generate_html()`'s output) that is reverted before Step 3, and show the NEW test FAILS against that same broken behavior; or
- **(B)** show the NEW assertion genuinely FAILS on current code (used only where the current code truly has not been exercised by any test — e.g. missing dependency declarations, or a code path no fixture ever drives).

Each task states which of (A) or (B) applies.

---

### Task 16: Declare pytest/hypothesis dev dependencies (`3.1`)

**Files:**
- Modify: `environment.yml:36` (insert after), `requirements.txt:30` (insert after)
- Test: `test_app_structure.py` (new test function)

**Interfaces:**
- Consumes: nothing
- Produces: nothing (manifest-only; no importable symbol)

- [ ] **Step 1: Write the failing test**
```python
def test_dev_dependencies_declared_in_manifests():
    """pytest and hypothesis (test_network_analysis.py uses @given/@settings
    from hypothesis at its top) must be declared in BOTH environment.yml and
    requirements.txt, or a fresh clone following either file cannot run the
    test suite it ships."""
    root = pathlib.Path(__file__).parent
    env_text = (root / "environment.yml").read_text(encoding="utf-8")
    req_text = (root / "requirements.txt").read_text(encoding="utf-8")
    for dep in ("pytest", "hypothesis"):
        assert dep in env_text, f"{dep} missing from environment.yml"
        assert dep in req_text, f"{dep} missing from requirements.txt"
```
Add this to `test_app_structure.py` (it already imports `pathlib` at line 3).

- [ ] **Step 2: Run to confirm RED (mode B — genuinely fails today)**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_dev_dependencies_declared_in_manifests -v`
Expected: FAIL — `requirements.txt` (30 lines, read in full) contains neither `pytest` nor `hypothesis`; `environment.yml` (39 lines, read in full) contains `pytest>=8.0` at line 36 but no `hypothesis` anywhere. The assertion for `hypothesis in env_text` and both `requirements.txt` checks fail.

- [ ] **Step 3: Declare the dependencies**
In `environment.yml`, after line 36 (`  - pytest>=8.0`), insert:
```yaml
  - pytest>=8.0
  - hypothesis>=6.100.0
```
(replacing just the single existing `- pytest>=8.0` line with these two lines, immediately before the existing `  - pip` at line 37).

In `requirements.txt`, after line 30 (`plotly>=5.14.0`, end of file), append:
```

# Dev / test
pytest>=8.0
hypothesis>=6.100.0
```

- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_dev_dependencies_declared_in_manifests -v` then `micromamba run -n shiny python -m pytest`
Expected: PASS — this task adds one new test; the suite total is the 133-test baseline plus every test added so far (Phases 1-2 have already added several; cumulative — do not expect an exact number). Only the 3 known `network_analysis.py` UserWarnings (lines 122, 134, 186); any other warning is a defect.

- [ ] **Step 5: Commit**
```bash
git add environment.yml requirements.txt test_app_structure.py
git commit -m "test: declare pytest/hypothesis dev deps in environment.yml and requirements.txt"
```

---

### Task 17: Pin the zero-biomass flux contract (`3.2`)

**Files:**
- Modify: `test_flux_calculations.py:433-445`
- Test: same file

**Interfaces:**
- Consumes: `fluxing(mat, biomasses, losses, efficiencies, ef_level="prey")` (`flux_calculations.py:17`)
- Produces: nothing

The current test (verified in full):
```python
def test_fluxing_with_zero_biomass():
    """Test handling of zero biomass values"""
    mat = np.array([[0, 1], [0, 0]])
    biomasses = np.array([0.0, 10.0])  # First species has zero biomass
    losses = np.array([0.1, 0.5])
    efficiencies = np.array([0.5, 0.6])

    # Should handle gracefully (may produce zeros or special values)
    flux_matrix = fluxing(mat, biomasses, losses, efficiencies, ef_level="prey")

    assert flux_matrix.shape == mat.shape
    # Allow some flexibility in how zero biomass is handled
    assert np.all(np.isfinite(flux_matrix) | np.isnan(flux_matrix))
```
`np.isfinite(x) | np.isnan(x)` is `True` for every float `x` there is (every real number is either finite or NaN, and `inf`/`-inf` are the only exceptions, which this scenario cannot even produce). The assertion cannot fail for ANY output the function could return — it is not testing zero-biomass handling at all.

Verified actual behavior (ran `fluxing` with these exact inputs): with `bioms_prefs=True` (default), species 0's zero biomass zeroes out row 0 of the preference matrix `W`; since species 0 is also basal (no prey of its own), `W` collapses to all-zero, `D_e` is grounded to 1, and the solved `F = [0.0, 5.0]` — but `flux_matrix = W * F[newaxis,:]` is then exactly `[[0, 0], [0, 0]]` because `W` is all-zero. So the pinned contract is: **the flux matrix is exactly zero everywhere** (no energy can flow from a zero-biomass prey).

- [ ] **Step 1: Write the failing test**
```python
def test_fluxing_with_zero_biomass():
    """A consumer whose only prey has zero biomass gets a preference column
    that sums to zero (bioms_prefs weights W by prey biomass), so no energy
    can flow from that prey. The pinned contract is an EXACTLY zero flux
    matrix -- not merely 'finite or NaN', which any bug that returns a
    constant NaN matrix, or a constant zero matrix from an unrelated cause,
    would also satisfy."""
    mat = np.array([[0, 1], [0, 0]])
    biomasses = np.array([0.0, 10.0])  # First species (prey) has zero biomass
    losses = np.array([0.1, 0.5])
    efficiencies = np.array([0.5, 0.6])

    flux_matrix = fluxing(mat, biomasses, losses, efficiencies, ef_level="prey")

    assert flux_matrix.shape == mat.shape
    np.testing.assert_allclose(flux_matrix, np.zeros((2, 2)))
```

- [ ] **Step 2: Run to confirm RED (mode A — old test is vacuous, revert after)**
Temporarily edit `flux_calculations.py`, inside `fluxing`, replacing the `return flux_matrix` line (`:204`) with:
```python
    return np.full_like(flux_matrix, np.nan)  # TEMPORARY: simulate a broken solver
```
Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py::test_fluxing_with_zero_biomass -v` with the **OLD** test body (from Step 1's "current test" quote above, i.e. before applying this task's Step 1 edit).
Expected: PASSES — `np.isfinite(nan) | np.isnan(nan)` is `True`, so the old assertion accepts an all-NaN "solved" matrix without complaint.
Now apply this task's Step 1 new test body and re-run the same command.
Expected: FAILS — `assert_allclose(all_nan, zeros)` raises, proving the new assertion catches what the old one missed.
Revert the temporary `flux_calculations.py` edit (`git checkout -- flux_calculations.py` or restore the original `return flux_matrix` line) before continuing.

- [ ] **Step 3: (no production change — test-only task)**
The Step 1 test body above is the final content; no source edit is needed since `fluxing` already produces the correct all-zero matrix.

- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_flux_calculations.py::test_fluxing_with_zero_biomass -v` then `micromamba run -n shiny python -m pytest`
Expected: PASS; suite green, no new warnings.

- [ ] **Step 5: Commit**
```bash
git add test_flux_calculations.py
git commit -m "test: pin exact-zero flux contract for zero-biomass prey"
```

---

### Task 18: Independent reference ranking for keystoneness (`3.3`)

**Files:**
- Modify: `test_network_analysis.py:676-692`
- Test: same file

**Interfaces:**
- Consumes: `calculate_keystoneness(G, biomass)` (`network_analysis.py:504`), `calculate_mti(G)` (used internally and importable from `network_analysis`)
- Produces: nothing

Current test (verified in full, `network_analysis.py:504-593` read alongside it):
```python
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
`calculate_keystoneness` (`network_analysis.py:591`) ends with `results.sort_values('keystoneness', ascending=False)`. The test reads back that SAME column from that SAME sorted frame and checks it is monotonically non-increasing — a property `pandas.sort_values` guarantees unconditionally. No production bug (wrong `overall_effect`, a species/value misalignment, a wrong log base) can ever make this assertion fail, because it never checks that the `species` column lines up with the values that were actually computed for each species — only that whatever ended up in the `keystoneness` column is sorted.

- [ ] **Step 1: Write the failing test**
```python
@settings(max_examples=40, deadline=None)
@given(
    n=st.integers(min_value=3, max_value=6),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_keystoneness_ranking_invariant_to_log_base(n, seed):
    """The keystoneness ranking must match an INDEPENDENTLY computed reference
    ranking (Libralato KS = log10(overall_effect * (1 - relative_biomass)),
    descending) with species identity intact -- not merely be internally
    self-consistent with whatever order sort_values produced."""
    from network_analysis import calculate_mti
    rng = np.random.default_rng(seed)
    A = np.triu(rng.integers(0, 2, size=(n, n)), k=1)
    G = nx.from_numpy_array(A, create_using=nx.DiGraph)
    biomass = rng.uniform(1.0, 100.0, size=n)

    MTI = calculate_mti(G)
    overall_effect = np.sqrt(np.sum(MTI ** 2, axis=0))
    relative_biomass = biomass / np.sum(biomass)
    with np.errstate(divide="ignore", invalid="ignore"):
        ref_ks = np.log10(overall_effect * (1.0 - relative_biomass))
    ref_ks[~np.isfinite(ref_ks)] = np.nan
    nodes = list(G.nodes())
    finite_idx = [i for i in range(n) if np.isfinite(ref_ks[i])]
    expected_order = [nodes[i] for i in sorted(finite_idx, key=lambda i: -ref_ks[i])]

    df = calculate_keystoneness(G, biomass)
    finite_df = df[df['keystoneness'].notna()]
    assert list(finite_df['species']) == expected_order, \
        (list(finite_df['species']), expected_order)
```

- [ ] **Step 2: Run to confirm RED (mode A — old test is vacuous, revert after)**
Temporarily edit `network_analysis.py`, right after the sort at line 591 (`results = results.sort_values('keystoneness', ascending=False).reset_index(drop=True)`) and before `return results` (line 593), insert:
```python
    results['species'] = results['species'].sample(frac=1, random_state=0).reset_index(drop=True)  # TEMPORARY: shuffle species labels only
```
Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_keystoneness_ranking_invariant_to_log_base -v` with the **OLD** test body (quoted above).
Expected: PASSES — the shuffle only touches the `species` column; the `keystoneness` column itself is untouched and still sorted descending, so `np.diff(finite) <= 1e-9` still holds.
Now swap in this task's Step 1 new test body and re-run.
Expected: FAILS — `expected_order` (computed independently, keyed to the original node identities) no longer matches `finite_df['species']` (now shuffled), so the list-equality assertion raises.
Revert the temporary `network_analysis.py` edit before continuing.

- [ ] **Step 3: (no production change — test-only task)**
The Step 1 test body above is final; `calculate_keystoneness` already produces correctly-aligned output.

- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_keystoneness_ranking_invariant_to_log_base -v` then `micromamba run -n shiny python -m pytest`
Expected: PASS (all 40 hypothesis examples); suite green.

- [ ] **Step 5: Commit**
```bash
git add test_network_analysis.py
git commit -m "test: keystoneness ranking test checks species identity, not just sortedness"
```

---

### Task 19: Escaped-form-present-AND-raw-absent for viz special chars (`3.4`)

**Files:**
- Modify: `test_network_viz_render.py:74-115`
- Test: same file

**Interfaces:**
- Consumes: `create_topology_network(G, species, groups, biomass, colors)` (`network_viz.py`), `.generate_html()` (pyvis `Network`)
- Produces: nothing

Current tests (verified in full):
```python
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
    assert '\\"trutta\\"' in html or '&quot;trutta&quot;' in html or '\\u0022trutta\\u0022' in html, \
        "double-quote in species name was dropped or wrongly escaped"
    assert 'Mytilus &amp; Co.' in html or 'Mytilus & Co.' in html or 'Mytilus \\u0026 Co.' in html, \
        "ampersand in species name was dropped"
    assert '&lt;i&gt;' in html or '<i>' in html or '\\u003ci\\u003eitalicus\\u003c/i\\u003e' in html, \
        "angle bracket in species name was dropped"
    assert '&amp;amp;' not in html, "double-escaped ampersand"
```
The bold-marker test only asserts the double-escaped form is ABSENT; it never asserts the tag is present in ANY form, so a regression that silently strips `<b>...</b>` entirely still passes.

The special-chars test is vacuous in a narrower but still real way. Its three-way `or` has one branch per form, and **two of the three accept the completely RAW, unescaped substring**:
- ampersand: `'Mytilus &amp; Co.' in html or 'Mytilus & Co.' in html or ...` — the middle branch is the raw form.
- angle brackets: `'&lt;i&gt;' in html or '<i>' in html or ...` — the middle branch is the raw form.
- double quote: `'\\"trutta\\"' or '&quot;trutta&quot;' or '\\u0022trutta\\u0022'` — **no** raw branch; this one would in fact catch a total-escaping regression.

So a regression that stops escaping entirely (a real security/rendering bug: raw `&` and `<i>` breaking out of the JSON string) is treated as success by the ampersand and angle-bracket assertions, and only the quote assertion would notice.

Verified actual `generate_html()` output for both fixtures (ran `create_topology_network(...).generate_html()` directly against this env's pyvis fork). The forms that ARE present, written as they appear in a Python source literal, are the JSON-unicode-escaped ones — exactly the forms Step 1 asserts:
- `'\\u003cb\\u003eSprat\\u003c/b\\u003e'` (bold marker)
- `'\\"trutta\\"'` (double-quote)
- `'Mytilus \\u0026 Co.'` (ampersand)
- `'\\u003ci\\u003eitalicus\\u003c/i\\u003e'` (angle brackets)

And the forms that are ABSENT — every raw form and every HTML-entity form — are: `'<b>Sprat</b>'`, `'&amp;lt;b&amp;gt;'`, `'&lt;b&gt;'`, `'"trutta"'`, `'&quot;trutta&quot;'`, `'\\u0022trutta\\u0022'`, `'Mytilus & Co.'`, `'Mytilus &amp; Co.'`, `'<i>italicus</i>'`, `'&lt;i&gt;'`, `'&amp;amp;'`. Every one of Step 1's `in`/`not in` assertions therefore holds against today's output; the point of this task is that the OLD assertions also hold against output where escaping is broken.

- [ ] **Step 1: Write the failing test**
```python
def test_topology_tooltip_bold_marker_round_trips(simple_test_network):
    """The <b>...</b> wrapper around species names in tooltips must reach
    the browser in a valid, single-escaped form -- not silently dropped
    (absence of the raw form alone proves nothing) and not double-escaped."""
    G, species, groups, biomass, colors = simple_test_network
    net = create_topology_network(G, species, groups, biomass, colors)
    html = net.generate_html()
    assert '\\u003cb\\u003eSprat\\u003c/b\\u003e' in html, \
        "tooltip bold markup for Sprat missing in escaped form"
    assert '<b>Sprat</b>' not in html, "tooltip bold markup leaked unescaped"
    assert '&amp;lt;b&amp;gt;' not in html, "tooltip bold markup got double-escaped — Jinja autoescape regression"


def test_topology_html_safe_for_special_chars():
    """Special characters in species names must round-trip to exactly one
    valid escaped form: present in that form AND absent in every other
    (raw or HTML-entity) form."""
    G = nx.DiGraph()
    G.add_nodes_from(['X', 'Y', 'Z'])
    G.add_edges_from([('X', 'Y'), ('Y', 'Z')])
    species = ['Salmo "trutta"', 'Mytilus & Co.', 'Genus <i>italicus</i>']
    groups = ['fish', 'shellfish', 'other']
    biomass = np.array([10.0, 5.0, 2.0])
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
    net = create_topology_network(G, species, groups, biomass, colors)
    html = net.generate_html()

    assert '\\"trutta\\"' in html, "double-quote in species name not escaped"
    assert '"trutta"' not in html, "double-quote in species name leaked raw"

    assert 'Mytilus \\u0026 Co.' in html, "ampersand in species name not escaped"
    assert 'Mytilus & Co.' not in html, "ampersand in species name leaked raw"
    assert 'Mytilus &amp; Co.' not in html, "ampersand escaped as HTML entity, not JSON unicode"

    assert '\\u003ci\\u003eitalicus\\u003c/i\\u003e' in html, "angle brackets in species name not escaped"
    assert '<i>italicus</i>' not in html, "angle brackets in species name leaked raw"
    assert '&lt;i&gt;' not in html, "angle brackets escaped as HTML entity, not JSON unicode"

    assert '&amp;amp;' not in html, "double-escaped ampersand"
```

- [ ] **Step 2: Run to confirm RED (mode A — old tests are vacuous; pure-Python demonstration, no file edit needed)**
No production or test file needs to be touched for this demonstration — construct each broken output as a literal Python string standing in for a real regression, and check the OLD and NEW assertions against it directly. Both regressions must be demonstrated, one per vacuous test.
Write this to a scratch file with the Write tool (never a heredoc) and run it with
`micromamba run -n shiny python <scratch>`. It needs TWO broken outputs, one per vacuous test.

**(A) `test_topology_html_safe_for_special_chars` — "escaping silently stopped working".**
```python
# A regression that emits species names raw, with no JSON escaping at all.
broken_raw = 'label": "Mytilus & Co.", "title": "Genus <i>italicus</i>", "x": "Salmo \\"trutta\\""'

# OLD assertions (three-way `or`) — the ampersand and angle-bracket ones PASS
# purely on their raw branch:
assert 'Mytilus &amp; Co.' in broken_raw or 'Mytilus & Co.' in broken_raw or 'Mytilus \\u0026 Co.' in broken_raw   # True (raw branch)
assert '&lt;i&gt;' in broken_raw or '<i>' in broken_raw or '\\u003ci\\u003eitalicus\\u003c/i\\u003e' in broken_raw  # True (raw branch)
print("OLD special-chars assertions accepted fully-unescaped output -> vacuous")

# NEW assertions against the same string — every one of them is False, i.e. would raise:
assert ('Mytilus \\u0026 Co.' in broken_raw) is False          # "ampersand not escaped"
assert ('Mytilus & Co.' not in broken_raw) is False            # "ampersand leaked raw"
assert ('\\u003ci\\u003eitalicus\\u003c/i\\u003e' in broken_raw) is False   # "angle brackets not escaped"
assert ('<i>italicus</i>' not in broken_raw) is False          # "angle brackets leaked raw"
print("NEW special-chars assertions all FAIL on that output -> not vacuous")
```

**(B) `test_topology_tooltip_bold_marker_round_trips` — "the `<b>` wrapper was silently stripped".**
This is the mode-A RED the bold-marker test needs, and it is a *different* regression from (A): here
escaping still works, but the `<b>…</b>` wrapper is gone from the tooltip entirely.
```python
# The wrapper is absent — no <b>, no \\u003cb\\u003e, no &lt;b&gt;, nothing.
broken_html_stripped = '"title": "Sprat\\u003cbr\\u003eBiomass: 10.0", "label": "Sprat"'

# OLD bold-marker assertion — the ONLY thing it checks:
assert '&amp;lt;b&amp;gt;' not in broken_html_stripped   # True -> OLD TEST PASSES
print("OLD bold-marker assertion PASSES on output with the <b> wrapper stripped -> vacuous")

# NEW bold-marker assertions against the same string:
assert '\\u003cb\\u003eSprat\\u003c/b\\u003e' not in broken_html_stripped   # the NEW `in` assertion FAILS
print("NEW bold-marker assertion FAILS on that output -> not vacuous")
```
Expected output: all four `print` lines, no `AssertionError`. This is the proof that both old tests
pass in exactly the state they claim to guard against, while both new tests fail there.

- [ ] **Step 3: (no production change — test-only task)**
The Step 1 test bodies above are final; `create_topology_network`/`generate_html()` already produce the correct escaped forms (verified above).

- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py -v` then `micromamba run -n shiny python -m pytest`
Expected: PASS; suite green.

- [ ] **Step 5: Commit**
```bash
git add test_network_viz_render.py
git commit -m "test: pin exact escaped form and assert raw form absent in viz special-char round-trip"
```

---

### Task 20: Actually invoke the stacked safe_render/render.text renderer (`3.5`)

**Files:**
- Modify: `test_app_structure.py:76-90`
- Test: same file

**Interfaces:**
- Consumes: `app.safe_render(kind)` (`app.py:72-84`), `shiny.render.text`
- Produces: nothing

Current test (verified in full):
```python
def test_safe_render_below_render_text_order():
    """@safe_render must work BELOW @render.text (render wraps the safe wrapper)."""
    from shiny import render
    app = importlib.import_module("app")
    @render.text
    @app.safe_render("text")
    def boom():
        raise RuntimeError("x")
    # Stacking @render.text above @safe_render must not raise at decoration time.
    # Invoking the safe-wrapped raw function directly must swallow the error and
    # return the uniform marker rather than propagating the RuntimeError.
    @app.safe_render("text")
    def raw_boom():
        raise RuntimeError("x")
    assert "could not be computed" in raw_boom().lower()
```
The stacked `boom` (the actual subject of the docstring's claim) is decorated and then never called at all. The assertion instead calls a SEPARATE, non-stacked `raw_boom` — which duplicates `test_safe_render_text_returns_marker_and_logs` (`test_app_structure.py:37-46`) and proves nothing about decorator ORDER, since `raw_boom` never has `@render.text` applied to it.

Verified (ran directly): `shiny.render.text` produces a `Renderer` object whose `.fn` attribute is an `AsyncValueFn`. When decorators are stacked in the CORRECT order (`@render.text` outermost, `@app.safe_render("text")` innermost), `asyncio.run(boom.fn())` invokes the safe-wrapped function and correctly returns `"This panel could not be computed — see logs."`. When the order is reversed (`@app.safe_render("text")` outermost, `@render.text` innermost), `functools.wraps` inside `safe_render` copies the inner `Renderer`'s `__dict__` — including its own `.fn` — onto the returned plain wrapper function, so the outer object's `.fn` ends up pointing at the ORIGINAL unprotected `boom`, bypassing `safe_render`'s `try/except` entirely: `asyncio.run(boom.fn())` then raises the raw `RuntimeError` uncaught.

- [ ] **Step 1: Write the failing test**
```python
def test_safe_render_below_render_text_order():
    """@safe_render must work BELOW @render.text (render wraps the safe
    wrapper). Actually invokes the stacked-decorated function's underlying
    callable -- not merely checks that decoration succeeds."""
    import asyncio
    from shiny import render
    app = importlib.import_module("app")

    @render.text
    @app.safe_render("text")
    def boom():
        raise RuntimeError("x")

    # boom is a shiny Renderer; its wrapped callable lives at .fn (an
    # AsyncValueFn). Invoking it must swallow the RuntimeError raised inside
    # the safe_render-wrapped body and return the uniform marker -- proving
    # the two decorators are stacked in the correct order.
    result = asyncio.run(boom.fn())
    assert "could not be computed" in result.lower()
```

- [ ] **Step 2: Run to confirm RED (mode A — old test is vacuous, revert after)**
With the **OLD** test body (quoted above) still in place, temporarily reverse the decoration order inside the test itself (swap the two decorator lines):
```python
    @app.safe_render("text")
    @render.text
    def boom():
        raise RuntimeError("x")
```
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_safe_render_below_render_text_order -v`
Expected: PASSES — the old test never calls `boom`, so a wrong decorator order on `boom` is invisible to it; only `raw_boom` (untouched, not stacked) is exercised.
Now replace the whole test with this task's Step 1 new body but keep the swapped (WRONG) decorator order on `boom`.
Expected: FAILS — `asyncio.run(boom.fn())` raises `RuntimeError: x` uncaught (per the verified mechanism above), so the assertion is never reached.
Restore the correct decorator order (`@render.text` outermost, `@app.safe_render("text")` innermost) as shown in Step 1 before continuing.

- [ ] **Step 3: (no production change — test-only task)**
The Step 1 test body above (with the correct decorator order) is final; `app.safe_render` already implements the contract correctly.

- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_safe_render_below_render_text_order -v` then `micromamba run -n shiny python -m pytest`
Expected: PASS; suite green.

- [ ] **Step 5: Commit**
```bash
git add test_app_structure.py
git commit -m "test: safe_render/render.text stacking test actually invokes the stacked renderer"
```

---

### Task 21: Pin nwC/nwG/nwV closed-form values (`3.6`)

**Files:**
- Modify: `test_network_analysis.py:307-325`
- Test: same file

**Interfaces:**
- Consumes: `get_node_weighted_indicators(G, biomass)` (`network_analysis.py:258-326`), `simple_linear_chain` and `simple_omnivory` fixtures (`test_network_analysis.py:31-49`, `:52-73`)
- Produces: nothing

Current test (verified in full):
```python
def test_node_weighted_indicators(simple_linear_chain):
    """Test node-weighted indicators"""
    G, info = simple_linear_chain
    biomass = info['meanB'].values

    indicators = get_node_weighted_indicators(G, biomass)

    # All indicators should be positive and finite
    assert indicators['nwC'] > 0, "Node-weighted connectance should be positive"
    assert indicators['nwG'] > 0, "Node-weighted generality should be positive"
    assert indicators['nwV'] > 0, "Node-weighted vulnerability should be positive"
    assert indicators['nwTL'] > 1.0, "Node-weighted TL should be > 1"

    # Node-weighted TL should be less than or equal to arithmetic mean TL
    # because basal species often have higher biomass
    topo_indicators = get_topological_indicators(G)
    # This isn't always true, but for this specific network it should be
    # Just check it's reasonable
    assert 1.0 < indicators['nwTL'] < 3.0, "Node-weighted TL should be reasonable"
```
`> 0` accepts any positive value regardless of magnitude — e.g. swapping `in_degrees`/`out_degrees` between the `nwG`/`nwV` formulas (`network_analysis.py:307-314`), or using the wrong biomass subset, still yields positive numbers and passes.

Verified closed-form (ran `get_node_weighted_indicators` directly against both fixtures):
- `simple_linear_chain` (A→B→C, biomass `[100, 50, 25]`, nodes in insertion order `[A,B,C]`): `in_degrees=[0,1,1]`, `out_degrees=[1,1,0]`, `total_degrees=[1,2,1]`, `S=3`, `total_biomass=175` → `nwC = (1·100+2·50+1·25)/(2·175·2) = 225/700 ≈ 0.32142857142857145`; predators `{B,C}` → `nwG = (1·50+1·25)/(50+25) = 75/75 = 1.0`; prey `{A,B}` → `nwV = (1·100+1·50)/(100+50) = 150/150 = 1.0`.
- `simple_omnivory` (A→B, A→C, B→C, biomass `[100, 50, 25]`): `in_degrees=[0,1,2]`, `out_degrees=[2,1,0]`, `total_degrees=[2,2,2]` → `nwC = (2·100+2·50+2·25)/(2·175·2) = 350/700 = 0.5`; predators `{B,C}` → `nwG = (1·50+2·25)/(50+25) = 100/75 ≈ 1.3333333333333333`; prey `{A,B}` → `nwV = (2·100+1·50)/(100+50) = 250/150 ≈ 1.6666666666666667`.

- [ ] **Step 1: Write the failing test**
```python
def test_node_weighted_indicators(simple_linear_chain):
    """Node-weighted indicators pinned to closed-form values on the linear
    chain (each predator has exactly 1 prey, each prey exactly 1 predator,
    so nwG=nwV=1.0 exactly) and on the omnivory web (nwG != nwV, catching a
    swapped in/out-degree regression that '> 0' cannot)."""
    G, info = simple_linear_chain
    biomass = info['meanB'].values  # [100.0, 50.0, 25.0]

    indicators = get_node_weighted_indicators(G, biomass)

    assert np.isclose(indicators['nwC'], 225.0 / 700.0), indicators['nwC']
    assert np.isclose(indicators['nwG'], 1.0), indicators['nwG']
    assert np.isclose(indicators['nwV'], 1.0), indicators['nwV']
    assert 1.0 < indicators['nwTL'] < 3.0, "Node-weighted TL should be reasonable"


def test_node_weighted_indicators_omnivory_pinned(simple_omnivory):
    """Same closed-form pin on a branching (non-chain) web, where nwG and
    nwV differ from each other and from 1.0 -- this is what actually
    distinguishes a correct in/out-degree assignment from a swapped one."""
    G, info = simple_omnivory
    biomass = info['meanB'].values  # [100.0, 50.0, 25.0]

    indicators = get_node_weighted_indicators(G, biomass)

    assert np.isclose(indicators['nwC'], 0.5), indicators['nwC']
    assert np.isclose(indicators['nwG'], 100.0 / 75.0), indicators['nwG']
    assert np.isclose(indicators['nwV'], 250.0 / 150.0), indicators['nwV']
```
(Keep `get_topological_indicators` imported as-is; it is unused by the new bodies but remains imported at the top of the file for other tests.)

- [ ] **Step 2: Run to confirm RED (mode A — old test is vacuous, revert after)**
Temporarily edit `network_analysis.py:307-314`, swapping which degree array feeds `nwG` vs `nwV` (a plausible real regression):
```python
    # Node-weighted generality (TEMPORARILY swapped with vulnerability below)
    predators = out_degrees > 0
    nwG = (np.sum((out_degrees * biomass)[predators]) / np.sum(biomass[predators])) \
        if np.sum(predators) > 0 and np.sum(biomass[predators]) > 0 else 0

    # Node-weighted vulnerability (TEMPORARILY swapped with generality above)
    prey = in_degrees > 0
    nwV = (np.sum((in_degrees * biomass)[prey]) / np.sum(biomass[prey])) \
        if np.sum(prey) > 0 and np.sum(biomass[prey]) > 0 else 0
```
Run: `micromamba run -n shiny python -m pytest test_network_analysis.py::test_node_weighted_indicators -v` with the **OLD** test body (quoted above).
Expected: PASSES — on the linear chain, this swap still yields `nwG=nwV=1.0` (symmetric fixture — every node has total in+out degree the same shape), and both remain `> 0`.
Now run the new `test_node_weighted_indicators` and `test_node_weighted_indicators_omnivory_pinned` from Step 1 against the same swapped code.
Expected: the omnivory test FAILS — the swap exchanges the whole quotient, denominator included: `nwG` goes from `100/75` to `250/150` and `nwV` from `250/150` to `100/75`, so the pinned `np.isclose` assertions raise.
Revert the temporary `network_analysis.py` edit before continuing.

- [ ] **Step 3: (no production change — test-only task)**
The Step 1 test bodies above are final; `get_node_weighted_indicators` already computes the correct values.

- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_network_analysis.py -k node_weighted_indicators -v` then `micromamba run -n shiny python -m pytest`
Expected: PASS — this task adds one new test function; the suite total is the 133-test baseline plus every test added so far (cumulative; do not expect an exact number). Only the 3 known `network_analysis.py` UserWarnings (lines 122, 134, 186); any other warning is a defect.

- [ ] **Step 5: Commit**
```bash
git add test_network_analysis.py
git commit -m "test: pin nwC/nwG/nwV closed-form values on chain and omnivory fixtures"
```

---

### Task 22: AST cache guard collects attribute calls and verifies coverage (`3.7`)

**Files:**
- Modify: `test_app_structure.py:1-34`
- Test: same file

**Interfaces:**
- Consumes: `app.py` renderer function names: `trophic_levels_table` (`app.py:1002`, `@render.data_frame` at `:1001`), `keystoneness_table` (`app.py:1296`, `@render.data_frame` at `:1295`)
- Produces: nothing

Current code (verified in full):
```python
RENDERERS = {
    "topological_indicators", "trophic_level_histogram", "node_weighted_indicators",
    "biomass_by_group", "biomass_distribution", "flux_indicators", "flux_heatmap",
    "flux_network_plot", "keystoneness_summary", "keystoneness_scatter",
    "mti_heatmap", "network_plot", "adjacency_heatmap",
}
FORBIDDEN = {"calculate_trophic_levels", "calculate_mti", "get_functional_group_colors"}


def _calls_in(node):
    return {n.func.id for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def test_analytical_renderers_use_caches_not_direct_compute():
    """Analytical renderers must go through the reactive caches, never recompute
    TL/MTI/colors directly. The cache-definition functions are excluded."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    offenders = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in RENDERERS:
            bad = _calls_in(node) & FORBIDDEN
            if bad:
                offenders[node.name] = sorted(bad)
    assert not offenders, f"renderers recompute cached values directly: {offenders}"
```
Two independent gaps: (1) `_calls_in` only collects `ast.Call` nodes whose `func` is a bare `ast.Name` (e.g. `calculate_mti(...)`) — a call reached through attribute access (e.g. `network_analysis.calculate_mti(...)`, `self.calculate_mti(...)`) is silently invisible to `bad = _calls_in(node) & FORBIDDEN`, so such a call inside a renderer is never flagged. (2) the loop only inspects `ast.FunctionDef` nodes whose `name in RENDERERS`; if a name in `RENDERERS` is renamed or deleted from `app.py`, the `for` loop simply never matches it — `offenders` stays empty and the test PASSES, giving zero coverage of that renderer with no signal that coverage was lost. Also, `app.py` has two more analytical renderers not in `RENDERERS` at all: `trophic_levels_table` (`@render.data_frame`, reads `trophic_levels_cached()`) and `keystoneness_table` (`@render.data_frame`, reads `keystoneness_cached()`) — both correctly use the caches today, but are entirely unguarded.

- [ ] **Step 1: Write the failing test**
```python
RENDERERS = {
    "topological_indicators", "trophic_level_histogram", "node_weighted_indicators",
    "biomass_by_group", "biomass_distribution", "flux_indicators", "flux_heatmap",
    "flux_network_plot", "keystoneness_summary", "keystoneness_scatter",
    "mti_heatmap", "network_plot", "adjacency_heatmap",
    "trophic_levels_table", "keystoneness_table",
}
FORBIDDEN = {"calculate_trophic_levels", "calculate_mti", "get_functional_group_colors"}


def _calls_in(node):
    names = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                names.add(n.func.id)
            elif isinstance(n.func, ast.Attribute):
                names.add(n.func.attr)
    return names


def test_analytical_renderers_use_caches_not_direct_compute():
    """Analytical renderers must go through the reactive caches, never recompute
    TL/MTI/colors directly (whether called as a bare name or via attribute
    access, e.g. `module.calculate_mti(...)`). The cache-definition functions
    are excluded. Every name in RENDERERS must actually be found as a
    function in app.py -- a renamed/removed renderer must not silently drop
    out of this guard's coverage."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    offenders = {}
    visited = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in RENDERERS:
            visited.add(node.name)
            bad = _calls_in(node) & FORBIDDEN
            if bad:
                offenders[node.name] = sorted(bad)
    assert visited == RENDERERS, f"renderers not found in app.py (renamed/removed?): {RENDERERS - visited}"
    assert not offenders, f"renderers recompute cached values directly: {offenders}"
```

- [ ] **Step 2: Run to confirm RED (mode A — old test is vacuous on two axes, revert after each)**

*(a) Missing-renderer coverage.* Temporarily rename the renderer at `app.py:1310` from `def mti_heatmap():` to `def mti_heatmap_renamed():` (leaving its body, including the `@output`/`@render.plot`/`@safe_render("plot")` decorators above it, untouched).
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_analytical_renderers_use_caches_not_direct_compute -v` with the **OLD** test body (quoted above).
Expected: PASSES — the `for` loop's `node.name in RENDERERS` never matches `mti_heatmap_renamed`, so `offenders` stays empty regardless of what that function's body does.
Now swap in this task's Step 1 new test body and re-run.
Expected: FAILS — `visited == RENDERERS` is false (`mti_heatmap` is in `RENDERERS - visited`).
Revert the rename (`def mti_heatmap():`) before continuing.

*(b) Attribute-call blind spot.* Temporarily edit `app.py:937-939` (inside `adjacency_heatmap`), changing:
```python
    def adjacency_heatmap():
        G = current_network()
        info = current_species_info()
```
to:
```python
    def adjacency_heatmap():
        G = current_network()
        info = current_species_info()
        import network_analysis as _na
        _na.calculate_mti(G)  # TEMPORARY: simulate a qualified-call regression
```
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_analytical_renderers_use_caches_not_direct_compute -v` with the **OLD** test body.
Expected: PASSES — `_calls_in` only matches `ast.Name` funcs, so `_na.calculate_mti(G)` (an `ast.Attribute` func) is invisible to `bad = _calls_in(node) & FORBIDDEN`.
Now swap in this task's Step 1 new test body and re-run.
Expected: FAILS — the extended `_calls_in` adds `"calculate_mti"` (via `n.func.attr`) to the collected names, so `offenders == {"adjacency_heatmap": ["calculate_mti"]}` and the second assertion raises.
Revert the temporary `app.py` edit before continuing.

- [ ] **Step 3: (no other production change — test-only task)**
The Step 1 test body above (RENDERERS/FORBIDDEN/`_calls_in`/test function) is final; `app.py`'s real renderers (including `trophic_levels_table` and `keystoneness_table`) already use their caches correctly, so adding them to `RENDERERS` introduces no new failures.

- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_analytical_renderers_use_caches_not_direct_compute -v` then `micromamba run -n shiny python -m pytest`
Expected: PASS; suite green.

- [ ] **Step 5: Commit**
```bash
git add test_app_structure.py
git commit -m "test: AST cache guard catches attribute calls and asserts full RENDERERS coverage"
```

---

### Task 23: Synthetic same-set/different-order GraphML+CSV reindex proof (`3.8`)

**Files:**
- Modify: `test_load_data_alignment.py` (append after line 79)
- Test: same file

**Interfaces:**
- Consumes: `load_data.load_baltic_data(base_dir: Path | None = None)` — the `base_dir` keyword is added by Task 1 (`1.2`) (`load_data.py:25-33` region); this task assumes Phase 1 has already landed, per the plan's build order (Phases 1→6 in sequence).
- Produces: nothing

The existing test in this file, `test_load_baltic_data_node_ids_are_species_names` (`test_load_data_alignment.py:5-12`), skips unless the TRACKED `BalticFW_network.graphml` is present, and per the design spec, the tracked GraphML's node order already equals the tracked CSV's row order — so the reindex branch at `load_data.py:65-66`:
```python
    node_list = list(G.nodes())
    if set(node_list) == set(info['species']):
        info = info.set_index('species').loc[node_list].reset_index()
```
takes the `if` branch but `.loc[node_list]` is a no-op reordering (the rows are already in that order). No existing test exercises a CSV whose rows are a genuine permutation of the GraphML's node order.

- [ ] **Step 1: Write the failing test**
```python
def test_load_baltic_data_reindexes_shuffled_csv_to_node_order(tmp_path):
    """CSV rows in a DIFFERENT order than the GraphML nodes, but the SAME
    species set, must be reindexed to match node order -- proving the
    set_index/.loc reindex branch (load_data.py:65-66) actually reorders,
    not merely no-ops because the tracked files already happen to agree."""
    g = nx.DiGraph()
    g.add_node('n0', name='Cod')
    g.add_node('n1', name='Sprat')
    g.add_node('n2', name='Herring')
    g.add_edge('n1', 'n0')
    g.add_edge('n2', 'n0')
    nx.write_graphml(g, tmp_path / "BalticFW_network.graphml")

    # Same species SET as the graph's node order (Cod, Sprat, Herring), but
    # rows written in a DIFFERENT order.
    pd.DataFrame({
        'species': ['Herring', 'Cod', 'Sprat'],
        'fg': ['Fish', 'Fish', 'Fish'],
        'meanB': [3.0, 1.0, 2.0],
        'bodymasses': [3.0, 1.0, 2.0],
        'met.types': ['Other', 'Other', 'Other'],
        'efficiencies': [0.5, 0.5, 0.5],
    }).to_csv(tmp_path / "BalticFW_species_info.csv", index=False)

    from load_data import load_baltic_data
    G, info = load_baltic_data(base_dir=tmp_path)

    assert list(G.nodes()) == ['Cod', 'Sprat', 'Herring']
    assert info['species'].tolist() == ['Cod', 'Sprat', 'Herring']
    # The reindex must move each row's OTHER values with its species label,
    # not merely overwrite the species column in place.
    assert info.loc[info['species'] == 'Herring', 'meanB'].iloc[0] == 3.0
    assert info.loc[info['species'] == 'Cod', 'meanB'].iloc[0] == 1.0
    assert info.loc[info['species'] == 'Sprat', 'meanB'].iloc[0] == 2.0
```

- [ ] **Step 2: Run to confirm RED (mode A — no existing test exercises this path, revert after)**
Temporarily delete the reindex branch, replacing `load_data.py:64-66`:
```python
    node_list = list(G.nodes())
    if set(node_list) == set(info['species']):
        info = info.set_index('species').loc[node_list].reset_index()
```
with just:
```python
    node_list = list(G.nodes())  # TEMPORARY: reindex branch removed
```
Run: `micromamba run -n shiny python -m pytest` (full suite).
Expected: every OTHER currently-passing test still PASSES — the tracked-file test (`test_load_baltic_data_node_ids_are_species_names`) still passes because the tracked GraphML/CSV already agree in order (per the design spec), and the mismatch test (`test_load_baltic_data_raises_on_name_mismatch`) still raises for the unrelated reason that its species SETS differ (`{Cod,Sprat}` vs `{Cod,Herring}`), which the final `if list(G.nodes()) != info['species'].tolist(): raise ValueError` (`load_data.py:67-71`) catches regardless of the reindex branch. This demonstrates the current suite has zero coverage of the reindex actually firing.
Now run: `micromamba run -n shiny python -m pytest test_load_data_alignment.py::test_load_baltic_data_reindexes_shuffled_csv_to_node_order -v` (Step 1's new test, with `load_data.py` still broken).
Expected: FAILS — with no reindexing, `info['species'].tolist()` stays `['Herring', 'Cod', 'Sprat']` while `list(G.nodes())` is `['Cod', 'Sprat', 'Herring']`; the final alignment check inside `load_baltic_data` itself raises `ValueError: Network nodes do not align with species rows by name...` before the function can even return.
Revert the temporary `load_data.py` edit (restore lines 64-66 exactly as quoted above) before continuing.

- [ ] **Step 3: (no production change — test-only task)**
The Step 1 test body above is final; `load_baltic_data`'s reindex branch already reorders correctly.

- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_load_data_alignment.py -v` then `micromamba run -n shiny python -m pytest`
Expected: PASS; suite green.

- [ ] **Step 5: Commit**
```bash
git add test_load_data_alignment.py
git commit -m "test: prove load_baltic_data's reindex branch reorders a shuffled CSV to node order"
```

---

### Task 24: Phase 3 gate

- [ ] **Step 1: Full suite**
Run: `micromamba run -n shiny python -m pytest`
Expected: all tests pass — the 133-test baseline plus every test added in Tasks 16-23 and all preceding phases (cumulative; do not expect an exact number). Only the 3 known `network_analysis.py` UserWarnings (lines 122, 134, 186); any other warning is a defect. (This phase's net-new `def test_...` come from Tasks 16, 21 and 23; Tasks 17-20 and 22 rewrite existing test bodies rather than adding functions.)

- [ ] **Step 2: App still imports**
Run: `micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: prints `app OK` with no exception.

- [ ] **Step 3: Tag**
```bash
git tag audit3-phase3
```

---

# PHASE 4 — Feedback path

**Spec items:** 4.1 (A4), 4.2 (A17), 4.3 (crit6). Baseline: 133 tests passing, 3 known `network_analysis.py` UserWarnings (lines 122, 134, 186) — no new warnings allowed. (That 133 is the *plan-start* baseline; Phases 1-3 have already added tests by the time this phase runs, so treat every count in this phase as cumulative, per the gate wording.)

**Files touched:**
- `feedback_reporter.py` — `create_github_issue` (:99-155), `submit_feedback` (:172-219)
- `app.py` — imports (:47), `colors_cached` (:639-642), `last_feedback_submit` (:667), feedback modal `_show_feedback_modal` (:709-759), submit effect `_handle_feedback_submit` (:761-837), `functional_groups_legend` (:865-883)
- `network_viz.py` — `get_functional_group_colors` (:289-319)
- `test_feedback_reporter.py`, `test_app_structure.py`, `test_network_viz_render.py`

**Read before starting:** `shiny/reactive/_reactives.py::Effect_.__init__` (installed at `C:\Users\arturas.baziukas\micromamba\envs\shiny\Lib\site-packages\shiny\reactive\_reactives.py:971-973`) shows `self._fn: EffectFunctionAsync = _utils.wrap_async(fn)` and `self._is_async: bool = _utils.is_async_callable(fn)` — `@reactive.effect` auto-detects an `async def` handler and awaits it during flush (`_run` at :1068, `await self._fn()` at :1084). No extra Shiny-side wiring is needed to make `_handle_feedback_submit` async; decorating an `async def` with `@reactive.effect` / `@reactive.event` is already supported. Confirmed interactively: `micromamba run -n shiny python -m pytest` picks up `pytest-asyncio` 0.26.0 in **strict** mode (no `asyncio_mode` config file exists in the repo), so async tests need an explicit `@pytest.mark.asyncio` marker — verified this repo's collected plugins include `asyncio-0.26.0` and that a bare `@pytest.mark.asyncio async def test_x(): assert True` passes today.

---

### Task 25: `get_functional_group_colors` coerces labels with `str()` before sorting (`4.3`, `crit6`)

**Files:**
- Modify: `network_viz.py:299,317`
- Test: `test_network_viz_render.py`

**Interfaces:**
- Consumes: nothing
- Produces: `get_functional_group_colors(functional_groups: List) -> (List[str], Dict[str,str])` still importable the same way at `app.py:43` and `app.py:641` (`colors_cached`); no signature change.

- [ ] **Step 1: Write the failing test**
```python
def test_color_mapping_coerces_mixed_type_labels():
    """A functional-group column read from a CSV can carry a stray NaN (float)
    alongside string labels (e.g. a blank cell). sorted(set(...)) on mixed
    str/float raises TypeError before any color is ever assigned."""
    import numpy as np
    from network_viz import get_functional_group_colors
    groups = ["Fish", float("nan"), "Fish", 3]
    node_colors, color_map = get_functional_group_colors(groups)
    assert len(node_colors) == 4
    assert set(color_map.keys()) == {"Fish", "nan", "3"}
    assert node_colors[0] == node_colors[2] == color_map["Fish"]
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py::test_color_mapping_coerces_mixed_type_labels -v`
Expected: FAIL — `TypeError: '<' not supported between instances of 'str' and 'int'` raised inside `sorted(list(set(functional_groups)))` at `network_viz.py:299` (verified interactively: `get_functional_group_colors(['Fish', np.nan, 'Fish', 3])` raises exactly this).
- [ ] **Step 3: Coerce to `str` before dedup/sort**
In `network_viz.py`, replace the body of `get_functional_group_colors` starting at line 299:
```python
    unique_groups = sorted(list(set(functional_groups)))
```
with:
```python
    functional_groups = [str(g) for g in functional_groups]
    unique_groups = sorted(set(functional_groups))
```
and leave the existing `color_map[group] = COLOR_SCHEME[i]` / cycling loop and the final
```python
    node_colors = [color_map[group] for group in functional_groups]
```
(line 317) unchanged — it now looks up the same coerced strings that built `color_map`, so no further edit is needed there.
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS — the 133-test baseline plus every test added so far (this task adds one; cumulative — do not expect an exact number). Only the 3 known `network_analysis.py` UserWarnings (lines 122, 134, 186); any other warning is a defect.
- [ ] **Step 5: Commit**
```bash
git add network_viz.py test_network_viz_render.py
git commit -m "fix: get_functional_group_colors coerces labels to str before sorting

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KKeResQLAndzvguE1xpqR6"
```

---

### Task 26: `functional_groups_legend` gets the `@safe_render("ui")` wrapper (`4.3`, `crit6`)

**Files:**
- Modify: `app.py:865-867`
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: `app.safe_render(kind)` (`app.py:72-84`, unchanged), `app._error_element("ui")` (`app.py:59-69`, unchanged)
- Produces: nothing new — `functional_groups_legend` keeps its existing `@output`/`@render.ui` stack and return shape.

- [ ] **Step 1: Write the failing test**

`functional_groups_legend` is a closure inside `server()` reading `current_species_info()` and `colors_cached()` from reactive state — it cannot be invoked standalone without a live Shiny session (same constraint the existing `RENDERERS` AST guard in this file works around). Use the same structural approach: parse `app.py` and assert the decorator is present.

Add to `test_app_structure.py`:
```python
def test_functional_groups_legend_has_safe_render_ui():
    """functional_groups_legend must be wrapped in @safe_render('ui') like every
    other panel renderer, so a bad functional-group value can't crash the
    whole dashboard instead of showing the uniform error element."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    node = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "functional_groups_legend"
    )
    safe_render_calls = [
        d for d in node.decorator_list
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "safe_render"
    ]
    assert safe_render_calls, "functional_groups_legend must carry @safe_render(...)"
    assert safe_render_calls[0].args[0].value == "ui"
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_functional_groups_legend_has_safe_render_ui -v`
Expected: FAIL — today `functional_groups_legend`'s `decorator_list` is only `[@output, @render.ui]` (verified by reading `app.py:865-867`); the generator expression finds no `safe_render` call, so `safe_render_calls` is empty and the `assert` fails.
- [ ] **Step 3: Add the decorator**
In `app.py`, change:
```python
    @output
    @render.ui
    def functional_groups_legend():
        info = current_species_info()
```
(lines 865-868) to:
```python
    @output
    @render.ui
    @safe_render("ui")
    def functional_groups_legend():
        info = current_species_info()
```
(matches the existing stacking order used by `network_plot` at `app.py:913-916`, confirmed correct by `test_safe_render_below_render_text_order`).
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS; suite green, no new warnings.
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "fix: wrap functional_groups_legend in @safe_render(\"ui\")

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KKeResQLAndzvguE1xpqR6"
```

---

### Task 27: Server-side length caps on feedback fields + `maxlength` on the inputs (`4.2`, `A17`)

**Files:**
- Modify: `app.py:709-759` (modal inputs)
- Read-only reference (NOT edited here — edited in Task 29, which rewrites this function wholesale for the async change): `app.py:771-798` (submit handler field reads; line 771 is `title = (input.fb_title() or "").strip()`)
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: `shiny.ui.input_text` / `ui.input_text_area` (unchanged signatures — confirmed via `inspect.signature`: neither accepts a `maxlength` kwarg, so the HTML attribute must be added to the built `Tag` after construction)
- Produces: `FEEDBACK_MAX_LENGTHS: dict[str,int]` (module-level, `app.py`), `_cap_feedback_text(value: str, field: str) -> str`, `_capped_input_text(id_, label, *, placeholder=None, width=None, max_len) -> Tag`, `_capped_input_text_area(id_, label, *, rows=None, placeholder=None, width=None, max_len) -> Tag` — all consumed by Task 29's handler rewrite.

- [ ] **Step 1: Write the failing test**

Confirmed interactively that `ui.input_text("x","X")` returns a `div` whose `.children[1]` is the `<input>` `Tag`, and that `.children[1].attrs["maxlength"] = "200"` renders `maxlength="200"` on the tag — so a helper that sets this after building the widget is sufficient; `shiny.ui.input_text`/`input_text_area` (`C:\Users\arturas.baziukas\micromamba\envs\shiny\Lib\site-packages\shiny\ui\_input_text.py:14-24,91-106`) take no `maxlength` parameter.

Add to `test_app_structure.py`:
```python
def test_cap_feedback_text_truncates_to_field_limit():
    app = importlib.import_module("app")
    assert app.FEEDBACK_MAX_LENGTHS == {
        "title": 200, "description": 5000, "steps": 5000, "browser_info": 512,
    }
    long_title = "x" * 250
    assert len(app._cap_feedback_text(long_title, "title")) == 200
    assert app._cap_feedback_text("short", "title") == "short"
    long_desc = "y" * 6000
    assert len(app._cap_feedback_text(long_desc, "description")) == 5000


def test_capped_text_inputs_carry_maxlength_attribute():
    app = importlib.import_module("app")
    title_tag = app._capped_input_text("fb_title", "Title", placeholder="p", width="100%", max_len=200)
    assert title_tag.children[1].attrs["maxlength"] == "200"
    desc_tag = app._capped_input_text_area("fb_description", "Description", rows=5, placeholder="p", width="100%", max_len=5000)
    assert desc_tag.children[1].attrs["maxlength"] == "5000"
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_cap_feedback_text_truncates_to_field_limit test_app_structure.py::test_capped_text_inputs_carry_maxlength_attribute -v`
Expected: FAIL — `AttributeError: module 'app' has no attribute 'FEEDBACK_MAX_LENGTHS'` (none of `FEEDBACK_MAX_LENGTHS`, `_cap_feedback_text`, `_capped_input_text`, `_capped_input_text_area` exist yet in `app.py`).
- [ ] **Step 3: Add the caps + helpers, and use them in the modal**
In `app.py`, near the top-level helpers below `safe_render` (after line 84), add:
```python
FEEDBACK_MAX_LENGTHS = {"title": 200, "description": 5000, "steps": 5000, "browser_info": 512}


def _cap_feedback_text(value: str, field: str) -> str:
    """Server-side length cap for a feedback field, enforced before local save
    (client-side maxlength is a hint only)."""
    return value[: FEEDBACK_MAX_LENGTHS[field]]


def _capped_input_text(id_, label, *, placeholder=None, width=None, max_len):
    tag = ui.input_text(id_, label, placeholder=placeholder, width=width)
    tag.children[1].attrs["maxlength"] = str(max_len)
    return tag


def _capped_input_text_area(id_, label, *, rows=None, placeholder=None, width=None, max_len):
    tag = ui.input_text_area(id_, label, rows=rows, placeholder=placeholder, width=width)
    tag.children[1].attrs["maxlength"] = str(max_len)
    return tag
```
Then in `_show_feedback_modal` (`app.py:726-740`), replace:
```python
                ui.input_text("fb_title", "Title", placeholder="Brief summary of your feedback", width="100%"),
                ui.input_text_area(
                    "fb_description",
                    "Description",
                    rows=5,
                    placeholder="Please describe in detail what happened or what you would like to see improved.",
                    width="100%",
                ),
                ui.input_text_area(
                    "fb_steps",
                    "Steps to Reproduce (bug reports only)",
                    rows=3,
                    placeholder="1. Open the Network tab\n2. Click ...\n3. Observed: ...",
                    width="100%",
                ),
```
with:
```python
                _capped_input_text("fb_title", "Title", placeholder="Brief summary of your feedback", width="100%", max_len=FEEDBACK_MAX_LENGTHS["title"]),
                _capped_input_text_area(
                    "fb_description",
                    "Description",
                    rows=5,
                    placeholder="Please describe in detail what happened or what you would like to see improved.",
                    width="100%",
                    max_len=FEEDBACK_MAX_LENGTHS["description"],
                ),
                _capped_input_text_area(
                    "fb_steps",
                    "Steps to Reproduce (bug reports only)",
                    rows=3,
                    placeholder="1. Open the Network tab\n2. Click ...\n3. Observed: ...",
                    width="100%",
                    max_len=FEEDBACK_MAX_LENGTHS["steps"],
                ),
```
(The handler-side enforcement of these caps on `title`/`description`/`steps`/`browser_info` is wired in Task 29, which rewrites `_handle_feedback_submit` anyway for the async change — doing it there avoids editing that function body twice.)
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS; suite green, no new warnings.
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "feat: add server-side feedback field length caps and input maxlength

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KKeResQLAndzvguE1xpqR6"
```

---

### Task 28: `submit_feedback_async` — GitHub call runs via `asyncio.to_thread`; catch `http.client.HTTPException` (`4.1`, `A4`)

**Files:**
- Modify: `feedback_reporter.py:14-24` (imports), `:99-155` (`create_github_issue`), `:172-219` (`submit_feedback`, refactored + new `submit_feedback_async`)
- Test: `test_feedback_reporter.py`

**Interfaces:**
- Consumes: `create_github_issue(title, body, labels, *, timeout=10.0) -> Optional[dict]` (unchanged signature), `save_feedback_local`, `_build_issue_body`, `LABEL_MAP`, `SubmissionResult` (all unchanged)
- Produces: `submit_feedback_async(*, title, description, type_="general", steps="", context=None, log_path=DEFAULT_LOG_PATH) -> SubmissionResult` (async, awaitable) — consumed by Task 29's  handler. `submit_feedback` (sync) keeps its exact existing signature and behavior — every existing test in `test_feedback_reporter.py` must still pass unchanged.

- [ ] **Step 1: Write the failing tests**

Two independent gaps: (a) `submit_feedback_async` does not exist; (b) `create_github_issue`'s except tuple at `feedback_reporter.py:150` (`except (urllib.error.URLError, TimeoutError, OSError)`) does not include `http.client.HTTPException`, so a raw `http.client.HTTPException` from `urlopen` propagates uncaught instead of degrading to `None` like every other transport failure.

Add to `test_feedback_reporter.py` (add `import http.client` and `import threading` to the file's existing import block at the top):
```python
def test_create_github_issue_returns_none_on_http_client_exception(monkeypatch):
    """http.client.HTTPException (e.g. BadStatusLine) is a transport failure
    like URLError/OSError and must degrade to None, not propagate."""
    monkeypatch.setenv("ECONETPY_GITHUB_TOKEN", "ghp_fake_token")

    def fake_urlopen(req, timeout):
        raise http.client.HTTPException("malformed response")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert create_github_issue("t", "b") is None


@pytest.mark.asyncio
async def test_submit_feedback_async_runs_github_call_off_the_event_loop(tmp_path, monkeypatch):
    """Decision #7: only the network call is async; save_feedback_local stays
    synchronous. Prove the GitHub call actually runs in a worker thread via
    asyncio.to_thread, not on the event loop thread."""
    from feedback_reporter import submit_feedback_async
    monkeypatch.setenv("ECONETPY_GITHUB_TOKEN", "ghp_fake")
    log = tmp_path / "f.ndjson"
    main_thread_id = threading.get_ident()
    seen_thread_ids = []

    class FakeResp:
        status = 201
        def read(self):
            return json.dumps({"html_url": "https://github.com/x/y/issues/9", "number": 9}).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        seen_thread_ids.append(threading.get_ident())
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = await submit_feedback_async(title="t", description="d", log_path=log)

    assert result.local_success is True
    assert result.github_success is True
    assert result.github_url == "https://github.com/x/y/issues/9"
    assert seen_thread_ids and seen_thread_ids[0] != main_thread_id
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").strip().splitlines()]
    assert len(entries) == 2  # original + URL-corrected, same NDJSON-append pattern as submit_feedback


@pytest.mark.asyncio
async def test_submit_feedback_async_validates_title_required(tmp_path):
    from feedback_reporter import submit_feedback_async
    with pytest.raises(ValueError, match="title"):
        await submit_feedback_async(title="  ", description="x", log_path=tmp_path / "f.ndjson")
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_feedback_reporter.py::test_create_github_issue_returns_none_on_http_client_exception test_feedback_reporter.py::test_submit_feedback_async_runs_github_call_off_the_event_loop test_feedback_reporter.py::test_submit_feedback_async_validates_title_required -v`
Expected: FAIL —
1. `test_create_github_issue_returns_none_on_http_client_exception`: `http.client.HTTPException: malformed response` propagates out of `create_github_issue` uncaught (its except tuple at `feedback_reporter.py:150` is `(urllib.error.URLError, TimeoutError, OSError)`, which does not match).
2. Both `submit_feedback_async` tests: `ImportError: cannot import name 'submit_feedback_async' from 'feedback_reporter'` — the function does not exist yet.
- [ ] **Step 3: Add the exception, refactor `submit_feedback` into shared helpers, add `submit_feedback_async`**
In `feedback_reporter.py`, insert two new lines directly **above** the existing `import json` at line 16 (`import json` itself is already there and must not be duplicated; the block stays alphabetical):
```python
import asyncio
import http.client
```
In `create_github_issue`, change the except clause at line 150:
```python
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.error("create_github_issue network: %s", exc)
        return None
```
to:
```python
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        logger.error("create_github_issue network: %s", exc)
        return None
```
Replace `submit_feedback` (lines 172-219) with the same behavior split into two shared helpers plus the sync and async entry points:
```python
def _prepare_submission(
    title: str, description: str, type_: str, steps: str, context: Optional[dict[str, Any]]
) -> tuple[list[str], str, dict[str, Any]]:
    if not title.strip():
        raise ValueError("title is required")
    if not description.strip():
        raise ValueError("description is required")

    ctx = context or {}
    labels = LABEL_MAP.get(type_, LABEL_MAP["general"])
    issue_body = _build_issue_body(description, steps, ctx)
    local_payload: dict[str, Any] = {
        "title": title,
        "description": description,
        "type": type_,
        "steps": steps,
        "labels": labels,
        "github_url": None,
        **ctx,
    }
    return labels, issue_body, local_payload


def _finalize_submission(
    local_payload: dict[str, Any], local_ok: bool, gh: Optional[dict[str, Any]], log_path: Path
) -> SubmissionResult:
    github_ok = gh is not None
    github_url = gh["url"] if github_ok else None
    # If GitHub succeeded, append a corrected entry with the URL. The original
    # entry remains (acceptable for NDJSON; matches the R behaviour).
    if github_ok and local_ok:
        save_feedback_local({**local_payload, "github_url": github_url}, path=log_path)
    return SubmissionResult(local_success=local_ok, github_success=github_ok, github_url=github_url)


def submit_feedback(
    *,
    title: str,
    description: str,
    type_: str = "general",
    steps: str = "",
    context: Optional[dict[str, Any]] = None,
    log_path: Path = DEFAULT_LOG_PATH,
) -> SubmissionResult:
    """Orchestrate local save + optional GitHub Issue creation, fully synchronous.

    Validation errors (empty title/description) raise ValueError —
    the caller is responsible for user-facing message.
    """
    labels, issue_body, local_payload = _prepare_submission(title, description, type_, steps, context)
    local_ok = save_feedback_local(local_payload, path=log_path)
    gh = create_github_issue(title, issue_body, labels)
    return _finalize_submission(local_payload, local_ok, gh, log_path)


async def submit_feedback_async(
    *,
    title: str,
    description: str,
    type_: str = "general",
    steps: str = "",
    context: Optional[dict[str, Any]] = None,
    log_path: Path = DEFAULT_LOG_PATH,
) -> SubmissionResult:
    """Same contract as submit_feedback(), except the GitHub network call runs
    off the event loop via asyncio.to_thread. The local NDJSON append stays
    synchronous (decision #7: only the network call becomes async)."""
    labels, issue_body, local_payload = _prepare_submission(title, description, type_, steps, context)
    local_ok = save_feedback_local(local_payload, path=log_path)
    gh = await asyncio.to_thread(create_github_issue, title, issue_body, labels)
    return _finalize_submission(local_payload, local_ok, gh, log_path)
```
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_feedback_reporter.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS — every pre-existing `submit_feedback` test in `test_feedback_reporter.py` (e.g. `test_submit_feedback_local_only_when_token_missing`, `test_submit_feedback_records_github_url_when_succeeds`, `test_submit_feedback_label_mapping_falls_back_for_unknown_type`) still passes unchanged, plus the 4 new tests. `app.py` is untouched by this task, so the full suite (including `test_app_structure.py`) stays exactly as green as it was before this task.
- [ ] **Step 5: Commit**
```bash
git add feedback_reporter.py test_feedback_reporter.py
git commit -m "feat: add submit_feedback_async; catch http.client.HTTPException in create_github_issue

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KKeResQLAndzvguE1xpqR6"
```

---

### Task 29: Process-wide rate limit + async wiring — `_handle_feedback_submit` becomes `async def`, uses `submit_feedback_async` (`4.1`, `4.2`, `A4`, `A17`)

Both spec items land in this one task because they both rewrite the same function body — a process-wide rate limiter is pointless to wire against the old synchronous call only to rewire it again for the async call one task later, and the two changes don't conflict with each other (limiter check/record wraps the call; the call itself becomes async).

**Files:**
- Modify: `app.py:18-19` (import), `app.py:47` (import), `app.py:667` (delete), `app.py` near the Task 27 helpers (add limiter), `app.py:761-837` (`_handle_feedback_submit`)
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: `submit_feedback_async` (Task 28), `_cap_feedback_text`/`FEEDBACK_MAX_LENGTHS` (Task 27)
- Produces: `FEEDBACK_RATE_LIMIT_SECONDS: float`, `_feedback_rate_limited(now: float) -> bool`, `_record_feedback_submit(now: float) -> None` — module-level, process-wide (not consumed further in this phase, but tests must reset the shared `_feedback_last_submit_at` dict before/after asserting on it since it persists across test functions in the same pytest run).

- [ ] **Step 1: Write the failing tests**

Two independent gaps, both in `app.py`: (a) the rate-limit guard `last_feedback_submit = reactive.Value(None)` at `app.py:667` is created fresh **per Shiny session** inside `server()` — two browser tabs (two sessions) each get their own clock, so the 30s window is per-user, not per-process; (b) `_handle_feedback_submit` is `def`, not `async def`, and calls `submit_feedback` (sync), not `submit_feedback_async`.

Add to `test_app_structure.py`:
```python
def test_feedback_rate_limit_is_process_wide_not_reactive_value():
    """The limiter must be a module-level (process-wide) clock, not a
    reactive.Value recreated per session — two independent callers sharing
    _feedback_last_submit_at must observe each other's submissions."""
    app = importlib.import_module("app")
    app._feedback_last_submit_at["t"] = None  # reset shared state before asserting
    assert app._feedback_rate_limited(1000.0) is False
    app._record_feedback_submit(1000.0)
    # A second, independent "session" checking 10s later must also be blocked --
    # this is exactly the process-wide behavior a per-session reactive.Value cannot give.
    assert app._feedback_rate_limited(1010.0) is True
    assert app._feedback_rate_limited(1031.0) is False
    app._feedback_last_submit_at["t"] = None  # leave shared state clean for later tests


def test_handle_feedback_submit_is_async_and_awaits_submit_feedback_async():
    """The submit effect must be async (Shiny's reactive.effect auto-detects and
    awaits an async def — verified in shiny/reactive/_reactives.py:971-973,1084)
    so the GitHub network call (routed through asyncio.to_thread inside
    submit_feedback_async) does not block the event loop."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    target = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "_handle_feedback_submit"),
        None,
    )
    assert target is not None, "_handle_feedback_submit must be declared `async def`"
    awaited_names = {
        n.value.func.id for n in ast.walk(target)
        if isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
    }
    assert "submit_feedback_async" in awaited_names
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_feedback_rate_limit_is_process_wide_not_reactive_value test_app_structure.py::test_handle_feedback_submit_is_async_and_awaits_submit_feedback_async -v`
Expected: FAIL —
1. `test_feedback_rate_limit_is_process_wide_not_reactive_value`: `AttributeError: module 'app' has no attribute '_feedback_last_submit_at'` (today the only rate-limit state is the per-session `reactive.Value` at `app.py:667`, not a module-level object).
2. `test_handle_feedback_submit_is_async_and_awaits_submit_feedback_async`: today (`app.py:762-763`) it is `def _handle_feedback_submit():` (a plain `FunctionDef`, not `AsyncFunctionDef`), so the `next(...)` lookup returns `None` and `assert target is not None` fails.
- [ ] **Step 3: Add the process-wide limiter, remove the per-session `reactive.Value`, rewrite the handler**
Add `import threading` to `app.py`'s import block (after `import functools` at line 19):
```python
import functools
import threading
```
Add near the other module-level feedback helpers added in Task 27 (after `FEEDBACK_MAX_LENGTHS` / `_cap_feedback_text`):
```python
FEEDBACK_RATE_LIMIT_SECONDS = 30.0
_feedback_rate_lock = threading.Lock()
_feedback_last_submit_at: dict[str, float | None] = {"t": None}


def _feedback_rate_limited(now: float) -> bool:
    """True if a feedback submission right now would be rate-limited. Process-
    wide (shared across all Shiny sessions in this worker), not per-session —
    a per-session reactive.Value let each browser tab reset its own clock."""
    with _feedback_rate_lock:
        last = _feedback_last_submit_at["t"]
        return last is not None and (now - last) < FEEDBACK_RATE_LIMIT_SECONDS


def _record_feedback_submit(now: float) -> None:
    with _feedback_rate_lock:
        _feedback_last_submit_at["t"] = now
```
Delete the per-session guard at `app.py:667`:
```python
    current_page = reactive.Value("dashboard")
    last_feedback_submit = reactive.Value(None)  # epoch seconds; rate-limit guard
```
becomes:
```python
    current_page = reactive.Value("dashboard")
```
In `app.py:47`, change the import:
```python
from feedback_reporter import collect_system_context, submit_feedback
```
to:
```python
from feedback_reporter import collect_system_context, submit_feedback_async
```
Replace the whole handler body (`app.py:761-837`):
```python
    @reactive.effect
    @reactive.event(input.fb_submit)
    def _handle_feedback_submit():
        # Rate limit (30s server-side)
        now = time.time()
        last = last_feedback_submit.get()
        if last is not None and (now - last) < 30:
            ui.notification_show("Please wait before submitting again.", type="warning", duration=4)
            return

        title = (input.fb_title() or "").strip()
        description = (input.fb_description() or "").strip()
        if not title:
            ui.notification_show("Please enter a title.", type="warning", duration=4)
            return
        if not description:
            ui.notification_show("Please enter a description.", type="warning", duration=4)
            return

        fb_type = input.fb_type() or "general"
        steps = (input.fb_steps() or "").strip() if fb_type == "bug" else ""

        # Snapshot counts; tolerate missing/invalid state
        try:
            info = current_species_info()
            species_count = int(len(info)) if info is not None else 0
        except Exception:
            species_count = 0
        try:
            g = current_network()
            edge_count = int(g.number_of_edges()) if g is not None else 0
        except Exception:
            edge_count = 0

        try:
            browser_info = input.fb_browser_info()
        except Exception:
            browser_info = "unknown"

        context = collect_system_context(
            current_tab=current_page() or "unknown",
            browser_info=browser_info or "unknown",
            species_count=species_count,
            edge_count=edge_count,
        )

        try:
            result = submit_feedback(
                title=title,
                description=description,
                type_=fb_type,
                steps=steps,
                context=context,
            )
        except ValueError as exc:
            ui.notification_show(f"Validation error: {exc}", type="warning", duration=5)
            return
        except Exception:
            logger.exception("feedback submission failed")
            ui.notification_show("Submission failed, please try again.", type="error", duration=6)
            return

        last_feedback_submit.set(now)

        if result.github_success:
            ui.notification_show(
                f"Thank you! Submitted as GitHub issue: {result.github_url}",
                type="message",
                duration=8,
            )
        elif result.local_success:
            ui.notification_show("Thank you! Your feedback has been saved.", type="message", duration=5)
        else:
            ui.notification_show("Feedback could not be saved. Please try again.", type="error", duration=8)
            return

        ui.modal_remove()
```
with:
```python
    @reactive.effect
    @reactive.event(input.fb_submit)
    async def _handle_feedback_submit():
        # Rate limit (30s, process-wide across all sessions)
        now = time.time()
        if _feedback_rate_limited(now):
            ui.notification_show("Please wait before submitting again.", type="warning", duration=4)
            return

        title = _cap_feedback_text((input.fb_title() or "").strip(), "title")
        description = _cap_feedback_text((input.fb_description() or "").strip(), "description")
        if not title:
            ui.notification_show("Please enter a title.", type="warning", duration=4)
            return
        if not description:
            ui.notification_show("Please enter a description.", type="warning", duration=4)
            return

        fb_type = input.fb_type() or "general"
        steps = _cap_feedback_text(
            (input.fb_steps() or "").strip() if fb_type == "bug" else "", "steps"
        )

        # Snapshot counts; tolerate missing/invalid state
        try:
            info = current_species_info()
            species_count = int(len(info)) if info is not None else 0
        except Exception:
            species_count = 0
        try:
            g = current_network()
            edge_count = int(g.number_of_edges()) if g is not None else 0
        except Exception:
            edge_count = 0

        try:
            browser_info = input.fb_browser_info()
        except Exception:
            browser_info = "unknown"
        browser_info = _cap_feedback_text(browser_info or "unknown", "browser_info")

        context = collect_system_context(
            current_tab=current_page() or "unknown",
            browser_info=browser_info,
            species_count=species_count,
            edge_count=edge_count,
        )

        try:
            result = await submit_feedback_async(
                title=title,
                description=description,
                type_=fb_type,
                steps=steps,
                context=context,
            )
        except ValueError as exc:
            ui.notification_show(f"Validation error: {exc}", type="warning", duration=5)
            return
        except Exception:
            logger.exception("feedback submission failed")
            ui.notification_show("Submission failed, please try again.", type="error", duration=6)
            return

        _record_feedback_submit(now)

        if result.github_success:
            ui.notification_show(
                f"Thank you! Submitted as GitHub issue: {result.github_url}",
                type="message",
                duration=8,
            )
        elif result.local_success:
            ui.notification_show("Thank you! Your feedback has been saved.", type="message", duration=5)
        else:
            ui.notification_show("Feedback could not be saved. Please try again.", type="error", duration=8)
            return

        ui.modal_remove()
```
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -m pytest`
Expected: PASS — the 133-test baseline plus every test added in Tasks 25-29 (9 in this phase) and all preceding phases (cumulative; do not expect an exact number). Only the 3 known `network_analysis.py` UserWarnings (lines 122, 134, 186); any other warning is a defect.
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "fix: make feedback submit effect async; wire process-wide rate limit and field caps

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KKeResQLAndzvguE1xpqR6"
```

---

### Task 30: Phase 4 gate

- [ ] **Step 1: Full suite**
Run: `micromamba run -n shiny python -m pytest`
Expected: all tests pass — the 133-test baseline plus every test added in Tasks 25-29 and all preceding phases (cumulative; do not expect an exact number). Only the 3 known `network_analysis.py` UserWarnings (lines 122, 134, 186); any other warning is a defect. (This phase's own additions are Task 25 x1, Task 26 x1, Task 27 x2, Task 28 x3, Task 29 x2 = 9.)
- [ ] **Step 2: Import sanity**
Run: `micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: prints `app OK` with no exception — confirms `load_default_data()` still succeeds and the rewritten feedback module imports (`submit_feedback_async`, not the now-unused `submit_feedback`) cleanly.
- [ ] **Step 3: Tag**
```bash
git tag audit3-phase4
```

---

# PHASE 5 — Deployment

> Spec items 5.1–5.6 (`docs/superpowers/specs/2026-09-05-econetpy-audit-remediation-3-design.md`). Decision 5: do not restructure `deploy.sh` — the allowlist-vs-rsync redesign stays out; these tasks make it runnable and honest. Decision 6: delete the R-era `deployment/` directory outright.
>
> There is no pytest for shell code. Verification per task is `bash -n deploy.sh` (syntax) plus a real RED/GREEN demonstration: either sourcing a self-contained slice of `deploy.sh` and calling the function directly in a subshell, or a structural `grep` when execution would touch the network/systemd/sudo. Every RED command below was run against the current file and its output is quoted.

---

### Task 31: Log directory created before first log line; `pipefail`; sourceable without running `main` (`5.1`)

**Files:**
- Modify: `deploy.sh:25` (`set -e`), `deploy.sh:46-50` (`LOG_DIR`/`LOG_FILE`), `deploy.sh:697` (`main "$@"` tail call)
- Test: none (shell-only; verified via subshell execution and `grep`, shown below)

**Interfaces:**
- Consumes: nothing
- Produces: `deploy.sh` becomes safe to `source` (functions/vars defined, `main` not invoked) because the trailing call is now guarded by `[[ "${BASH_SOURCE[0]}" == "${0}" ]]`. Every later task in this phase sources the file this way to call one function in isolation: `source ./deploy.sh; <override vars>; <call function>`.

Current code (verified):
```
25	set -e  # Exit on error
...
46	# Local paths
47	PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
48	LOG_DIR="${PROJECT_ROOT}/deployment_logs"
49	TIMESTAMP=$(date +%Y%m%d_%H%M%S)
50	LOG_FILE="${LOG_DIR}/deploy_${TIMESTAMP}.log"
```
```
140	log() {
141	  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $@"
142	  echo "$msg" | tee -a "$LOG_FILE"
143	}
```
`LOG_DIR` is only ever `mkdir -p`'d inside `check_prerequisites` (line 252-255), but `main()` calls `log_info "Deployment started"` at line 645 — 13 lines before it calls `check_prerequisites` at line 658. The very first log line in every run writes through a directory that does not exist yet. The script's last line is a bare `main "$@"` (line 697), so sourcing it for testing runs the whole deployment.

- [ ] **Step 1: Write the failing test (RED, run now)**
```bash
cd "/c/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/EconetPy"
rm -rf deployment_logs
bash -c '
set -e
source <(sed -n "1,161p" deploy.sh)   # vars + print_msg/log/log_info/log_warn/log_error only, no main
log_info "probe line"
'
echo "exit=$?"
```
- [ ] **Step 2: Run to confirm RED**
Run the command in Step 1.
Expected: FAIL — `tee: /…/deployment_logs/deploy_<ts>.log: No such file or directory`, non-zero exit, because `mkdir -p "$LOG_DIR"` only exists inside `check_prerequisites`, which this slice never calls.
- [ ] **Step 3: Create the log dir at assignment time; add `pipefail`; guard `main`**
```bash
# line 25
set -e  # Exit on error
set -o pipefail
```
```bash
# lines 46-51
# Local paths
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/deployment_logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/deploy_${TIMESTAMP}.log"
mkdir -p "$LOG_DIR"
```
```bash
# line 697 (was: main "$@")
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
```
(Leave the now-redundant `if [ ! -d "$LOG_DIR" ]; then mkdir -p "$LOG_DIR"; ...; fi` block inside `check_prerequisites` — it is harmless and idempotent; removing it is not required by 5.1.)
- [ ] **Step 4: Run to confirm GREEN, plus the guard check**
```bash
rm -rf deployment_logs
bash -c '
set -e
source <(sed -n "1,164p" deploy.sh)
log_info "probe line"
'
echo "exit=$?"
ls deployment_logs/*.log
bash -n deploy.sh
grep -n 'BASH_SOURCE\[0\]' deploy.sh
```
Expected: PASS — `probe line` logged, `exit=0`, one log file listed, `bash -n` silent (exit 0), and the `grep` finds the guard.
- [ ] **Step 5: Commit**
```bash
git add deploy.sh
git commit -m "fix: deploy.sh creates log dir before first log line, adds pipefail, guards main()"
```

---

### Task 32: FILES pre-flight/verification use `-e` not `-f`; drop `BalticFW.pkl` from the required list (`5.2`)

**Files:**
- Modify: `deploy.sh:69-81` (`FILES` array), `deploy.sh:306-323` (`check_prerequisites` file loop), `deploy.sh:579-597` (`verify_deployment` file loop)
- Test: none (shell-only)

**Interfaces:**
- Consumes: the sourceable `deploy.sh` from Task 31 (`source ./deploy.sh` does not run `main`)
- Produces: nothing further tasks depend on

Current code (verified):
```
69	FILES=(
70	  "app.py"
71	  "network_analysis.py"
72	  "network_viz.py"
73	  "load_data.py"
74	  "BalticFW.pkl"
75	  "BalticFW_metadata.json"
76	  "requirements.txt"
77	  "README.md"
78	  "README_PYTHON.md"
79	  "www/"
80	  "examples/"
81	)
```
```
308	  local missing_files=()
309	  for file in "${FILES[@]}"; do
310	    if [ ! -f "$file" ]; then
311	      log_warn "File not found: $file"
312	      missing_files+=("$file")
313	    fi
314	  done
```
`"www/"` and `"examples/"` are directories; `[ -f "www/" ]` is false for a directory, so these two entries are reported "not found" on every run regardless of `--force`. `BalticFW.pkl` is gitignored (`.gitignore:45`) and rebuilt locally by `load_data.py` — it will be genuinely absent on a fresh clone, wrongly forcing `--force` for a normal first deploy. `verify_deployment` (lines 581-597) has the identical `[ -f ... ]` bug against the same array, both in the local and SSH branches (`[ -f ${APP_DEPLOY_PATH}/${file} ]` / the SSH `"[ -f ...]"` string).

- [ ] **Step 1: Write the failing test (RED, run now)**
```bash
cd "/c/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/EconetPy"
bash -c '
source ./deploy.sh
IS_LOCAL_DEPLOYMENT=true
FORCE=true
SHINY_SERVER_ROOT=/tmp
check_prerequisites
' 2>&1 | grep -E "File not found: (www/|examples/)"
```
- [ ] **Step 2: Run to confirm RED**
Run the command in Step 1.
Expected: FAIL (in the "test proves the bug" sense — it PASSES/matches, proving the bug) — output contains both `File not found: www/` and `File not found: examples/` even though both directories exist in the repo.
- [ ] **Step 3: Use `-e`, drop `BalticFW.pkl`**
```bash
# lines 69-80 (BalticFW.pkl line removed)
FILES=(
  "app.py"
  "network_analysis.py"
  "network_viz.py"
  "load_data.py"
  "BalticFW_metadata.json"
  "requirements.txt"
  "README.md"
  "README_PYTHON.md"
  "www/"
  "examples/"
)
```
```bash
# line 310 (check_prerequisites)
    if [ ! -e "$file" ]; then
```
```bash
# lines 583/591 (verify_deployment, both branches)
      if [ -e "${APP_DEPLOY_PATH}/${file}" ]; then
...
      if ssh "${SERVER_USER}@${SERVER_HOST}" "[ -e ${APP_DEPLOY_PATH}/${file} ]"; then
```
- [ ] **Step 4: Run to confirm GREEN**
```bash
bash -c '
source ./deploy.sh
IS_LOCAL_DEPLOYMENT=true
FORCE=true
SHINY_SERVER_ROOT=/tmp
check_prerequisites
' 2>&1 | grep -E "File not found: (www/|examples/|BalticFW.pkl)"
echo "grep_exit=$?"
bash -n deploy.sh
```
Expected: PASS — grep finds nothing (`grep_exit=1`), `bash -n` silent.
- [ ] **Step 5: Commit**
```bash
git add deploy.sh
git commit -m "fix: deploy.sh pre-flight/verify use -e for directories, drop gitignored pickle from required files"
```

---

### Task 33: Package install, service restart, and post-deploy verification become fatal unless `--force`; stderr no longer suppressed (`5.3`)

**Files:**
- Modify: `deploy.sh:486-512` (`install_packages`), `deploy.sh:514-562` (`restart_shiny_server`), `deploy.sh:568-615` (`verify_deployment`)
- Test: none (shell-only)

**Interfaces:**
- Consumes: the sourceable `deploy.sh` from Task 31
- Produces: nothing further tasks depend on

Current code (verified):
```
499	  if [ "$IS_LOCAL_DEPLOYMENT" = true ]; then
500	    bash -c "$install_cmd" || {
501	      log_warn "Package installation had some issues (may need manual check)"
502	      log_warn "Try manually: conda activate ${CONDA_ENV_NAME} && pip install -r ${APP_DEPLOY_PATH}/requirements.txt"
503	    }
504	  else
505	    ssh "${SERVER_USER}@${SERVER_HOST}" "$install_cmd" || {
506	      log_warn "Package installation had some issues (may need manual check)"
507	      log_warn "Try manually on server: conda activate ${CONDA_ENV_NAME} && pip install -r ${APP_DEPLOY_PATH}/requirements.txt"
508	    }
509	  fi
```
```
529	    if sudo systemctl restart "${service_name}" 2>/dev/null; then
...
543	    if ssh "${SERVER_USER}@${SERVER_HOST}" "sudo systemctl restart ${service_name}" 2>/dev/null; then
```
```
603	  if command -v curl &> /dev/null; then
604	    if curl -s -f "$app_url" > /dev/null; then
605	      log_info "Application is accessible!"
606	    else
607	      log_warn "Could not verify application accessibility"
608	      log_warn "Please check manually: $app_url"
609	    fi
610	  else
```
None of the three failure branches ever aborts the script (`set -e` doesn't fire because the `||`/`if` consumes the non-zero status), and `2>/dev/null` on the two `systemctl restart` invocations throws away the actual error text.

- [ ] **Step 1: Write the failing tests (RED, run now)**
```bash
cd "/c/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/EconetPy"

# (a) install_packages: force a broken conda path, confirm it does NOT abort
bash -c '
source ./deploy.sh
IS_LOCAL_DEPLOYMENT=true; DRY_RUN=false; FORCE=false
CONDA_PATH=/nonexistent-conda-path; APP_DEPLOY_PATH=/tmp
install_packages
echo REACHED_AFTER_INSTALL
'
echo "a_exit=$?"

# (b) restart_shiny_server: the systemctl restart cannot succeed on this dev box,
#     confirm its stderr is suppressed + no abort
bash -c '
source ./deploy.sh
IS_LOCAL_DEPLOYMENT=true; DRY_RUN=false; FORCE=false; APP_NAME=EcoNeTool
restart_shiny_server
echo REACHED_AFTER_RESTART
' 2>/tmp/restart_stderr.txt
echo "b_exit=$?"; echo "--- captured stderr ---"; cat /tmp/restart_stderr.txt

# (c) verify_deployment: nothing listens on 127.0.0.1:8000, confirm non-2xx does NOT abort
bash -c '
source ./deploy.sh
IS_LOCAL_DEPLOYMENT=true; DRY_RUN=false; FORCE=false
SERVER_HOST=127.0.0.1; APP_DEPLOY_PATH=/tmp
verify_deployment
echo REACHED_AFTER_VERIFY
'
echo "c_exit=$?"
```
- [ ] **Step 2: Run to confirm RED**
Run the three commands in Step 1.
Expected: FAIL (bug confirmed) — all three print their `REACHED_AFTER_*` line and exit `0`; `/tmp/restart_stderr.txt` is **empty**, because whatever the failing `sudo systemctl restart` wrote to stderr is swallowed by `2>/dev/null`.

**Environment note — do not pin the assertion to a specific message.** The pass/fail criterion is
environment-independent: *the stderr file is empty before the fix and non-empty (containing a real
error) after it.* The actual text differs per box. On this Windows dev machine `sudo` resolves to
`C:\WINDOWS\system32\sudo` (the Windows shim, not the Unix one), which exits `5` and writes
`Sudo is disabled on this machine. To enable it, go to the Developer Settings page in the Settings
app` (~138 bytes) to **stderr** — verified. It is *not* `systemctl: command not found`. What matters
for the test is only that `sudo systemctl restart` returns non-zero (so the `else` branch runs) and
that its stderr reaches the capture file once `2>/dev/null` is removed. On the Linux server the same
criterion holds with a systemd error message instead.
- [ ] **Step 3: Make each failure fatal unless `--force`; stop swallowing stderr**
```bash
# lines 499-509 (install_packages)
  if [ "$IS_LOCAL_DEPLOYMENT" = true ]; then
    bash -c "$install_cmd" || {
      log_error "Package installation failed"
      log_error "Try manually: conda activate ${CONDA_ENV_NAME} && pip install -r ${APP_DEPLOY_PATH}/requirements.txt"
      if [ "$FORCE" != true ]; then
        exit 1
      fi
      log_warn "Continuing despite failed package installation (--force)"
    }
  else
    ssh "${SERVER_USER}@${SERVER_HOST}" "$install_cmd" || {
      log_error "Package installation failed"
      log_error "Try manually on server: conda activate ${CONDA_ENV_NAME} && pip install -r ${APP_DEPLOY_PATH}/requirements.txt"
      if [ "$FORCE" != true ]; then
        exit 1
      fi
      log_warn "Continuing despite failed package installation (--force)"
    }
  fi
```
```bash
# lines 527-540 (restart_shiny_server, local branch — remove 2>/dev/null, add fatal exit)
  if [ "$IS_LOCAL_DEPLOYMENT" = true ]; then
    # Local restart
    if sudo systemctl restart "${service_name}"; then
      log_info "Python Shiny app restarted successfully (systemctl)"
    else
      log_error "Could not restart Python Shiny app automatically"
      echo "  sudo systemctl restart ${service_name}"
      echo ""
      log_info "Or run manually in conda environment:"
      echo "  cd ${APP_DEPLOY_PATH}"
      echo "  conda activate ${CONDA_ENV_NAME}"
      echo "  shiny run --host 0.0.0.0 --port 8000 app.py"
      if [ "$FORCE" != true ]; then
        exit 1
      fi
    fi
  else
    # Remote restart via SSH
    if ssh "${SERVER_USER}@${SERVER_HOST}" "sudo systemctl restart ${service_name}"; then
      log_info "Python Shiny app restarted successfully (systemctl)"
    else
      log_error "Could not restart Python Shiny app automatically"
      echo "  ssh ${SERVER_USER}@${SERVER_HOST}"
      echo "  sudo systemctl restart ${service_name}"
      echo ""
      log_info "Or run manually in conda environment:"
      echo "  ssh ${SERVER_USER}@${SERVER_HOST}"
      echo "  cd ${APP_DEPLOY_PATH}"
      echo "  conda activate ${CONDA_ENV_NAME}"
      echo "  shiny run --host 0.0.0.0 --port 8000 app.py"
      if [ "$FORCE" != true ]; then
        exit 1
      fi
    fi
  fi
```
```bash
# lines 603-611 (verify_deployment)
  if command -v curl &> /dev/null; then
    if curl -s -f "$app_url" > /dev/null; then
      log_info "Application is accessible!"
    else
      log_error "Application did not return a successful (2xx) response"
      log_error "Please check manually: $app_url"
      if [ "$FORCE" != true ]; then
        exit 1
      fi
    fi
  else
```
- [ ] **Step 4: Run to confirm GREEN**
```bash
bash -c '
source ./deploy.sh
IS_LOCAL_DEPLOYMENT=true; DRY_RUN=false; FORCE=false
CONDA_PATH=/nonexistent-conda-path; APP_DEPLOY_PATH=/tmp
install_packages
echo REACHED_AFTER_INSTALL
'
echo "a_exit=$?"

bash -c '
source ./deploy.sh
IS_LOCAL_DEPLOYMENT=true; DRY_RUN=false; FORCE=false; APP_NAME=EcoNeTool
restart_shiny_server
echo REACHED_AFTER_RESTART
' 2>/tmp/restart_stderr.txt
echo "b_exit=$?"; cat /tmp/restart_stderr.txt

bash -c '
source ./deploy.sh
IS_LOCAL_DEPLOYMENT=true; DRY_RUN=false; FORCE=false
SERVER_HOST=127.0.0.1; APP_DEPLOY_PATH=/tmp
verify_deployment
echo REACHED_AFTER_VERIFY
'
echo "c_exit=$?"
bash -n deploy.sh
```
Expected: PASS — none of the three print their `REACHED_AFTER_*` line, all three `_exit` values are `1`, and `/tmp/restart_stderr.txt` is now **non-empty and contains a real error message** from the failed `sudo systemctl restart` (on this Windows dev box that text is `Sudo is disabled on this machine…`; on the Linux server it is a systemd error — assert non-emptiness, not the wording). Check it with `[ -s /tmp/restart_stderr.txt ] && echo STDERR_CAPTURED || echo STDERR_STILL_SWALLOWED`. `bash -n` silent.
- [ ] **Step 5: Commit**
```bash
git add deploy.sh
git commit -m "fix: deploy.sh package install, restart and verification are fatal unless --force; stop swallowing stderr"
```

---

### Task 34: Delete the R-era `deployment/` directory; point README at DEPLOYMENT.md (`5.4`)

**Files:**
- Modify: `README.md:196`
- Delete: `deployment/deploy.sh`, `deployment/pre-deploy-check.R`, `deployment/install_dependencies.R`, `deployment/shiny-server.conf`, `deployment/README.md`
- Test: none (shell-only)

**Interfaces:**
- Consumes: nothing
- Produces: nothing further tasks depend on

The design spec's task list (5.4) names four files to delete (`deploy.sh`, `pre-deploy-check.R`, `install_dependencies.R`, `shiny-server.conf`); its Decision 6 says to delete the whole `deployment/` directory. Deleting only the four leaves `deployment/README.md` behind, dangling — it still documents `deploy.sh --shiny-server`, `pre-deploy-check.R`, `install_dependencies.R` and `shiny-server.conf`, all now gone (confirmed by reading the file: e.g. `cd deployment && sudo ./deploy.sh --shiny-server`, `Rscript pre-deploy-check.R`, `Rscript install_dependencies.R`). This task follows Decision 6 and removes the whole directory, `README.md` included — the one place the two instructions disagree, noted for the record.

`README.md:196` is the only reference to `deployment/` anywhere in tracked `.md`/`.py` files (verified: `grep -rn "deployment/" --include="*.md" .` and `grep -rln "deployment/" --include="*.py" .`; `DEPLOYMENT.md` and `conftest.py` have no hits).

Current code (verified):
```
193	## 📚 Documentation
194	
195	- **Format Examples**: Check the `examples/` directory
196	- **Deployment Guide**: See `deployment/README.md`
```

- [ ] **Step 1: Write the failing test (RED, run now)**
```bash
cd "/c/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/EconetPy"
git ls-files deployment/
grep -n "deployment/README.md" README.md
```
- [ ] **Step 2: Run to confirm RED**
Run the commands in Step 1.
Expected: FAIL (bug confirmed) — `git ls-files deployment/` lists all 5 tracked files; `grep` matches `README.md:196: - **Deployment Guide**: See \`deployment/README.md\``.
- [ ] **Step 3: Delete the directory, fix the README reference**
```bash
git rm -r deployment/
```
```markdown
<!-- README.md:196, was: - **Deployment Guide**: See `deployment/README.md` -->
- **Deployment Guide**: See `DEPLOYMENT.md`
```
- [ ] **Step 4: Run to confirm GREEN**
```bash
git ls-files deployment/
echo "ls_exit=$?"
[ -d deployment ] && echo STILL_EXISTS || echo GONE
grep -rn "deployment/" README.md DEPLOYMENT.md
echo "grep_exit=$?"
```
Expected: PASS — `git ls-files deployment/` prints nothing, `GONE` printed, the `grep` across both docs prints nothing (`grep_exit=1`).
- [ ] **Step 5: Commit**
```bash
git add -A README.md deployment
git commit -m "chore: delete R-era deployment/ directory, point README at DEPLOYMENT.md"
```

---

### Task 35: Rebuild the data pickle on the server after transfer (`5.5`)

**Files:**
- Modify: `deploy.sh` — new function `rebuild_data_pickle()` placed after `install_packages()` (currently ends `deploy.sh:512`) and before `restart_shiny_server()` (currently starts `deploy.sh:514`); call added to `main()` between the existing `install_packages` and `restart_shiny_server` calls (`deploy.sh:662-663`)
- Test: none (shell-only)

**Interfaces:**
- Consumes: `install_packages`, `restart_shiny_server`, `CONDA_PATH`, `CONDA_ENV_NAME`, `APP_DEPLOY_PATH`, `IS_LOCAL_DEPLOYMENT`, `DRY_RUN`, `FORCE`, `SERVER_USER`, `SERVER_HOST` — all already defined earlier in `deploy.sh`
- Produces: `rebuild_data_pickle` (new function), invoked once from `main()`

Currently `deploy.sh` never rebuilds the pickle on the server: the server runs on whatever `BalticFW.pkl` happened to arrive, or on none at all (it is gitignored, so a fresh clone has none).

Note precisely what does and does not determine that. The `FILES` array does **not** gate what ships — `deploy.sh:60-65` says so in its own comment: *"This curated list is used ONLY for pre-flight verification … it does NOT gate what actually ships. The rsync step below mirrors the working tree wholesale (./), filtered only by EXCLUDE_PATTERNS, so any tracked file not excluded is transferred regardless of whether it appears in FILES."* So neither the current `"BalticFW.pkl"` entry nor Task 32's removal of it changes whether the pickle is transferred; what ships is whatever the developer's working tree happens to hold at rsync time (a stale local pickle, or nothing). That is exactly why the server must rebuild it from the tracked sources itself.

Confirmed by `grep -n "load_data" deploy.sh` today: the only hit is the `FILES` array entry `"load_data.py"` (the script itself, not an invocation) — there is no `python load_data.py` call and no function named `rebuild`/`rebuild_data_pickle` anywhere in the file.

- [ ] **Step 1: Write the failing test (RED, run now)**
```bash
cd "/c/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/EconetPy"
grep -n "rebuild_data_pickle\|python load_data.py" deploy.sh
echo "exit=$?"
```
- [ ] **Step 2: Run to confirm RED**
Run the command in Step 1.
Expected: FAIL — no match, `exit=1`: there is no pickle-rebuild step today, so the server ends up running on whatever pickle `rsync` happened to transfer (or none).
- [ ] **Step 3: Add the rebuild function and call it from `main`**
```bash
# new function, placed immediately after install_packages() (after its closing brace, before restart_shiny_server())
rebuild_data_pickle() {
  print_header "Rebuilding Data Pickle"

  if [ "$DRY_RUN" = true ]; then
    log_info "DRY RUN MODE - Skipping pickle rebuild"
    return 0
  fi

  log_info "Rebuilding BalticFW.pkl from source data on the server..."

  local rebuild_cmd="source ${CONDA_PATH}/etc/profile.d/conda.sh && conda activate ${CONDA_ENV_NAME} && cd ${APP_DEPLOY_PATH} && python load_data.py"

  if [ "$IS_LOCAL_DEPLOYMENT" = true ]; then
    bash -c "$rebuild_cmd" || {
      log_error "Failed to rebuild BalticFW.pkl"
      if [ "$FORCE" != true ]; then
        exit 1
      fi
      log_warn "Continuing despite failed pickle rebuild (--force)"
    }
  else
    ssh "${SERVER_USER}@${SERVER_HOST}" "$rebuild_cmd" || {
      log_error "Failed to rebuild BalticFW.pkl on server"
      if [ "$FORCE" != true ]; then
        exit 1
      fi
      log_warn "Continuing despite failed pickle rebuild (--force)"
    }
  fi

  log_info "Data pickle rebuild completed"
}
```
```bash
# main(), lines 662-663 (was: install_packages \n restart_shiny_server)
  install_packages
  rebuild_data_pickle
  restart_shiny_server
```
- [ ] **Step 4: Run to confirm GREEN**
```bash
grep -n "rebuild_data_pickle\|python load_data.py" deploy.sh
bash -n deploy.sh
bash -c '
source ./deploy.sh
DRY_RUN=true
rebuild_data_pickle
echo "rebuild_exit=$?"
'
```
Expected: PASS — `grep` finds the function definition, its call site in `main`, and the `python load_data.py` command string; `bash -n` silent; the dry-run invocation prints "DRY RUN MODE - Skipping pickle rebuild" and `rebuild_exit=0`.
- [ ] **Step 5: Commit**
```bash
git add deploy.sh
git commit -m "feat: deploy.sh rebuilds BalticFW.pkl on the server instead of shipping the developer's copy"
```

---

### Task 36: Drop unused packages from requirements.txt, environment.yml, and the README dependency list (`5.6`)

**Files:**
- Modify: `requirements.txt:5,21,24-25,30`, `environment.yml:25,30-32,35`, `README.md:72,78-80,83`
- Test: none (shell/docs-only)

**Interfaces:**
- Consumes: nothing
- Produces: nothing further tasks depend on

Confirmed by reading every `.py` file in the repo root:
```
$ grep -rniE "shinywidgets|great.tables|openpyxl|xlrd|plotly" *.py
(no output)
```
None of `plotly`, `great-tables`, `openpyxl`, `xlrd`, `shinywidgets` is imported anywhere. Current `requirements.txt` (verified):
```
 5	shinywidgets>=0.3.0
...
21	great-tables>=0.1.0
...
24	openpyxl>=3.1.0  # For Excel files
25	xlrd>=2.0.0      # For older Excel files
...
30	plotly>=5.14.0
```
Current `environment.yml` (verified):
```
25	  - shinywidgets>=0.3.0
...
30	  - great-tables>=0.1.0
31	  - openpyxl>=3.1.0
32	  - xlrd>=2.0.0
...
35	  - plotly>=5.14.0
```
`README.md`'s "Required Python Packages" list (regenerated in remediation #2 to agree with `requirements.txt`; verified) currently repeats the same five entries at lines 72, 78, 79, 80, 83:
```
69	- shiny>=1.0.0
70	- htmltools>=0.5.0
71	- shinyswatch>=0.4.0
72	- shinywidgets>=0.3.0
73	- networkx>=3.0
74	- pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2
75	- pandas>=2.0.0
76	- numpy>=2.0.0
77	- scipy>=1.10.0
78	- great-tables>=0.1.0
79	- openpyxl>=3.1.0
80	- xlrd>=2.0.0
81	- matplotlib>=3.7.0
82	- seaborn>=0.12.0
83	- plotly>=5.14.0
```

- [ ] **Step 1: Write the failing test (RED, run now)**
```bash
cd "/c/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/EconetPy"
grep -nE "^(shinywidgets|great-tables|openpyxl|xlrd|plotly)" requirements.txt
grep -nE "^  - (shinywidgets|great-tables|openpyxl|xlrd|plotly)" environment.yml
grep -nE "shinywidgets|great-tables|openpyxl|xlrd|plotly" README.md
```
- [ ] **Step 2: Run to confirm RED**
Run the commands in Step 1.
Expected: FAIL (bug confirmed) — all three greps match: 5 lines in `requirements.txt`, 5 lines in `environment.yml`, 5 lines in `README.md` — none of the five packages is imported, so all three files list dead dependencies.
- [ ] **Step 3: Remove the five entries from all three files**
```
# requirements.txt: delete lines 5 (shinywidgets), 21 (great-tables),
# 24-25 (openpyxl, xlrd), 30 (plotly); resulting file:
# Core Shiny Framework
shiny>=1.0.0
htmltools>=0.5.0
shinyswatch>=0.4.0  # Bootstrap themes

# Network Analysis
networkx>=3.0

# Network Visualization
pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2  # razinkele fork; not on PyPI. Requires git on PATH at install time.

# Data Processing
pandas>=2.0.0
numpy>=2.0.0

# Scientific Computing
scipy>=1.10.0

# Plotting
matplotlib>=3.7.0
seaborn>=0.12.0
```
```yaml
# environment.yml: delete the shinywidgets, great-tables, openpyxl, xlrd,
# plotly lines from `dependencies:`; resulting block:
dependencies:
  - python=3.13.*
  - git                          # required so pip can resolve git+https URLs at install time
  - shiny>=1.0.0
  - htmltools>=0.5.0
  - shinyswatch>=0.4.0
  - networkx>=3.0
  - pandas>=2.0.0
  - numpy>=2.0.0
  - scipy>=1.10.0
  - matplotlib>=3.7.0
  - seaborn>=0.12.0
  - pytest>=8.0
  - pip
  - pip:
      - pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2
```
```markdown
<!-- README.md "Required Python Packages" list: delete the shinywidgets,
     great-tables, openpyxl, xlrd, plotly lines; resulting list: -->
- shiny>=1.0.0
- htmltools>=0.5.0
- shinyswatch>=0.4.0
- networkx>=3.0
- pyvis @ git+https://github.com/razinkele/pyvis.git@v4.2
- pandas>=2.0.0
- numpy>=2.0.0
- scipy>=1.10.0
- matplotlib>=3.7.0
- seaborn>=0.12.0
```
- [ ] **Step 4: Run to confirm GREEN**
```bash
grep -nE "^(shinywidgets|great-tables|openpyxl|xlrd|plotly)" requirements.txt
echo "req_exit=$?"
grep -nE "^  - (shinywidgets|great-tables|openpyxl|xlrd|plotly)" environment.yml
echo "env_exit=$?"
grep -nE "shinywidgets|great-tables|openpyxl|xlrd|plotly" README.md
echo "readme_exit=$?"
```
Expected: PASS — all three greps find nothing (`req_exit=1`, `env_exit=1`, `readme_exit=1`); `requirements.txt`/`environment.yml`/README stay in agreement on the same trimmed package list.
- [ ] **Step 5: Commit**
```bash
git add requirements.txt environment.yml README.md
git commit -m "chore: drop unused plotly/great-tables/openpyxl/xlrd/shinywidgets from deps and README"
```

---

### Task 37: Gate — full suite, app import, deploy.sh syntax, tag (`gate`)

**Files:** none (verification only)

**Interfaces:**
- Consumes: nothing
- Produces: `audit3-phase5` git tag

- [ ] **Step 1: Full pytest suite**
Run: `micromamba run -n shiny python -m pytest`
Expected: all tests pass — the 133-test baseline plus every test added in Tasks 31-36 and all preceding phases (cumulative; do not expect an exact number). Only the 3 known `network_analysis.py` UserWarnings (lines 122, 134, 186); any other warning is a defect. (This phase itself touches no `.py` behavior — deploy.sh and dependency-manifest edits only — so the count should be unchanged from the Phase 4 gate, whatever that count was.)
- [ ] **Step 2: App import still clean**
Run: `micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: prints `app OK`.
- [ ] **Step 3: deploy.sh syntax and structural checks**
```bash
bash -n deploy.sh
grep -n 'BASH_SOURCE\[0\]' deploy.sh
grep -c '"BalticFW.pkl"' deploy.sh
grep -n "rebuild_data_pickle" deploy.sh
[ -d deployment ] && echo STILL_EXISTS || echo GONE
```
Expected: `bash -n` silent; guard line found; `BalticFW.pkl` count `0`; `rebuild_data_pickle` found; `GONE` printed.
- [ ] **Step 4: Tag**
```bash
git tag audit3-phase5
```

---

# PHASE 6 — Remaining UI and latent items

> Baseline note: line numbers below were verified against the current tree (`feature/audit-remediation-2`,
> which is `master` + remediation #2, matching the spec's "PAGES registry" and "menu-effect loop" already
> in place). Phases 1-5 land first per the build order; if any of them touch `network_plot`,
> `download_network`, `flux_network_plot`, or the biomass-plot bodies, re-`grep -n` the anchor before
> editing — the surrounding lines may have shifted by a few lines, the call shapes quoted here will not
> have changed.

### Task 38: Page inputs persist across menu navigation (`6.1` part A)

**Files:**
- Modify: `app.py:695-703` (menu-effect loop), `app.py:843-847` (`main_content`)
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: `PAGES` registry (`app.py:372-380`, unchanged: `{page_key: (menu_input_id, builder)}`)
- Produces: a `ui.navset_hidden(id="page_nav", ...)` mounted once per session; later tasks (none in this phase) may rely on `"page_nav"` as the update-target id

Today `main_content` reads `current_page()` and rebuilds `builder()` from scratch on every navigation:
```python
    @output
    @render.ui
    def main_content():
        _, builder = PAGES.get(current_page(), ("", dashboard_ui))
        return builder()
```
Because `@render.ui` invalidates and rebuilds whenever a reactive read inside it changes, every click of a
`menu_*` link destroys the whole previous page's DOM — including any `ui.input_select`/`ui.input_slider`/
`ui.input_numeric` on it — and recreates it from the builder's hard-coded defaults. That is why
`network_type`, `network_height`, and `temperature` reset every time a user leaves and returns to a tab.

- [ ] **Step 1: Write the failing structural tests**
```python
def test_main_content_builds_once_no_current_page_read():
    """main_content must not read current_page() -- doing so forces Shiny to
    tear down and rebuild the whole page (destroying every input.*, resetting
    network_type/network_height/temperature to their defaults) on every menu
    click. It must build a static ui.navset_hidden(...) once instead, so
    every page's inputs stay mounted across navigation."""
    import ast
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    main_content_fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "main_content"
    )
    name_calls = {n.func.id for n in ast.walk(main_content_fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    attr_calls = {n.func.attr for n in ast.walk(main_content_fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "current_page" not in name_calls, \
        "main_content still reads current_page() -- it rebuilds and destroys every page's inputs on each navigation"
    assert "navset_hidden" in attr_calls, \
        "main_content must build ui.navset_hidden(...) wrapping all PAGES builders so inputs persist"


def test_menu_effect_updates_hidden_navset():
    """Now that main_content builds once, page switching must happen by
    telling the client-side navset which panel to show, not by re-rendering
    server-side UI."""
    import ast
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    make_effect_fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_make_menu_effect"
    )
    attr_calls = {n.func.attr for n in ast.walk(make_effect_fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "update_navset" in attr_calls, \
        "_make_menu_effect must call ui.update_navset('page_nav', selected=page_key) to switch the now-static navset"
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_main_content_builds_once_no_current_page_read test_app_structure.py::test_menu_effect_updates_hidden_navset -v`
Expected: both FAIL. `main_content`'s body today is exactly `_, builder = PAGES.get(current_page(), ("", dashboard_ui)); return builder()` — `current_page` is in `name_calls` and `navset_hidden` is not in `attr_calls`. `_make_menu_effect`'s body today is exactly `current_page.set(page_key)` — no `update_navset` call anywhere.
- [ ] **Step 3: Build the static hidden navset once; drive it from the menu effects**
Replace `app.py:843-847`:
```python
    @output
    @render.ui
    def main_content():
        return ui.navset_hidden(
            *[ui.nav_panel(key, builder(), value=key) for key, (_, builder) in PAGES.items()],
            id="page_nav",
            selected="dashboard",
        )
```
Replace `app.py:695-703`:
```python
    def _make_menu_effect(page_key, menu_input_id):
        @reactive.effect
        @reactive.event(getattr(input, menu_input_id))
        def _():
            current_page.set(page_key)
            ui.update_navset("page_nav", selected=page_key)
        return _

    for _page_key, (_menu_input_id, _builder) in PAGES.items():
        _make_menu_effect(_page_key, _menu_input_id)
```
`current_page` reactive.Value is kept (it still feeds the feedback-modal `current_tab` context at
`app.py:801`); it now just tracks the page key for that purpose rather than driving a rebuild.
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -m pytest -q`
Expected: both new tests PASS; full suite green (no test drives a live Shiny session against `main_content`'s output, so no other test asserts its old return shape).
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "fix: mount all pages once via hidden navset so inputs persist across navigation"
```

---

### Task 39: `flux_results` records the temperature used; the panel displays it (`6.1` part B)

**Files:**
- Modify: `app.py:1089-1152` (`calculate_fluxes` effect), `app.py:1154-1170` (`flux_indicators`)
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: nothing from Task 38. **Depends on Phase 2 Task 11 having landed**, which already
  rewrote both edit sites: it inserted the `if not validation['balanced']:` warning branch above
  `flux_results.set({...})` and added the `balance_line` computation plus a `{balance_line}` row to
  `flux_indicators`. This task ADDS one dict key and one panel line to Task 11's version — it does
  not replace it. Locate both sites by the quoted text below, not by line number; Task 11's insertion
  has already shifted everything in this region.
- Produces: `flux_results()` dict now carries a `'temperature'` key (in addition to
  `'flux_matrix'`, `'losses'`, `'validation'`)

The temperature the solver actually ran with is the local `temp = input.temperature()`
(`app.py:1095` pre-Task-11), fed to `calculate_losses(...)`, but it is never recorded. As left by
Task 11 the call site ends:
```python
        if not validation['balanced']:
            logger.warning(
                "Flux equilibrium not balanced: max_imbalance=%.6g",
                validation['max_imbalance'],
            )
            ui.notification_show(
                f"Flux solution is not fully balanced (max imbalance "
                f"{validation['max_imbalance']:.4g}). Results may be approximate.",
                type="warning",
                duration=8,
            )

        flux_results.set({
            'flux_matrix': flux_matrix,
            'losses': losses,
            'validation': validation
        })
```
and `flux_indicators`, as left by Task 11, reports the balance verdict but never the temperature:
```python
        balance_line = (
            "  Equilibrium: BALANCED" if validation['balanced']
            else f"  Equilibrium: NOT BALANCED (max imbalance {validation['max_imbalance']:.4g})"
        )

        return f"""
Flux-Based Indicators:

  Link-Weighted Connectance (lwC): {indicators['lwC']:.4f}
  Link-Weighted Generality (lwG): {indicators['lwG']:.4f}
  Link-Weighted Vulnerability (lwV): {indicators['lwV']:.4f}
{balance_line}
        """
```
A user who recalculates at a different temperature has no way to tell, from the panel, which temperature
produced the matrix currently on screen.

- [ ] **Step 1: Write the failing structural test**
```python
def test_flux_results_records_and_displays_temperature_used():
    """flux_results must record the temperature the calculation actually ran
    with, and flux_indicators must display it."""
    import ast
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source)

    calc_effect = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_":
            deco_src = "\n".join(ast.unparse(d) for d in node.decorator_list)
            if "calculate_fluxes" in deco_src:
                calc_effect = node
                break
    assert calc_effect is not None, "could not find the calculate_fluxes reactive.effect"

    dict_keys = set()
    for node in ast.walk(calc_effect):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "set" and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "flux_results"):
            for arg in node.args:
                if isinstance(arg, ast.Dict):
                    dict_keys = {k.value for k in arg.keys if isinstance(k, ast.Constant)}
    assert "temperature" in dict_keys, \
        "flux_results.set(...) is missing a 'temperature' key recording the temperature used"

    indicators_fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "flux_indicators"
    )
    fn_src = ast.get_source_segment(source, indicators_fn)
    assert "temperature" in fn_src.lower(), \
        "flux_indicators panel does not display the recorded temperature"
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_flux_results_records_and_displays_temperature_used -v`
Expected: FAIL at the `"temperature" in dict_keys` assertion — the `flux_results.set({...})` dict
literal (Task 11's version) has exactly the keys `{'flux_matrix', 'losses', 'validation'}`.
- [ ] **Step 3: Record and display it — add one key and one line to Task 11's version**

Do NOT rewrite the surrounding block: the `if not validation['balanced']:` branch above the `set()`
call and the `balance_line` computation in `flux_indicators` are Task 11's and stay exactly as they
are. `temp` is the existing local in the `calculate_fluxes` effect (`temp = input.temperature()`),
already in scope at the `set()` call.

Add the `'temperature': temp` key to the existing `flux_results.set({...})` call (find it by text):
```python
        flux_results.set({
            'flux_matrix': flux_matrix,
            'losses': losses,
            'validation': validation,
            'temperature': temp
        })
```
Add one line to the existing `flux_indicators` f-string, above the lwC line and keeping Task 11's
`{balance_line}` row:
```python
        return f"""
Flux-Based Indicators:

  Temperature Used (°C): {flux_results()['temperature']:.1f}
  Link-Weighted Connectance (lwC): {indicators['lwC']:.4f}
  Link-Weighted Generality (lwG): {indicators['lwG']:.4f}
  Link-Weighted Vulnerability (lwV): {indicators['lwV']:.4f}
{balance_line}
        """
```
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -m pytest -q`
Expected: PASS; full suite green.
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "fix: flux_results records the temperature used; flux_indicators displays it"
```

---

### Task 40: Cache the built network on data only; height slider drives the iframe, not the network object (`6.2`)

**Files:**
- Modify: `app.py:644-664` (`_build_network`), `app.py:913-932` (`network_plot`, `download_network`), `app.py:1209-1216` (`flux_network_plot`)
- Test: `test_app_structure.py`

**Interfaces:**
- Consumes: `colors_cached()`, `trophic_levels_cached()` (existing `@reactive.calc`s, unchanged)
- Produces: `topology_network_cached()` and `flux_network_cached()`, two `@reactive.calc`-decorated
  functions taking no arguments, replacing `_build_network(kind, height=...)`. `flux_network_cached()`
  reads `flux_results()['flux_matrix']` unconditionally — callers MUST guard `flux_results() is not None`
  first, exactly as `_build_network("flux", ...)` required before.

Today `_build_network` is a plain function, re-invoked (and fully rebuilt: node styling, tooltips, edges,
physics) every time `network_plot` re-renders because `input.network_height()` is one of its reads:
```python
    def _build_network(kind, height="600px"):
        ...
        G = current_network()
        info = current_species_info()
        node_colors, _ = colors_cached()
        tl = trophic_levels_cached()
        if kind == "topology":
            return create_topology_network(
                G, species_names=info['species'].tolist(),
                functional_groups=info['fg'].tolist(),
                biomass=info['meanB'].values, colors=node_colors,
                height=height, trophic_levels=tl)
        return create_flux_network(
            G, species_names=info['species'].tolist(),
            functional_groups=info['fg'].tolist(),
            biomass=info['meanB'].values, colors=node_colors,
            flux_matrix=flux_results()['flux_matrix'],
            height=height, trophic_levels=tl)
```
```python
    @output
    @render.ui
    @safe_render("ui")
    def network_plot():
        h = f"{input.network_height()}px"
        if input.network_type() == "Topology":
            net = _build_network("topology", height=h)
        else:
            if flux_results() is None:
                return ui.p("Please calculate fluxes first in the Energy Fluxes tab.")
            net = _build_network("flux", height=h)
        return render_network(net, height=h, width="100%")

    @render.download(filename="econetool_network.html")
    def download_network():
        if input.network_type() == "Flux-Weighted" and flux_results() is not None:
            net = _build_network("flux")
        else:
            net = _build_network("topology")
        yield net.generate_html()
```
`render_network(net, height=h, ...)` (`pyvis/shiny/wrapper.py:214-273`) already sets the iframe's own
`height`/`style` independent of `net`'s internal height — so the height slider never needed to reach the
builder at all.

- [ ] **Step 1: Write the failing structural test**
```python
def test_network_build_cached_independent_of_height_slider():
    """The pyvis Network build must live in a @reactive.calc keyed on data
    only -- moving the height slider must not rebuild node styling, tooltips,
    and physics from scratch every time."""
    import ast
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source)

    calc_fn_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            deco_names = {d.attr if isinstance(d, ast.Attribute) else getattr(d, "id", None)
                          for d in node.decorator_list}
            if "calc" in deco_names:
                calc_fn_names.add(node.name)

    build_calls = [n for n in ast.walk(tree)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in {"create_topology_network", "create_flux_network"}]
    assert build_calls, "no create_topology_network/create_flux_network call sites found"

    all_fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    for call in build_calls:
        enclosing = min(
            (fn for fn in all_fns if fn.lineno <= call.lineno <= fn.end_lineno),
            key=lambda fn: fn.end_lineno - fn.lineno,
        )
        assert enclosing.name in calc_fn_names, (
            f"create_*_network call at line {call.lineno} is in {enclosing.name!r}, "
            "not a @reactive.calc -- it will rebuild on every height-slider tick"
        )
        for kw in call.keywords:
            if kw.arg == "height":
                assert isinstance(kw.value, ast.Constant), (
                    f"height= passed to the network builder at line {call.lineno} must be a fixed "
                    f"constant, not derived from input.network_height() -- got {ast.dump(kw.value)}"
                )
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py::test_network_build_cached_independent_of_height_slider -v`
Expected: FAIL — both `create_topology_network(...)` and `create_flux_network(...)` calls today are
enclosed by `_build_network`, a plain `def` with no `@reactive.calc` decorator, so `enclosing.name in
calc_fn_names` is `False`.
- [ ] **Step 3: Split into two data-only reactive.calcs**
Replace `app.py:644-664`:
```python
    @reactive.calc
    def topology_network_cached():
        """Build the topology pyvis Network from the shared caches. Cached on
        data only -- NOT on the height slider, so resizing does not rebuild
        node styling/tooltips/physics from scratch."""
        G = current_network()
        info = current_species_info()
        node_colors, _ = colors_cached()
        tl = trophic_levels_cached()
        return create_topology_network(
            G, species_names=info['species'].tolist(),
            functional_groups=info['fg'].tolist(),
            biomass=info['meanB'].values, colors=node_colors,
            height="100%", trophic_levels=tl)

    @reactive.calc
    def flux_network_cached():
        """Build the flux-weighted pyvis Network. Cached on data + flux_results
        only -- NOT on the height slider. Callers MUST guard that
        flux_results() is not None before calling this."""
        G = current_network()
        info = current_species_info()
        node_colors, _ = colors_cached()
        tl = trophic_levels_cached()
        return create_flux_network(
            G, species_names=info['species'].tolist(),
            functional_groups=info['fg'].tolist(),
            biomass=info['meanB'].values, colors=node_colors,
            flux_matrix=flux_results()['flux_matrix'],
            height="100%", trophic_levels=tl)
```
Replace `app.py:913-932`:
```python
    @output
    @render.ui
    @safe_render("ui")
    def network_plot():
        h = f"{input.network_height()}px"
        if input.network_type() == "Topology":
            net = topology_network_cached()
        else:
            if flux_results() is None:
                return ui.p("Please calculate fluxes first in the Energy Fluxes tab.")
            net = flux_network_cached()
        return render_network(net, height=h, width="100%")

    @render.download(filename="econetool_network.html")
    def download_network():
        if input.network_type() == "Flux-Weighted" and flux_results() is not None:
            net = flux_network_cached()
        else:
            net = topology_network_cached()
        yield net.generate_html()
```
Replace `app.py:1215`:
```python
        net = flux_network_cached()
```
(leaving `flux_network_plot`'s `flux_results() is None` guard at `app.py:1213-1214` and the
`render_network(net, height="600px", width="100%")` return at `app.py:1216` unchanged).
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_app_structure.py -v && micromamba run -n shiny python -m pytest -q`
Expected: PASS; full suite green.
- [ ] **Step 5: Commit**
```bash
git add app.py test_app_structure.py
git commit -m "perf: cache built network on data only; height slider resizes the iframe, not the graph"
```

---

### Task 41: Pin trophic level as vertical position with `fixed={'y': True}` (`6.3`)

**Files:**
- Modify: `network_viz.py:67-78` (`_add_styled_nodes`)
- Test: `test_network_viz_render.py:167-203` (`test_topology_node_size_and_y_position_pinned`,
  `test_flux_node_size_and_y_position_pinned` — updated in this same task, not left stale)

**Interfaces:**
- Consumes: nothing new
- Produces: every emitted node dict now carries `'fixed': {'y': True}` — both builders, via the shared
  `_add_styled_nodes` helper

Today's node-add call (identical block, shared by both builders via `_add_styled_nodes`):
```python
        net.add_node(
            node,
            label=species_names[i],
            title=title,
            color=colors[i],
            size=node_size,
            x=None,  # Let physics determine X position
            y=y_positions[i],
            physics=True,
            shape="dot",
            group=functional_groups[i]
        )
```
`pyvis.Network.add_node(n_id, ..., **kw_options)` (`pyvis/network.py:281`) forwards arbitrary kwargs
straight into the stored node dict (`pyvis/node.py:18`, `Node.__init__(self, n_id, shape, label, font_color, **opts)`),
so `fixed={'y': True}` becomes `net.nodes[i]['fixed'] == {'y': True}` — a currently-untested key. The
pinned viz tests (`test_network_viz_render.py:167-203`) read `net.nodes` via `by_label = {n['label']: n
for n in net.nodes}` but today assert only on `'size'` and `'y'`; this task adds `'fixed'` assertions to
both, which is what turns RED before the implementation change.

- [ ] **Step 1: Extend the pinned tests to assert `fixed` (this is the failing test)**
In `test_network_viz_render.py`, append to `test_topology_node_size_and_y_position_pinned` (after its
existing `assert np.isclose(by_label['Cod']['y'], 100.0)` at line 181):
```python
    assert by_label['Sprat']['fixed'] == {'y': True}
    assert by_label['Herring']['fixed'] == {'y': True}
    assert by_label['Cod']['fixed'] == {'y': True}
```
And append the identical three lines to `test_flux_node_size_and_y_position_pinned` (after its existing
`assert np.isclose(by_label['Cod']['y'], 100.0)` at line 203).
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py::test_topology_node_size_and_y_position_pinned test_network_viz_render.py::test_flux_node_size_and_y_position_pinned -v`
Expected: both FAIL with `KeyError: 'fixed'` — today's node dict has no `'fixed'` key at all (only `id`,
`label`, `title`, `color`, `size`, `x`, `y`, `physics`, `shape`, `group`).
- [ ] **Step 3: Add `fixed={'y': True}` in `_add_styled_nodes`**
`network_viz.py:67-78`:
```python
        net.add_node(
            node,
            label=species_names[i],
            title=title,
            color=colors[i],
            size=node_size,
            x=None,  # Let physics determine X position
            y=y_positions[i],
            physics=True,
            shape="dot",
            group=functional_groups[i],
            fixed={'y': True}  # lock Y to trophic level; X still free for physics
        )
```
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py -v && micromamba run -n shiny python -m pytest -q`
Expected: both pinned tests PASS (sizes/y unchanged: `[29.0, 16.5, 10.25]` / `[0, 50, 100]`, now with
`fixed` present too); `test_topology_builder_nan_tl_safe` and the NaN-sentinel test are unaffected (they
only read `y`); full suite green.
- [ ] **Step 5: Commit**
```bash
git add network_viz.py test_network_viz_render.py
git commit -m "fix: pin nodes' Y to trophic level (fixed={'y': True}); update pinned size/y tests"
```

---

### Task 42: Biomass is `g/km²`, not `g/km²/day` (`6.4`)

**Files:**
- Modify: `network_viz.py:62` (tooltip), `app.py:1054` (`biomass_by_group` ylabel), `app.py:1078` (`biomass_distribution` xlabel)
- Test: `test_network_viz_render.py`, `test_app_structure.py`

**Interfaces:**
- Consumes: nothing
- Produces: nothing new (label text only)

`meanB` is a standing-stock areal biomass density, not a flux — three places wrongly suffix it `/day`:
```python
# network_viz.py:62
        title = f"<b>{species_names[i]}</b><br>Functional Group: {functional_groups[i]}<br>Trophic Level: {tl_str}<br>Biomass: {biomass[i]:.2f} g/km²/day"
```
```python
# app.py:1054
        ax.set_ylabel('Total Biomass (g/km²/day)')
```
```python
# app.py:1078
        ax.set_xlabel('Biomass (g/km²/day)')
```

- [ ] **Step 1: Write the failing tests**
In `test_network_viz_render.py`, add:
```python
def test_tooltip_biomass_units_are_areal_not_daily(viz_graph):
    """Biomass is a standing-stock areal density (g/km²), not a flux
    (g/km²/day) -- the node tooltip must not claim a per-day unit."""
    from network_viz import create_topology_network
    G, species, groups, biomass, colors = viz_graph
    net = create_topology_network(G, species, groups, biomass, colors)
    html = net.generate_html()
    assert "g/km²/day" not in html, "biomass tooltip wrongly labeled as a per-day flux"
    assert "g/km²" in html, "biomass tooltip missing the g/km² unit"
```
In `test_app_structure.py`, add:
```python
def test_biomass_plot_labels_are_areal_not_daily():
    """meanB is a standing-stock biomass (g/km²), not a daily flux; the
    biomass plot axis labels must not claim g/km²/day."""
    source = APP.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for name in ("biomass_by_group", "biomass_distribution"):
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
        fn_src = ast.get_source_segment(source, fn)
        assert "g/km²/day" not in fn_src, f"{name} axis label wrongly claims a per-day flux unit"
        assert "g/km²)" in fn_src, f"{name} axis label missing the g/km² unit"
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py::test_tooltip_biomass_units_are_areal_not_daily test_app_structure.py::test_biomass_plot_labels_are_areal_not_daily -v`
Expected: both FAIL. The tooltip test fails on `assert "g/km²/day" not in html` (network_viz.py:62
puts it there verbatim). The plot-label test fails on the same assertion for `biomass_by_group`'s source
(`app.py:1054` has `'Total Biomass (g/km²/day)'`).
- [ ] **Step 3: Drop the `/day` suffix in all three places**
`network_viz.py:62`:
```python
        title = f"<b>{species_names[i]}</b><br>Functional Group: {functional_groups[i]}<br>Trophic Level: {tl_str}<br>Biomass: {biomass[i]:.2f} g/km²"
```
`app.py:1054`:
```python
        ax.set_ylabel('Total Biomass (g/km²)')
```
`app.py:1078`:
```python
        ax.set_xlabel('Biomass (g/km²)')
```
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_network_viz_render.py test_app_structure.py -v && micromamba run -n shiny python -m pytest -q`
Expected: PASS; full suite green.
- [ ] **Step 5: Commit**
```bash
git add network_viz.py app.py test_network_viz_render.py test_app_structure.py
git commit -m "fix: biomass is g/km² (standing stock), not g/km²/day, in tooltip and plots"
```

---

### Task 43: Transpose example adjacency CSVs to the tracked rows=prey convention (`6.5`)

**Files:**
- Modify: `examples/Simple_3Species_network.csv`, `examples/Caribbean_Reef_network.csv`, `examples/README.md`
- Test: `test_examples_data_convention.py` (new)

**Interfaces:**
- Consumes: nothing
- Produces: nothing

The tracked `BalticFW_adjacency.csv` uses **rows = prey, columns = predator**
(`BalticFW_adjacency.csv:1-5`: row `"Autotroph"` has a `1` in column `"Synchaeta"`, meaning
Autotroph — the prey — is eaten by Synchaeta — the predator). The bundled example CSVs use the opposite,
row-eats-column convention, and `examples/README.md:54-57` documents that inverted convention as the
rule:
```
### Network CSV (Adjacency Matrix)
- Square matrix where rows and columns are species
- Value = 1 means row species eats column species
- Value = 0 means no feeding link
```
`examples/Simple_3Species_network.csv` today (row-eats-column: row `"Zooplankton"` has a `1` in column
`"Phytoplankton"`, i.e. Zooplankton eats Phytoplankton):
```
"","Phytoplankton","Zooplankton","Fish"
"Phytoplankton",0,0,0
"Zooplankton",1,0,0
"Fish",0,1,0
```
`examples/Caribbean_Reef_network.csv` today (same row-eats-column convention):
```
"","Phytoplankton","Macroalgae","Zooplankton","Sea_Urchin","Parrotfish","Damselfish","Snapper","Grouper","Octopus","Barracuda"
"Phytoplankton",0,0,0,0,0,0,0,0,0,0
"Macroalgae",0,0,0,0,0,0,0,0,0,0
"Zooplankton",1,0,0,0,0,0,0,0,0,0
"Sea_Urchin",0,1,0,0,0,0,0,0,0,0
"Parrotfish",0,1,0,0,0,0,0,0,0,0
"Damselfish",1,0,1,0,0,0,0,0,0,0
"Snapper",0,0,1,1,0,1,0,0,0,0
"Grouper",0,0,0,0,1,1,1,0,1,0
"Octopus",0,0,0,1,0,1,0,0,0,0
"Barracuda",0,0,0,0,1,1,1,1,0,0
```
`examples/Template_network.csv` is an all-zero 3x3 matrix; its transpose is itself, so it needs no content
change (only the README fix in this task applies to it).

- [ ] **Step 1: Write the failing test (new file `test_examples_data_convention.py`)**
```python
"""The bundled example adjacency CSVs must use the same rows=prey,
columns=predator convention as the tracked BalticFW_adjacency.csv, or a
user who follows examples/README.md builds an inverted food web."""
import pathlib
import pandas as pd

EXAMPLES = pathlib.Path(__file__).parent / "examples"


def test_simple_3species_csv_uses_rows_are_prey_convention():
    df = pd.read_csv(EXAMPLES / "Simple_3Species_network.csv", index_col=0)
    # Phytoplankton -> Zooplankton -> Fish: Zooplankton eats Phytoplankton,
    # Fish eats Zooplankton. Under rows=prey, M[prey][predator] == 1.
    assert df.loc["Phytoplankton", "Zooplankton"] == 1, \
        "Phytoplankton (prey) -> Zooplankton (predator) must be 1 under rows=prey"
    assert df.loc["Zooplankton", "Fish"] == 1, \
        "Zooplankton (prey) -> Fish (predator) must be 1 under rows=prey"
    assert df.loc["Zooplankton", "Phytoplankton"] == 0, \
        "row-eats-column cell must be 0 under rows=prey"
    assert df.loc["Fish", "Zooplankton"] == 0, \
        "row-eats-column cell must be 0 under rows=prey"


def test_caribbean_reef_csv_uses_rows_are_prey_convention():
    df = pd.read_csv(EXAMPLES / "Caribbean_Reef_network.csv", index_col=0)
    # Zooplankton eats Phytoplankton; Grouper eats Barracuda's prey chain
    # (Barracuda eats Grouper, per the original row-eats-column data).
    assert df.loc["Phytoplankton", "Zooplankton"] == 1, \
        "Phytoplankton (prey) -> Zooplankton (predator) must be 1 under rows=prey"
    assert df.loc["Grouper", "Barracuda"] == 1, \
        "Grouper (prey) -> Barracuda (predator) must be 1 under rows=prey"
    assert df.loc["Zooplankton", "Phytoplankton"] == 0, \
        "row-eats-column cell must be 0 under rows=prey"
    assert df.loc["Barracuda", "Grouper"] == 0, \
        "row-eats-column cell must be 0 under rows=prey"


def test_examples_readme_documents_rows_are_prey_convention():
    text = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    assert "row species eats column species" not in text, \
        "README still documents the inverted row-eats-column convention"
    assert "prey" in text.lower() and "predator" in text.lower(), \
        "README must document the rows=prey, columns=predator convention"
```
- [ ] **Step 2: Run to confirm RED**
Run: `micromamba run -n shiny python -m pytest test_examples_data_convention.py -v`
Expected: all three FAIL. `Simple_3Species_network.csv` has `df.loc["Zooplankton", "Phytoplankton"] == 1`
today (row-eats-column), so the first test's `df.loc["Phytoplankton", "Zooplankton"] == 1` assertion
fails; likewise `Caribbean_Reef_network.csv` has `df.loc["Zooplankton", "Phytoplankton"] == 1` and
`df.loc["Barracuda", "Grouper"] == 1` today; `examples/README.md:56` contains the literal string
`"row species eats column species"`.
- [ ] **Step 3: Transpose the two CSVs; fix the README**
Replace the full contents of `examples/Simple_3Species_network.csv`:
```
"","Phytoplankton","Zooplankton","Fish"
"Phytoplankton",0,1,0
"Zooplankton",0,0,1
"Fish",0,0,0
```
Replace the full contents of `examples/Caribbean_Reef_network.csv`:
```
"","Phytoplankton","Macroalgae","Zooplankton","Sea_Urchin","Parrotfish","Damselfish","Snapper","Grouper","Octopus","Barracuda"
"Phytoplankton",0,0,1,0,0,1,0,0,0,0
"Macroalgae",0,0,0,1,1,0,0,0,0,0
"Zooplankton",0,0,0,0,0,1,1,0,0,0
"Sea_Urchin",0,0,0,0,0,0,1,0,1,0
"Parrotfish",0,0,0,0,0,0,0,1,0,1
"Damselfish",0,0,0,0,0,0,1,1,1,1
"Snapper",0,0,0,0,0,0,0,1,0,1
"Grouper",0,0,0,0,0,0,0,0,0,1
"Octopus",0,0,0,0,0,0,0,1,0,0
"Barracuda",0,0,0,0,0,0,0,0,0,0
```
In `examples/README.md`, replace lines 54-57:
```
### Network CSV (Adjacency Matrix)
- Square matrix where rows and columns are species
- Value = 1 means row species (prey) is eaten by column species (predator)
- Value = 0 means no feeding link
- This matches the rows=prey, columns=predator convention used throughout EcoNeTool
```
And replace line 73 — verified current text is `4. Set feeding links (1 = eats, 0 = no link)`
(it is the 4th item in the "Creating Your Own Dataset" list; keep the leading `4.`):
```
4. Set feeding links (1 = row species is eaten by column species, 0 = no link)
```
- [ ] **Step 4: Run + full suite**
Run: `micromamba run -n shiny python -m pytest test_examples_data_convention.py -v && micromamba run -n shiny python -m pytest -q`
Expected: PASS; full suite green (no other test reads `examples/`, so no regression risk there).
- [ ] **Step 5: Commit**
```bash
git add examples/Simple_3Species_network.csv examples/Caribbean_Reef_network.csv examples/README.md test_examples_data_convention.py
git commit -m "fix: transpose example adjacency CSVs to the tracked rows=prey convention"
```

---

### Task 44: Phase 6 gate

- [ ] **Step 1: Full suite + import smoke**
Run: `micromamba run -n shiny python -m pytest -v`
Expected: all tests pass — the 133-test baseline plus every test added in Tasks 38-43 and all preceding phases (cumulative; do not expect an exact number). Only the 3 known `network_analysis.py` UserWarnings (lines 122, 134, 186); any other warning is a defect.
- [ ] **Step 2: App import smoke**
Run: `micromamba run -n shiny python -c "import app; print('app OK')"`
Expected: `app OK`.
- [ ] **Step 3: Tag**
```bash
git tag audit3-phase6
```

---

### Task 45: Post-Phase-6 live smoke — editor round-trip, `safe_render` panel, self-contained download (`gate`, spec L105)

This is the acceptance gate for the **whole plan**: the spec's "After Phase 6: a live smoke that
drives the Data Editor (the gap remediation #2 never closed), forces a renderer error, and downloads
the network HTML" (`docs/superpowers/specs/2026-09-05-econetpy-audit-remediation-3-design.md:105`).
Everything before this point is unit- or AST-level; nothing in the plan has yet started the real app
and clicked it. Runs only after Tasks 1-44 have all landed.

**Files:**
- Create: `test_live_smoke.py` (new file — the only live/browser test in the suite)
- Modify: `app.py` (`topological_indicators`, currently `app.py:965-984`; add an inert env-var-guarded
  raise at the top of the function body — locate it by the `def topological_indicators():` text, not
  by line number, since Phases 1-6 have shifted everything)
- Modify: `environment.yml`, `requirements.txt` (declare `pytest-playwright` alongside the
  `pytest`/`hypothesis` dev block Task 16 added)

**Interfaces:**
- Consumes: `shiny.pytest.create_app_fixture`, `shiny.playwright.controller.OutputDataFrame`
  (verified present in this env: `set_cell(text, *, row, col, finish_key=None)`,
  `expect_cell(value, *, row, col)`), `playwright.sync_api.Page`; `app.PAGES` menu ids
  (`menu_editor`, `menu_topology`, `menu_network` — `app.py:372-380`, `app.py:582-587`);
  `species_info_editor` / `update_species_info` (`app.py:363-364`); `download_network`
  (`app.py:249`, `app.py:926`); `app._ERROR_MSG` (`app.py:56`,
  `"This panel could not be computed — see logs."`); `app._network_download_html` (Task 14).
- Consumes (navigation model): **Task 38 has already replaced the `@render.ui main_content` rebuild
  with a single static `ui.navset_hidden(...)` mounting every page at once**, and the `menu_*` effects
  now switch panels client-side. So all three target elements (`#species_info_editor`,
  `#topological_indicators`, `#download_network`) exist in the DOM from session start; clicking the
  menu link only reveals the panel. The menu link labels are the exact strings in `app.py:582-588`
  (`"Food Web Network"`, `"Topological Metrics"`, `"Data Editor"` — verified).
- Produces: nothing — terminal acceptance gate.

**Shiny 1.7.0 constraint (restated):** `render.DataGrid` has NO `editable_columns`. The grid is
built as `render.DataGrid(info, editable=True, ...)` and the species/fg columns are protected by
`@species_info_editor.set_patch_fn` (`app.py:1355-1362`). Part (a) below therefore proves BOTH
halves of that arrangement: an edit to `meanB` must survive `data_patched()` into
`current_species_info`, and an edit to `species` must be reverted by the patch function.

**Why an env var for part (b):** the app under test runs in its own subprocess, so the test cannot
monkeypatch it. The trigger goes in ONE renderer body, not inside `safe_render` itself — Task 20's
structural test inspects `safe_render`, and changing it would perturb that test. The check is inert
whenever the variable is unset, which is every run except this one.

- [ ] **Step 1: Write the failing live smoke**
```python
# test_live_smoke.py (new file)
"""Post-Phase-6 live smoke. Skipped unless ECONETOOL_LIVE_SMOKE=1 so the normal
suite (and every phase gate) stays browser-free and warning-clean."""
import os
import re

import pytest

pytest.importorskip("playwright")
pytest.importorskip("shiny.playwright")

if os.environ.get("ECONETOOL_LIVE_SMOKE") != "1":
    pytest.skip("live smoke: set ECONETOOL_LIVE_SMOKE=1 to run", allow_module_level=True)

from playwright.sync_api import Page, expect
from shiny.playwright import controller
from shiny.pytest import create_app_fixture
from shiny.run import ShinyAppProc

app = create_app_fixture("app.py")

# species_info column order is species, fg, meanB, bodymasses, met.types, efficiencies
COL_SPECIES = 0
COL_MEANB = 2


def _open_editor(page: Page, app: ShinyAppProc) -> controller.OutputDataFrame:
    page.goto(app.url)
    page.get_by_text("Data Editor").first.click()
    grid = controller.OutputDataFrame(page, "species_info_editor")
    # Wait for the grid to actually paint before touching cells; the row count is
    # data-dependent (Baltic vs example network), so wait on the first cell.
    expect(grid.cell_locator(row=0, col=COL_SPECIES)).to_be_visible(timeout=30_000)
    return grid


def test_live_species_info_edit_round_trips_through_data_patched(page: Page, app: ShinyAppProc):
    """(a) An edit made in the DataGrid must reach current_species_info via
    data_patched(), and an edit to a key column must be reverted by set_patch_fn."""
    grid = _open_editor(page, app)

    original = grid.cell_locator(row=0, col=COL_MEANB).inner_text().strip()
    new_value = "12345.0"
    assert original != new_value

    grid.set_cell(new_value, row=0, col=COL_MEANB, finish_key="Enter")
    page.get_by_role("button", name="Update Species Info").click()
    expect(page.get_by_text("Species info updated.")).to_be_visible(timeout=15_000)

    # The grid re-renders from current_species_info(); the value survives only if
    # data_patched() -> current_species_info.set(df) actually happened.
    grid.expect_cell(re.compile(r"12345"), row=0, col=COL_MEANB, timeout=15_000)

    # set_patch_fn must refuse an edit to a key column: the cell reverts.
    species_before = grid.cell_locator(row=0, col=COL_SPECIES).inner_text().strip()
    grid.set_cell("NOT_A_SPECIES", row=0, col=COL_SPECIES, finish_key="Enter")
    grid.expect_cell(species_before, row=0, col=COL_SPECIES, timeout=15_000)


def test_live_safe_render_shows_clean_panel_not_traceback(page: Page, app: ShinyAppProc):
    """(b) A renderer that raises must surface app._ERROR_MSG, not a traceback."""
    page.goto(app.url)
    page.get_by_text("Topological Metrics").first.click()
    panel = page.locator("#topological_indicators")
    expect(panel).to_contain_text("could not be computed", timeout=30_000)
    assert "Traceback" not in panel.inner_text()
    assert "ECONETOOL_FORCE_RENDER_ERROR" not in panel.inner_text()


def test_live_downloaded_network_html_is_self_contained(page: Page, app: ShinyAppProc, tmp_path):
    """(c) The downloaded network HTML must inline its assets — no src="lib/."""
    page.goto(app.url)
    page.get_by_text("Food Web Network").first.click()
    # NOTE: ui.download_button renders an <a class="btn ... shiny-download-link">,
    # NOT a <button> — its ARIA role is "link", so get_by_role("button", ...) does
    # not match. Locate it by id (verified against `ui.download_button(...)` output).
    with page.expect_download(timeout=60_000) as dl_info:
        page.locator("#download_network").click()
    target = tmp_path / "network.html"
    dl_info.value.save_as(target)

    html = target.read_text(encoding="utf-8", errors="replace")
    assert 'src="lib/' not in html, 'downloaded HTML still references local lib/ assets'
    assert 'href="lib/' not in html, 'downloaded HTML still references local lib/ assets'
    assert "vis-network" in html, "downloaded HTML does not appear to embed the vis-network bundle"
    # Size floor verified empirically on this pyvis fork with a 3-node network:
    # cdn_resources="local" -> ~7.2 KB, cdn_resources="in_line" -> ~660 KB.
    assert len(html) > 200_000, f"downloaded HTML is only {len(html)} bytes — assets not inlined"
```
- [ ] **Step 2: Run to confirm RED**
Run (Git Bash):
```bash
ECONETOOL_LIVE_SMOKE=1 micromamba run -n shiny python -m pytest test_live_smoke.py -v
```
Expected: FAIL — test (b) fails: with no error injected, `topological_indicators` renders the real
indicator block, so `expect(panel).to_contain_text("could not be computed")` times out. Tests (a)
and (c) may already pass here (Phase 1-6 landed their fixes); (b) is the RED that gates Step 3, and
Step 4 adds the second, mode-A RED for (c).
- [ ] **Step 3: Add the inert error-injection hook**
```python
# app.py, first two lines of the topological_indicators body (locate by the
# `def topological_indicators():` text — line numbers have shifted through
# Phases 1-6). Inert unless the env var names this output id.
    @output
    @render.text
    @safe_render("text")
    def topological_indicators():
        if os.environ.get("ECONETOOL_FORCE_RENDER_ERROR") == "topological_indicators":
            raise RuntimeError("forced renderer error (live smoke)")
        G = current_network()
```
`app.py` already imports `os` at module level (`import os`); if a prior task removed it, re-add it
with the other stdlib imports. Declare the browser-test dev dependency exactly where Task 16 put
`hypothesis` — as a conda-forge entry in the top-level `dependencies:` list of `environment.yml`
(NOT in the `pip:` block; `pytest-playwright` is on conda-forge, and the project rule is conda-forge
over pip):
```yaml
# environment.yml, immediately after Task 16's `  - hypothesis>=6.100.0`
# and still before the existing `  - pip`
  - pytest-playwright>=0.5.0
```
```
# requirements.txt, under the "# Dev / test" comment
pytest-playwright>=0.5.0
```
- [ ] **Step 4: Second RED — mode A for part (c)**
Temporarily revert Task 14's inlining by making `download_network` yield `net.generate_html()`
directly again (bypassing `_network_download_html`), then:
```bash
ECONETOOL_LIVE_SMOKE=1 micromamba run -n shiny python -m pytest \
  test_live_smoke.py::test_live_downloaded_network_html_is_self_contained -v
```
Expected: FAIL — the saved file contains `src="lib/vis-9.1.2/vis-network.min.js"`, so the
`'src="lib/' not in html` assertion raises. **Revert the temporary `app.py` edit before continuing.**
- [ ] **Step 5: Run GREEN — all three parts**
```bash
ECONETOOL_FORCE_RENDER_ERROR=topological_indicators ECONETOOL_LIVE_SMOKE=1 \
  micromamba run -n shiny python -m pytest test_live_smoke.py -v
```
Expected: 3 passed. Then re-run (a) and (c) with the injection variable unset, to prove the hook is
inert:
```bash
ECONETOOL_LIVE_SMOKE=1 micromamba run -n shiny python -m pytest test_live_smoke.py -v \
  -k "round_trips or self_contained"
```
Expected: 2 passed.
- [ ] **Step 6: Full suite — the live smoke must be invisible to it**
Run: `micromamba run -n shiny python -m pytest`
Expected: all tests pass — the 133-test baseline plus every test added in Tasks 1-44 (cumulative; do
not expect an exact number), with `test_live_smoke.py` reported as **skipped** (the module-level
`pytest.skip` fires because `ECONETOOL_LIVE_SMOKE` is unset). Only the 3 known
`network_analysis.py` UserWarnings (lines 122, 134, 186); any other warning — including any
`PytestUnknownMarkWarning` — is a defect.
- [ ] **Step 7: Commit**
```bash
git add test_live_smoke.py app.py environment.yml requirements.txt
git commit -m "test: post-Phase-6 live smoke — editor round-trip, safe_render panel, self-contained download"
```
(No new tag: the Global Constraints allow exactly `audit3-phase1` .. `audit3-phase6`, and
`audit3-phase6` is already placed by Task 44.)

---

