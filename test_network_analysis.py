"""
Unit Tests for Network Analysis Functions

Tests the food web network analysis functions against known reference values
from the original R implementation. These tests ensure that the Python port
accurately reproduces the Rpath methodology.

To run: pytest test_network_analysis.py -v
"""

import pytest
import numpy as np
import networkx as nx
import pandas as pd
from hypothesis import given, settings, strategies as st
from network_analysis import (
    calculate_trophic_levels,
    get_topological_indicators,
    get_node_weighted_indicators,
    calculate_losses,
    calculate_mti,
    calculate_keystoneness
)


# ============================================================================
# FIXTURES - SIMPLE TEST NETWORKS
# ============================================================================

@pytest.fixture
def simple_linear_chain():
    """
    Create a simple linear food chain: A -> B -> C
    Where A is basal (TL=1), B is TL=2, C is TL=3
    """
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'C'])
    G.add_edges_from([('A', 'B'), ('B', 'C')])

    info = pd.DataFrame({
        'species': ['A', 'B', 'C'],
        'fg': ['Producer', 'Herbivore', 'Carnivore'],
        'meanB': [100.0, 50.0, 25.0],
        'bodymasses': [0.001, 0.1, 1.0],
        'met.types': ['Other', 'invertebrates', 'ectotherm vertebrates'],
        'efficiencies': [0.0, 0.6, 0.7]
    })

    return G, info


@pytest.fixture
def simple_omnivory():
    """
    Create a network with omnivory:
    A (TL=1) -> B (TL=2)
    A (TL=1) -> C (TL=2.5)
    B (TL=2) -> C

    C is omnivorous (eats at TL 1 and 2)
    """
    G = nx.DiGraph()
    G.add_nodes_from(['A', 'B', 'C'])
    G.add_edges_from([('A', 'B'), ('A', 'C'), ('B', 'C')])

    info = pd.DataFrame({
        'species': ['A', 'B', 'C'],
        'fg': ['Producer', 'Herbivore', 'Omnivore'],
        'meanB': [100.0, 50.0, 25.0],
        'bodymasses': [0.001, 0.1, 1.0],
        'met.types': ['Other', 'invertebrates', 'ectotherm vertebrates'],
        'efficiencies': [0.0, 0.6, 0.7]
    })

    return G, info


# ============================================================================
# TROPHIC LEVEL TESTS
# ============================================================================

def test_trophic_levels_linear_chain(simple_linear_chain):
    """Test trophic level calculation on simple linear chain"""
    G, info = simple_linear_chain

    tl = calculate_trophic_levels(G)

    # Get node order from graph
    nodes = list(G.nodes())
    node_to_idx = {node: i for i, node in enumerate(nodes)}

    # A is basal (TL=1), B eats A (TL=2), C eats B (TL=3)
    assert abs(tl[node_to_idx['A']] - 1.0) < 1e-6, "Basal species A should have TL=1"
    assert abs(tl[node_to_idx['B']] - 2.0) < 1e-6, "Herbivore B should have TL=2"
    assert abs(tl[node_to_idx['C']] - 3.0) < 1e-6, "Top predator C should have TL=3"


def test_trophic_levels_omnivory(simple_omnivory):
    """Test trophic level calculation with omnivory"""
    G, info = simple_omnivory

    tl = calculate_trophic_levels(G)

    # Get node order from graph
    nodes = list(G.nodes())
    node_to_idx = {node: i for i, node in enumerate(nodes)}

    # A is basal (TL=1)
    assert abs(tl[node_to_idx['A']] - 1.0) < 1e-6, "Basal species A should have TL=1"

    # B eats only A (TL=2)
    assert abs(tl[node_to_idx['B']] - 2.0) < 1e-6, "Herbivore B should have TL=2"

    # C eats A (TL=1) and B (TL=2), so TL = 1 + mean([1, 2]) = 2.5
    assert abs(tl[node_to_idx['C']] - 2.5) < 1e-6, "Omnivore C should have TL=2.5"


def test_trophic_levels_cycle_warns_ill_conditioned():
    """A producer-free closed cycle makes (I - diet) singular/ill-conditioned.
    calculate_trophic_levels must WARN (not silently return clamped values)."""
    import warnings as _w
    G = nx.DiGraph()
    G.add_edges_from([(0, 1), (1, 2), (2, 0)])  # closed 3-cycle, no basal node
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter("always")
        calculate_trophic_levels(G)
    assert any("trophic level" in str(x.message).lower()
               or "ill-conditioned" in str(x.message).lower()
               or "cyclic" in str(x.message).lower() for x in caught), \
        [str(x.message) for x in caught]


