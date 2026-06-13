"""
Network Analysis Functions for EcoNeTool

This module contains all the helper functions for food web network analysis,
converted from R to Python. Includes topological metrics, biomass-weighted indicators,
energy flux calculations, and keystoneness analysis.

IMPORTANT: For proper energy flux calculations, use the fluxing() function from
flux_calculations module, which implements the complete fluxweb algorithm.
"""

import numpy as np
import pandas as pd
import networkx as nx
from scipy.linalg import inv
from typing import Dict, List
import warnings

# Import flux calculation functions
from flux_calculations import (
    calculate_losses_allometric,
)

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

    # Get adjacency matrix
    # In NetworkX: adj[i,j] = 1 means edge from node i to node j
    # For food webs where edges go prey→predator: adj[i,j] = i is eaten by j
    nodes = list(G.nodes())
    adj = nx.to_numpy_array(G, nodelist=nodes)

    # Short-weighted / prey-averaged trophic level via linear solve.
    # For binary adjacency, diet fractions are uniform (1/#prey), so this is
    # identical to "1 + mean(TL of prey)" for acyclic webs but is stable on cycles.
    col_sums = adj.sum(axis=0)
    col_sums_safe = np.where(col_sums == 0, 1, col_sums)
    # diet[i,j] = fraction of predator i's diet that is prey j
    diet = (adj / col_sums_safe[np.newaxis, :]).T
    A = np.eye(n) - diet
    try:
        tl = np.linalg.solve(A, np.ones(n))
    except np.linalg.LinAlgError:
        warnings.warn("Trophic-level system singular; using pseudo-inverse")
        tl = np.linalg.lstsq(A, np.ones(n), rcond=None)[0]

    # Dense cycles make (I - diet) singular OR merely ill-conditioned. In the
    # ill-conditioned case np.linalg.solve does NOT raise and silently returns
    # values like 1e16; cycles can also produce TL < 1 or negative. Trophic
    # levels are physically >= 1, so flag and clamp non-physical results.
    if not np.all(np.isfinite(tl)) or np.any(tl < 1) or np.any(tl > 100):
        warnings.warn("Trophic levels non-physical (likely a cyclic web); clamped to [1, 100]")
        tl = np.clip(np.nan_to_num(tl, nan=1.0, posinf=100.0, neginf=1.0), 1.0, 100.0)

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
    # Multiply each row by corresponding prey TL (adjacency: rows=prey, cols=predators)
    webtl = adj * tlnodes[:, np.newaxis]
    webtl[webtl == 0] = np.nan

    # Standard deviation of prey TL for each predator (across rows, for each column)
    # axis=0 aggregates rows (calculates SD of prey TL for each predator column)
    with warnings.catch_warnings():
        # ddof=1 makes single-prey predators yield NaN (intended exclusion);
        # that emits a benign "Degrees of freedom <= 0" RuntimeWarning.
        warnings.simplefilter("ignore", RuntimeWarning)
        omninodes = np.nanstd(webtl, axis=0, ddof=1)
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

    NOTE: This function is kept for backward compatibility. For new code,
    use calculate_losses_allometric() from flux_calculations module.

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
    # Use the implementation from flux_calculations module
    return calculate_losses_allometric(bodymasses, met_types, temp)


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
    using the Ulanowicz & Puccia (1990) formulation: Q = DC - PD^T, where DC
    is the column-normalized diet matrix and PD the row-normalized predation
    distribution; MTI = (I - Q)^-1 @ Q with the diagonal zeroed. MTI represents
    the net effect of increasing the biomass of one species on all others.

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

    # Diet composition: DC[i,j] = fraction of predator j's diet that is prey i
    # (column-normalized; columns are predators)
    col_sums = np.sum(adj_matrix, axis=0)
    col_sums_safe = np.where(col_sums == 0, 1, col_sums)
    DC = adj_matrix / col_sums_safe[np.newaxis, :]

    # Predation distribution: PD[i,j] = fraction of prey i's mortality
    # due to predator j (row-normalized; rows are prey)
    row_sums = np.sum(adj_matrix, axis=1)
    row_sums_safe = np.where(row_sums == 0, 1, row_sums)
    PD = adj_matrix / row_sums_safe[:, np.newaxis]

    # Net direct impact of i on j: positive as food (DC) minus negative as
    # predator (PD transposed):  Q[i,j] = DC[i,j] - PD[j,i]
    Q = DC - PD.T

    I = np.eye(n)
    I_minus_Q = I - Q
    if np.abs(np.linalg.det(I_minus_Q)) < 1e-10:
        warnings.warn("(I - Q) is singular or near-singular. Using pseudo-inverse.")
        inv_I_minus_Q = np.linalg.pinv(I_minus_Q)
    else:
        inv_I_minus_Q = inv(I_minus_Q)

    # M[i,j] = total (direct + indirect) impact of i on j (pre-transpose;
    # the return value below transposes to MTI[i,j] = impact of j on i)
    M = inv_I_minus_Q @ Q
    np.fill_diagonal(M, 0)

    # Preserve existing convention: MTI[i,j] = impact of j on i
    return M.T


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

    # Overall effect epsilon_i = L2 norm of species i's impacts.
    # MTI[i,j] = impact of j on i, so species i's impacts are column i.
    overall_effect = np.sqrt(np.sum(MTI ** 2, axis=0))

    # Relative biomass p_i
    total_biomass = np.sum(biomass)
    relative_biomass = biomass / total_biomass if total_biomass > 0 else biomass

    # Libralato (2006) keystoneness index: KS_i = log10(eps_i * (1 - p_i))
    with np.errstate(divide="ignore", invalid="ignore"):
        keystoneness = np.log10(overall_effect * (1.0 - relative_biomass))
    keystoneness[~np.isfinite(keystoneness)] = np.nan

    # Classify relative to the median KS (high impact) and a biomass threshold.
    finite = keystoneness[np.isfinite(keystoneness)]
    ks_threshold = np.median(finite) if finite.size else np.nan
    keystone_status = []
    for i in range(len(keystoneness)):
        if np.isnan(keystoneness[i]):
            keystone_status.append("Undefined")
        elif keystoneness[i] >= ks_threshold and relative_biomass[i] < 0.05:
            keystone_status.append("Keystone")
        elif keystoneness[i] >= ks_threshold and relative_biomass[i] >= 0.05:
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
