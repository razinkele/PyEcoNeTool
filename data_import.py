"""Parse and validate user-supplied food-web data (adjacency CSV + species CSV).

Pure functions, no Shiny: ``parse_food_web`` returns ``(G, info)`` ready to
drop into the app's session state, or raises ``ValueError`` with a message
fit to show the user. Nothing here executes uploaded content (no pickle /
RData), and nothing touches module globals or the shared Baltic cache.

Conventions (same as ``BalticFW_adjacency.csv`` and ``examples/``):
- network CSV: square matrix, first column = row labels, header = column
  labels, ``M[prey, predator] = 1`` (rows = prey). Edges run prey -> predator.
- species CSV: one row per species with at least ``REQUIRED_COLUMNS``.
"""
from __future__ import annotations

import io
import math
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from flux_calculations import validate_met_types

MAX_BYTES = 2 * 1024 * 1024
MAX_SPECIES = 500

REQUIRED_COLUMNS = ["species", "fg", "meanB", "bodymasses", "met.types", "efficiencies"]
NUMERIC_COLUMNS = ["meanB", "bodymasses", "efficiencies"]

EXAMPLES_DIR = Path(__file__).parent / "examples"
# key -> (label, network csv, species csv). Template_* is deliberately absent:
# it has no feeding links, so it cannot be analysed.
EXAMPLE_DATASETS = {
    "Simple_3Species": ("Simple 3-species chain",
                        "Simple_3Species_network.csv", "Simple_3Species_info.csv"),
    "Caribbean_Reef": ("Caribbean reef (10 species)",
                       "Caribbean_Reef_network.csv", "Caribbean_Reef_info.csv"),
}


# --- reading -----------------------------------------------------------------

def _read_bytes(src, what: str) -> bytes:
    if isinstance(src, (bytes, bytearray)):
        data = bytes(src)
    elif isinstance(src, (str, Path)):
        path = Path(src)
        if path.stat().st_size > MAX_BYTES:
            raise ValueError(f"The {what} file is too large (limit {MAX_BYTES // 1024 // 1024} MB).")
        data = path.read_bytes()
    elif hasattr(src, "read"):
        data = src.read(MAX_BYTES + 1)
    else:
        raise TypeError(f"Unsupported {what} source: {type(src).__name__}")
    if len(data) > MAX_BYTES:
        raise ValueError(f"The {what} file is too large (limit {MAX_BYTES // 1024 // 1024} MB).")
    if not data.strip():
        raise ValueError(f"The {what} file is empty.")
    return data


def _decode(data: bytes, what: str) -> str:
    # UTF-8 (with or without BOM) first; then the Baltic Windows code page that
    # a Lithuanian-locale Excel uses for "CSV (Comma delimited)".
    for enc in ("utf-8-sig", "cp1257"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"The {what} file is not readable text (save it as CSV, UTF-8).")
    if "\x00" in text:
        raise ValueError(f"The {what} file is not a text CSV (save it as CSV, UTF-8).")
    return text


def _sniff_sep(text: str) -> str:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    counts = {sep: first.count(sep) for sep in (",", ";", "\t")}
    sep = max(counts, key=counts.get)
    return sep if counts[sep] > 0 else ","


def _read_table(src, what: str) -> tuple[pd.DataFrame, str]:
    text = _decode(_read_bytes(src, what), what)
    sep = _sniff_sep(text)
    try:
        raw = pd.read_csv(io.StringIO(text), sep=sep, header=None, dtype=str,
                          keep_default_na=False, skip_blank_lines=True)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError(f"Could not read the {what} file as CSV: {exc}") from None
    raw = raw.apply(lambda col: col.str.strip())
    return raw, sep


def _to_number(series: pd.Series, decimal_comma: bool) -> pd.Series:
    s = series.astype(str).str.strip()
    if decimal_comma:
        s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _dupes(names) -> list[str]:
    seen, dup = set(), []
    for n in names:
        if n in seen and n not in dup:
            dup.append(n)
        seen.add(n)
    return dup


def _preview(names, k: int = 5) -> str:
    names = sorted(names)
    more = f" (+{len(names) - k} more)" if len(names) > k else ""
    return ", ".join(repr(n) for n in names[:k]) + more


# --- network -----------------------------------------------------------------

def _parse_network(src) -> pd.DataFrame:
    raw, sep = _read_table(src, "network")
    if raw.shape[0] < 2 or raw.shape[1] < 2:
        raise ValueError("The network file needs a header row and at least one species row.")
    cols = raw.iloc[0, 1:].tolist()
    rows = raw.iloc[1:, 0].tolist()
    values = raw.iloc[1:, 1:]

    if len(rows) > MAX_SPECIES or len(cols) > MAX_SPECIES:
        raise ValueError(f"The network has too many species (limit {MAX_SPECIES}).")
    if len(rows) != len(cols):
        raise ValueError(
            f"The network matrix must be square: {len(rows)} rows but {len(cols)} columns. "
            "The first column holds the species names; the header repeats them.")
    for label, names in (("row", rows), ("column", cols)):
        if any(n == "" for n in names):
            raise ValueError(f"The network has a blank {label} name.")
        dup = _dupes(names)
        if dup:
            raise ValueError(f"Duplicate species {label} name(s) in the network: {_preview(dup)}.")
    if set(rows) != set(cols):
        only_r, only_c = set(rows) - set(cols), set(cols) - set(rows)
        raise ValueError(
            "Network rows and columns must list the same species. "
            f"Only in rows: {_preview(only_r) or '-'}; only in columns: {_preview(only_c) or '-'}.")

    numeric = values.apply(lambda c: _to_number(c, decimal_comma=(sep == ";")))
    bad = ~numeric.isin([0, 1])
    if bad.to_numpy().any():
        r, c = np.argwhere(bad.to_numpy())[0]
        raise ValueError(
            "Network cells must be 0 or 1 (1 = row species is eaten by column species); "
            f"found {values.iat[r, c]!r} at row {rows[r]!r}, column {cols[c]!r}.")

    M = pd.DataFrame(numeric.to_numpy(dtype=int), index=rows, columns=cols)
    M = M.loc[rows, rows]  # columns in row order
    if M.to_numpy().sum() == 0:
        raise ValueError("The network has no feeding links (every cell is 0).")
    return M