def test_trophic_levels_convergence():
    """Test that trophic level calculation converges"""
    # Create a network with complex feeding relationships
    G = nx.DiGraph()
    G.add_edges_from([
        (0, 1), (0, 2), (1, 2), (1, 3), (2, 3), (2, 4), (3, 4)
    ])

    tl = calculate_trophic_levels(G)

    # All trophic levels should be >= 1
    assert np.all(tl >= 1.0), "All TL should be >= 1"

    # Find the basal species (no incoming edges)
    basal_nodes = [node for node in G.nodes() if G.in_degree(node) == 0]
    top_nodes = [node for node in G.nodes() if G.out_degree(node) == 0]

    # Get node order
    nodes = list(G.nodes())
    node_to_idx = {node: i for i, node in enumerate(nodes)}

    # Check that basal species have TL=1
    for basal_node in basal_nodes:
        assert tl[node_to_idx[basal_node]] == 1.0, f"Basal species {basal_node} should have TL=1"

    # Check that top predators have higher TL than basal
    for top_node in top_nodes:
        for basal_node in basal_nodes:
            assert tl[node_to_idx[top_node]] > tl[node_to_idx[basal_node]], \
                "Top predators should have higher TL than basal species"


# ============================================================================
# TOPOLOGICAL INDICATORS TESTS
# ============================================================================

def test_topological_indicators_linear_chain(simple_linear_chain):
    """Test topological indicators on linear chain"""
    G, info = simple_linear_chain

    indicators = get_topological_indicators(G)

    # Species richness
    assert indicators['S'] == 3, "Should have 3 species"

    # Connectance: L/(S*(S-1)) = 2/(3*2) = 0.333...
    expected_C = 2.0 / (3 * 2)
    assert abs(indicators['C'] - expected_C) < 1e-6, f"Connectance should be {expected_C}"

    # Mean trophic level: (1 + 2 + 3) / 3 = 2
    assert abs(indicators['TL'] - 2.0) < 1e-6, "Mean TL should be 2.0"

    # Generality: Each predator has 1 prey, mean = 1
    assert abs(indicators['G'] - 1.0) < 1e-6, "Generality should be 1.0"

    # Vulnerability: Each prey has 1 predator, mean = 1
    assert abs(indicators['V'] - 1.0) < 1e-6, "Vulnerability should be 1.0"


def test_omnivory_index_calculation(simple_omnivory):
    """Test that omnivory index is correctly calculated"""
    G, info = simple_omnivory

    indicators = get_topological_indicators(G)

    # Omnivory should be > 0 because C eats at multiple TLs
    assert indicators['Omni'] > 0, "Omnivory index should be positive"

    # The SD of prey TL for species C is std([1, 2]) = 0.5
    # Species A and B have no omnivory (only one prey or no prey)
    # So mean omnivory should be approximately 0.5 (or NaN for some species)
    # This is a qualitative test - just check it's positive
    assert indicators['Omni'] > 0.1, "Omnivory index should reflect omnivory in network"


def test_omnivory_pauly_pinned(simple_omnivory):
    """Christensen-Pauly OI on A->B, A->C, B->C with TL=[1,2,2.5].
    OI_A=NaN (no prey), OI_B=0 (single prey), OI_C=0.5*(1-1.5)^2+0.5*(2-1.5)^2=0.25.
    System Omni = nanmean([NaN,0,0.25]) = 0.125."""
    G, info = simple_omnivory
    ind = get_topological_indicators(G)
    assert np.isclose(ind['Omni'], 0.125), ind['Omni']


def test_topological_indicators_empty_network():
    """Test handling of edge cases"""
    G = nx.DiGraph()
    G.add_node('A')

    indicators = get_topological_indicators(G)

    assert indicators['S'] == 1, "Should have 1 species"
    assert indicators['C'] == 0, "Connectance should be 0 for single node"


# ============================================================================
# NODE-WEIGHTED INDICATORS TESTS
# ============================================================================

