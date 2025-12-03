"""
EcoNeTool - Food Web Network Analysis Tool
Python Shiny Application

Converted from R Shiny to Python Shiny with PyVis network visualization.
Fixed: Node tooltips now properly formatted, edges have uniform width in topology view.
Optimized: Reduced stabilization iterations to 1000 for faster network loading.
"""

from shiny import App, ui, render, reactive
from shiny.types import ImgData
import pandas as pd
import numpy as np
import networkx as nx
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import pickle
import json
from typing import Dict, List, Tuple, Optional
import shinyswatch

# Import custom modules
from network_analysis import (
    calculate_trophic_levels,
    get_topological_indicators,
    get_node_weighted_indicators,
    calculate_losses,
    calculate_flux_indicators,
    calculate_mti,
    calculate_keystoneness,
    COLOR_SCHEME,
    FLUX_CONVERSION_FACTOR
)

from network_viz import (
    create_topology_network,
    create_flux_network,
    get_functional_group_colors,
    save_network_html
)

# ============================================================================
# DATA LOADING
# ============================================================================

def load_default_data():
    """Load the default Baltic Food Web data."""
    # For now, we'll create a placeholder structure
    # In production, you would load from a pickle file or similar
    # that contains the NetworkX graph and species info DataFrame

    # This is a placeholder - you'll need to convert BalticFW.Rdata to a Python format
    # You can use rpy2 or manually export to CSV/Excel from R

    data_file = Path("BalticFW.pkl")

    if data_file.exists():
        with open(data_file, 'rb') as f:
            data = pickle.load(f)
        return data['network'], data['info']
    else:
        # Create a simple example network if data file doesn't exist
        return create_example_network()


def create_example_network():
    """Create a simple example food web network for demonstration."""
    # Create a simple 10-node example network
    G = nx.DiGraph()

    # Add nodes
    nodes = [f"Species_{i}" for i in range(1, 11)]
    G.add_nodes_from(nodes)

    # Add some edges (prey -> predator direction)
    edges = [
        (nodes[0], nodes[3]), (nodes[1], nodes[3]), (nodes[2], nodes[4]),
        (nodes[3], nodes[5]), (nodes[4], nodes[5]), (nodes[3], nodes[6]),
        (nodes[4], nodes[7]), (nodes[5], nodes[8]), (nodes[6], nodes[8]),
        (nodes[7], nodes[9]), (nodes[8], nodes[9])
    ]
    G.add_edges_from(edges)

    # Create species info DataFrame
    info = pd.DataFrame({
        'species': nodes,
        'fg': ['Phytoplankton', 'Phytoplankton', 'Detritus', 'Zooplankton', 'Zooplankton',
               'Fish', 'Fish', 'Benthos', 'Fish', 'Fish'],
        'meanB': np.random.uniform(10, 100, 10),
        'bodymasses': np.random.uniform(0.001, 10, 10),
        'met.types': ['Other', 'Other', 'Other', 'invertebrates', 'invertebrates',
                      'ectotherm vertebrates', 'ectotherm vertebrates', 'invertebrates',
                      'ectotherm vertebrates', 'ectotherm vertebrates'],
        'efficiencies': np.random.uniform(0.1, 0.85, 10)
    })

    return G, info


# Load data at startup
try:
    network, species_info = load_default_data()
except Exception as e:
    print(f"Warning: Could not load default data: {e}")
    print("Using example network instead.")
    network, species_info = create_example_network()

# Get functional group colors
node_colors, color_map = get_functional_group_colors(species_info['fg'].tolist())

# ============================================================================
# CONTENT DEFINITIONS (must be defined before app_ui)
# ============================================================================