# --- species -----------------------------------------------------------------

def _parse_species(src) -> pd.DataFrame:
    raw, sep = _read_table(src, "species")
    if raw.shape[0] < 2:
        raise ValueError("The species file needs a header row and at least one species row.")
    header = raw.iloc[0].tolist()
    dup = _dupes(header)
    if dup:
        raise ValueError(f"Duplicate column(s) in the species file: {_preview(dup)}.")
    info = raw.iloc[1:].copy()
    info.columns = header
    info = info.reset_index(drop=True)

    missing = [c for c in REQUIRED_COLUMNS if c not in info.columns]
    if missing:
        raise ValueError(
            f"The species file is missing required column(s): {', '.join(missing)}. "
            f"Required: {', '.join(REQUIRED_COLUMNS)}.")

    for col in ("species", "fg", "met.types"):
        blank = info.index[info[col] == ""]
        if len(blank):
            raise ValueError(f"Column '{col}' is blank on data row {blank[0] + 1}.")
    dup = _dupes(info["species"])
    if dup:
        raise ValueError(f"Duplicate species in the species file: {_preview(dup)}.")

    decimal_comma = sep == ";"
    for col in NUMERIC_COLUMNS:
        num = _to_number(info[col], decimal_comma)
        bad = ~np.isfinite(num.to_numpy(dtype=float))
        if bad.any():
            i = int(np.argmax(bad))
            raise ValueError(
                f"Column '{col}' must be a number; got {info[col].iat[i]!r} for {info['species'].iat[i]!r}.")
        info[col] = num.astype(float)

    for col in ("meanB", "bodymasses"):
        bad = info[col] <= 0
        if bad.any():
            sp = info.loc[bad, "species"].iat[0]
            raise ValueError(f"Column '{col}' must be greater than 0 (check {sp!r}).")
    bad = (info["efficiencies"] <= 0) | (info["efficiencies"] > 1)
    if bad.any():
        sp = info.loc[bad, "species"].iat[0]
        raise ValueError(f"Column 'efficiencies' must be in (0, 1] (check {sp!r}).")

    validate_met_types(info["met.types"].tolist(), context="the species file")

    # Optional extra columns: keep; make fully-numeric ones numeric.
    for col in info.columns:
        if col in REQUIRED_COLUMNS:
            continue
        num = _to_number(info[col], decimal_comma)
        if num.notna().all():
            info[col] = num
    return info


# --- web structure -----------------------------------------------------------

def _check_energy_reaches_every_species(G: nx.DiGraph) -> None:
    """Every species must be basal (eats nothing but possibly itself) or be
    reachable from a basal species along prey -> predator links. A closed
    loop with no basal input has no defined trophic level: prey-averaged TL
    collapses to clamped values and short-weighted TL is NaN
    (network_analysis.calculate_trophic_levels), so reject it up front."""
    basal = [n for n in G if set(G.predecessors(n)) <= {n}]
    if not basal:
        raise ValueError(
            "The network has no basal species (a species that eats nothing, e.g. "
            "phytoplankton or detritus). Check the orientation: rows = prey, "
            "columns = predators.")
    reached = set(basal)
    for b in basal:
        reached |= nx.descendants(G, b)
    cut_off = set(G) - reached
    if cut_off:
        raise ValueError(
            "These species only feed in a closed loop that no basal species "
            f"supplies, so their trophic level is undefined: {_preview(cut_off)}.")


# --- public ------------------------------------------------------------------

def parse_food_web(network_src, info_src) -> tuple[nx.DiGraph, pd.DataFrame]:
    """Parse an adjacency CSV + species CSV into an aligned ``(G, info)``.

    Each source may be bytes, a path, or a binary file object.
    Raises ``ValueError`` (user-readable) on any problem.
    """
    M = _parse_network(network_src)
    info = _parse_species(info_src)

    names = M.index.tolist()
    in_net, in_info = set(names), set(info["species"])
    if in_net != in_info:
        raise ValueError(
            "The two files must list the same species. "
            f"In network only: {_preview(in_net - in_info) or '-'}; "
            f"in species file only: {_preview(in_info - in_net) or '-'}.")

    info = info.set_index("species").loc[names].reset_index()
    G = nx.from_pandas_adjacency(M, create_using=nx.DiGraph)
    _check_energy_reaches_every_species(G)
    if list(G.nodes()) != info["species"].tolist():  # defensive; from_pandas keeps order
        raise ValueError("Internal error: network and species order diverged.")
    return G, info


def load_example(key: str) -> tuple[nx.DiGraph, pd.DataFrame]:
    """Load a bundled example dataset by registry key."""
    if key not in EXAMPLE_DATASETS:
        raise ValueError(f"Unknown example dataset {key!r}.")
    _, net, inf = EXAMPLE_DATASETS[key]
    return parse_food_web(EXAMPLES_DIR / net, EXAMPLES_DIR / inf)
