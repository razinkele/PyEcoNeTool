"""Tests for ecopath_import: EwE native database -> (G, info)."""
import os
import pathlib

import numpy as np
import pandas as pd
import pytest

from ecopath_import import ecopath_tables_to_food_web, parse_ecopath_db, classify_group


def _groups(rows):
    return pd.DataFrame(rows, columns=["GroupID", "GroupName", "Sequence", "Type", "Biomass"])


def _diet(rows):
    return pd.DataFrame(rows, columns=["PredID", "PreyID", "Diet"])


GROUPS = _groups([
    (1, "Detritus", 5, 2, 10.0),
    (2, "Phytoplankton", 1, 1, 5.0),
    (3, "Mesozooplankton", 2, 0, 3.0),
    (4, "Baltic herring (adult)", 3, 0, 0.5),
    (5, "Great cormorant", 4, 0, 0.01),
])
DIET = _diet([
    (3, 2, 0.8), (3, 1, 0.2),      # zooplankton eats phyto + detritus
    (4, 3, 1.0),                   # herring eats zooplankton
    (5, 4, 1.0),                   # cormorant eats herring
    (3, 0, 0.0),                   # PreyID 0 = import, ignored
    (4, 2, 0.0),                   # zero diet share = no link
])


def test_diet_rows_become_prey_to_predator_edges():
    G, info, notes = ecopath_tables_to_food_web(GROUPS, DIET)
    assert set(G.edges()) == {
        ("Phytoplankton", "Mesozooplankton"), ("Detritus", "Mesozooplankton"),
        ("Mesozooplankton", "Baltic herring (adult)"),
        ("Baltic herring (adult)", "Great cormorant"),
    }
    # species ordered by EwE Sequence
    assert info["species"].tolist()[:2] == ["Phytoplankton", "Mesozooplankton"]


def test_types_and_names_map_to_functional_groups_and_defaults():
    _, info, _ = ecopath_tables_to_food_web(GROUPS, DIET)
    row = info.set_index("species")
    assert row.loc["Detritus", "fg"] == "Detritus"
    assert row.loc["Detritus", "met.types"] == "Other"
    assert row.loc["Phytoplankton", "fg"] == "Phytoplankton"
    assert row.loc["Phytoplankton", "efficiencies"] == pytest.approx(0.77)
    assert row.loc["Mesozooplankton", "fg"] == "Zooplankton"
    assert row.loc["Baltic herring (adult)", "fg"] == "Fish"
    assert row.loc["Baltic herring (adult)", "met.types"] == "ectotherm vertebrates"
    assert row.loc["Great cormorant", "fg"] == "Birds & mammals"
    assert row.loc["Phytoplankton", "meanB"] == 5.0
    assert (info["bodymasses"] > 0).all()


def test_endotherms_are_flagged_in_notes():
    _, _, notes = ecopath_tables_to_food_web(GROUPS, DIET)
    assert any("cormorant" in n.lower() and "endotherm" in n.lower() for n in notes)


def test_groups_with_missing_biomass_are_dropped_and_reported():
    g = pd.concat([GROUPS, _groups([(6, "Common gobies", 6, 0, -9999.0),
                                    (7, "Mysids", 7, 0, 0.0)])], ignore_index=True)
    d = pd.concat([DIET, _diet([(6, 3, 1.0), (7, 3, 1.0), (4, 6, 0.0)])], ignore_index=True)
    G, info, notes = ecopath_tables_to_food_web(g, d)
    assert "Common gobies" not in G and "Mysids" not in G
    assert any("Common gobies" in n and "Mysids" in n for n in notes)


def test_name_classifier_examples():
    assert classify_group("Macrophytobenthos", 1) == "Macrophytes"
    assert classify_group("Mixotrophs", 0.5) == "Phytoplankton"
    assert classify_group("Macrozoobenthos filtrators", 0) == "Benthos"
    assert classify_group("Polychaetes", 0) == "Benthos"
    assert classify_group("Pike-perch (juvenile/sub-adult)", 0) == "Fish"
    assert classify_group("Grey seal", 0) == "Birds & mammals"
    assert classify_group("Jellyfish", 0) == "Zooplankton"
    assert classify_group("Squid", 0) == "Invertebrates"


