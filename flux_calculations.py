"""
Flux Calculations for Food Web Energy Flows

Implementation of the fluxweb algorithm from Gauzens et al. (2019).
Methods in Ecology and Evolution, 10(2), 270-279.

This module implements energy flux calculations based on metabolic theory
and an equilibrium assumption where ingoing fluxes balance outgoing fluxes
for each species.
"""

import numpy as np
import warnings
from typing import Optional, Literal


def fluxing(
    mat: np.ndarray,
    biomasses: Optional[np.ndarray] = None,
    losses: np.ndarray = None,
    efficiencies: np.ndarray = None,
    bioms_prefs: bool = True,
    bioms_losses: bool = True,
    ef_level: Literal["prey", "pred", "link"] = "prey"
) -> np.ndarray:
    """
    Calculate energy fluxes in a food web based on equilibrium assumption.

    Computes fluxes where for each species, the sum of ingoing fluxes
    (gains from eating prey) balances the sum of outgoing fluxes
    (consumption by predators plus metabolic losses).

    Args:
        mat: Square adjacency matrix (n x n) where mat[i,j] = 1 if species j eats species i
             Rows = prey, Columns = predators
        biomasses: Species biomass vector of length n (optional, but recommended)
        losses: Energy losses (metabolic + mortality) for each species (vector of length n)
                Units should be consistent with desired flux output (e.g., J/sec)
        efficiencies: Assimilation efficiencies for each species or link
                     Values between 0 and 1
        bioms_prefs: If True, scale consumer preferences by prey biomass
        bioms_losses: If True, scale losses by biomass
        ef_level: Level at which efficiencies are defined:
                 "prey" = prey-level (efficiency is property of prey)
                 "pred" = predator-level (efficiency is property of predator)
                 "link" = link-specific (efficiencies is n x n matrix)

    Returns:
        Flux matrix (n x n) where flux[i,j] is the energy flow from prey i to predator j
        Units match the losses parameter (e.g., J/sec)

    References:
        Gauzens, B., et al. (2019). fluxweb: An R package to easily estimate
        energy fluxes in food webs. Methods in Ecology and Evolution, 10(2), 270-279.

        Based on the allometric scaling approach from:
        Brown, J. H., et al. (2004). Toward a metabolic theory of ecology.
        Ecology, 85(7), 1771-1789.
    """
    # Input validation
    if not isinstance(mat, np.ndarray):
        mat = np.array(mat)

    if mat.ndim != 2 or mat.shape[0] != mat.shape[1]:
        raise ValueError("mat must be a square matrix")

    n = mat.shape[0]

    if losses is None:
        raise ValueError("losses parameter is required")

    if efficiencies is None:
        raise ValueError("efficiencies parameter is required")

    # Convert inputs to numpy arrays
    losses = np.asarray(losses)
    efficiencies = np.asarray(efficiencies)

    if biomasses is not None:
        biomasses = np.asarray(biomasses)
        if len(biomasses) != n:
            raise ValueError(f"biomasses length ({len(biomasses)}) must match matrix dimension ({n})")

    if losses.ndim != 1 or len(losses) != n:
        raise ValueError(f"losses must be a vector of length {n}")

    # Validate efficiencies
    if ef_level in ["prey", "pred"]:
        if efficiencies.ndim != 1 or len(efficiencies) != n:
            raise ValueError(f"For ef.level='{ef_level}', efficiencies must be a vector of length {n}")
        if np.any((efficiencies < 0) | (efficiencies > 1)):
            warnings.warn("Some efficiency values are outside [0,1] range")
    elif ef_level == "link":
        if efficiencies.shape != (n, n):
            raise ValueError(f"For ef.level='link', efficiencies must be {n}x{n} matrix")
        if np.any((efficiencies < 0) | (efficiencies > 1)):
            warnings.warn("Some efficiency values are outside [0,1] range")
    else:
        raise ValueError(f"ef_level must be 'prey', 'pred', or 'link', got '{ef_level}'")

    # Calculate preference matrix W
    # W[i,j] represents predator j's preference for prey i
    W = mat.copy().astype(float)

    if bioms_prefs and biomasses is not None:
        # Weight by prey biomass: W[i,j] = mat[i,j] * biomass[i]
        W = W * biomasses[:, np.newaxis]

    # Normalize preferences (column-wise, so each predator's preferences sum to 1)
    col_sums = np.sum(W, axis=0)
    # Avoid division by zero for species with no prey
    col_sums[col_sums == 0] = 1
    W = W / col_sums[np.newaxis, :]

    # Calculate total losses per species
    L = losses.copy()
    if bioms_losses and biomasses is not None:
        L = L * biomasses

    # Solve for fluxes based on efficiency level
    if ef_level == "prey":
        # Prey-level efficiency: F_i = (L_i + sum_j W_ij*F_j) / sum_j W_ji*e_j
        #
        # Rearranging for all species simultaneously:
        # F_i * sum_j W_ji*e_j = L_i + sum_j W_ij*F_j
        # F_i * sum_j W_ji*e_j - sum_j W_ij*F_j = L_i
        #
        # In matrix form: (D_e - W.T) @ F = L
        # where D_e is diagonal matrix with D_e[i,i] = sum_j W_ji*e_j

        # Calculate D_e: d_i = sum_j W_ji * e_j = (W.T @ e)_i
        # (efficiency-weighted column combination, NOT row-sum * e_i)
        D_e = W.T @ efficiencies

        # Handle basal species (no prey -> column sums to 0) to avoid singularity
        D_e[D_e == 0] = 1

        # Coefficient matrix: (diag(D_e) - W) @ F = L   (no transpose on W)
        A = np.diag(D_e) - W

        # Solve: A @ F = L
        try:
            F = np.linalg.solve(A, L)
        except np.linalg.LinAlgError:
            warnings.warn("Singular matrix, using pseudo-inverse")
            F = np.linalg.lstsq(A, L, rcond=None)[0]

    elif ef_level == "pred":
        # Predator-level efficiency: F_i = (1/e_i) * (L_i + sum_j W_ij*F_j)
        #
        # Rearranging:
        # e_i * F_i = L_i + sum_j W_ij*F_j
        # e_i * F_i - sum_j W_ij*F_j = L_i
        #
        # In matrix form: (D_e - W.T) @ F = L
        # where D_e is diagonal matrix with D_e[i,i] = e_i

        # Basal species (no prey -> normalized column sums to 0) get diagonal 1.
        # fluxweb grounds basal species by no-prey (colSums(adj)==0), NOT by
        # efficiency==0 (which leaves a real basal species ungrounded and scales
        # its solved intake by 1/e_basal).
        eff_adj = efficiencies.copy().astype(float)
        eff_adj[W.sum(axis=0) == 0] = 1
        A = np.diag(eff_adj) - W

        # Solve
        try:
            F = np.linalg.solve(A, L)
        except np.linalg.LinAlgError:
            warnings.warn("Singular matrix, using pseudo-inverse")
            F = np.linalg.lstsq(A, L, rcond=None)[0]

    else:  # ef_level == "link"
        # Link-specific efficiencies (not commonly used, simplified implementation)
        raise NotImplementedError("Link-specific efficiencies not yet implemented")

    # Ensure non-negative fluxes
    F = np.maximum(F, 0)

    # Create flux matrix: flux[i,j] = W[i,j] * F[j]
    # This represents the flux from prey i to predator j
    flux_matrix = W * F[np.newaxis, :]

    return flux_matrix


