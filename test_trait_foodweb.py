"""Tests for trait_foodweb: port of the R EcoNeTool trait-based food web."""
import pathlib

import numpy as np
import pandas as pd
import pytest

from trait_foodweb import (
    TRAIT_CODES, SIZE_EXTENSION, interaction_probability, probability_matrix,
    trait_adjacency,
)

HERE = pathlib.Path(__file__).parent
EXAMPLES = ["simple", "marine_invertebrates", "coastal_ecosystem"]


def _traits(rows):
    return pd.DataFrame(rows, columns=["species", "MS", "FS", "MB", "EP", "PR"])


# --- R parity -------------------------------------------------------------------

@pytest.mark.parametrize("name", EXAMPLES)
def test_matches_r_probabilities_exactly(name):
    d = pd.read_csv(HERE / "examples" / f"trait_foodweb_{name}.csv")
    R = pd.read_csv(HERE / "test_fixtures" / f"trait_probs_{name}.csv", index_col=0)
    P = probability_matrix(d, extend_sizes=False)
    assert list(P.index) == list(R.index) == list(d["species"])
    assert list(P.columns) == list(R.columns) == list(d["species"])
    assert np.allclose(P.to_numpy(), R.to_numpy())


# --- the size table -------------------------------------------------------------

_BAND = {0: .95, -1: .80, 1: .80, -2: .50, 2: .50, -3: .20, 3: .05}


def _band(k):
    return _BAND.get(k, .20 if k < -3 else .05)


def test_size_table_follows_one_diagonal_band():
    """All four R size rows follow one band around 'prey two classes below
    the consumer'; the extension rows are that band extrapolated."""
    from trait_foodweb import MS_MS
    for c in range(3, 7):
        assert MS_MS[f"MS{c}"] == [_band(r - (c - 2)) for r in range(1, 7)]
    for c in (1, 2, 7):
        assert SIZE_EXTENSION[f"MS{c}"] == [_band(r - (c - 2)) for r in range(1, 7)]


def test_extension_rows_are_the_spec_values():
    assert SIZE_EXTENSION["MS1"] == [0.50, .05, .05, .05, .05, .05]
    assert SIZE_EXTENSION["MS2"] == [0.80, 0.50, .05, .05, .05, .05]
    assert SIZE_EXTENSION["MS7"] == [0.20, 0.20, 0.50, 0.80, 0.95, 0.80]


def test_vocabulary():
    assert TRAIT_CODES["MS"] == tuple(f"MS{i}" for i in range(1, 8))
    assert TRAIT_CODES["FS"] == tuple(f"FS{i}" for i in range(0, 8))
    assert TRAIT_CODES["MB"] == tuple(f"MB{i}" for i in range(1, 6))
    assert TRAIT_CODES["EP"] == tuple(f"EP{i}" for i in range(1, 5))
    assert TRAIT_CODES["PR"] == tuple(f"PR{i}" for i in range(0, 9))


# --- rules -----------------------------------------------------------------------

PHYTO_RES = {"MS": "MS1", "MB": "MB2", "EP": "EP1", "PR": "PR0"}


def test_exclusions():
    big_prey = {"MS": "MS7", "MB": "MB5", "EP": "EP1", "PR": "PR0"}
    predator = {"MS": "MS6", "FS": "FS1", "MB": "MB5", "EP": "EP1"}
    assert interaction_probability(predator, big_prey) == 0
    producer = {"MS": "MS4", "FS": "FS0", "MB": "MB1", "EP": "EP3"}
    assert interaction_probability(producer, PHYTO_RES) == 0
    small_grazer = {"MS": "MS2", "FS": "FS6", "MB": "MB2", "EP": "EP1"}
    assert interaction_probability(small_grazer, PHYTO_RES, extend_sizes=False) == 0
    assert interaction_probability(small_grazer, PHYTO_RES, extend_sizes=True) > 0.05


def test_grazer_eats_phytoplankton_orientation():
    d = _traits([("Phyto", "MS1", "FS0", "MB2", "EP1", "PR0"),
                 ("Grazer", "MS3", "FS4", "MB3", "EP1", "PR0")])
    A = trait_adjacency(probability_matrix(d))
    assert A.loc["Phyto", "Grazer"] == 1   # rows = prey
    assert A.loc["Grazer", "Phyto"] == 0


def test_no_self_links():
    d = _traits([("A", "MS4", "FS3", "MB4", "EP2", "PR0"),
                 ("B", "MS4", "FS3", "MB4", "EP2", "PR0")])
    P = probability_matrix(d)
    assert np.all(np.diag(P.to_numpy()) == 0)


def test_threshold_is_strict():
    cons = {"MS": "MS3", "FS": "FS1", "MB": "MB5", "EP": "EP1"}
    res = {"MS": "MS4", "MB": "MB5", "EP": "EP1", "PR": "PR0"}
    assert interaction_probability(cons, res) == pytest.approx(0.05)
    d = _traits([("Small", "MS3", "FS1", "MB5", "EP1", "PR0"),
                 ("Bigger", "MS4", "FS0", "MB5", "EP1", "PR0")])
    A = trait_adjacency(probability_matrix(d), threshold=0.05)
    assert A.loc["Bigger", "Small"] == 0


def test_missing_codes_are_role_aware():
    d = _traits([("Phyto", "MS1", "FS0", "MB2", "EP1", "PR0"),
                 ("NoPR", "MS3", "FS4", "MB3", "EP1", np.nan),
                 ("NoFS", "MS3", np.nan, "MB3", "EP1", "PR0"),
                 ("Pred", "MS5", "FS1", "MB5", "EP1", "PR0")])
    P = probability_matrix(d)                      # [consumer, resource]
    assert P.loc["NoPR"].sum() > 0                 # still eats
    assert P["NoPR"].sum() == 0                    # never eaten
    assert P.loc["NoFS"].sum() == 0                # never eats
    assert P["NoFS"].sum() > 0                     # can be eaten