dashboard_ui = lambda: ui.layout_sidebar(
        ui.sidebar(
            ui.h4("EcoNeTool"),
            ui.p("Interactive Food Web Analysis"),
            ui.hr(),
            ui.h5("Dataset Info"),
            ui.output_text_verbatim("dataset_summary"),
            ui.hr(),
            ui.h5("Functional Groups"),
            ui.output_ui("functional_groups_legend"),
            width=300
        ),
        ui.card(
            ui.card_header("Welcome to EcoNeTool"),
            ui.markdown(
                """
                ### Food Web Explorer

                This interactive dashboard allows you to explore and analyze marine food web networks.
                The tool integrates qualitative and quantitative network analysis approaches to understand
                food web structure and dynamics.

                #### Features:
                - **Food Web Network**: Interactive visualization of species interactions
                - **Topological Metrics**: Qualitative indicators (Connectance, Generality, Vulnerability, etc.)
                - **Biomass Analysis**: Node-weighted metrics accounting for species biomass
                - **Energy Fluxes**: Metabolic theory-based energy flow calculations
                - **Keystoneness Analysis**: Identify keystone species using Mixed Trophic Impact

                #### Navigation:
                Use the menu on the left to navigate through different analysis sections.
                """
            )
        ),
        ui.layout_column_wrap(
            ui.value_box(
                "Species",
                ui.output_text("n_species"),
                theme="primary"
            ),
            ui.value_box(
                "Links",
                ui.output_text("n_links"),
                theme="success"
            ),
            ui.value_box(
                "Functional Groups",
                ui.output_text("n_groups"),
                theme="info"
            ),
            width=1/3
        )
    )

network_ui = lambda: ui.layout_sidebar(
        ui.sidebar(
            ui.h4("Network Options"),
            ui.input_select(
                "network_type",
                "Network Type",
                choices=["Topology", "Flux-Weighted"],
                selected="Topology"
            ),
            ui.hr(),
            ui.input_slider(
                "network_height",
                "Network Height (px)",
                min=400,
                max=1000,
                value=600,
                step=50
            ),
            ui.hr(),
            ui.download_button("download_network", "Download Network HTML"),
            width=250
        ),
        ui.card(
            ui.card_header(
                ui.div(
                    ui.output_text("network_title_dynamic"),
                    style="font-weight: bold; font-size: 1.1em;"
                )
            ),
            ui.output_ui("network_plot"),
            full_screen=True
        ),
        ui.card(
            ui.card_header("Adjacency Matrix"),
            ui.output_plot("adjacency_heatmap", height="500px"),
            full_screen=True
        )
    )

topology_ui = lambda: ui.div(
    ui.layout_columns(
        ui.card(
            ui.card_header("Qualitative Network Indicators"),
            ui.output_text_verbatim("topological_indicators")
        ),
        ui.card(
            ui.card_header("Trophic Level Distribution"),
            ui.output_plot("trophic_level_histogram")
        ),
        col_widths=[6, 6]
    ),
    ui.card(
        ui.card_header("Species Trophic Levels"),
        ui.output_data_frame("trophic_levels_table")
    )
)

biomass_ui = lambda: ui.div(
    ui.layout_columns(
        ui.card(
            ui.card_header("Node-Weighted Indicators"),
            ui.output_text_verbatim("node_weighted_indicators")
        ),
        ui.card(
            ui.card_header("Biomass by Functional Group"),
            ui.output_plot("biomass_by_group")
        ),
        col_widths=[6, 6]
    ),
    ui.card(
        ui.card_header("Species Biomass Distribution"),
        ui.output_plot("biomass_distribution", height="400px")
    )
)

fluxes_ui = lambda: ui.layout_sidebar(
        ui.sidebar(
            ui.h4("Flux Calculation"),
            ui.input_numeric(
                "temperature",
                "Temperature (°C)",
                value=3.5,
                min=-5,
                max=30,
                step=0.5
            ),
            ui.input_action_button(
                "calculate_fluxes",
                "Calculate Fluxes",
                class_="btn-primary"
            ),
            ui.hr(),
            ui.output_text_verbatim("flux_indicators"),
            width=300
        ),
        ui.card(
            ui.card_header("Flux Matrix Heatmap"),
            ui.output_plot("flux_heatmap", height="600px"),
            full_screen=True
        ),
        ui.card(
            ui.card_header("Flux-Weighted Network"),
            ui.output_ui("flux_network_plot"),
            full_screen=True
        )
    )