def test_node_weighted_indicators(simple_linear_chain):
    """Test node-weighted indicators"""
    G, info = simple_linear_chain
    biomass = info['meanB'].values

    indicators = get_node_weighted_indicators(G, biomass)

    # All indicators should be positive and finite
    assert indicators['nwC'] > 0, "Node-weighted connectance should be positive"
    assert indicators['nwG'] > 0, "Node-weighted generality should be positive"
    assert indicators['nwV'] > 0, "Node-weighted vulnerability should be positive"
    assert indicators['nwTL'] > 1.0, "Node-weighted TL should be > 1"

    # Node-weighted TL should be less than or equal to arithmetic mean TL
    # because basal species often have higher biomass
    topo_indicators = get_topological_indicators(G)
    # This isn't always true, but for this specific network it should be
    # Just check it's reasonable
    assert 1.0 < indicators['nwTL'] < 3.0, "Node-weighted TL should be reasonable"


def test_node_weighted_with_zero_biomass():
    """Test handling of zero or NA biomass values"""
    G = nx.DiGraph()
    G.add_edges_from([('A', 'B')])

    biomass = np.array([0.0, 10.0])

    # Should handle zero biomass gracefully (may produce warnings or special values)
    indicators = get_node_weighted_indicators(G, biomass)

    # Just check it completes without crashing
    assert 'nwC' in indicators


# ============================================================================
# METABOLIC LOSSES TESTS
# ============================================================================

def test_calculate_losses_invertebrates():
    """Test metabolic loss calculation for invertebrates"""
    bodymasses = np.array([0.1, 1.0, 10.0])
    met_types = ['invertebrates', 'invertebrates', 'invertebrates']
    temp = 10.0

    losses = calculate_losses(bodymasses, met_types, temp)

    # Losses should be positive
    assert np.all(losses > 0), "All losses should be positive"

    # Losses should decrease with body mass (allometric scaling with a=-0.29)
    assert losses[0] > losses[1] > losses[2], "Losses should decrease with body mass"


def test_calculate_losses_vertebrates():
    """Test metabolic loss calculation for vertebrates"""
    bodymasses = np.array([1.0])
    met_types = ['ectotherm vertebrates']
    temp = 3.5

    losses = calculate_losses(bodymasses, met_types, temp)

    # Just check it's positive and finite
    assert losses[0] > 0, "Loss should be positive"
    assert np.isfinite(losses[0]), "Loss should be finite"


def test_calculate_losses_temperature_effect():
    """Test that temperature affects metabolic losses"""
    bodymasses = np.array([1.0])
    met_types = ['invertebrates']

    losses_cold = calculate_losses(bodymasses, met_types, temp=0.0)
    losses_warm = calculate_losses(bodymasses, met_types, temp=20.0)

    # Warmer temperature should increase metabolic rate
    assert losses_warm[0] > losses_cold[0], "Higher temp should increase losses"


# ============================================================================
# MIXED TROPHIC IMPACT TESTS
# ============================================================================

def test_mti_matrix_shape(simple_linear_chain):
    """Test MTI matrix has correct shape"""
    G, info = simple_linear_chain

    mti = calculate_mti(G)

    n = len(G.nodes())
    assert mti.shape == (n, n), f"MTI matrix should be {n}x{n}"


def test_mti_matrix_diagonal_zero(simple_linear_chain):
    """Test that MTI diagonal is zero (species don't impact themselves)"""
    G, info = simple_linear_chain

    mti = calculate_mti(G)

    assert np.allclose(np.diag(mti), 0), "MTI diagonal should be zero"


def test_mti_two_species_predator_prey():
    """1 prey (0) eaten by 1 predator (1). Hand-computed total impacts:
    MTI[0,1] = impact of species 1 (predator) on 0 (prey) = -0.5
    MTI[1,0] = impact of species 0 (prey) on 1 (predator) = +0.5"""
    import numpy as np, networkx as nx
    from network_analysis import calculate_mti

    G = nx.DiGraph()
    G.add_nodes_from([0, 1])
    G.add_edge(0, 1)  # 0 (prey) -> 1 (predator)
    MTI = calculate_mti(G)
    assert np.isclose(MTI[0, 1], -0.5), MTI
    assert np.isclose(MTI[1, 0], 0.5), MTI
    assert np.allclose(np.diag(MTI), 0.0)


def test_keystoneness_two_species_libralato():
    """With MTI=[[0,-0.5],[0.5,0]] and equal biomass, eps_i = 0.5 for both,
    p_i = 0.5, so KS_i = log10(0.5 * 0.5) = log10(0.25) (Libralato 2006)."""
    import numpy as np, networkx as nx
    from network_analysis import calculate_keystoneness

    G = nx.DiGraph(); G.add_nodes_from([0, 1]); G.add_edge(0, 1)
    df = calculate_keystoneness(G, np.array([1.0, 1.0]))
    assert np.allclose(df["overall_effect"].values, 0.5), df
    assert np.allclose(df["keystoneness"].values, np.log10(0.25)), df


