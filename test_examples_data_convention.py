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
