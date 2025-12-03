"""
Network Analysis Functions for EcoNeTool

This module contains all the helper functions for food web network analysis,
converted from R to Python. Includes topological metrics, biomass-weighted indicators,
energy flux calculations, and keystoneness analysis.
"""

import numpy as np
import pandas as pd
import networkx as nx
import igraph as ig
from scipy.linalg import inv
from typing import Dict, Tuple, List
import warnings

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

# Color scheme for functional groups (Benthos, Detritus, Fish, Phytoplankton, Zooplankton)
COLOR_SCHEME = ["orange", "darkgrey", "blue", "green", "cyan"]

# Trophic level calculation parameters
TROPHIC_LEVEL_MAX_ITER = 100      # Maximum iterations for convergence
TROPHIC_LEVEL_CONVERGENCE = 0.0001  # Convergence threshold

# Flux calculation parameters
FLUX_CONVERSION_FACTOR = 86.4     # Convert J/sec to kJ/day
FLUX_LOG_EPSILON = 0.00001        # Small value to avoid log(0)

# Visualization parameters
NODE_SIZE_SCALE = 25              # Scaling factor for node size by biomass
NODE_SIZE_MIN = 4                 # Minimum node size
EDGE_WIDTH_SCALE = 15             # Scaling factor for edge width by flux
EDGE_WIDTH_MIN = 0.1              # Minimum edge width
EDGE_ARROW_SIZE_TOPOLOGY = 0.3    # Arrow size for topology networks
EDGE_ARROW_SIZE_FLUX = 0.05       # Arrow size for flux networks


# ============================================================================
# TROPHIC LEVEL CALCULATION
# ============================================================================

def calculate_trophic_levels(G: nx.DiGraph) -> np.ndarray:
    """
    Calculate trophic levels for a food web.

    Computes trophic levels using an iterative algorithm. Basal species
    (no prey) are assigned TL = 1. Consumer species have TL = 1 + mean(TL of prey).
    The algorithm iterates until convergence or maximum iterations reached.

    Args:
        G: NetworkX DiGraph representing the food web (directed graph)
           Edges go from prey to predator

    Returns:
        numpy array of trophic levels for each species/node

    References:
        Williams, R. J., & Martinez, N. D. (2004). Limits to trophic levels and
        omnivory in complex food webs. Proceedings of the Royal Society B, 271(1540), 549-556.
    """
    if not isinstance(G, nx.DiGraph):
        raise ValueError("Input 'G' must be a NetworkX DiGraph object")

    n = len(G.nodes())
    if n == 0:
        raise ValueError("Network contains no vertices")

    # Initialize all to TL = 1
    tl = np.ones(n)

    # Get adjacency matrix (rows = predators, cols = prey)
    nodes = list(G.nodes())
    adj = nx.to_numpy_array(G, nodelist=nodes)

    # Iterate until convergence
    converged = False
    for iteration in range(TROPHIC_LEVEL_MAX_ITER):
        tl_old = tl.copy()

        for i in range(n):
            # Find prey of species i (incoming edges)
            prey_indices = np.where(adj[i, :] > 0)[0]

            if len(prey_indices) > 0:
                # TL = 1 + mean TL of prey
                tl[i] = 1 + np.mean(tl[prey_indices])
            else:
                # Basal species
                tl[i] = 1

        # Check for convergence
        if np.max(np.abs(tl - tl_old)) < TROPHIC_LEVEL_CONVERGENCE:
            converged = True
            break

    if not converged:
        warnings.warn(f"Trophic level calculation did not converge after {TROPHIC_LEVEL_MAX_ITER} iterations")

    return tl


# ============================================================================
# TOPOLOGICAL (QUALITATIVE) INDICATORS
# ============================================================================