keystoneness_ui = lambda: ui.div(
    ui.layout_columns(
        ui.card(
            ui.card_header("Keystoneness Summary"),
            ui.output_text_verbatim("keystoneness_summary")
        ),
        ui.card(
            ui.card_header("Keystoneness vs Biomass"),
            ui.output_plot("keystoneness_scatter")
        ),
        col_widths=[6, 6]
    ),
    ui.card(
        ui.card_header("Species Keystoneness Rankings"),
        ui.output_data_frame("keystoneness_table")
    ),
    ui.card(
        ui.card_header("Mixed Trophic Impact (MTI) Matrix"),
        ui.output_plot("mti_heatmap", height="600px"),
        full_screen=True
    )
)

editor_ui = lambda: ui.layout_columns(
        ui.card(
            ui.card_header("Species Information"),
            ui.output_data_frame("species_info_editor"),
            ui.input_action_button("update_species_info", "Update Species Info", class_="btn-success")
        ),
        col_widths=[12]
    )


# ============================================================================
# UI DEFINITION - CLEAN LEFT MENU + RIGHT CONTENT LAYOUT
# ============================================================================

app_ui = ui.page_fluid(
    ui.tags.style("""
        body { margin: 0; padding: 0; }
        .container-fluid { padding: 0 !important; }
        .app-container { display: flex; flex-direction: column; height: 100vh; }
        .top-bar {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            z-index: 1000;
        }
        .top-bar-left {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .top-bar-title {
            font-size: 1.5em;
            font-weight: bold;
            margin: 0;
        }
        .top-bar-subtitle {
            font-size: 0.9em;
            opacity: 0.9;
        }
        .top-bar-right {
            display: flex;
            align-items: center;
            gap: 20px;
            font-size: 0.9em;
        }
        .main-layout { display: flex; flex: 1; overflow: hidden; }
        .footer-bar {
            background: #2c3e50;
            color: white;
            padding: 12px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.85em;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
        }
        .footer-left {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .footer-right {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .left-menu {
            width: 250px;
            background: #2c3e50;
            color: white;
            padding: 0;
            overflow-y: auto;
            transition: all 0.3s ease;
            position: relative;
        }
        .left-menu.collapsed {
            width: 60px;
        }
        .menu-header {
            padding: 20px;
            background: #34495e;
            text-align: center;
            font-size: 1.3em;
            font-weight: bold;
            border-bottom: 2px solid #1a252f;
            white-space: nowrap;
            overflow: hidden;
        }
        .left-menu.collapsed .menu-header {
            padding: 20px 5px;
            font-size: 0.9em;
            writing-mode: vertical-rl;
            text-orientation: mixed;
        }
        .menu-item {
            padding: 15px 20px;
            cursor: pointer;
            border-bottom: 1px solid #34495e;
            transition: all 0.3s;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .menu-item:hover {
            background: #34495e;
            padding-left: 25px;
        }
        .menu-item.active {
            background: #3498db;
            border-left: 4px solid #2980b9;
        }
        .left-menu.collapsed .menu-item {
            padding: 15px 5px;
            font-size: 0;
            text-align: center;
        }
        .left-menu.collapsed .menu-item:hover {
            padding-left: 5px;
        }
        .left-menu.collapsed .menu-item::first-letter {
            font-size: 16px;
        }
        .toggle-btn {
            position: absolute;
            top: 10px;
            right: -15px;
            width: 30px;
            height: 30px;
            background: #3498db;
            border: none;
            border-radius: 50%;
            color: white;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            z-index: 1000;
            box-shadow: 0 2px 5px rgba(0,0,0,0.3);
            transition: all 0.3s;
        }
        .toggle-btn:hover {
            background: #2980b9;
            transform: scale(1.1);
        }
        .right-content {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #ecf0f1;
            transition: all 0.3s ease;
        }
    """),
    ui.tags.script("""
        function toggleSidebar() {
            const sidebar = document.querySelector('.left-menu');
            sidebar.classList.toggle('collapsed');
            const btn = document.getElementById('toggle-sidebar-btn');
            if (sidebar.classList.contains('collapsed')) {
                btn.innerHTML = '☰';
            } else {
                btn.innerHTML = '☰';
            }
        }

        // Update active menu item highlighting
        document.addEventListener('DOMContentLoaded', function() {
            const menuLinks = document.querySelectorAll('[id^="menu_"]');
            menuLinks.forEach(link => {
                link.addEventListener('click', function(e) {
                    // Remove active class from all menu items
                    document.querySelectorAll('.menu-item').forEach(item => {
                        item.classList.remove('active');
                    });
                    // Add active class to clicked item
                    const menuItem = this.querySelector('.menu-item');
                    if (menuItem) {
                        menuItem.classList.add('active');
                    }
                });
            });
        });
    """),
    ui.div(
        {"class": "app-container"},
        # Top Bar
        ui.div(
            {"class": "top-bar"},
            ui.div(
                {"class": "top-bar-left"},
                ui.div({"class": "top-bar-title"}, "EcoNeTool"),
                ui.div({"class": "top-bar-subtitle"}, "Marine Food Web Network Analysis")
            ),
            ui.div(
                {"class": "top-bar-right"},
                ui.output_ui("top_bar_info")
            )
        ),
        # Main Layout
        ui.div(
            {"class": "main-layout"},
            # Left Menu
            ui.div(
                {"class": "left-menu", "id": "sidebar"},
                ui.tags.button(
                    {"class": "toggle-btn", "id": "toggle-sidebar-btn", "onclick": "toggleSidebar()"},
                    "☰"
                ),
                ui.div({"class": "menu-header"}, "Navigation"),
                ui.input_action_link("menu_dashboard", ui.div({"class": "menu-item active", "id": "menu_dashboard_div", "title": "Dashboard - Overview and summary statistics"}, "Dashboard")),
                ui.input_action_link("menu_network", ui.div({"class": "menu-item", "id": "menu_network_div", "title": "Food Web Network - Interactive network visualization"}, "Food Web Network")),
                ui.input_action_link("menu_topology", ui.div({"class": "menu-item", "id": "menu_topology_div", "title": "Topological Metrics - Network structure analysis"}, "Topological Metrics")),
                ui.input_action_link("menu_biomass", ui.div({"class": "menu-item", "id": "menu_biomass_div", "title": "Biomass Analysis - Species biomass distribution"}, "Biomass Analysis")),
                ui.input_action_link("menu_fluxes", ui.div({"class": "menu-item", "id": "menu_fluxes_div", "title": "Energy Fluxes - Energy flow calculations"}, "Energy Fluxes")),
                ui.input_action_link("menu_keystoneness", ui.div({"class": "menu-item", "id": "menu_keystoneness_div", "title": "Keystoneness Analysis - Identify keystone species"}, "Keystoneness Analysis")),
                ui.input_action_link("menu_editor", ui.div({"class": "menu-item", "id": "menu_editor_div", "title": "Data Editor - Edit species and interaction data"}, "Data Editor"))
            ),
            # Right Content
            ui.div(
                {"class": "right-content"},
                ui.output_ui("main_content")
            )
        ),
        # Footer Bar
        ui.div(
            {"class": "footer-bar"},
            ui.div(
                {"class": "footer-left"},
                ui.HTML("&copy; 2025 EcoNeTool | Horizon Europe Project"),
                ui.output_ui("footer_info")
            ),
            ui.div(
                {"class": "footer-right"},
                ui.HTML("Version 1.0.0 | Python Shiny")
            )
        )
    ),
    title="EcoNeTool - Food Web Network Analysis",
    theme=shinyswatch.theme.flatly()
)


