"""
Network Visualization Functions for EcoNeTool using PyVis

This module handles the conversion from R's visNetwork to Python's PyVis,
creating interactive network visualizations for food web analysis.
"""

import networkx as nx
import numpy as np
import pandas as pd
from pyvis.network import Network
from typing import Dict, List, Tuple, Optional
from network_analysis import (
    calculate_trophic_levels,
    COLOR_SCHEME,
    NODE_SIZE_SCALE,
    NODE_SIZE_MIN,
    EDGE_WIDTH_SCALE,
    EDGE_WIDTH_MIN
)


def create_topology_network(
    G: nx.DiGraph,
    species_names: List[str],
    functional_groups: List[str],
    biomass: np.ndarray,
    colors: List[str],
    width: str = "100%",
    height: str = "600px"
) -> Network:
    """
    Create an interactive topology network visualization using PyVis.

    This function converts a NetworkX DiGraph to a PyVis Network with
    nodes sized by biomass and positioned by trophic level.

    Args:
        G: NetworkX DiGraph representing the food web
        species_names: List of species names (node labels)
        functional_groups: List of functional group assignments
        biomass: numpy array of biomass values
        colors: List of colors for each node (by functional group)
        width: Width of the visualization (default: "100%")
        height: Height of the visualization (default: "600px")

    Returns:
        PyVis Network object
    """
    # Calculate trophic levels for Y positioning
    trophic_levels = calculate_trophic_levels(G)

    # Create PyVis network
    net = Network(
        width=width,
        height=height,
        directed=True,
        notebook=False,
        bgcolor="#ffffff",
        font_color="#000000"
    )

    # Configure physics for Barnes-Hut layout (similar to R visNetwork)
    net.set_options("""
    {
        "physics": {
            "enabled": true,
            "solver": "barnesHut",
            "barnesHut": {
                "gravitationalConstant": -2000,
                "centralGravity": 0.1,
                "springLength": 200,
                "springConstant": 0.02,
                "damping": 0.7,
                "avoidOverlap": 0.2
            },
            "stabilization": {
                "enabled": true,
                "iterations": 1000,
                "updateInterval": 50,
                "onlyDynamicEdges": false,
                "fit": true
            },
            "minVelocity": 0.5,
            "maxVelocity": 20
        },
        "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true
        },
        "edges": {
            "smooth": {
                "type": "curvedCW",
                "roundness": 0.2
            },
            "arrows": {
                "to": {
                    "enabled": true,
                    "scaleFactor": 0.5
                }
            },
            "scaling": {
                "min": 1,
                "max": 1
            }
        }
    }
    """)

    # Normalize Y positions based on trophic levels
    min_tl = np.min(trophic_levels)
    max_tl = np.max(trophic_levels)
    y_positions = 100 * (trophic_levels - min_tl) / (max_tl - min_tl) if max_tl > min_tl else np.zeros(len(trophic_levels))

    # Add nodes
    nodes = list(G.nodes())
    for i, node in enumerate(nodes):
        # Create tooltip with species information (single line HTML for PyVis)
        title = f"<b>{species_names[i]}</b><br>Functional Group: {functional_groups[i]}<br>Trophic Level: {trophic_levels[i]:.2f}<br>Biomass: {biomass[i]:.2f} g/km²/day"

        # Calculate node size based on biomass
        node_size = NODE_SIZE_MIN + (biomass[i] / np.max(biomass) * NODE_SIZE_SCALE) if np.max(biomass) > 0 else NODE_SIZE_MIN

        net.add_node(
            node,
            label=species_names[i],
            title=title,
            color=colors[i],
            size=node_size,
            x=None,  # Let physics determine X position
            y=y_positions[i],
            physics=True,
            shape="dot",
            group=functional_groups[i]
        )

    # Add edges (no value attribute to prevent auto-scaling)
    for edge in G.edges():
        net.add_edge(
            edge[0],
            edge[1],
            width=1.0,
            color="rgba(128, 128, 128, 0.5)",
            title=""  # No hover text for edges in topology view
        )

    return net


