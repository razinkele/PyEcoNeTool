"""Tests for data_import.parse_food_web — the pure upload parser/validator."""
import io
import pathlib

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from data_import import parse_food_web, EXAMPLE_DATASETS, load_example

HERE = pathlib.Path(__file__).parent
EX = HERE / "examples"

NET_3 = (
    ',Phyto,Zoo,Fish\n'
    'Phyto,0,1,0\n'
    'Zoo,0,0,1\n'
    'Fish,0,0,0\n'
)
INFO_3 = (
    'species,fg,meanB,bodymasses,met.types,efficiencies\n'
    'Phyto,Phytoplankton,5000,1e-05,Other,0.45\n'
    'Zoo,Zooplankton,800,0.001,invertebrates,0.75\n'
    'Fish,Fish,100,50,ectotherm vertebrates,0.85\n'
)


def _b(s: str) -> bytes:
    return s.encode("utf-8")


# --- happy path ------------------------------------------------------------

def test_parses_rows_are_prey_into_prey_to_predator_edges():
    G, info = parse_food_web(_b(NET_3), _b(INFO_3))
    assert isinstance(G, nx.DiGraph)
    assert set(G.edges()) == {("Phyto", "Zoo"), ("Zoo", "Fish")}
    assert G.in_degree("Phyto") == 0  # basal
    assert list(G.nodes()) == info["species"].tolist()


def test_info_rows_reordered_to_matrix_order_and_extra_columns_kept():
    lines = INFO_3.strip().split("\n")
    header = lines[0] + ",taxon"
    rows = [r + ",x" for r in reversed(lines[1:])]
    G, info = parse_food_web(_b(NET_3), _b("\n".join([header, *rows]) + "\n"))
    assert info["species"].tolist() == ["Phyto", "Zoo", "Fish"]
    assert "taxon" in info.columns
    assert info.index.tolist() == [0, 1, 2]


def test_numeric_columns_are_floats():
    _, info = parse_food_web(_b(NET_3), _b(INFO_3))
    for col in ("meanB", "bodymasses", "efficiencies"):
        assert info[col].dtype.kind == "f"


def test_accepts_semicolon_decimal_comma_and_bom():
    net = "﻿" + NET_3.replace(",", ";")
    info = "﻿" + (
        'species;fg;meanB;bodymasses;met.types;efficiencies\n'
        'Phyto;Phytoplankton;5000,5;0,00001;Other;0,45\n'
        'Zoo;Zooplankton;800;0,001;invertebrates;0,75\n'
        'Fish;Fish;100;50;ectotherm vertebrates;0,85\n'
    )
    G, df = parse_food_web(_b(net), _b(info))
    assert G.number_of_edges() == 2
    assert df.loc[0, "meanB"] == pytest.approx(5000.5)
    assert df.loc[0, "efficiencies"] == pytest.approx(0.45)


def test_names_are_stripped_of_whitespace():
    net = NET_3.replace("Zoo,0,0,1", " Zoo ,0,0,1")
    G, _ = parse_food_web(_b(net), _b(INFO_3))
    assert "Zoo" in G


def test_baltic_adjacency_round_trips_to_graphml_edges():
    from load_data import load_baltic_data
    G_ref, info_ref = load_baltic_data()
    info_csv = (HERE / "BalticFW_species_info.csv").read_bytes()
    net_csv = (HERE / "BalticFW_adjacency.csv").read_bytes()
    G, info = parse_food_web(net_csv, info_csv)
    assert set(G.edges()) == set(G_ref.edges())
    assert set(G.nodes()) == set(G_ref.nodes())


# --- rejections --------------------------------------------------------------

@pytest.mark.parametrize("net, match", [
    (',A,B\nA,0,1\n', "square"),
    (',A,B\nA,0,1\nC,0,0\n', "same species"),
    (',A,A\nA,0,1\nA,0,0\n', "[Dd]uplicate"),
    (',A,B\nA,0,2\nB,0,0\n', "0 or 1"),
    (',A,B\nA,0,x\nB,0,0\n', "0 or 1"),
    (',A,B\nA,0,\nB,0,0\n', "0 or 1"),
])
def test_bad_network_rejected(net, match):
    info = (
        'species,fg,meanB,bodymasses,met.types,efficiencies\n'
        'A,Phytoplankton,1,1,Other,0.5\nB,Fish,1,1,Other,0.5\n'
    )
    with pytest.raises(ValueError, match=match):
        parse_food_web(_b(net), _b(info))


