"""Shared pytest fixtures for EconetPy tests."""
import numpy as np
import networkx as nx
import pytest


@pytest.fixture
def viz_graph():
    """3-node A->B->C with biomass for viz builder tests."""
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'C'])
    G.add_edges_from([('A', 'B'), ('B', 'C')])
    species = ['Sprat', 'Herring', 'Cod']
    groups = ['planktivore', 'planktivore', 'piscivore']
    biomass = np.array([100.0, 50.0, 25.0])
    colors = ['#1f77b4', '#1f77b4', '#ff7f0e']
    return G, species, groups, biomass, colors
