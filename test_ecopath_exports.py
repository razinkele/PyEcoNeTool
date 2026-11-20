"""Tests for ecopath_import.parse_ecopath_exports: EwE GUI CSV/Excel exports
("Basic estimates" / "Basic input" + "Diet composition") -> (G, info, notes).

The fixtures are synthetic but copy the layout of real EwE 6 exports: an
unnamed group-number column, unquoted names (one with a comma in it, one with
a leading space), a trailing comma on every line, predator columns keyed by
group number for consumers only, and Import / Sum / (1 - Sum) rows.
"""
import io
import os
import pathlib

import pandas as pd
import pytest

from ecopath_import import parse_ecopath_exports

BASIC = (
    ',"Group name","Trophic level","Habitat area (fraction)","Biomass in habitat area (g/m²)",'
    '"Biomass (g/m²)","Production / biomass (computed) (/year)","Consumption / biomass (/year)",'
    '"Ecotrophic Efficiency","Production / consumption","Biom. accumul. (g/m²/year)","Biom. acc. rate (/year)",\n'
    "1,Phytopl,1,1,0.5,0.5,200,,0.79,,,,\n"
    "2,Zoopl (<9,9mm),2,1,0.2,0.2,50,150,0.9,0.33,,,\n"
    "3, Fishes,3.1,0.5,0.04,0.02,1.2,4.1,3.277712E-08,0.29,,,\n"
    "4,Detritu,1,0.057,232,13.224,,,0.78,,,,\n"
)
DIET = (
    ',"Prey \\ predator",2,3,\n'
    "1,Phytopl,0.9,0,\n"
    "2,Zoopl (<9,9mm),0,1,\n"
    "3, Fishes,0,0,\n"
    "4,Detritu,0.1,0,\n"
    "5,Import,0,0,\n"
    "6,Sum,1,1,\n"
    '7,"(1 - Sum)",0,0,\n'
)


def _b(text):
    return text.encode("utf-8")


def test_export_pair_becomes_prey_to_predator_web():
    G, info, notes = parse_ecopath_exports(_b(BASIC), _b(DIET))
    assert set(G.nodes()) == {"Phytopl", "Zoopl (<9,9mm)", "Fishes", "Detritu"}
    assert set(G.edges()) == {("Phytopl", "Zoopl (<9,9mm)"), ("Detritu", "Zoopl (<9,9mm)"),
                              ("Zoopl (<9,9mm)", "Fishes")}


def test_biomass_is_the_overall_column_not_habitat_area():
    _, info, _ = parse_ecopath_exports(_b(BASIC), _b(DIET))
    b = info.set_index("species")["meanB"]
    assert b["Detritu"] == pytest.approx(13.224)
    assert b["Fishes"] == pytest.approx(0.02)


def test_types_inferred_from_rates_and_diet():
    _, info, _ = parse_ecopath_exports(_b(BASIC), _b(DIET))
    t = info.set_index("species")
    assert t.loc["Phytopl", "ewe.type"] == 1
    assert t.loc["Zoopl (<9,9mm)", "ewe.type"] == 0
    assert t.loc["Fishes", "ewe.type"] == 0
    assert t.loc["Detritu", "ewe.type"] == 2
    assert t.loc["Phytopl", "fg"] == "Phytoplankton"
    assert t.loc["Detritu", "fg"] == "Detritus"
    assert t.loc["Fishes", "fg"] == "Fish"
    assert t.loc["Zoopl (<9,9mm)", "PB"] == pytest.approx(50)
    assert t.loc["Zoopl (<9,9mm)", "QB"] == pytest.approx(150)


def test_notes_name_the_export_and_its_unit():
    _, _, notes = parse_ecopath_exports(_b(BASIC), _b(DIET))
    text = " ".join(notes)
    assert "g/m²" in text
    assert "export" in text.lower()
    assert "database" not in text.lower()
    assert "t/km²" not in text


def test_basic_input_uses_habitat_biomass_times_area():
    basic_input = (
        ',"Group name","Habitat area (fraction)","Biomass in habitat area (t/km²)","Z (/year)",'
        '"Production / biomass (/year)","Consumption / biomass (/year)","Ecotrophic efficiency",'
        '"Production / consumption","Unassimil. / consumption","Detritus import (t/km²/year)"\n'
        '1,"Phytopl",1,0.5,,200,,,,"0",\n'
        '2,"Zoopl (<9,9mm)",1,0.2,,50,150,,,"0.2",\n'
        '3,"Fishes",0.5,0.04,,1.2,4.1,,,"0.2",\n'
        '4,"Detritu",0.057,232,,,,,,"0",\n'
    )
    _, info, notes = parse_ecopath_exports(_b(basic_input), _b(DIET))
    b = info.set_index("species")["meanB"]
    assert b["Fishes"] == pytest.approx(0.02)
    assert b["Detritu"] == pytest.approx(232 * 0.057)
    assert "t/km²" in " ".join(notes)


