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
