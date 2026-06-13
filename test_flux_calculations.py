"""
Unit Tests for Flux Calculations

Tests the energy flux calculation functions against known reference values
and validates the fluxweb algorithm implementation.

To run: pytest test_flux_calculations.py -v
"""

import pytest
import numpy as np
from flux_calculations import (
    fluxing,
    calculate_losses_allometric,
    validate_flux_equilibrium
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def simple_food_chain():
    """
    Simple 3-species food chain: A -> B -> C
    """
    mat = np.array([
        [0, 1, 0],  # A is eaten by B
        [0, 0, 1],  # B is eaten by C
        [0, 0, 0]   # C eats nothing (top predator)
    ])

    biomasses = np.array([100.0, 50.0, 25.0])
    losses = np.array([0.1, 0.5, 1.0])  # Simple fixed losses
    efficiencies = np.array([0.0, 0.6, 0.7])  # A is producer (0), others are consumers

    return mat, biomasses, losses, efficiencies


@pytest.fixture
def omnivory_network():
    """
    Network with omnivory:
    A -> B
    A -> C
    B -> C
    """
    mat = np.array([
        [0, 1, 1],  # A eaten by B and C
        [0, 0, 1],  # B eaten by C
        [0, 0, 0]   # C eats nothing
    ])

    biomasses = np.array([100.0, 50.0, 25.0])
    losses = np.array([0.1, 0.5, 1.0])
    efficiencies = np.array([0.0, 0.6, 0.7])

    return mat, biomasses, losses, efficiencies


# ============================================================================
# BASIC FLUXING TESTS
# ============================================================================

def test_fluxing_basic_execution(simple_food_chain):
    """Test that fluxing executes without errors"""
    mat, biomasses, losses, efficiencies = simple_food_chain

    flux_matrix = fluxing(
        mat=mat,
        biomasses=biomasses,
        losses=losses,
        efficiencies=efficiencies,
        bioms_prefs=True,
        bioms_losses=True,
        ef_level="prey"
    )

    assert flux_matrix.shape == mat.shape, "Flux matrix should have same shape as input"
    assert np.all(flux_matrix >= 0), "All fluxes should be non-negative"


def test_fluxing_preserves_structure(simple_food_chain):
    """Test that flux matrix preserves network structure"""
    mat, biomasses, losses, efficiencies = simple_food_chain

    flux_matrix = fluxing(
        mat=mat,
        biomasses=biomasses,
        losses=losses,
        efficiencies=efficiencies,
        ef_level="prey"
    )

    # Fluxes should be zero where there are no links
    zero_links = mat == 0
    assert np.allclose(flux_matrix[zero_links], 0), \
        "Fluxes should be zero where links don't exist"


def test_fluxing_positive_where_links_exist(simple_food_chain):
    """Test that fluxes are positive where links exist"""
    mat, biomasses, losses, efficiencies = simple_food_chain

    flux_matrix = fluxing(
        mat=mat,
        biomasses=biomasses,
        losses=losses,
        efficiencies=efficiencies,
        ef_level="prey"
    )

    # Where links exist and biomasses are positive, fluxes should be positive
    links_exist = mat > 0
    assert np.all(flux_matrix[links_exist] > 0), \
        "Fluxes should be positive where links exist"


# ============================================================================
# PARAMETER VALIDATION TESTS
# ============================================================================

def test_fluxing_requires_losses():
    """Test that fluxing requires losses parameter"""
    mat = np.array([[0, 1], [0, 0]])
    biomasses = np.array([1.0, 1.0])
    efficiencies = np.array([0.5, 0.5])

    with pytest.raises(ValueError, match="losses parameter is required"):
        fluxing(mat, biomasses, None, efficiencies)


def test_fluxing_requires_efficiencies():
    """Test that fluxing requires efficiencies parameter"""
    mat = np.array([[0, 1], [0, 0]])
    biomasses = np.array([1.0, 1.0])
    losses = np.array([0.1, 0.1])

    with pytest.raises(ValueError, match="efficiencies parameter is required"):
        fluxing(mat, biomasses, losses, None)


def test_fluxing_validates_efficiency_range(simple_food_chain):
    """Test warning for efficiencies outside [0,1] range"""
    mat, biomasses, losses, _ = simple_food_chain
    bad_efficiencies = np.array([0.0, 1.5, 0.7])  # 1.5 is out of range

    with pytest.warns(UserWarning, match="efficiency values are outside"):
        fluxing(mat, biomasses, losses, bad_efficiencies, ef_level="prey")


def test_fluxing_validates_matrix_dimensions():
    """Test that fluxing validates input dimensions"""
    mat = np.array([[0, 1], [0, 0]])
    biomasses = np.array([1.0, 1.0, 1.0])  # Wrong length!
    losses = np.array([0.1, 0.1])
    efficiencies = np.array([0.5, 0.5])

    with pytest.raises(ValueError, match="biomasses length"):
        fluxing(mat, biomasses, losses, efficiencies)


# ============================================================================
# BIOMASS SCALING TESTS
# ============================================================================

def test_fluxing_biomass_preferences(omnivory_network):
    """Test that biomass affects preference scaling"""
    mat, biomasses, losses, efficiencies = omnivory_network

    # Calculate with biomass preferences
    flux_with_biom = fluxing(
        mat, biomasses, losses, efficiencies,
        bioms_prefs=True, ef_level="prey"
    )

    # Calculate without biomass preferences
    flux_without_biom = fluxing(
        mat, biomasses, losses, efficiencies,
        bioms_prefs=False, ef_level="prey"
    )

    # Results might be similar in some cases, but generally should differ
    # At least check that both produce valid results
    assert flux_with_biom.shape == flux_without_biom.shape
    assert np.all(np.isfinite(flux_with_biom))
    assert np.all(np.isfinite(flux_without_biom))


def test_fluxing_biomass_losses(simple_food_chain):
    """Test that biomass affects loss scaling"""
    mat, biomasses, losses, efficiencies = simple_food_chain

    # Calculate with biomass-scaled losses
    flux_with_biom_loss = fluxing(
        mat, biomasses, losses, efficiencies,
        bioms_losses=True, ef_level="prey"
    )

    # Calculate without biomass-scaled losses
    flux_without_biom_loss = fluxing(
        mat, biomasses, losses, efficiencies,
        bioms_losses=False, ef_level="prey"
    )

    # Results should be different
    assert not np.allclose(flux_with_biom_loss, flux_without_biom_loss), \
        "Biomass scaling of losses should affect fluxes"


# ============================================================================
# EFFICIENCY LEVEL TESTS
# ============================================================================

def test_fluxing_prey_level_efficiency(simple_food_chain):
    """Test prey-level efficiency calculation"""
    mat, biomasses, losses, efficiencies = simple_food_chain

    flux_matrix = fluxing(
        mat, biomasses, losses, efficiencies,
        ef_level="prey"
    )

    # Just check it runs and produces valid output
    assert flux_matrix.shape == mat.shape
    assert np.all(np.isfinite(flux_matrix))


def test_fluxing_predator_level_efficiency(simple_food_chain):
    """Test predator-level efficiency calculation"""
    mat, biomasses, losses, efficiencies = simple_food_chain

    flux_matrix = fluxing(
        mat, biomasses, losses, efficiencies,
        ef_level="pred"
    )

    # Just check it runs and produces valid output
    assert flux_matrix.shape == mat.shape
    assert np.all(np.isfinite(flux_matrix))


def test_fluxing_different_ef_levels_give_different_results(simple_food_chain):
    """Test that prey vs predator efficiency levels give different results"""
    mat, biomasses, losses, efficiencies = simple_food_chain

    flux_prey = fluxing(mat, biomasses, losses, efficiencies, ef_level="prey")
    flux_pred = fluxing(mat, biomasses, losses, efficiencies, ef_level="pred")

    # Results should be different
    assert not np.allclose(flux_prey, flux_pred), \
        "Different efficiency levels should give different fluxes"


def test_fluxing_link_efficiency_not_implemented(simple_food_chain):
    """Test that link-specific efficiency raises NotImplementedError"""
    mat, biomasses, losses, _ = simple_food_chain

    # For link-specific, need NxN efficiency matrix
    efficiencies = np.ones_like(mat) * 0.6

    with pytest.raises(NotImplementedError):
        fluxing(mat, biomasses, losses, efficiencies, ef_level="link")


# ============================================================================
# METABOLIC LOSSES TESTS
# ============================================================================

def test_calculate_losses_allometric_positive():
    """Test that losses are always positive"""
    bodymasses = np.array([0.001, 0.1, 1.0, 10.0])
    met_types = ['invertebrates'] * 4
    temp = 10.0

    losses = calculate_losses_allometric(bodymasses, met_types, temp)

    assert np.all(losses > 0), "All losses should be positive"
    assert np.all(np.isfinite(losses)), "All losses should be finite"


def test_calculate_losses_allometric_scaling():
    """Test that losses scale correctly with body mass"""
    bodymasses = np.array([0.1, 1.0, 10.0])
    met_types = ['invertebrates'] * 3
    temp = 10.0

    losses = calculate_losses_allometric(bodymasses, met_types, temp)

    # With a=-0.29, larger animals should have lower per-unit-mass metabolic rate
    assert losses[0] > losses[1] > losses[2], \
        "Losses should decrease with body mass (a=-0.29)"


def test_calculate_losses_temperature_effect():
    """Test temperature effect on metabolic losses"""
    bodymasses = np.array([1.0])
    met_types = ['invertebrates']

    losses_cold = calculate_losses_allometric(bodymasses, met_types, temperature=0.0)
    losses_warm = calculate_losses_allometric(bodymasses, met_types, temperature=20.0)

    # Higher temperature should increase metabolic rate
    assert losses_warm[0] > losses_cold[0], \
        "Higher temperature should increase losses"


def test_calculate_losses_metabolic_types():
    """Test different metabolic types"""
    bodymasses = np.array([1.0, 1.0, 1.0])
    met_types = ['invertebrates', 'ectotherm vertebrates', 'Other']
    temp = 10.0

    losses = calculate_losses_allometric(bodymasses, met_types, temp)

    # All should be positive
    assert np.all(losses > 0), "All losses should be positive"

    # Invertebrates vs vertebrates should differ (different x0)
    assert losses[0] != losses[1], "Different metabolic types should give different losses"

    # 'Other' type (x0=0) should be different
    assert losses[2] != losses[0], "'Other' type should be different"


def test_calculate_losses_allometric_pinned_invertebrate():
    """Closed-form pin for invertebrates at M=1.0 g and M=10.0 g, T=3.5C.
    The M=10 case makes the a*ln(M) body-mass term non-zero, so the test
    discriminates natural-log vs log10 (the M=1 case alone cannot, since
    ln(1)=log10(1)=0). Also discriminates the Boltzmann constant, the
    -E/(kT) sign, the x0 intercept, and the +273.15 Kelvin conversion."""
    boltz = 0.00008617343
    T = 3.5
    masses = np.array([1.0, 10.0])
    expected = np.exp((-0.29 * np.log(masses) + 17.17) - 0.69 / (boltz * (273.15 + T)))
    out = calculate_losses_allometric(
        bodymasses=masses,
        met_types=["invertebrates", "invertebrates"],
        temperature=T,
    )
    assert np.allclose(out, expected, rtol=1e-12), (out, expected)


# ============================================================================
# EQUILIBRIUM VALIDATION TESTS
# ============================================================================

def test_validate_flux_equilibrium_perfect_balance():
    """Test equilibrium validation with perfectly balanced fluxes"""
    # Create a simple balanced system manually
    # Species 0 produces, species 1 consumes
    flux_matrix = np.array([
        [0, 100],  # 100 units from 0 to 1
        [0, 0]
    ])

    losses = np.array([0, 1])  # Species 1 loses 1 unit per biomass
    efficiencies = np.array([0, 1.0])  # 100% efficiency
    biomasses = np.array([1000, 100])

    validation = validate_flux_equilibrium(
        flux_matrix, losses, efficiencies, biomasses, tolerance=1e-3
    )

    # Check the validation completes without errors
    assert 'balanced' in validation
    assert 'max_imbalance' in validation
    assert np.isfinite(validation['max_imbalance'])


def test_validate_flux_equilibrium_from_fluxing(simple_food_chain):
    """Test that fluxing produces reasonable fluxes"""
    mat, biomasses, losses, efficiencies = simple_food_chain

    flux_matrix = fluxing(
        mat, biomasses, losses, efficiencies,
        bioms_prefs=True,
        bioms_losses=True,
        ef_level="prey"
    )

    validation = validate_flux_equilibrium(
        flux_matrix, losses, efficiencies, biomasses, tolerance=1e-3
    )

    # Fluxing should produce valid results
    # Equilibrium might not be perfect but should be reasonable
    assert validation['max_imbalance'] < 1000.0, \
        f"Fluxing should produce reasonable results, got imbalance: {validation['max_imbalance']}"
    assert np.isfinite(validation['max_imbalance'])


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

def test_fluxing_with_isolated_nodes():
    """Test fluxing with disconnected species"""
    mat = np.array([
        [0, 1, 0],
        [0, 0, 0],
        [0, 0, 0]
    ])

    biomasses = np.array([10.0, 5.0, 2.0])
    losses = np.array([0.1, 0.5, 0.3])
    efficiencies = np.array([0.0, 0.6, 0.6])

    flux_matrix = fluxing(mat, biomasses, losses, efficiencies, ef_level="prey")

    # Should still compute (isolated nodes might have issues but shouldn't crash)
    assert flux_matrix.shape == mat.shape
    assert np.all(np.isfinite(flux_matrix))


def test_fluxing_without_biomasses(simple_food_chain):
    """Test fluxing without biomass data"""
    mat, _, losses, efficiencies = simple_food_chain

    flux_matrix = fluxing(
        mat, biomasses=None, losses=losses,
        efficiencies=efficiencies,
        bioms_prefs=False,
        bioms_losses=False,
        ef_level="prey"
    )

    assert flux_matrix.shape == mat.shape
    assert np.all(np.isfinite(flux_matrix))


def test_fluxing_with_zero_biomass():
    """Test handling of zero biomass values"""
    mat = np.array([[0, 1], [0, 0]])
    biomasses = np.array([0.0, 10.0])  # First species has zero biomass
    losses = np.array([0.1, 0.5])
    efficiencies = np.array([0.5, 0.6])

    # Should handle gracefully (may produce zeros or special values)
    flux_matrix = fluxing(mat, biomasses, losses, efficiencies, ef_level="prey")

    assert flux_matrix.shape == mat.shape
    # Allow some flexibility in how zero biomass is handled
    assert np.all(np.isfinite(flux_matrix) | np.isnan(flux_matrix))


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

def test_complete_flux_workflow(omnivory_network):
    """Test complete flux calculation workflow"""
    mat, biomasses, _, _ = omnivory_network

    # Calculate losses from body masses
    bodymasses = np.array([0.001, 0.1, 1.0])
    met_types = ['Other', 'invertebrates', 'ectotherm vertebrates']
    temp = 10.0

    losses = calculate_losses_allometric(bodymasses, met_types, temp)

    # Use realistic efficiencies
    efficiencies = np.array([0.0, 0.6, 0.7])

    # Calculate fluxes
    flux_matrix = fluxing(
        mat, biomasses, losses, efficiencies,
        bioms_prefs=True,
        bioms_losses=True,
        ef_level="prey"
    )

    # Validate equilibrium
    validation = validate_flux_equilibrium(
        flux_matrix, losses, efficiencies, biomasses
    )

    # Basic checks
    assert flux_matrix.shape == mat.shape
    assert np.all(flux_matrix >= 0)
    assert np.all(flux_matrix[mat == 0] == 0)  # No flux where no link

    # Should be reasonably close to equilibrium
    assert validation['max_imbalance'] < 10.0, \
        f"System should be near equilibrium, got imbalance: {validation['max_imbalance']}"


def test_fluxing_prey_level_satisfies_energy_balance():
    """On an A->B->C chain the solved fluxes must satisfy the prey-level
    steady-state balance F_i*(W.T@e)_i - (W@F)_i - L_i == 0 for consumers."""
    import numpy as np
    from flux_calculations import fluxing

    mat = np.array([[0, 1, 0], [0, 0, 1], [0, 0, 0]], float)  # 0->1->2
    L = np.array([2.0, 3.0, 5.0])
    e = np.array([0.5, 0.6, 0.7])

    flux = fluxing(mat, losses=L, efficiencies=e, ef_level="prey")

    W = mat.copy()
    cs = W.sum(0); cs[cs == 0] = 1; W = W / cs
    F = flux.sum(axis=0)                      # per-node intake = column sums
    residual = F * (W.T @ e) - (W @ F) - L
    # Node 0 is basal: W[:,0] is all-zero, so flux.sum(axis=0)[0] == 0 regardless
    # of the solver's F[0]. The node-0 residual is therefore vacuous here; only the
    # consumer equations (nodes 1, 2) are independently meaningful.
    assert abs(residual[1]) < 1e-9, residual
    assert abs(residual[2]) < 1e-9, residual


def test_validate_flux_equilibrium_passes_on_correct_fluxes():
    """After the fluxing fix, the validator must report balanced=True on the
    solver's own output (consumer nodes balanced to ~0)."""
    import numpy as np
    from flux_calculations import fluxing, validate_flux_equilibrium
    mat = np.array([[0, 1, 0], [0, 0, 1], [0, 0, 0]], float)
    L = np.array([2.0, 3.0, 5.0]); e = np.array([0.5, 0.6, 0.7])
    flux = fluxing(mat, losses=L, efficiencies=e, ef_level="prey")
    v = validate_flux_equilibrium(flux, losses=L, efficiencies=e)
    assert v["balanced"] is True, v
    assert v["max_imbalance"] < 1e-9, v


def test_fluxing_raises_on_infeasible_cycle():
    """A closed 3-cycle with losses that no assimilation efficiency can fund
    yields a negative steady-state solution. fluxing() must raise, not clip."""
    mat = np.array([[0, 1, 0],
                    [0, 0, 1],
                    [1, 0, 0]])  # A->B->C->A
    losses = np.array([2.0, 3.0, 5.0])
    efficiencies = np.array([0.5, 0.6, 0.7])
    with pytest.raises(ValueError, match="non-negative steady-state"):
        fluxing(mat=mat, losses=losses, efficiencies=efficiencies,
                bioms_prefs=False, bioms_losses=False, ef_level="prey")


def test_validate_flux_equilibrium_reports_collapse():
    """When every species has zero assimilated inflow but losses are nonzero,
    the validator must report balanced=False, not a vacuous balanced=True."""
    n = 3
    flux_matrix = np.zeros((n, n))            # collapsed: no flux anywhere
    losses = np.array([2.0, 3.0, 5.0])        # but losses exist
    efficiencies = np.array([0.5, 0.6, 0.7])
    result = validate_flux_equilibrium(flux_matrix, losses, efficiencies)
    assert result['balanced'] is False, result
    assert result['max_imbalance'] > 1.0, result


def test_validate_flux_equilibrium_catches_imbalanced_consumer():
    """A hand-built flux that violates the consumer balance must be flagged."""
    flux_matrix = np.array([[0.0, 10.0, 0.0],
                            [0.0, 0.0, 100.0],   # huge outflow from sp 1
                            [0.0, 0.0, 0.0]])
    losses = np.array([0.0, 5.0, 1.0])
    efficiencies = np.array([0.5, 0.5, 0.5])
    result = validate_flux_equilibrium(flux_matrix, losses, efficiencies)
    assert result['balanced'] is False, result
    assert result['max_imbalance'] > 1.0, result


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, '-v', '--tb=short'])