def get_topological_indicators(G: nx.DiGraph) -> Dict[str, float]:
    """
    Calculate topological (qualitative) indicators for a food web.

    Computes structural properties of the food web network without considering
    node weights (biomass). These are purely topological metrics.

    Args:
        G: NetworkX DiGraph representing the food web

    Returns:
        Dictionary containing:
            S: Species richness (number of taxa)
            C: Connectance (proportion of realized links)
            G: Generality (mean number of prey per predator)
            V: Vulnerability (mean number of predators per prey)
            ShortPath: Mean shortest path length
            TL: Mean trophic level
            Omni: Omnivory index (mean SD of prey trophic levels)

    References:
        Williams, R. J., & Martinez, N. D. (2000). Simple rules yield complex food webs.
        Nature, 404(6774), 180-183.
    """
    if not isinstance(G, nx.DiGraph):
        raise ValueError("Input 'G' must be a NetworkX DiGraph object")

    S = len(G.nodes())
    if S <= 1:
        warnings.warn("Network has only one or zero species. Metrics may be undefined.")

    # Connectance
    L = len(G.edges())
    C = L / (S * (S - 1)) if S > 1 else 0

    # Generality (mean in-degree for predators)
    in_degrees = dict(G.in_degree())
    predators = [node for node, deg in in_degrees.items() if deg > 0]
    G_val = np.mean([in_degrees[p] for p in predators]) if predators else 0

    # Vulnerability (mean out-degree for prey)
    out_degrees = dict(G.out_degree())
    prey = [node for node, deg in out_degrees.items() if deg > 0]
    V = np.mean([out_degrees[p] for p in prey]) if prey else 0

    # Mean shortest path
    try:
        if nx.is_weakly_connected(G):
            ShortPath = nx.average_shortest_path_length(G.to_undirected())
        else:
            # For disconnected graphs, calculate on largest component
            largest_cc = max(nx.weakly_connected_components(G), key=len)
            subG = G.subgraph(largest_cc).to_undirected()
            ShortPath = nx.average_shortest_path_length(subG)
    except:
        ShortPath = np.nan

    # Trophic levels
    tlnodes = calculate_trophic_levels(G)
    TL = np.mean(tlnodes)

    # Omnivory index
    adj = nx.to_numpy_array(G, nodelist=list(G.nodes()))
    webtl = adj * tlnodes  # Broadcasting TL values
    webtl[webtl == 0] = np.nan

    # Standard deviation of prey TL for each consumer
    omninodes = np.nanstd(webtl, axis=1)
    Omni = np.nanmean(omninodes)

    return {
        'S': S,
        'C': C,
        'G': G_val,
        'V': V,
        'ShortPath': ShortPath,
        'TL': TL,
        'Omni': Omni
    }


# ============================================================================
# NODE-WEIGHTED (QUANTITATIVE) INDICATORS
# ============================================================================

def get_node_weighted_indicators(G: nx.DiGraph, biomass: np.ndarray) -> Dict[str, float]:
    """
    Calculate node-weighted (quantitative) indicators for a food web.

    Computes network metrics weighted by node biomass. These metrics account
    for the relative importance of species based on their biomass.

    Args:
        G: NetworkX DiGraph representing the food web
        biomass: numpy array of biomass values for each node (same order as G.nodes())

    Returns:
        Dictionary containing:
            nwC: Node-weighted connectance
            nwG: Node-weighted generality
            nwV: Node-weighted vulnerability
            nwTL: Node-weighted mean trophic level

    References:
        Olivier, P., et al. (2019). Exploring the temporal variability of a food web
        using long-term biomonitoring data. Ecography, 42(11), 2107-2121.
    """
    if not isinstance(G, nx.DiGraph):
        raise ValueError("Input 'G' must be a NetworkX DiGraph object")

    if len(biomass) != len(G.nodes()):
        raise ValueError("Length of biomass must match number of nodes")

    if np.any(biomass < 0):
        raise ValueError("Biomass values must be non-negative")

    if np.any(np.isnan(biomass)):
        warnings.warn("NA values found in biomass, results may be unreliable")

    # Calculate trophic levels
    tlnodes = calculate_trophic_levels(G)

    # Get degrees
    in_degrees = np.array([G.in_degree(node) for node in G.nodes()])
    out_degrees = np.array([G.out_degree(node) for node in G.nodes()])
    total_degrees = in_degrees + out_degrees

    S = len(G.nodes())
    total_biomass = np.sum(biomass)

    # Node-weighted connectance
    nwC = np.sum(total_degrees * biomass) / (2 * total_biomass * (S - 1)) if S > 1 and total_biomass > 0 else 0

    # Node-weighted generality
    predators = in_degrees > 0
    nwG = (np.sum((in_degrees * biomass)[predators]) / np.sum(biomass[predators])) if np.sum(predators) > 0 else 0

    # Node-weighted vulnerability
    prey = out_degrees > 0
    nwV = (np.sum((out_degrees * biomass)[prey]) / np.sum(biomass[prey])) if np.sum(prey) > 0 else 0

    # Node-weighted mean trophic level
    nwTL = np.sum(tlnodes * biomass) / total_biomass if total_biomass > 0 else 0

    return {
        'nwC': nwC,
        'nwG': nwG,
        'nwV': nwV,
        'nwTL': nwTL
    }


# ============================================================================
# METABOLIC LOSSES CALCULATION
# ============================================================================