def test_missing_required_column_rejected():
    info = INFO_3.replace(",efficiencies", "").replace(",0.45", "").replace(",0.75", "").replace(",0.85", "")
    with pytest.raises(ValueError, match="efficiencies"):
        parse_food_web(_b(NET_3), _b(info))


def test_species_set_mismatch_rejected():
    info = INFO_3.replace("Fish,Fish", "Cod,Fish")
    with pytest.raises(ValueError, match="Fish|Cod"):
        parse_food_web(_b(NET_3), _b(info))


def test_duplicate_species_in_info_rejected():
    info = INFO_3 + 'Fish,Fish,100,50,ectotherm vertebrates,0.85\n'
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        parse_food_web(_b(NET_3), _b(info))


@pytest.mark.parametrize("old, new, match", [
    ("5000,1e-05", "abc,1e-05", "meanB"),
    ("5000,1e-05", "-1,1e-05", "meanB"),
    ("800,0.001", "800,0", "bodymasses"),
    ("Other,0.45", "Other,1.5", "efficiencies"),
    ("Other,0.45", "Other,", "efficiencies"),
    ("Other,0.45", "plants,0.45", "met.types"),
])
def test_bad_species_values_rejected(old, new, match):
    with pytest.raises(ValueError, match=match):
        parse_food_web(_b(NET_3), _b(INFO_3.replace(old, new)))


def test_oversized_file_rejected():
    big = b"x" * (2 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="too large"):
        parse_food_web(big, _b(INFO_3))


def test_too_many_species_rejected(monkeypatch):
    import data_import
    monkeypatch.setattr(data_import, "MAX_SPECIES", 2)
    with pytest.raises(ValueError, match="species"):
        parse_food_web(_b(NET_3), _b(INFO_3))


def test_no_links_rejected():
    net = ',Phyto,Zoo,Fish\nPhyto,0,0,0\nZoo,0,0,0\nFish,0,0,0\n'
    with pytest.raises(ValueError, match="no feeding links"):
        parse_food_web(_b(net), _b(INFO_3))


def test_empty_or_garbage_rejected_with_valueerror():
    with pytest.raises(ValueError):
        parse_food_web(b"", _b(INFO_3))
    with pytest.raises(ValueError):
        parse_food_web(b"\x00\xff\xfe garbage", _b(INFO_3))


def test_accepts_paths_and_file_objects():
    G1, _ = parse_food_web(EX / "Simple_3Species_network.csv", EX / "Simple_3Species_info.csv")
    G2, _ = parse_food_web(io.BytesIO(_b(NET_3)), io.BytesIO(_b(INFO_3)))
    assert G1.number_of_edges() == 2 and G2.number_of_edges() == 2


# --- examples + downstream acceptance ----------------------------------------

def test_example_registry_lists_only_loadable_datasets():
    assert set(EXAMPLE_DATASETS) == {"Simple_3Species", "Caribbean_Reef"}
    for key in EXAMPLE_DATASETS:
        G, info = load_example(key)
        assert G.number_of_edges() > 0


def test_unknown_example_rejected():
    with pytest.raises(ValueError):
        load_example("../BalticFW")


def _run_all_analyses(G, info):
    from network_analysis import (
        calculate_trophic_levels, get_topological_indicators,
        get_node_weighted_indicators, calculate_losses, calculate_mti,
        calculate_keystoneness,
    )
    from flux_calculations import fluxing
    for method in ("prey_averaged", "short_weighted"):
        tl = calculate_trophic_levels(G, method=method)
        assert np.all(np.isfinite(np.asarray(list(tl.values()) if isinstance(tl, dict) else tl, dtype=float)))
    get_topological_indicators(G)
    losses = calculate_losses(info["bodymasses"].values, info["met.types"].tolist(), 3.5)
    adj = nx.to_numpy_array(G, nodelist=info["species"].tolist())
    flux = fluxing(mat=adj, biomasses=info["meanB"].values, losses=losses,
                   efficiencies=info["efficiencies"].values, bioms_prefs=True,
                   bioms_losses=True, ef_level="prey")
    assert np.all(np.isfinite(flux))
    get_node_weighted_indicators(G, info["meanB"].values)
    mti = calculate_mti(G)
    calculate_keystoneness(G, info["meanB"].values, mti=mti)