# ============================================================================
# SERVER LOGIC
# ============================================================================

def server(input, output, session):

    # Reactive values
    current_network = reactive.Value(network)
    current_species_info = reactive.Value(species_info)
    flux_results = reactive.Value(None)
    current_page = reactive.Value("dashboard")

    # ========================================================================
    # TOP BAR AND FOOTER RENDERERS
    # ========================================================================

    @output
    @render.ui
    def top_bar_info():
        """Render dynamic information in the top bar"""
        n_species = current_network().number_of_nodes()
        n_links = current_network().number_of_edges()
        return ui.div(
            ui.HTML(f"<strong>Species:</strong> {n_species} | <strong>Links:</strong> {n_links}")
        )

    @output
    @render.ui
    def footer_info():
        """Render dynamic information in the footer"""
        from datetime import datetime
        current_time = datetime.now().strftime("%H:%M:%S")
        return ui.HTML(f"Last updated: {current_time}")

    # ========================================================================
    # MENU CLICK HANDLERS - Simple page switching
    # ========================================================================

    @reactive.effect
    @reactive.event(input.menu_dashboard)
    def _():
        current_page.set("dashboard")

    @reactive.effect
    @reactive.event(input.menu_network)
    def _():
        current_page.set("network")

    @reactive.effect
    @reactive.event(input.menu_topology)
    def _():
        current_page.set("topology")

    @reactive.effect
    @reactive.event(input.menu_biomass)
    def _():
        current_page.set("biomass")

    @reactive.effect
    @reactive.event(input.menu_fluxes)
    def _():
        current_page.set("fluxes")

    @reactive.effect
    @reactive.event(input.menu_keystoneness)
    def _():
        current_page.set("keystoneness")

    @reactive.effect
    @reactive.event(input.menu_editor)
    def _():
        current_page.set("editor")

    # ========================================================================
    # MAIN CONTENT RENDERER
    # ========================================================================

    @output
    @render.ui
    def main_content():
        page = current_page()

        if page == "dashboard":
            return dashboard_ui()
        elif page == "network":
            return network_ui()
        elif page == "topology":
            return topology_ui()
        elif page == "biomass":
            return biomass_ui()
        elif page == "fluxes":
            return fluxes_ui()
        elif page == "keystoneness":
            return keystoneness_ui()
        elif page == "editor":
            return editor_ui()
        else:
            return dashboard_ui()

    # ========================================================================
    # DASHBOARD TAB
    # ========================================================================

    @output
    @render.text
    def dataset_summary():
        G = current_network()
        info = current_species_info()
        return f"""
Network Statistics:
  Species: {len(G.nodes())}
  Links: {len(G.edges())}
  Functional Groups: {info['fg'].nunique()}
        """

    @output
    @render.ui
    def functional_groups_legend():
        info = current_species_info()
        unique_groups = sorted(info['fg'].unique())
        _, color_map = get_functional_group_colors(info['fg'].tolist())

        legend_items = []
        for group in unique_groups:
            color = color_map.get(group, "gray")
            legend_items.append(
                ui.div(
                    ui.span("●", style=f"color: {color}; font-size: 20px; margin-right: 10px;"),
                    ui.span(group),
                    style="margin-bottom: 5px;"
                )
            )

        return ui.div(*legend_items)

    @output
    @render.text
    def n_species():
        return str(len(current_network().nodes()))

    @output
    @render.text
    def n_links():
        return str(len(current_network().edges()))

    @output
    @render.text
    def n_groups():
        return str(current_species_info()['fg'].nunique())

    # ========================================================================
    # NETWORK TAB
    # ========================================================================

    @output
    @render.text
    def network_title_dynamic():
        net_type = input.network_type()
        if net_type == "Topology":
            return "Interactive Food Web Network (Topology View)"
        else:
            return "Interactive Food Web Network (Flux-Weighted View)"

    @output
    @render.ui
    def network_plot():
        G = current_network()
        info = current_species_info()
        height = input.network_height()

        node_colors, _ = get_functional_group_colors(info['fg'].tolist())

        if input.network_type() == "Topology":
            net = create_topology_network(
                G,
                species_names=info['species'].tolist(),
                functional_groups=info['fg'].tolist(),
                biomass=info['meanB'].values,
                colors=node_colors,
                height=f"{height}px"
            )
            filename = "topology_network.html"
        else:
            # Flux-weighted network
            if flux_results() is None:
                return ui.p("Please calculate fluxes first in the Energy Fluxes tab.")

            flux_matrix = flux_results()['flux_matrix']
            net = create_flux_network(
                G,
                species_names=info['species'].tolist(),
                functional_groups=info['fg'].tolist(),
                biomass=info['meanB'].values,
                colors=node_colors,
                flux_matrix=flux_matrix,
                height=f"{height}px"
            )
            filename = "flux_network.html"

        # Save to www directory for static serving
        www_path = Path("www") / filename
        save_network_html(net, str(www_path))

        # Use iframe to display the network (static_assets serves from root)
        return ui.tags.iframe(
            src=f"/{filename}",
            width="100%",
            height=f"{height}px",
            frameborder="0",
            style="border: none;"
        )

    @output
    @render.plot
    def adjacency_heatmap():
        G = current_network()
        info = current_species_info()

        adj_matrix = nx.to_numpy_array(G)
        labels = info['species'].tolist()

        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(
            adj_matrix,
            cmap="YlOrRd",
            xticklabels=labels,
            yticklabels=labels,
            cbar_kws={'label': 'Connection'},
            ax=ax,
            square=True
        )
        ax.set_title("Food Web Adjacency Matrix\n(Rows = Predators, Columns = Prey)")
        plt.xticks(rotation=90, ha='right')
        plt.yticks(rotation=0)
        plt.tight_layout()

        return fig

    # ========================================================================
    # TOPOLOGICAL METRICS TAB
    # ========================================================================

    @output
    @render.text
    def topological_indicators():
        G = current_network()
        indicators = get_topological_indicators(G)

        return f"""
Topological Network Indicators:

  Species Richness (S): {indicators['S']}
  Connectance (C): {indicators['C']:.4f}
  Generality (G): {indicators['G']:.4f}
  Vulnerability (V): {indicators['V']:.4f}
  Mean Shortest Path: {indicators['ShortPath']:.4f}
  Mean Trophic Level (TL): {indicators['TL']:.4f}
  Omnivory Index: {indicators['Omni']:.4f}
        """

    @output
    @render.plot
    def trophic_level_histogram():
        G = current_network()
        tl = calculate_trophic_levels(G)

        fig, ax = plt.subplots(figsize=(8, 6))
        ax.hist(tl, bins=20, edgecolor='black', color='skyblue')
        ax.set_xlabel('Trophic Level')
        ax.set_ylabel('Number of Species')
        ax.set_title('Distribution of Trophic Levels')
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        return fig

    @output
    @render.data_frame
    def trophic_levels_table():
        G = current_network()
        info = current_species_info()
        tl = calculate_trophic_levels(G)

        df = pd.DataFrame({
            'Species': info['species'],
            'Functional Group': info['fg'],
            'Trophic Level': tl
        })
        df = df.sort_values('Trophic Level', ascending=False).reset_index(drop=True)

        return render.DataGrid(df, width="100%")

    # ========================================================================
    # BIOMASS ANALYSIS TAB
    # ========================================================================

    @output
    @render.text
    def node_weighted_indicators():
        G = current_network()
        info = current_species_info()

        indicators = get_node_weighted_indicators(G, info['meanB'].values)

        return f"""
Node-Weighted Network Indicators:

  Node-Weighted Connectance (nwC): {indicators['nwC']:.4f}
  Node-Weighted Generality (nwG): {indicators['nwG']:.4f}
  Node-Weighted Vulnerability (nwV): {indicators['nwV']:.4f}
  Node-Weighted Mean TL (nwTL): {indicators['nwTL']:.4f}
        """

    @output
    @render.plot
    def biomass_by_group():
        info = current_species_info()

        fig, ax = plt.subplots(figsize=(8, 6))

        # Group by functional group and sum biomass
        grouped = info.groupby('fg')['meanB'].sum().sort_values(ascending=False)

        colors_list = [color_map.get(group, 'gray') for group in grouped.index]

        ax.bar(range(len(grouped)), grouped.values, color=colors_list)
        ax.set_xticks(range(len(grouped)))
        ax.set_xticklabels(grouped.index, rotation=45, ha='right')
        ax.set_ylabel('Total Biomass (g/km²/day)')
        ax.set_title('Total Biomass by Functional Group')
        ax.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()

        return fig

    @output
    @render.plot
    def biomass_distribution():
        info = current_species_info()

        fig, ax = plt.subplots(figsize=(10, 6))

        # Sort by biomass
        sorted_info = info.sort_values('meanB', ascending=False)

        colors_list = [color_map.get(fg, 'gray') for fg in sorted_info['fg']]

        ax.barh(range(len(sorted_info)), sorted_info['meanB'].values, color=colors_list)
        ax.set_yticks(range(len(sorted_info)))
        ax.set_yticklabels(sorted_info['species'].values)
        ax.set_xlabel('Biomass (g/km²/day)')
        ax.set_title('Species Biomass Distribution')
        ax.grid(True, alpha=0.3, axis='x')
        plt.tight_layout()

        return fig

    # ========================================================================
    # ENERGY FLUXES TAB
    # ========================================================================

    @reactive.Effect
    @reactive.event(input.calculate_fluxes)
    def _():
        # Calculate fluxes when button is clicked
        G = current_network()
        info = current_species_info()
        temp = input.temperature()

        # Calculate metabolic losses
        losses = calculate_losses(
            info['bodymasses'].values,
            info['met.types'].tolist(),
            temp
        )

        # Create flux matrix (simplified - you would use fluxweb package equivalent)
        # For now, using a simple approximation based on network structure
        adj_matrix = nx.to_numpy_array(G)
        biomass = info['meanB'].values

        # Simple flux calculation (this would be replaced with proper fluxing algorithm)
        flux_matrix = adj_matrix * biomass[:, np.newaxis] * losses[:, np.newaxis] * FLUX_CONVERSION_FACTOR / 1000

        flux_results.set({
            'flux_matrix': flux_matrix,
            'losses': losses
        })

    @output
    @render.text
    def flux_indicators():
        if flux_results() is None:
            return "Click 'Calculate Fluxes' to compute energy fluxes."

        flux_matrix = flux_results()['flux_matrix']
        indicators = calculate_flux_indicators(flux_matrix, loop=False)

        return f"""
Flux-Based Indicators:

  Link-Weighted Connectance (lwC): {indicators['lwC']:.4f}
  Link-Weighted Generality (lwG): {indicators['lwG']:.4f}
  Link-Weighted Vulnerability (lwV): {indicators['lwV']:.4f}
        """

    @output
    @render.plot
    def flux_heatmap():
        if flux_results() is None:
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.text(0.5, 0.5, 'Click "Calculate Fluxes" to generate heatmap',
                   ha='center', va='center', fontsize=14)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            return fig

        flux_matrix = flux_results()['flux_matrix']
        info = current_species_info()
        labels = info['species'].tolist()

        # Log transform for better visualization
        flux_log = np.log10(flux_matrix + 1e-10)

        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(
            flux_log,
            cmap="viridis",
            xticklabels=labels,
            yticklabels=labels,
            cbar_kws={'label': 'log10(Flux) [kJ/day/km²]'},
            ax=ax,
            square=True
        )
        ax.set_title("Energy Flux Matrix (log-transformed)\n(Rows = Predators, Columns = Prey)")
        plt.xticks(rotation=90, ha='right')
        plt.yticks(rotation=0)
        plt.tight_layout()

        return fig

    @output
    @render.ui
    def flux_network_plot():
        if flux_results() is None:
            return ui.p("Click 'Calculate Fluxes' in the sidebar to generate the flux-weighted network.")

        G = current_network()
        info = current_species_info()
        flux_matrix = flux_results()['flux_matrix']

        node_colors, _ = get_functional_group_colors(info['fg'].tolist())

        net = create_flux_network(
            G,
            species_names=info['species'].tolist(),
            functional_groups=info['fg'].tolist(),
            biomass=info['meanB'].values,
            colors=node_colors,
            flux_matrix=flux_matrix,
            height="600px"
        )

        # Save to www directory for static serving
        www_path = Path("www") / "flux_network_energy_tab.html"
        save_network_html(net, str(www_path))

        # Use iframe to display the network (static_assets serves from root)
        return ui.tags.iframe(
            src="/flux_network_energy_tab.html",
            width="100%",
            height="600px",
            frameborder="0",
            style="border: none;"
        )

    # ========================================================================
    # KEYSTONENESS ANALYSIS TAB
    # ========================================================================

    @output
    @render.text
    def keystoneness_summary():
        G = current_network()
        info = current_species_info()

        keystoneness_df = calculate_keystoneness(G, info['meanB'].values)

        n_keystone = (keystoneness_df['keystone_status'] == 'Keystone').sum()
        n_dominant = (keystoneness_df['keystone_status'] == 'Dominant').sum()
        n_rare = (keystoneness_df['keystone_status'] == 'Rare').sum()

        top_species = keystoneness_df.iloc[0]['species']
        top_ks = keystoneness_df.iloc[0]['keystoneness']

        return f"""
Keystoneness Analysis Summary:

  Keystone Species: {n_keystone}
  Dominant Species: {n_dominant}
  Rare Species: {n_rare}

  Top Keystone Species: {top_species}
  Keystoneness Index: {top_ks:.4f}
        """

    @output
    @render.plot
    def keystoneness_scatter():
        G = current_network()
        info = current_species_info()

        keystoneness_df = calculate_keystoneness(G, info['meanB'].values)

        fig, ax = plt.subplots(figsize=(10, 8))

        # Color by status
        status_colors = {
            'Keystone': 'red',
            'Dominant': 'blue',
            'Rare': 'gray'
        }

        for status in ['Rare', 'Dominant', 'Keystone']:
            mask = keystoneness_df['keystone_status'] == status
            ax.scatter(
                keystoneness_df.loc[mask, 'relative_biomass'],
                keystoneness_df.loc[mask, 'keystoneness'],
                c=status_colors[status],
                label=status,
                s=100,
                alpha=0.6
            )

        # Add species labels for keystone species
        keystone_mask = keystoneness_df['keystone_status'] == 'Keystone'
        for _, row in keystoneness_df[keystone_mask].iterrows():
            ax.annotate(
                row['species'],
                (row['relative_biomass'], row['keystoneness']),
                xytext=(5, 5),
                textcoords='offset points',
                fontsize=8
            )

        ax.set_xlabel('Relative Biomass')
        ax.set_ylabel('Keystoneness Index')
        ax.set_title('Keystoneness vs Relative Biomass')
        ax.axhline(y=1, color='k', linestyle='--', alpha=0.3)
        ax.axvline(x=0.05, color='k', linestyle='--', alpha=0.3)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        return fig

    @output
    @render.data_frame
    def keystoneness_table():
        G = current_network()
        info = current_species_info()

        keystoneness_df = calculate_keystoneness(G, info['meanB'].values)

        # Format for display
        display_df = keystoneness_df.copy()
        display_df['overall_effect'] = display_df['overall_effect'].round(4)
        display_df['relative_biomass'] = display_df['relative_biomass'].round(6)
        display_df['keystoneness'] = display_df['keystoneness'].round(4)

        return render.DataGrid(display_df, width="100%")

    @output
    @render.plot
    def mti_heatmap():
        G = current_network()
        info = current_species_info()

        mti_matrix = calculate_mti(G)
        labels = info['species'].tolist()

        fig, ax = plt.subplots(figsize=(12, 10))

        # Use diverging colormap centered at 0
        vmax = np.abs(mti_matrix).max()
        sns.heatmap(
            mti_matrix,
            cmap="RdBu_r",
            center=0,
            vmin=-vmax,
            vmax=vmax,
            xticklabels=labels,
            yticklabels=labels,
            cbar_kws={'label': 'MTI (Impact)'},
            ax=ax,
            square=True
        )
        ax.set_title("Mixed Trophic Impact (MTI) Matrix\n(Rows = Impacted, Columns = Impactor)")
        ax.set_xlabel("Impacting Species")
        ax.set_ylabel("Impacted Species")
        plt.xticks(rotation=90, ha='right')
        plt.yticks(rotation=0)
        plt.tight_layout()

        return fig

    # ========================================================================
    # DATA EDITOR TAB
    # ========================================================================

    @output
    @render.data_frame
    def species_info_editor():
        info = current_species_info()
        return render.DataGrid(info, editable=True, width="100%")


# ============================================================================
# CREATE APP WITH STATIC FILE SERVING
# ============================================================================

# Create www directory if it doesn't exist (absolute path required)
www_dir = Path(__file__).parent / "www"
www_dir.mkdir(exist_ok=True)

app = App(app_ui, server, static_assets=www_dir)