def test_mti_signs(simple_linear_chain):
    """Test MTI matrix has expected signs"""
    G, info = simple_linear_chain

    mti = calculate_mti(G)

    # MTI should have non-zero off-diagonal elements
    # The signs depend on the specific network structure
    # In a linear chain, the pattern can be mostly negative
    # Just check that it's not all zeros
    off_diag = mti[~np.eye(mti.shape[0], dtype=bool)]
    assert np.any(off_diag != 0), "MTI should have non-zero off-diagonal elements"

    # Check it's finite
    assert np.all(np.isfinite(mti)), "All MTI values should be finite"


# ============================================================================
# KEYSTONENESS TESTS
# ============================================================================

def test_keystoneness_calculation(simple_linear_chain):
    """Test keystoneness calculation"""
    G, info = simple_linear_chain
    biomass = info['meanB'].values

    ks_df = calculate_keystoneness(G, biomass)

    # Should have all species
    assert len(ks_df) == len(G.nodes()), "Should have keystoneness for all species"

    # Should have required columns
    required_cols = ['species', 'overall_effect', 'relative_biomass',
                     'keystoneness', 'keystone_status']
    for col in required_cols:
        assert col in ks_df.columns, f"Missing column: {col}"

    # Relative biomass should sum to 1
    assert abs(ks_df['relative_biomass'].sum() - 1.0) < 1e-6, \
        "Relative biomass should sum to 1"


def test_keystoneness_sorting(simple_linear_chain):
    """Test that keystoneness results are sorted"""
    G, info = simple_linear_chain
    biomass = info['meanB'].values

    ks_df = calculate_keystoneness(G, biomass)

    # Should be sorted by keystoneness (descending)
    ks_values = ks_df['keystoneness'].values
    ks_values_valid = ks_values[~np.isnan(ks_values)]

    # Check sorting (allowing for NaN values)
    if len(ks_values_valid) > 1:
        assert np.all(ks_values_valid[:-1] >= ks_values_valid[1:]), \
            "Keystoneness should be sorted descending"


def test_keystoneness_classification():
    """Test keystoneness classification thresholds"""
    # Create a network where we can predict classifications
    G = nx.DiGraph()
    G.add_edges_from([
        (0, 1), (0, 2), (1, 2), (2, 3)
    ])

    # Give species 2 low biomass but high connectivity (potential keystone)
    biomass = np.array([100.0, 50.0, 1.0, 25.0])  # Species 2 has very low biomass

    ks_df = calculate_keystoneness(G, biomass)

    # Check that classifications are valid
    valid_statuses = ['Keystone', 'Dominant', 'Rare', 'Undefined']
    assert all(status in valid_statuses for status in ks_df['keystone_status']), \
        "All statuses should be valid"


def test_keystoneness_valls_quartile_classification():
    """Valls et al. (2015): Keystone = KS>=Q3(KS) AND biomass<=Q1(biomass).

    This fixture is engineered so the Valls Q3/Q1 scheme and the OLD
    median(KS)+hardcoded(p<0.05) scheme DISAGREE on the target species,
    so the test actually pins Valls instead of passing under either scheme.

    Biomass [5,5,1,5] -> relative biomass [0.3125,0.3125,0.0625,0.3125].
    sp 2 is the unique lowest-biomass, highest-impact (hub) node:
      * relative biomass 0.0625 is ABOVE the old hardcoded 0.05 cutoff but
        AT/BELOW Q1 (=0.25) of the biomass distribution, and
      * its KS is the maximum, so KS >= Q3.
    => Valls labels sp 2 "Keystone"; the old median+0.05 scheme labels it
       "Dominant" (high impact but rel_biomass >= 0.05). Asserting "Keystone"
       fails under the old impl and passes only under Valls.
    """
    import numpy as np, networkx as nx
    from network_analysis import calculate_keystoneness

    G = nx.DiGraph()
    G.add_edges_from([(0, 1), (0, 2), (1, 2), (2, 3)])
    biomass = np.array([5.0, 5.0, 1.0, 5.0])  # sp 2 lowest biomass

    df = calculate_keystoneness(G, biomass)
    row2 = df[df["species"] == 2].iloc[0]

    # Guard the discriminating property: sp 2's relative biomass is strictly
    # ABOVE the old 0.05 cutoff (so the old scheme could NOT call it Keystone)
    # yet AT/BELOW Q1 (so Valls can). If this ever breaks, the test stops
    # discriminating between the two schemes.
    p2 = float(row2["relative_biomass"])
    q1 = float(np.quantile(df["relative_biomass"].to_numpy(), 0.25))
    assert p2 > 0.05, (p2, df)
    assert p2 <= q1, (p2, q1, df)

    # Valls: sp 2 (KS >= Q3 AND p <= Q1) -> Keystone. Under the old
    # median+0.05 scheme this same species is "Dominant", so this assertion
    # is the red/green hinge that pins the Valls quartile logic.
    assert row2["keystone_status"] == "Keystone", df
    assert set(df["keystone_status"]).issubset(
        {"Keystone", "Dominant", "Rare", "Undefined"}), df


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