def calculate_losses(bodymasses: np.ndarray, met_types: List[str], temp: float = 3.5) -> np.ndarray:
    """
    Calculate metabolic losses for species.

    Computes species-specific metabolic losses using the allometric equation
    from metabolic theory of ecology (Brown et al. 2004).

    Args:
        bodymasses: numpy array of body masses in grams
        met_types: list of metabolic types ("invertebrates", "ectotherm vertebrates", or "Other")
        temp: Temperature in degrees Celsius (default = 3.5°C for Gulf of Riga spring)

    Returns:
        numpy array of metabolic losses (J/sec) for each species

    References:
        Brown, J. H., et al. (2004). Toward a metabolic theory of ecology.
        Ecology, 85(7), 1771-1789.
    """
    # Constants from metabolic theory
    boltz = 0.00008617343  # Boltzmann constant
    a = -0.29              # Allometric scaling (for biomass)
    E = 0.69               # Activation energy

    # Normalization constants (intercept of body-mass metabolism scaling relationship)
    losses_param = {
        "invertebrates": 17.17,
        "ectotherm vertebrates": 18.47,
        "Other": 0
    }

    # Get x0 for each species based on metabolic type
    x0 = np.array([losses_param.get(mt, 0) for mt in met_types])

    # Calculate losses using allometric equation
    # Formula: exp((a * log(M_i) + x0) - E/(k*(T+273.15)))
    losses = np.exp((a * np.log(bodymasses) + x0) - E / (boltz * (273.15 + temp)))

    return losses


# ============================================================================
# FLUX INDICATORS (SHANNON DIVERSITY-BASED)
# ============================================================================

def calculate_flux_indicators(flux_matrix: np.ndarray, loop: bool = False) -> Dict[str, float]:
    """
    Calculate link-weighted flux indicators.

    Computes Shannon diversity-based indicators from an energy flux matrix.
    These metrics account for the distribution of energy flows across trophic links.

    Args:
        flux_matrix: numpy array of energy fluxes between species
        loop: whether to include self-loops in connectance calculation

    Returns:
        Dictionary containing:
            lwC: Link-weighted connectance
            lwG: Link-weighted generality (effective number of prey)
            lwV: Link-weighted vulnerability (effective number of predators)

    References:
        Bersier, L. F., et al. (2002). Quantitative descriptors of food web matrices.
        Ecology, 83(9), 2394-2407.
    """
    W_net = flux_matrix.copy()

    # Taxon-specific Shannon indices of inflows
    sum_in = np.sum(W_net, axis=0)  # Column sums

    # Diversity of k species inflows
    with np.errstate(divide='ignore', invalid='ignore'):
        H_in_mat = (W_net.T / sum_in).T * np.log((W_net.T / sum_in).T)
    H_in_mat[~np.isfinite(H_in_mat)] = 0  # Convert NaN to 0's
    H_in = -np.sum(H_in_mat, axis=0)

    # Effective number of prey or resources
    N_res = np.where(sum_in == 0, H_in, np.exp(H_in))

    # Taxon-specific Shannon indices of outflows
    sum_out = np.sum(W_net, axis=1)  # Row sums

    # Diversity of k species outflows
    with np.errstate(divide='ignore', invalid='ignore'):
        H_out_mat = (W_net / sum_out[:, np.newaxis]) * np.log(W_net / sum_out[:, np.newaxis])
    H_out_mat[~np.isfinite(H_out_mat)] = 0
    H_out = -np.sum(H_out_mat, axis=1)

    # Effective number of predators or consumers
    N_con = np.where(sum_out == 0, H_out, np.exp(H_out))

    # Quantitative weighted connectance
    no_species = W_net.shape[0]
    tot_mat = np.sum(W_net)

    LD = (1 / (2 * tot_mat)) * (np.sum(sum_in * N_res) + np.sum(sum_out * N_con)) if tot_mat > 0 else 0
    lwC = LD / (no_species if loop else (no_species - 1)) if no_species > 1 else 0

    # Positional index
    denominator = sum_in * N_res + sum_out * N_con
    pos_ind = np.where(denominator > 0, (sum_in * N_res) / denominator, 0)

    # Weighted quantitative Generality
    lwG = np.sum(sum_in * N_res) / tot_mat if tot_mat > 0 else 0

    # Weighted quantitative Vulnerability
    lwV = np.sum(sum_out * N_con) / tot_mat if tot_mat > 0 else 0

    return {
        'lwC': lwC,
        'lwG': lwG,
        'lwV': lwV
    }


