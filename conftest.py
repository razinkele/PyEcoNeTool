"""Shared pytest fixtures for EconetPy tests."""
import numpy as np
import networkx as nx
import pandas as pd
import pytest


@pytest.fixture
def linear_chain():
    """A -> B -> C; TL = [1, 2, 3]."""
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'C'])
    G.add_edges_from([('A', 'B'), ('B', 'C')])
    return G


@pytest.fixture
def omnivore_web():
    """A->B, A->C, B->C; TL = [1, 2, 2.5]; C is the omnivore."""
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'C'])
    G.add_edges_from([('A', 'B'), ('A', 'C'), ('B', 'C')])
    return G


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
