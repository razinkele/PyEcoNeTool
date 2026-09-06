"""The bundled example adjacency CSVs must use the same rows=prey,
columns=predator convention as the tracked BalticFW_adjacency.csv, or a
user who follows examples/README.md builds an inverted food web."""
import pathlib
import pandas as pd
import networkx as nx

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


def test_simple_3species_basal_species_has_zero_in_degree():
    # Under rows=prey, columns=predator, an edge is drawn prey -> predator, so
    # a basal species (eats nothing) must have zero in-degree in the built graph.
    df = pd.read_csv(EXAMPLES / "Simple_3Species_network.csv", index_col=0)
    graph = nx.from_pandas_adjacency(df, create_using=nx.DiGraph)
    assert graph.in_degree("Phytoplankton") == 0, \
        "Phytoplankton is basal (eats nothing) and must have in-degree zero"


def test_caribbean_reef_basal_species_have_zero_in_degree():
    df = pd.read_csv(EXAMPLES / "Caribbean_Reef_network.csv", index_col=0)
    graph = nx.from_pandas_adjacency(df, create_using=nx.DiGraph)
    # Phytoplankton and Macroalgae are the reef's primary producers (basal
    # species): they eat nothing, so under rows=prey/columns=predator they
    # must have zero in-degree in the built graph.
    assert graph.in_degree("Phytoplankton") == 0, \
        "Phytoplankton is basal (eats nothing) and must have in-degree zero"
    assert graph.in_degree("Macroalgae") == 0, \
        "Macroalgae is basal (eats nothing) and must have in-degree zero"


def test_examples_readme_documents_rows_are_prey_convention():
    text = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    assert "row species eats column species" not in text, \
        "README still documents the inverted row-eats-column convention"
    assert "prey" in text.lower() and "predator" in text.lower(), \
        "README must document the rows=prey, columns=predator convention"