def calculate_losses_allometric(
    bodymasses: np.ndarray,
    met_types: list,
    temperature: float = 3.5,
    a: float = -0.29,
    E: float = 0.69
) -> np.ndarray:
    """
    Calculate metabolic losses using allometric scaling.

    Uses the metabolic theory of ecology equation from Brown et al. (2004).

    Args:
        bodymasses: Body masses in grams
        met_types: Metabolic types for each species
                  ("invertebrates", "ectotherm vertebrates", or "Other")
        temperature: Temperature in degrees Celsius (default 3.5°C)
        a: Allometric scaling exponent (default -0.29 for biomass)
        E: Activation energy (default 0.69)

    Returns:
        Metabolic losses in J/sec

    References:
        Brown, J. H., et al. (2004). Toward a metabolic theory of ecology.
        Ecology, 85(7), 1771-1789.
    """
    boltz = 0.00008617343  # Boltzmann constant

    # Normalization constants (intercept of body-mass metabolism scaling)
    losses_param = {
        "invertebrates": 17.17,
        "ectotherm vertebrates": 18.47,
        "Other": 0
    }

    # Get x0 for each species
    x0 = np.array([losses_param.get(mt, 0) for mt in met_types])

    # Calculate losses: exp((a * log(M) + x0) - E/(k*T))
    losses = np.exp(
        (a * np.log(bodymasses) + x0) - E / (boltz * (273.15 + temperature))
    )

    return losses


def validate_flux_equilibrium(
    flux_matrix: np.ndarray,
    losses: np.ndarray,
    efficiencies: np.ndarray,
    biomasses: Optional[np.ndarray] = None,
    tolerance: float = 1e-6
) -> dict:
    """
    Validate that calculated fluxes satisfy equilibrium conditions.

    Checks that for each species: inflows - outflows ≈ 0
    (accounting for metabolic losses)

    Args:
        flux_matrix: Calculated flux matrix
        losses: Metabolic losses vector
        efficiencies: Assimilation efficiencies
        biomasses: Species biomasses (optional)
        tolerance: Maximum allowed imbalance

    Returns:
        Dictionary with validation results:
            'balanced': Boolean, True if all species are in equilibrium
            'imbalances': Vector of imbalances for each species
            'max_imbalance': Maximum absolute imbalance
    """
    n = flux_matrix.shape[0]

    # Calculate inflows (prey being consumed)
    inflows = np.sum(flux_matrix, axis=1) * efficiencies

    # Calculate outflows (consumption by predators + losses)
    outflows = np.sum(flux_matrix, axis=0)

    # Add losses
    L = losses.copy()
    if biomasses is not None:
        L = L * biomasses
    outflows = outflows + L

    # Calculate imbalances
    imbalances = inflows - outflows
    max_imbalance = np.max(np.abs(imbalances))

    return {
        'balanced': max_imbalance < tolerance,
        'imbalances': imbalances,
        'max_imbalance': max_imbalance,
        'mean_imbalance': np.mean(np.abs(imbalances)),
        'relative_imbalance': max_imbalance / np.mean(outflows) if np.mean(outflows) > 0 else np.inf
    }
