"""Tests for load_data.py (offline pickle builder)."""
import pickle
import numpy as np
import networkx as nx
import pandas as pd
import pytest

from load_data import save_to_pickle


def test_pickle_roundtrip_preserves_schema_and_content(tmp_path):
    """save_to_pickle must write a {'network','info'} dict that round-trips —
    this is the exact contract app.py:67-72 depends on."""
    G = nx.DiGraph()
    G.add_edges_from([('A', 'B'), ('B', 'C')])
    info = pd.DataFrame({'species': ['A', 'B', 'C'], 'meanB': [1.0, 2.0, 3.0]})
    out = tmp_path / "test.pkl"
    save_to_pickle(G, info, output_file=str(out))

    with open(out, 'rb') as f:
        data = pickle.load(f)
    assert set(data.keys()) == {'network', 'info'}
    assert list(data['network'].edges()) == [('A', 'B'), ('B', 'C')]
    pd.testing.assert_frame_equal(data['info'], info)
