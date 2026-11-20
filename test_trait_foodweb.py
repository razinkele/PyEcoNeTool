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


# --- trait files (Task 2) -------------------------------------------------------

import io

from trait_foodweb import TRAIT_EXAMPLES, TraitImport, load_trait_example, parse_trait_file

FOUR = (
    "species,MS,FS,MB,EP,PR\n"
    "Phyto,MS1,FS0,MB2,EP1,PR0\n"
    "Zoo,MS2,FS6,MB2,EP1,PR4\n"
    "Fish,MS5,FS1,MB5,EP2,PR0\n"
    "Worm,MS3,FS5,MB3,EP4,PR2\n"
)


def _b(s):
    return s.encode("utf-8")


@pytest.mark.parametrize("key", EXAMPLES)
def test_examples_load_and_analyse(key):
    from test_data_import import _run_all_analyses
    assert key in TRAIT_EXAMPLES
    r = load_trait_example(key)
    assert isinstance(r, TraitImport)
    assert r.placeholder_biomass is True
    _run_all_analyses(r.G, r.info)


@pytest.mark.parametrize("key, with_ext, without", [
    ("simple", 7, 6), ("marine_invertebrates", 92, 84), ("coastal_ecosystem", 551, 478)])
def test_extension_link_counts(key, with_ext, without):
    on, off = load_trait_example(key), load_trait_example(key, extend_sizes=False)
    assert on.G.number_of_edges() == with_ext
    assert off.G.number_of_edges() == without
    note = next(n for n in on.notes if "R EcoNeTool" in n)
    assert str(with_ext - without) in note
    assert not any("R EcoNeTool" in n for n in off.notes)


def test_estimates_follow_spec():
    r = parse_trait_file(_b(FOUR))
    row = r.info.set_index("species")
    assert row["fg"].to_dict() == {"Phyto": "Primary producers", "Zoo": "Zooplankton",
                                   "Fish": "Fish", "Worm": "Benthos"}
    assert row.loc["Fish", "bodymasses"] == pytest.approx(0.01 * 35 ** 3)
    assert row.loc["Phyto", "bodymasses"] == pytest.approx(0.01 * 0.05 ** 3)
    assert row.loc["Fish", "met.types"] == "ectotherm vertebrates"
    assert row.loc["Zoo", "met.types"] == "invertebrates"
    assert row.loc["Phyto", "efficiencies"] == pytest.approx(0.77)
    assert row.loc["Zoo", "efficiencies"] == pytest.approx(0.906)
    assert (r.info["meanB"] == 1.0).all()
    assert r.placeholder_biomass is True
    assert any("placeholder" in n.lower() for n in r.notes)
    assert any("fg" in n for n in r.notes)          # points to adding an fg column


def test_given_columns_are_used_and_no_placeholder_flag():
    lines = FOUR.strip().split("\n")
    text = lines[0] + ",meanB\n" + "\n".join(f"{l},{v}" for l, v in zip(lines[1:], [50, 8, 2, 4])) + "\n"
    r = parse_trait_file(_b(text))
    assert r.info.set_index("species")["meanB"].to_dict() == {"Phyto": 50, "Zoo": 8, "Fish": 2, "Worm": 4}
    assert r.placeholder_biomass is False
    assert not any("placeholder" in n.lower() for n in r.notes)


def test_partly_filled_optional_column_rejected():
    lines = FOUR.strip().split("\n")
    text = lines[0] + ",meanB\n" + "\n".join(f"{l},{v}" for l, v in zip(lines[1:], [50, "", 2, 4])) + "\n"
    with pytest.raises(ValueError, match="meanB"):
        parse_trait_file(_b(text))


def test_no_prey_and_isolated_are_listed():
    r = load_trait_example("coastal_ecosystem", extend_sizes=False)
    assert any("Seal_grey" in n and "isolated" in n.lower() for n in r.notes)
    assert any("Copepod_small" in n and "prey" in n.lower() for n in r.notes)


def test_threshold_changes_links():
    loose = load_trait_example("coastal_ecosystem", threshold=0.0)
    strict = load_trait_example("coastal_ecosystem", threshold=0.5)
    assert loose.G.number_of_edges() > 551 > strict.G.number_of_edges()


# Review Focus
def test_codes_case_and_spaces_normalised():
    r = parse_trait_file(_b(FOUR.replace("MS5,FS1", " ms5 , fs1 ")))
    assert r.info.set_index("species").loc["Fish", "MS"] == "MS5"


@pytest.mark.parametrize("bad", ["3", "MS9"])
def test_bad_codes_rejected(bad):
    with pytest.raises(ValueError, match=r"MS.*MS1") as e:
        parse_trait_file(_b(FOUR.replace("Fish,MS5", f"Fish,{bad}")))
    assert bad in str(e.value)


def test_only_producers_rejected():
    text = "species,MS,FS,MB,EP,PR\nA,MS1,FS0,MB2,EP1,PR0\nB,MS2,FS0,MB2,EP1,PR0\n"
    with pytest.raises(ValueError, match="no feeding links"):
        parse_trait_file(_b(text))


def test_xlsx_with_blank_rows_and_extra_columns():
    df = pd.read_csv(io.StringIO(FOUR))
    df["notes"] = ["a", "b", "c", "d"]
    df = pd.concat([df, pd.DataFrame([[None] * df.shape[1]] * 2, columns=df.columns)])
    buf = io.BytesIO(); df.to_excel(buf, index=False, engine="openpyxl")
    r = parse_trait_file(buf.getvalue())
    assert r.G.number_of_nodes() == 4
    assert "notes" in r.info.columns


def test_missing_required_trait_column_rejected():
    text = "\n".join(",".join(l.split(",")[:-1]) for l in FOUR.strip().split("\n")) + "\n"
    with pytest.raises(ValueError, match="PR"):
        parse_trait_file(_b(text))


def test_duplicate_species_rejected():
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        parse_trait_file(_b(FOUR + "Fish,MS5,FS1,MB5,EP2,PR0\n"))


@pytest.mark.parametrize("name", ["MS_MS", "FS_MS", "MB_MB", "EP_MS", "PR_MS"])
def test_tables_match_r_cell_by_cell(name):
    """Every cell of every table, including rows no example uses (FS3, FS7,
    PR1, PR2, PR4), against the tables exported from R."""
    import trait_foodweb
    R = pd.read_csv(HERE / "test_fixtures" / f"trait_table_{name}.csv", index_col=0)
    port = getattr(trait_foodweb, name)
    assert list(port) == list(R.index)
    for row in R.index:
        assert port[row] == pytest.approx(R.loc[row].tolist()), f"{name}[{row}]"