def test_semicolon_decimal_comma_export():
    basic = BASIC.replace(",", ";").replace("(<9;9mm)", "(<9,9mm)")
    # decimal commas in the numbers
    basic = basic.replace("0.5;0.5", "0,5;0,5").replace("13.224", "13,224")
    diet = DIET.replace(",", ";").replace("(<9;9mm)", "(<9,9mm)").replace("0.9;", "0,9;")
    G, info, _ = parse_ecopath_exports(_b(basic), _b(diet))
    assert "Zoopl (<9,9mm)" in G
    assert info.set_index("species").loc["Detritu", "meanB"] == pytest.approx(13.224)
    assert ("Phytopl", "Zoopl (<9,9mm)") in G.edges()


def test_xlsx_exports(tmp_path):
    import csv

    def to_xlsx(text):
        rows = list(csv.reader(io.StringIO(text)))
        # Excel keeps the name in one cell: re-join the unquoted comma split.
        fixed = []
        for r in rows:
            if r and r[1:2] == ["Zoopl (<9"]:
                r = [r[0], "Zoopl (<9,9mm)"] + r[3:]
            fixed.append(r)
        buf = io.BytesIO()
        pd.DataFrame(fixed).to_excel(buf, header=False, index=False)
        return buf.getvalue()

    G, info, _ = parse_ecopath_exports(to_xlsx(BASIC), to_xlsx(DIET))
    assert set(G.edges()) == {("Phytopl", "Zoopl (<9,9mm)"), ("Detritu", "Zoopl (<9,9mm)"),
                              ("Zoopl (<9,9mm)", "Fishes")}


def test_files_from_different_models_rejected():
    other = DIET.replace("3, Fishes", "3,Herring")
    with pytest.raises(ValueError, match="different models"):
        parse_ecopath_exports(_b(BASIC), _b(other))


def test_swapped_files_rejected():
    with pytest.raises(ValueError, match="swapped"):
        parse_ecopath_exports(_b(DIET), _b(BASIC))


def test_wrong_file_rejected():
    with pytest.raises(ValueError, match="Basic estimates"):
        parse_ecopath_exports(_b("a,b,c\n1,2,3\n"), _b(DIET))
    with pytest.raises(ValueError, match="Diet composition"):
        parse_ecopath_exports(_b(BASIC), _b("a,b,c\n1,2,3\n"))


def test_non_numeric_diet_cell_rejected():
    bad = DIET.replace("1,Phytopl,0.9,0,", "1,Phytopl,abc,0,")
    with pytest.raises(ValueError, match="abc"):
        parse_ecopath_exports(_b(BASIC), _b(bad))


def test_blank_biomasses_give_a_readable_error():
    blank = "\n".join(
        ",".join(f if i not in (4, 5) or n == 0 else "" for i, f in enumerate(line.split(",")))
        if "Zoopl" not in line else line.replace(",0.2,0.2,", ",,,")
        for n, line in enumerate(BASIC.splitlines())) + "\n"
    with pytest.raises(ValueError, match="biomass"):
        parse_ecopath_exports(_b(blank), _b(DIET))


def test_result_runs_through_every_analysis():
    from test_data_import import _run_all_analyses
    G, info, _ = parse_ecopath_exports(_b(BASIC), _b(DIET))
    _run_all_analyses(G, info)


# Real exports are research data and are not committed. Point
# ECONETPY_EWE_EXPORTS at a folder holding "<model>-Basic estimates.csv" and
# "<model>-Diet composition.csv" pairs to run this.
_EXPORTS = os.environ.get("ECONETPY_EWE_EXPORTS")
_PAIRS = []
if _EXPORTS:
    for basic in sorted(pathlib.Path(_EXPORTS).rglob("*-Basic estimates.csv")):
        diet = basic.with_name(basic.name.replace("Basic estimates", "Diet composition"))
        if diet.exists():
            _PAIRS.append((basic, diet))


@pytest.mark.skipif(not _PAIRS, reason="set ECONETPY_EWE_EXPORTS to a folder of EwE export pairs")
@pytest.mark.parametrize("pair", _PAIRS, ids=[str(p[0].parent.name) for p in _PAIRS])
def test_real_exports_import(pair):
    G, info, notes = parse_ecopath_exports(*pair)
    assert G.number_of_nodes() >= 2 and G.number_of_edges() >= 1
    assert (info["ewe.type"] == 2).sum() >= 1
    from test_data_import import _run_all_analyses
    _run_all_analyses(G, info)