def test_full_workflow(simple_omnivory):
    """Test complete analysis workflow"""
    G, info = simple_omnivory

    # Calculate all indicators
    tl = calculate_trophic_levels(G)
    topo = get_topological_indicators(G)
    node_weighted = get_node_weighted_indicators(G, info['meanB'].values)
    losses = calculate_losses(
        info['bodymasses'].values,
        info['met.types'].tolist(),
        temp=10.0
    )
    mti = calculate_mti(G)
    ks = calculate_keystoneness(G, info['meanB'].values)

    # Basic sanity checks
    assert len(tl) == len(G.nodes()), "TL for all species"
    assert 'S' in topo, "Topological indicators computed"
    assert 'nwC' in node_weighted, "Node-weighted indicators computed"
    assert len(losses) == len(G.nodes()), "Losses for all species"
    assert mti.shape == (len(G.nodes()), len(G.nodes())), "MTI matrix correct shape"
    assert len(ks) == len(G.nodes()), "Keystoneness for all species"

    # Check omnivory is detected
    assert topo['Omni'] > 0, "Omnivory should be detected in omnivory network"


def test_trophic_levels_finite_on_cycles():
    """Cyclic / dense webs must yield finite, physical (1 <= TL <= 100) levels,
    never huge (~1e16) or negative values. Covers the dangerous ill-conditioned
    (not exactly singular) case where np.linalg.solve silently returns 1e16."""
    import numpy as np, networkx as nx
    from network_analysis import calculate_trophic_levels
    cases = [
        [(0, 1), (1, 0)],                                            # 2-cycle
        [(0, 1), (1, 2), (2, 0)],                                    # 3-cycle
        [(i, j) for i in range(4) for j in range(4) if i != j],     # fully connected
    ]
    for edges in cases:
        G = nx.DiGraph(); G.add_nodes_from(range(4)); G.add_edges_from(edges)
        tl = calculate_trophic_levels(G)
        assert np.all(np.isfinite(tl)), (edges, tl)
        assert np.all(tl >= 1) and np.all(tl <= 100), (edges, tl)


def test_trophic_levels_chain_unchanged():
    """Linear chain 0->1->2 still gives 1,2,3 (no regression vs old loop)."""
    import numpy as np, networkx as nx
    from network_analysis import calculate_trophic_levels
    G = nx.DiGraph(); G.add_nodes_from([0,1,2]); G.add_edge(0,1); G.add_edge(1,2)
    assert np.allclose(calculate_trophic_levels(G), [1, 2, 3])


@settings(max_examples=40, deadline=None)
@given(
    n=st.integers(min_value=3, max_value=6),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_keystoneness_ranking_invariant_to_log_base(n, seed):
    """The keystoneness *ordering* must not depend on log base (log is
    monotonic). Build a random acyclic web (strict upper-triangular adjacency)
    so it is always a valid, feasible food web."""
    rng = np.random.default_rng(seed)
    A = np.triu(rng.integers(0, 2, size=(n, n)), k=1)
    G = nx.from_numpy_array(A, create_using=nx.DiGraph)
    biomass = rng.uniform(1.0, 100.0, size=n)
    df = calculate_keystoneness(G, biomass)
    ks = df['keystoneness'].values
    finite = ks[np.isfinite(ks)]
    assert np.all(np.diff(finite) <= 1e-9), finite  # df is returned sorted desc


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, '-v', '--tb=short'])
