import networkx as nx, pandas as pd, pytest
from pathlib import Path


def test_load_baltic_data_node_ids_are_species_names():
    """After load, node IDs == species names, in the same order."""
    import os
    if not Path("BalticFW_network.graphml").exists():
        pytest.skip("source GraphML not present")
    from load_data import load_baltic_data
    G, info = load_baltic_data()
    assert list(G.nodes()) == info['species'].tolist()


def test_load_baltic_data_raises_on_name_mismatch(tmp_path, monkeypatch):
    """A GraphML/CSV name mismatch must raise, not print-and-continue."""
    # Build a tiny mismatched pair and point load_baltic_data at it via cwd.
    g = nx.DiGraph(); g.add_node('n0', name='Cod'); g.add_node('n1', name='Sprat')
    g.add_edge('n0', 'n1')
    nx.write_graphml(g, tmp_path / "BalticFW_network.graphml")
    pd.DataFrame({'species': ['Cod', 'Herring'], 'fg': ['Fish', 'Fish'],
                  'meanB': [1.0, 2.0], 'bodymasses': [1.0, 2.0],
                  'met.types': ['Other', 'Other'], 'efficiencies': [0.5, 0.5]}
                 ).to_csv(tmp_path / "BalticFW_species_info.csv", index=False)
    monkeypatch.chdir(tmp_path)
    from load_data import load_baltic_data
    with pytest.raises(ValueError, match="match|align"):
        load_baltic_data()


def test_load_default_data_pickle_is_name_keyed():
    """The on-disk pickle path must yield name-keyed nodes (catches a stale pkl)."""
    if not Path("BalticFW_network.graphml").exists():
        pytest.skip("source not present")
    import app
    G, info = app.load_default_data()
    assert list(G.nodes()) == info['species'].tolist()