@pytest.mark.parametrize("name, fg", [
    ("grey heron", "Birds & mammals"), ("larus", "Birds & mammals"),
    ("goosander", "Birds & mammals"), ("Scoters", "Birds & mammals"),
    ("Long-tailed duck", "Birds & mammals"),
    ("Perciformes", "Fish"), ("Cypriniformes", "Fish"), ("Planktivorous fish", "Fish"),
    ("Polycha", "Benthos"), ("Amphipo", "Benthos"), ("oligochets", "Benthos"),
    ("Mobile crustaceans", "Benthos"), ("Saduria entomon", "Benthos"),
    ("Copepod", "Zooplankton"), ("Apendic", "Zooplankton"), ("Ichthyopl", "Zooplankton"),
])
def test_classifier_on_names_seen_in_real_models(name, fg):
    assert classify_group(name, 0) == fg


@pytest.mark.parametrize("name", ["Seagras", "Rhodoph"])
def test_truncated_macrophyte_names(name):
    assert classify_group(name, 1) == "Macrophytes"


def test_unmatched_consumers_are_unclassified_and_listed():
    g = pd.concat([GROUPS, _groups([(6, "Hgutula", 6, 0, 0.2)])], ignore_index=True)
    d = pd.concat([DIET, _diet([(6, 3, 1.0)])], ignore_index=True)
    _, info, notes = ecopath_tables_to_food_web(g, d)
    assert info.set_index("species").loc["Hgutula", "fg"] == "Unclassified consumers"
    assert any("Hgutula" in n and "classif" in n.lower() for n in notes)


def test_result_runs_through_every_analysis():
    from test_data_import import _run_all_analyses
    G, info, _ = ecopath_tables_to_food_web(GROUPS, DIET)
    _run_all_analyses(G, info)


def test_no_usable_diet_rejected():
    with pytest.raises(ValueError, match="link"):
        ecopath_tables_to_food_web(GROUPS, _diet([(3, 0, 1.0)]))


def test_missing_tables_columns_rejected():
    with pytest.raises(ValueError, match="GroupName"):
        ecopath_tables_to_food_web(GROUPS.drop(columns=["GroupName"]), DIET)


def test_parse_rejects_non_database_file(tmp_path):
    f = tmp_path / "x.ewemdb"
    f.write_bytes(b"not an access database")
    with pytest.raises(ValueError):
        parse_ecopath_db(f)


def test_parse_rejects_wrong_extension(tmp_path):
    f = tmp_path / "x.csv"
    f.write_bytes(b"a,b\n")
    with pytest.raises(ValueError, match=r"extension|.ewemdb"):
        parse_ecopath_db(f)


# Real EwE databases are not committed (third-party model data). Point
# ECONETPY_EWE_SAMPLES at a folder of .ewemdb/.eweaccdb files to run this.
_SAMPLES = os.environ.get("ECONETPY_EWE_SAMPLES")
_SAMPLE_FILES = sorted(
    p for ext in ("*.ewemdb", "*.eweaccdb", "*.mdb", "*.accdb")
    for p in (pathlib.Path(_SAMPLES).glob(ext) if _SAMPLES else [])
)


@pytest.mark.skipif(not _SAMPLE_FILES, reason="set ECONETPY_EWE_SAMPLES to a folder of EwE databases")
@pytest.mark.parametrize("path", _SAMPLE_FILES, ids=lambda p: p.name)
def test_real_ewe_databases_import_and_analyse(path):
    from test_data_import import _run_all_analyses
    G, info, notes = parse_ecopath_db(path)
    assert G.number_of_edges() > 0
    _run_all_analyses(G, info)