# ============================================================================
# MIXED TROPHIC IMPACT (MTI) ANALYSIS
# ============================================================================

def calculate_mti(G: nx.DiGraph) -> np.ndarray:
    """
    Calculate Mixed Trophic Impact (MTI) matrix.

    Computes the direct and indirect impacts of each species on all others
    using the ECOPATH approach. MTI represents the net effect of increasing
    the biomass of one species on all other species in the food web.

    Args:
        G: NetworkX DiGraph representing the food web

    Returns:
        Matrix where MTI[i,j] represents the impact of species j on species i

    References:
        Ulanowicz, R. E., & Puccia, C. J. (1990). Mixed trophic impacts in ecosystems.
        Coenoses, 5(1), 7-16.

        Libralato, S., et al. (2006). A method for identifying keystone species in
        food web models. Ecological Modelling, 195(3-4), 153-171.
    """
    if not isinstance(G, nx.DiGraph):
        raise ValueError("Input 'G' must be a NetworkX DiGraph object")

    n = len(G.nodes())
    nodes = list(G.nodes())
    adj_matrix = nx.to_numpy_array(G, nodelist=nodes)

    # Create Diet Composition (DC) matrix
    # DC[i,j] = proportion of predator i's diet that is prey j
    DC = np.zeros((n, n))

    # Calculate row sums (total consumption per predator)
    row_sums = np.sum(adj_matrix, axis=1)

    # Normalize each row by its sum (if non-zero)
    for i in range(n):
        if row_sums[i] > 0:
            DC[i, :] = adj_matrix[i, :] / row_sums[i]

    # Create identity matrix
    I = np.eye(n)

    # Calculate (I - DC)^(-1)
    I_minus_DC = I - DC

    # Check if matrix is invertible
    if np.abs(np.linalg.det(I_minus_DC)) < 1e-10:
        warnings.warn("Diet composition matrix is singular or near-singular. Using pseudo-inverse.")
        I_minus_DC_inv = np.linalg.pinv(I_minus_DC)
    else:
        I_minus_DC_inv = inv(I_minus_DC)

    # Calculate MTI matrix
    MTI = -I_minus_DC_inv @ DC

    # Set diagonal to 0
    np.fill_diagonal(MTI, 0)

    return MTI


# ============================================================================
# KEYSTONENESS ANALYSIS
# ============================================================================

def calculate_keystoneness(G: nx.DiGraph, biomass: np.ndarray) -> pd.DataFrame:
    """
    Calculate Keystoneness Index.

    Computes the keystoneness index for each species based on their
    overall impact on the ecosystem and their relative biomass.

    Args:
        G: NetworkX DiGraph representing the food web
        biomass: numpy array of biomass values for each node

    Returns:
        DataFrame with columns:
            species: Species name
            overall_effect: Total impact on the ecosystem
            relative_biomass: Biomass relative to total
            keystoneness: Keystoneness index
            keystone_status: Classification (Keystone/Dominant/Rare)

    References:
        Libralato, S., et al. (2006). A method for identifying keystone species in
        food web models. Ecological Modelling, 195(3-4), 153-171.
    """
    # Calculate MTI matrix
    MTI = calculate_mti(G)

    # Calculate overall effect (sum of absolute MTI values for each impactor)
    overall_effect = np.sum(np.abs(MTI), axis=0)

    # Calculate relative biomass
    total_biomass = np.sum(biomass)
    relative_biomass = biomass / total_biomass if total_biomass > 0 else biomass

    # Calculate keystoneness index
    keystoneness = np.log(1 + overall_effect) / np.log(1 + relative_biomass)

    # Handle infinite or undefined values
    keystoneness[np.isinf(keystoneness)] = np.nan
    keystoneness[np.isnan(keystoneness)] = np.nan

    # Classify species
    keystone_status = []
    for i in range(len(keystoneness)):
        if np.isnan(keystoneness[i]):
            keystone_status.append("Undefined")
        elif keystoneness[i] > 1 and relative_biomass[i] < 0.05:
            keystone_status.append("Keystone")
        elif keystoneness[i] > 0 and relative_biomass[i] >= 0.05:
            keystone_status.append("Dominant")
        else:
            keystone_status.append("Rare")

    # Create results dataframe
    results = pd.DataFrame({
        'species': list(G.nodes()),
        'overall_effect': overall_effect,
        'relative_biomass': relative_biomass,
        'keystoneness': keystoneness,
        'keystone_status': keystone_status
    })

    # Sort by keystoneness (descending)
    results = results.sort_values('keystoneness', ascending=False).reset_index(drop=True)

    return results
