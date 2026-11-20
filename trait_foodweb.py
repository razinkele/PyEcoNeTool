"""Trait-based food web: infer feeding links from coded species traits.

Port of R EcoNeTool's ``R/functions/trait_foodweb.R`` (sha256 c6d61a2e…8196,
2026-10-21). Each species carries five codes:

- MS  body size class        MS1 (<0.1 cm) … MS7 (>150 cm)
- FS  foraging strategy      FS0 primary producer … FS7 xylophagous
- MB  mobility               MB1 sessile … MB5 obligate swimmer
- EP  environmental position EP1 pelagic … EP4 endobenthic
- PR  protection             PR0 none … PR8 armoured

For a consumer/resource pair, five tables give a probability each (size ×
size, foraging × prey size, mobility × mobility, position × prey size,
prey protection × prey size); the link probability is their **minimum**, and
a link exists iff it is **strictly above** the threshold (default 0.05, the
tables' "implausible" floor). R's exclusions are kept: MS7 is never prey,
FS0 never eats, no self-links, and only consumers with a size-table row eat.

**Extension (``extend_sizes=True``, the default):** R's size table has
consumer rows MS3–MS6 only, so every MS1/MS2/MS7 consumer (zooplankton,
copepods, small grazers, seals) gets no prey and lands at trophic level 1.
``SIZE_EXTENSION`` adds MS1, MS2 and MS7 rows, derived (not chosen) from the
band all four R rows follow: 0.95 where prey is two classes below the
consumer, 0.80 one class either side, 0.50 two, 0.20 three below, 0.05 three
above. ``extend_sizes=False`` reproduces R exactly (the parity test).

Matrices: ``probability_matrix`` is ``[consumer, resource]`` like R;
``trait_adjacency`` transposes once into EconetPy's rows-are-prey matrix.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

TRAIT_CODES = {
    "MS": tuple(f"MS{i}" for i in range(1, 8)),
    "FS": tuple(f"FS{i}" for i in range(0, 8)),
    "MB": tuple(f"MB{i}" for i in range(1, 6)),
    "EP": tuple(f"EP{i}" for i in range(1, 5)),
    "PR": tuple(f"PR{i}" for i in range(0, 9)),
}
_PREY_MS = TRAIT_CODES["MS"][:6]   # MS1–MS6: MS7 is never prey
_MB = TRAIT_CODES["MB"]
CONSUMER_TRAITS = ("MS", "FS", "MB", "EP")
RESOURCE_TRAITS = ("MS", "MB", "EP", "PR")

# Tables copied from the R source. Rows: consumer code (PR: resource code);
# columns: resource MS1–MS6 (MB_MB: resource MB1–MB5).
MS_MS = {
    "MS3": [0.95, 0.80, 0.50, 0.05, 0.05, 0.05],
    "MS4": [0.80, 0.95, 0.80, 0.50, 0.05, 0.05],
    "MS5": [0.50, 0.80, 0.95, 0.80, 0.50, 0.05],
    "MS6": [0.20, 0.50, 0.80, 0.95, 0.80, 0.50],
}
SIZE_EXTENSION = {
    "MS1": [0.50, 0.05, 0.05, 0.05, 0.05, 0.05],
    "MS2": [0.80, 0.50, 0.05, 0.05, 0.05, 0.05],
    "MS7": [0.20, 0.20, 0.50, 0.80, 0.95, 0.80],
}
FS_MS = {
    "FS1": [0.20, 0.50, 0.95, 0.80, 0.50, 0.20],
    "FS2": [0.05, 0.20, 0.50, 0.95, 0.80, 0.50],
    "FS3": [0.50, 0.50, 0.50, 0.50, 0.50, 0.50],
    "FS4": [0.95, 0.80, 0.05, 0.05, 0.05, 0.05],
    "FS5": [0.80, 0.80, 0.50, 0.05, 0.05, 0.05],
    "FS6": [0.95, 0.95, 0.20, 0.05, 0.05, 0.05],
    "FS7": [0.05, 0.20, 0.50, 0.80, 0.20, 0.05],
}
MB_MB = {
    "MB1": [0.95, 0.10, 0.10, 0.10, 0.10],
    "MB2": [0.80, 0.95, 0.20, 0.20, 0.20],
    "MB3": [0.80, 0.95, 0.95, 0.20, 0.20],
    "MB4": [0.80, 0.80, 0.80, 0.80, 0.80],
    "MB5": [0.20, 0.50, 0.95, 0.95, 0.95],
}
EP_MS = {
    "EP1": [0.95, 0.95, 0.80, 0.50, 0.05, 0.05],
    "EP2": [0.80, 0.80, 0.95, 0.80, 0.50, 0.50],
    "EP3": [0.50, 0.50, 0.80, 0.95, 0.80, 0.80],
    "EP4": [0.05, 0.05, 0.50, 0.80, 0.05, 0.05],
}
PR_MS = {
    "PR0": [0.95, 0.95, 0.95, 0.80, 0.50, 0.50],
    "PR1": [0.95, 0.95, 0.95, 0.80, 0.50, 0.50],
    "PR2": [0.80, 0.80, 0.80, 0.50, 0.05, 0.05],
    "PR3": [0.80, 0.80, 0.80, 0.50, 0.05, 0.05],
    "PR4": [0.50, 0.50, 0.50, 0.80, 0.50, 0.50],
    "PR5": [0.80, 0.80, 0.50, 0.50, 0.20, 0.20],
    "PR6": [0.50, 0.50, 0.50, 0.80, 0.50, 0.50],
    "PR7": [0.20, 0.20, 0.20, 0.50, 0.20, 0.20],
    "PR8": [0.20, 0.20, 0.20, 0.50, 0.20, 0.20],
}


def interaction_probability(consumer: Mapping[str, str], resource: Mapping[str, str],
                            extend_sizes: bool = True) -> float:
    """Probability that ``consumer`` (MS FS MB EP) eats ``resource``
    (MS MB EP PR); codes must be valid (see ``TRAIT_CODES``)."""
    if resource["MS"] == "MS7" or consumer["FS"] == "FS0":
        return 0.0
    size = {**MS_MS, **SIZE_EXTENSION} if extend_sizes else MS_MS
    if consumer["MS"] not in size:
        return 0.0
    j = _PREY_MS.index(resource["MS"])
    return float(min(size[consumer["MS"]][j], FS_MS[consumer["FS"]][j],
                     MB_MB[consumer["MB"]][_MB.index(resource["MB"])],
                     EP_MS[consumer["EP"]][j], PR_MS[resource["PR"]][j]))


def _missing(value) -> bool:
    return value is None or (isinstance(value, float) and np.isnan(value))


def probability_matrix(traits: pd.DataFrame, extend_sizes: bool = True) -> pd.DataFrame:
    """``[consumer, resource]`` link probabilities for every species pair.

    ``traits`` has ``species MS FS MB EP PR``. A blank (NaN) code is
    role-aware, as in R: a species missing a consumer trait never eats; one
    missing a resource trait is never eaten. Diagonal is 0 (no self-links)."""
    names = traits["species"].tolist()
    rows = traits.to_dict("records")
    can_eat = [not any(_missing(r[t]) for t in CONSUMER_TRAITS) for r in rows]
    can_be_eaten = [not any(_missing(r[t]) for t in RESOURCE_TRAITS) for r in rows]
    P = np.zeros((len(rows), len(rows)))
    for i, cons in enumerate(rows):
        if not can_eat[i]:
            continue
        for j, res in enumerate(rows):
            if i != j and can_be_eaten[j]:
                P[i, j] = interaction_probability(cons, res, extend_sizes)
    return pd.DataFrame(P, index=names, columns=names)


def trait_adjacency(P: pd.DataFrame, threshold: float = 0.05) -> pd.DataFrame:
    """0/1 adjacency in EconetPy's orientation (rows = prey, columns =
    predators) from a ``[consumer, resource]`` probability matrix; a link
    needs a probability strictly above ``threshold``."""
    return (P.T > threshold).astype(int)


# --- trait files -> food web ---------------------------------------------------

from dataclasses import dataclass, field  # noqa: E402
from pathlib import Path  # noqa: E402

import networkx as nx  # noqa: E402

from data_import import _read_table, _to_number, _preview, build_food_web  # noqa: E402

EXAMPLES_DIR = Path(__file__).parent / "examples"
TRAIT_EXAMPLES = {
    "simple": ("Simple chain (5 species)", "trait_foodweb_simple.csv"),
    "marine_invertebrates": ("Marine invertebrates (15 species)",
                             "trait_foodweb_marine_invertebrates.csv"),
    "coastal_ecosystem": ("Baltic / North Sea coastal (35 species)",
                          "trait_foodweb_coastal_ecosystem.csv"),
}
TRAIT_COLUMNS = ("MS", "FS", "MB", "EP", "PR")
OPTIONAL_TEXT = ("fg", "met.types")
OPTIONAL_NUMERIC = ("meanB", "bodymasses", "efficiencies")
# Length (cm) per size class for the body-mass estimate W = 0.01 * L^3 (g).
MS_LENGTH_CM = {"MS1": 0.05, "MS2": 0.5, "MS3": 3, "MS4": 12, "MS5": 35,
                "MS6": 100, "MS7": 200}
PLACEHOLDER_BIOMASS = 1.0


@dataclass
class TraitImport:
    G: nx.DiGraph
    info: pd.DataFrame
    notes: list = field(default_factory=list)
    placeholder_biomass: bool = False


def estimate_fg(ms, fs, mb, ep) -> str:
    """Functional group from trait codes (rules applied in order)."""
    if fs == "FS0":
        return "Primary producers"
    if fs in ("FS2", "FS5") and ep in ("EP3", "EP4"):
        return "Benthos"
    if mb == "MB2":
        return "Zooplankton"
    if mb == "MB5" and ms in ("MS4", "MS5", "MS6", "MS7"):
        return "Fish"
    if ep in ("EP3", "EP4"):
        return "Benthos"
    return "Consumers"


def _read_trait_table(src) -> pd.DataFrame:
    raw, sep = _read_table(src, "trait")
    if raw.shape[0] < 2:
        raise ValueError("The trait file needs a header row and at least one species row.")
    header = [str(h).strip() for h in raw.iloc[0].tolist()]
    if len(set(header)) != len(header):
        raise ValueError("The trait file has duplicate column names.")
    df = raw.iloc[1:].copy()
    df.columns = header
    df = df[(df != "").any(axis=1)].reset_index(drop=True)   # drop blank rows
    missing = [c for c in ("species",) + TRAIT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"The trait file is missing required column(s): {', '.join(missing)}. "
                         "Required: species, MS, FS, MB, EP, PR.")
    df.attrs["decimal_comma"] = sep == ";"
    return df


def _clean_codes(df: pd.DataFrame) -> pd.DataFrame:
    df["species"] = df["species"].astype(str).str.strip()
    if (df["species"] == "").any():
        raise ValueError("A species name is blank in the trait file.")
    dup = df["species"][df["species"].duplicated()].unique().tolist()
    if dup:
        raise ValueError(f"Duplicate species in the trait file: {_preview(dup)}.")
    for col in TRAIT_COLUMNS:
        codes = df[col].astype(str).str.replace(r"\s+", "", regex=True).str.upper()
        codes = codes.where(codes != "", np.nan)
        bad = sorted(set(codes.dropna()) - set(TRAIT_CODES[col]))
        if bad:
            raise ValueError(f"Column '{col}' has invalid code(s) {bad}; "
                             f"valid codes: {', '.join(TRAIT_CODES[col])}.")
        df[col] = codes
    return df


def _optional_columns(df: pd.DataFrame) -> list:
    """Validate the optional analysis columns present in the file; return the
    names of those that must be estimated."""
    to_estimate = []
    for col in OPTIONAL_TEXT + OPTIONAL_NUMERIC:
        if col not in df.columns:
            to_estimate.append(col)
            continue
        blank = df["species"][df[col].astype(str).str.strip() == ""].tolist()
        if blank:
            raise ValueError(
                f"Column '{col}' is filled for some species but blank for {_preview(blank)}; "
                "fill it for every species or remove the column.")
        if col in OPTIONAL_NUMERIC:
            num = _to_number(df[col], df.attrs.get("decimal_comma", False))
            bad = df["species"][~np.isfinite(num.to_numpy(dtype=float))].tolist()
            if bad:
                raise ValueError(f"Column '{col}' must be a number (check {_preview(bad)}).")
            df[col] = num.astype(float)
        else:
            df[col] = df[col].astype(str).str.strip()
    return to_estimate


def _estimate(df: pd.DataFrame, to_estimate: list) -> None:
    if "fg" in to_estimate:
        df["fg"] = [estimate_fg(*r) for r in df[["MS", "FS", "MB", "EP"]].itertuples(index=False)]
    if "bodymasses" in to_estimate:
        # A blank MS (species that can neither eat nor be eaten by size) gets MS4's.
        df["bodymasses"] = [0.01 * MS_LENGTH_CM.get(m, MS_LENGTH_CM["MS4"]) ** 3 for m in df["MS"]]
    if "met.types" in to_estimate:
        df["met.types"] = np.where(df["fg"] == "Fish", "ectotherm vertebrates", "invertebrates")
    if "efficiencies" in to_estimate:
        df["efficiencies"] = np.where(df["FS"] == "FS0", 0.77, 0.906)
    if "meanB" in to_estimate:
        df["meanB"] = PLACEHOLDER_BIOMASS


def _notes(df, G, to_estimate, extend_sizes, threshold) -> list:
    notes = []
    est = [c for c in to_estimate if c != "meanB"]
    if est:
        notes.append(
            f"Estimated from the trait codes: {', '.join(est)} (body mass from the size "
            "class length, W = 0.01·L³). Body mass, metabolic type and efficiency can be "
            "edited in the Data Editor; to set functional groups, add an 'fg' column to "
            "the file.")
    if "meanB" in to_estimate:
        notes.append(
            "No biomass column: every species has a placeholder biomass of 1.0, so "
            "biomass-weighted results (Biomass, Energy Fluxes, Keystoneness) are not "
            "meaningful. Add a 'meanB' column to the file or enter biomass in the Data Editor.")
    if extend_sizes:
        r_links = int(trait_adjacency(probability_matrix(df, extend_sizes=False), threshold)
                      .to_numpy().sum())
        added = G.number_of_edges() - r_links
        if added > 0:
            notes.append(
                f"The size extension (small and extra-large species can eat) added {added} "
                f"link(s); the R EcoNeTool trait model gives {added} fewer.")
    producers = set(df.loc[df["FS"] == "FS0", "species"])
    isolated = [s for s in G if G.degree(s) == 0]
    no_prey = [s for s in G if G.in_degree(s) == 0 and s not in producers and s not in isolated]
    if no_prey:
        notes.append(
            f"{len(no_prey)} consumer(s) found no prey under the trait rules and are treated "
            f"as basal (trophic level 1): {', '.join(no_prey)}.")
    if isolated:
        notes.append(f"{len(isolated)} species are isolated (no links): {', '.join(isolated)}.")
    for traits, what in ((CONSUMER_TRAITS, "cannot eat"), (RESOURCE_TRAITS, "cannot be eaten")):
        lost = df["species"][df[list(traits)].isna().any(axis=1)].tolist()
        if lost:
            notes.append(f"Blank {'/'.join(traits)} code, so these {what}: {', '.join(lost)}.")
    return notes


def parse_trait_file(src, threshold: float = 0.05, extend_sizes: bool = True) -> TraitImport:
    """Build a food web from a species x trait-code file (CSV or .xlsx).

    Optional columns ``fg meanB bodymasses met.types efficiencies`` are used
    when present (and must then be filled for every species); missing ones are
    estimated and listed in ``notes``. Raises ``ValueError``."""
    df = _clean_codes(_read_trait_table(src))
    to_estimate = _optional_columns(df)
    _estimate(df, to_estimate)
    M = trait_adjacency(probability_matrix(df, extend_sizes=extend_sizes), threshold)
    lead = ["species", "fg", "meanB", "bodymasses", "met.types", "efficiencies", *TRAIT_COLUMNS]
    G, info = build_food_web(M, df[lead + [c for c in df.columns if c not in lead]])
    return TraitImport(G=G, info=info, notes=_notes(df, G, to_estimate, extend_sizes, threshold),
                       placeholder_biomass="meanB" in to_estimate)


def load_trait_example(key: str, threshold: float = 0.05, extend_sizes: bool = True) -> TraitImport:
    """Load a bundled trait example by ``TRAIT_EXAMPLES`` key."""
    if key not in TRAIT_EXAMPLES:
        raise ValueError(f"Unknown trait example {key!r}.")
    return parse_trait_file(EXAMPLES_DIR / TRAIT_EXAMPLES[key][1], threshold, extend_sizes)