def create_flux_network(
    G: nx.DiGraph,
    species_names: List[str],
    functional_groups: List[str],
    biomass: np.ndarray,
    colors: List[str],
    flux_matrix: np.ndarray,
    width: str = "100%",
    height: str = "600px"
) -> Network:
    """
    Create an interactive flux-weighted network visualization using PyVis.

    Similar to topology network but with edge widths weighted by energy flux.

    Args:
        G: NetworkX DiGraph representing the food web
        species_names: List of species names (node labels)
        functional_groups: List of functional group assignments
        biomass: numpy array of biomass values
        colors: List of colors for each node (by functional group)
        flux_matrix: numpy array of flux values (kJ/day/km²)
        width: Width of the visualization (default: "100%")
        height: Height of the visualization (default: "600px")

    Returns:
        PyVis Network object
    """
    # Calculate trophic levels for Y positioning
    trophic_levels = calculate_trophic_levels(G)

    # Create weighted graph from flux matrix
    G_weighted = nx.DiGraph()
    nodes = list(G.nodes())
    G_weighted.add_nodes_from(nodes)

    # Add weighted edges from flux matrix
    for i, from_node in enumerate(nodes):
        for j, to_node in enumerate(nodes):
            if flux_matrix[i, j] > 0:
                G_weighted.add_edge(from_node, to_node, weight=flux_matrix[i, j])

    # Create PyVis network
    net = Network(
        width=width,
        height=height,
        directed=True,
        notebook=False,
        bgcolor="#ffffff",
        font_color="#000000"
    )

    # Configure physics (same as topology network)
    net.set_options("""
    {
        "physics": {
            "enabled": true,
            "solver": "barnesHut",
            "barnesHut": {
                "gravitationalConstant": -2000,
                "centralGravity": 0.1,
                "springLength": 200,
                "springConstant": 0.02,
                "damping": 0.7,
                "avoidOverlap": 0.2
            },
            "stabilization": {
                "enabled": true,
                "iterations": 1000,
                "updateInterval": 50,
                "onlyDynamicEdges": false,
                "fit": true
            },
            "minVelocity": 0.5,
            "maxVelocity": 20
        },
        "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true
        },
        "edges": {
            "smooth": {
                "type": "curvedCW",
                "roundness": 0.2
            },
            "arrows": {
                "to": {
                    "enabled": true,
                    "scaleFactor": 0.3
                }
            },
            "scaling": {
                "min": 0.1,
                "max": 15
            }
        }
    }
    """)

    # Normalize Y positions based on trophic levels
    min_tl = np.min(trophic_levels)
    max_tl = np.max(trophic_levels)
    y_positions = 100 * (trophic_levels - min_tl) / (max_tl - min_tl) if max_tl > min_tl else np.zeros(len(trophic_levels))

    # Add nodes
    for i, node in enumerate(nodes):
        # Create tooltip (single line HTML for PyVis)
        title = f"<b>{species_names[i]}</b><br>Functional Group: {functional_groups[i]}<br>Trophic Level: {trophic_levels[i]:.2f}<br>Biomass: {biomass[i]:.2f} g/km²/day"

        # Calculate node size based on biomass
        node_size = NODE_SIZE_MIN + (biomass[i] / np.max(biomass) * NODE_SIZE_SCALE) if np.max(biomass) > 0 else NODE_SIZE_MIN

        net.add_node(
            node,
            label=species_names[i],
            title=title,
            color=colors[i],
            size=node_size,
            x=None,
            y=y_positions[i],
            physics=True,
            shape="dot",
            group=functional_groups[i]
        )

    # Get all flux values for scaling
    flux_values = []
    for edge in G_weighted.edges(data=True):
        flux_values.append(edge[2]['weight'])

    max_flux = np.max(flux_values) if flux_values else 1.0

    # Add weighted edges
    for edge in G_weighted.edges(data=True):
        flux = edge[2]['weight']

        # Calculate edge width based on flux
        edge_width = EDGE_WIDTH_MIN + (flux / max_flux * EDGE_WIDTH_SCALE)

        # Format flux value for tooltip
        if flux >= 0.01:
            flux_display = f"{flux:.4f}"
        elif flux >= 0.0001:
            flux_display = f"{flux:.6f}"
        else:
            flux_display = f"{flux:.2e}"

        title = f"Flux: {flux_display} kJ/day/km²"

        net.add_edge(
            edge[0],
            edge[1],
            width=edge_width,
            title=title,
            color="rgba(128, 128, 128, 0.5)"
        )

    return net


def get_functional_group_colors(functional_groups: List[str]) -> Tuple[List[str], Dict[str, str]]:
    """
    Map functional groups to colors from the COLOR_SCHEME.

    Args:
        functional_groups: List of functional group names

    Returns:
        Tuple of (list of colors for each node, dict mapping group name to color)
    """
    unique_groups = sorted(list(set(functional_groups)))

    # Create color mapping
    color_map = {}
    for i, group in enumerate(unique_groups):
        if i < len(COLOR_SCHEME):
            color_map[group] = COLOR_SCHEME[i]
        else:
            # If more groups than colors, cycle through colors
            color_map[group] = COLOR_SCHEME[i % len(COLOR_SCHEME)]

    # Create list of colors for each node
    node_colors = [color_map[group] for group in functional_groups]

    return node_colors, color_map