@pytest.mark.parametrize("key", ["Simple_3Species", "Caribbean_Reef"])
def test_examples_run_through_every_analysis(key):
    G, info = load_example(key)
    _run_all_analyses(G, info)


def test_hand_written_upload_runs_through_every_analysis():
    G, info = parse_food_web(_b(NET_3), _b(INFO_3))
    _run_all_analyses(G, info)


# --- web shapes ----------------------------------------------------------------

INFO_4 = INFO_3 + 'Seal,Fish,200,80000,ectotherm vertebrates,0.85\n'


@pytest.mark.parametrize("name, net", [
    ("cannibal", ',Phyto,Zoo,Fish\nPhyto,0,1,0\nZoo,0,0,1\nFish,0,0,1\n'),
    ("two-species loop fed from a basal", ',Phyto,Zoo,Fish\nPhyto,0,1,0\nZoo,0,0,1\nFish,0,1,0\n'),
    ("isolated species", ',Phyto,Zoo,Fish\nPhyto,0,1,0\nZoo,0,0,0\nFish,0,0,0\n'),
])
def test_unusual_but_valid_shapes_load_and_analyse(name, net):
    G, info = parse_food_web(_b(net), _b(INFO_3))
    _run_all_analyses(G, info)


def test_web_without_basal_species_rejected():
    net = ',Phyto,Zoo,Fish\nPhyto,0,1,0\nZoo,0,0,1\nFish,1,0,0\n'
    with pytest.raises(ValueError, match="basal"):
        parse_food_web(_b(net), _b(INFO_3))


def test_closed_loop_unreachable_from_basal_rejected():
    # Phyto -> Zoo is fine; Fish <-> Seal only eat each other.
    net = (',Phyto,Zoo,Fish,Seal\nPhyto,0,1,0,0\nZoo,0,0,0,0\n'
           'Fish,0,0,0,1\nSeal,0,0,1,0\n')
    with pytest.raises(ValueError, match="Fish|Seal"):
        parse_food_web(_b(net), _b(INFO_4))


# --- Excel -----------------------------------------------------------------------

def _xlsx(csv_text: str, header: bool = True) -> bytes:
    df = pd.read_csv(io.StringIO(csv_text), header=None, dtype=str, keep_default_na=False)
    buf = io.BytesIO()
    df.to_excel(buf, header=False, index=False, engine="openpyxl")
    return buf.getvalue()


def test_xlsx_files_parse_like_csv():
    G, info = parse_food_web(_xlsx(NET_3), _xlsx(INFO_3))
    assert set(G.edges()) == {("Phyto", "Zoo"), ("Zoo", "Fish")}
    assert info["meanB"].tolist() == [5000.0, 800.0, 100.0]


def test_xlsx_with_numeric_cells_parses():
    net = pd.DataFrame([[0, 1, 0], [0, 0, 1], [0, 0, 0]],
                       index=["Phyto", "Zoo", "Fish"], columns=["Phyto", "Zoo", "Fish"])
    buf = io.BytesIO(); net.to_excel(buf, engine="openpyxl")
    info = pd.read_csv(io.StringIO(INFO_3))
    buf2 = io.BytesIO(); info.to_excel(buf2, index=False, engine="openpyxl")
    G, df = parse_food_web(buf.getvalue(), buf2.getvalue())
    assert G.number_of_edges() == 2 and df["bodymasses"].iloc[0] == pytest.approx(1e-5)


def test_corrupt_xlsx_rejected_with_valueerror():
    with pytest.raises(ValueError, match="Excel"):
        parse_food_web(b"PK\x03\x04 not really a zip", _b(INFO_3))
