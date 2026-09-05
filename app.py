"""
EcoNeTool - Food Web Network Analysis Tool
Python Shiny Application

Converted from R Shiny to Python Shiny with PyVis network visualization.
Fixed: Node tooltips now properly formatted, edges have uniform width in topology view.
Optimized: Reduced stabilization iterations to 1000 for faster network loading.
"""

from shiny import App, ui, render, reactive, req
import pandas as pd
import numpy as np
import networkx as nx
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import pickle
import time
import functools
import os
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
    FLUX_CONVERSION_FACTOR
)

from flux_calculations import (
    fluxing,
    validate_flux_equilibrium,
    validate_met_types,
)

from network_viz import (
    create_topology_network,
    create_flux_network,
    get_functional_group_colors,
)
from pyvis.shiny import render_network

from feedback_reporter import collect_system_context, submit_feedback

import logging
logging.basicConfig(
    level=os.environ.get("ECONETPY_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("econetpy.app")

_ERROR_MSG = "This panel could not be computed — see logs."


def _error_element(kind):
    """Uniform error element per render kind: 'text' -> str, 'plot' -> Figure,
    'ui' -> ui.div."""
    if kind == "plot":
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, _ERROR_MSG, ha="center", va="center", wrap=True)
        ax.axis("off")
        return fig
    if kind == "ui":
        return ui.div(_ERROR_MSG, class_="econetpy-render-error")
    return _ERROR_MSG


def safe_render(kind):
    """Decorator: wrap a render function so a compute exception logs and returns
    a uniform error element instead of a raw traceback. Apply BELOW @render.*."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                logger.exception("Render %s failed", fn.__name__)
                return _error_element(kind)
        return wrapper
    return decorator


# ============================================================================
# DATA LOADING
# ============================================================================

DATA_DIR = Path(__file__).parent
USING_EXAMPLE_NETWORK = False


def _assert_aligned(G, info):
    """Raise ValueError if the network's node order and species_info's row
    order have diverged. Called on every load_default_data() return path and
    before current_species_info.set(df) in the editor apply handler."""
    nodes = list(G.nodes())
    species = info['species'].tolist()
    if nodes != species:
        divergence_idx = None
        for i in range(min(len(nodes), len(species))):
            if nodes[i] != species[i]:
                divergence_idx = i
                break
        if divergence_idx is not None:
            detail = (
                f"first divergence at index {divergence_idx}: "
                f"nodes[{divergence_idx}]={nodes[divergence_idx]!r} != "
                f"species[{divergence_idx}]={species[divergence_idx]!r}"
            )
        else:
            detail = (
                f"lengths differ: len(nodes)={len(nodes)}, "
                f"len(species)={len(species)} (common prefix matches)"
            )
        raise ValueError(
            "Network nodes and species_info rows are misaligned: "
            f"{detail}"
        )


def load_default_data():
    """Load the default Baltic Food Web data.

    Resolution order:
    1. BalticFW.pkl — fast prebuilt cache (gitignored; present on dev machines).
    2. Tracked text sources (BalticFW_network.graphml + _species_info.csv +
       _metadata.json) via load_data.load_baltic_data() — used on a fresh clone
       where the pickle is absent.
    3. A small synthetic example network, only if neither is available.

    All sources resolve against DATA_DIR (this file's own directory), never
    the process cwd, so `shiny run /path/to/app.py` from another directory
    still finds the Baltic data.
    """
    data_file = DATA_DIR / "BalticFW.pkl"

    if data_file.exists():
        # Trusted local cache: this .pkl is produced by load_data.save_to_pickle
        # from the project's own tracked GraphML/CSV/JSON, never fetched from
        # an external/untrusted source, so pickle.load here is safe.
        try:
            with open(data_file, 'rb') as f:
                data = pickle.load(f)
            if not (isinstance(data, dict) and {'network', 'info'} <= set(data.keys())):
                print("BalticFW.pkl missing 'network'/'info'; rebuilding from sources.")
            else:
                G_pkl, info_pkl = data['network'], data['info']
                required = ['species', 'fg', 'meanB', 'bodymasses', 'met.types', 'efficiencies']
                if (all(c in info_pkl.columns for c in required)
                        and info_pkl['species'].tolist() == list(G_pkl.nodes())):
                    _assert_aligned(G_pkl, info_pkl)
                    return G_pkl, info_pkl
                print("BalticFW.pkl stale/misaligned; rebuilding from sources.")
        except (EOFError, pickle.UnpicklingError, AttributeError, ModuleNotFoundError) as exc:
            print(f"BalticFW.pkl is unreadable ({exc}); rebuilding from sources.")
        # fall through to reconstruction

    # No pickle cache (or a stale one) — reconstruct from the tracked
    # GraphML/CSV/JSON sources.
    try:
        from load_data import load_baltic_data
        G, info = load_baltic_data(base_dir=DATA_DIR)
        _assert_aligned(G, info)
        # Repair a stale/absent/corrupt cache once, so the next start takes
        # the fast pickle path instead of rebuilding on every run.
        # NOTE the handler is (OSError, ImportError), not just OSError: this
        # `from load_data import save_to_pickle` sits INSIDE the outer
        # `try: ... except (FileNotFoundError, ImportError)`. A narrower
        # handler would let an ImportError from this line escape to the outer
        # clause and silently drop the app onto the example network even
        # though the Baltic data loaded fine. Catching it here keeps the
        # failure local to the cache.
        try:
            from load_data import save_to_pickle
            save_to_pickle(G, info, output_file=str(DATA_DIR / "BalticFW.pkl"))
        except (OSError, ImportError) as exc:
            print(f"Could not re-save BalticFW.pkl ({exc}); continuing without cache.")
        return G, info
    except (FileNotFoundError, ImportError) as exc:
        global USING_EXAMPLE_NETWORK
        print(f"Baltic sources unavailable ({exc}); using example network.")
        USING_EXAMPLE_NETWORK = True
        G, info = create_example_network()
        _assert_aligned(G, info)
        return G, info


def create_example_network():
    """Create a simple example food web network for demonstration."""
    rng = np.random.default_rng(0)
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
        'meanB': rng.uniform(10, 100, 10),
        'bodymasses': rng.uniform(0.001, 10, 10),
        'met.types': ['Other', 'Other', 'Other', 'invertebrates', 'invertebrates',
                      'ectotherm vertebrates', 'ectotherm vertebrates', 'invertebrates',
                      'ectotherm vertebrates', 'ectotherm vertebrates'],
        'efficiencies': rng.uniform(0.1, 0.85, 10)
    })

    return G, info


# Load data at startup. Narrowed to the two cases load_default_data() itself
# does not already resolve into the example network internally (this except
# is a defensive backstop in case load_default_data ever propagates one of
# these two): a data ValueError (misalignment, unknown met.types, ...) is a
# bug to fix, not a fallback, and must abort import.
try:
    network, species_info = load_default_data()
except (FileNotFoundError, ImportError) as e:
    print(f"Warning: Could not load default data: {e}")
    print("Using example network instead.")
    network, species_info = create_example_network()
    USING_EXAMPLE_NETWORK = True

# ============================================================================
# CONTENT DEFINITIONS (must be defined before app_ui)
# ============================================================================

def dashboard_ui():
    banner = (
        ui.div(
            "Showing a synthetic example network — the Baltic data sources "
            "were unavailable at startup. See server logs for details.",
            class_="econetpy-example-network-banner",
            style=(
                "background:#fff3cd; color:#664d03; border:1px solid #ffecb5; "
                "border-radius:6px; padding:10px 16px; margin-bottom:12px; "
                "font-weight:600;"
            ),
        )
        if USING_EXAMPLE_NETWORK else None
    )
    layout = ui.layout_sidebar(
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
    return ui.div(banner, layout) if banner is not None else layout

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


# Ordered registry of the 7 navigable pages: page_key -> (menu_input_id, ui_builder).
# menu_feedback is deliberately excluded - it opens a modal, not a page.
PAGES = {
    "dashboard": ("menu_dashboard", dashboard_ui),
    "network": ("menu_network", network_ui),
    "topology": ("menu_topology", topology_ui),
    "biomass": ("menu_biomass", biomass_ui),
    "fluxes": ("menu_fluxes", fluxes_ui),
    "keystoneness": ("menu_keystoneness", keystoneness_ui),
    "editor": ("menu_editor", editor_ui),
}


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
        .menu-item {
            padding: 15px 20px;
            cursor: pointer;
            border-bottom: 1px solid #34495e;
            transition: all 0.3s;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .menu-item:first-of-type {
            margin-top: 15px;
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
            top: 15px;
            right: -18px;
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: 2px solid white;
            border-radius: 50%;
            color: white;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            font-weight: bold;
            z-index: 1000;
            box-shadow: 0 3px 8px rgba(0,0,0,0.3);
            transition: all 0.3s ease;
        }
        .toggle-btn:hover {
            background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
            transform: scale(1.15);
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
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
                ui.input_select(
                    "tl_method",
                    "Trophic level",
                    {"prey_averaged": "Prey-averaged", "short_weighted": "Short-weighted (W&M 2004)"},
                    selected="prey_averaged",
                    width="200px",
                ),
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
                ui.input_action_link("menu_dashboard", ui.div({"class": "menu-item active", "id": "menu_dashboard_div", "title": "Dashboard - Overview and summary statistics"}, "Dashboard")),
                ui.input_action_link("menu_network", ui.div({"class": "menu-item", "id": "menu_network_div", "title": "Food Web Network - Interactive network visualization"}, "Food Web Network")),
                ui.input_action_link("menu_topology", ui.div({"class": "menu-item", "id": "menu_topology_div", "title": "Topological Metrics - Network structure analysis"}, "Topological Metrics")),
                ui.input_action_link("menu_biomass", ui.div({"class": "menu-item", "id": "menu_biomass_div", "title": "Biomass Analysis - Species biomass distribution"}, "Biomass Analysis")),
                ui.input_action_link("menu_fluxes", ui.div({"class": "menu-item", "id": "menu_fluxes_div", "title": "Energy Fluxes - Energy flow calculations"}, "Energy Fluxes")),
                ui.input_action_link("menu_keystoneness", ui.div({"class": "menu-item", "id": "menu_keystoneness_div", "title": "Keystoneness Analysis - Identify keystone species"}, "Keystoneness Analysis")),
                ui.input_action_link("menu_editor", ui.div({"class": "menu-item", "id": "menu_editor_div", "title": "Data Editor - Edit species and interaction data"}, "Data Editor")),
                ui.input_action_link("menu_feedback", ui.div({"class": "menu-item", "id": "menu_feedback_div", "title": "Feedback - Report a bug or suggest an improvement"}, "Feedback")),
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
                ui.HTML(f"Version {(Path(__file__).parent / 'VERSION').read_text(encoding='utf-8').strip() if (Path(__file__).parent / 'VERSION').exists() else 'unknown'} | Python Shiny"),
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

    @reactive.calc
    def trophic_levels_cached():
        return calculate_trophic_levels(current_network(), method=input.tl_method())

    @reactive.calc
    def mti_cached():
        return calculate_mti(current_network())

    @reactive.calc
    def keystoneness_cached():
        return calculate_keystoneness(current_network(), current_species_info()["meanB"].values,
                                      mti=mti_cached())

    @reactive.calc
    def colors_cached():
        node_colors, color_map = get_functional_group_colors(current_species_info()['fg'].tolist())
        return node_colors, color_map

    def _build_network(kind, height="600px"):
        """Build the topology or flux pyvis Network from the shared caches.
        kind in {'topology','flux'}. Returns a pyvis Network; callers wrap it
        (render_network for the UI panels, net.generate_html() for download).
        The 'flux' kind reads flux_results()['flux_matrix'] — callers MUST guard
        that flux_results() is not None before requesting kind='flux'."""
        G = current_network()
        info = current_species_info()
        node_colors, _ = colors_cached()
        tl = trophic_levels_cached()
        if kind == "topology":
            return create_topology_network(
                G, species_names=info['species'].tolist(),
                functional_groups=info['fg'].tolist(),
                biomass=info['meanB'].values, colors=node_colors,
                height=height, trophic_levels=tl)
        return create_flux_network(
            G, species_names=info['species'].tolist(),
            functional_groups=info['fg'].tolist(),
            biomass=info['meanB'].values, colors=node_colors,
            flux_matrix=flux_results()['flux_matrix'],
            height=height, trophic_levels=tl)
    current_page = reactive.Value("dashboard")
    last_feedback_submit = reactive.Value(None)  # epoch seconds; rate-limit guard

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

    def _make_menu_effect(page_key, menu_input_id):
        @reactive.effect
        @reactive.event(getattr(input, menu_input_id))
        def _():
            current_page.set(page_key)
        return _

    for _page_key, (_menu_input_id, _builder) in PAGES.items():
        _make_menu_effect(_page_key, _menu_input_id)

    # ========================================================================
    # FEEDBACK MODAL (bug reports + suggestions)
    # ========================================================================

    @reactive.effect
    @reactive.event(input.menu_feedback)
    def _show_feedback_modal():
        ui.modal_show(
            ui.modal(
                ui.p("Help us improve EconetPy by reporting bugs or suggesting features."),
                ui.input_radio_buttons(
                    "fb_type",
                    "Report type",
                    choices={
                        "bug": "Bug Report",
                        "suggestion": "Improvement Suggestion",
                        "general": "General Feedback",
                    },
                    selected="bug",
                    inline=False,
                ),
                ui.input_text("fb_title", "Title", placeholder="Brief summary of your feedback", width="100%"),
                ui.input_text_area(
                    "fb_description",
                    "Description",
                    rows=5,
                    placeholder="Please describe in detail what happened or what you would like to see improved.",
                    width="100%",
                ),
                ui.input_text_area(
                    "fb_steps",
                    "Steps to Reproduce (bug reports only)",
                    rows=3,
                    placeholder="1. Open the Network tab\n2. Click ...\n3. Observed: ...",
                    width="100%",
                ),
                ui.tags.small(
                    {"class": "text-muted", "style": "display:block; margin-top:8px;"},
                    "System info (app version, current tab, browser User-Agent, species and edge counts) "
                    "will be attached automatically to help diagnose issues.",
                ),
                ui.tags.script(
                    "setTimeout(function(){if(typeof Shiny!=='undefined'){"
                    "Shiny.setInputValue('fb_browser_info', navigator.userAgent);"
                    "}}, 50);"
                ),
                title="Send Feedback",
                footer=ui.tags.div(
                    ui.modal_button("Cancel"),
                    ui.input_action_button("fb_submit", "Submit Feedback", class_="btn-primary"),
                ),
                easy_close=False,
                size="l",
            )
        )

    @reactive.effect
    @reactive.event(input.fb_submit)
    def _handle_feedback_submit():
        # Rate limit (30s server-side)
        now = time.time()
        last = last_feedback_submit.get()
        if last is not None and (now - last) < 30:
            ui.notification_show("Please wait before submitting again.", type="warning", duration=4)
            return

        title = (input.fb_title() or "").strip()
        description = (input.fb_description() or "").strip()
        if not title:
            ui.notification_show("Please enter a title.", type="warning", duration=4)
            return
        if not description:
            ui.notification_show("Please enter a description.", type="warning", duration=4)
            return

        fb_type = input.fb_type() or "general"
        steps = (input.fb_steps() or "").strip() if fb_type == "bug" else ""

        # Snapshot counts; tolerate missing/invalid state
        try:
            info = current_species_info()
            species_count = int(len(info)) if info is not None else 0
        except Exception:
            species_count = 0
        try:
            g = current_network()
            edge_count = int(g.number_of_edges()) if g is not None else 0
        except Exception:
            edge_count = 0

        try:
            browser_info = input.fb_browser_info()
        except Exception:
            browser_info = "unknown"

        context = collect_system_context(
            current_tab=current_page() or "unknown",
            browser_info=browser_info or "unknown",
            species_count=species_count,
            edge_count=edge_count,
        )

        try:
            result = submit_feedback(
                title=title,
                description=description,
                type_=fb_type,
                steps=steps,
                context=context,
            )
        except ValueError as exc:
            ui.notification_show(f"Validation error: {exc}", type="warning", duration=5)
            return
        except Exception:
            logger.exception("feedback submission failed")
            ui.notification_show("Submission failed, please try again.", type="error", duration=6)
            return

        last_feedback_submit.set(now)

        if result.github_success:
            ui.notification_show(
                f"Thank you! Submitted as GitHub issue: {result.github_url}",
                type="message",
                duration=8,
            )
        elif result.local_success:
            ui.notification_show("Thank you! Your feedback has been saved.", type="message", duration=5)
        else:
            ui.notification_show("Feedback could not be saved. Please try again.", type="error", duration=8)
            return

        ui.modal_remove()

    # ========================================================================
    # MAIN CONTENT RENDERER
    # ========================================================================

    @output
    @render.ui
    def main_content():
        _, builder = PAGES.get(current_page(), ("", dashboard_ui))
        return builder()

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
        _, color_map = colors_cached()

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
    @safe_render("ui")
    def network_plot():
        h = f"{input.network_height()}px"
        if input.network_type() == "Topology":
            net = _build_network("topology", height=h)
        else:
            if flux_results() is None:
                return ui.p("Please calculate fluxes first in the Energy Fluxes tab.")
            net = _build_network("flux", height=h)
        return render_network(net, height=h, width="100%")

    @render.download(filename="econetool_network.html")
    def download_network():
        if input.network_type() == "Flux-Weighted" and flux_results() is not None:
            net = _build_network("flux")
        else:
            net = _build_network("topology")
        yield net.generate_html()

    @output
    @render.plot
    @safe_render("plot")
    def adjacency_heatmap():
        G = current_network()
        info = current_species_info()

        adj_matrix = nx.to_numpy_array(G, nodelist=info['species'].tolist())
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
    @safe_render("text")
    def topological_indicators():
        G = current_network()
        indicators = get_topological_indicators(G, trophic_levels=trophic_levels_cached())

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
    @safe_render("plot")
    def trophic_level_histogram():
        tl = trophic_levels_cached()

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
        info = current_species_info()
        tl = trophic_levels_cached()

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
    @safe_render("text")
    def node_weighted_indicators():
        G = current_network()
        info = current_species_info()

        indicators = get_node_weighted_indicators(G, info['meanB'].values, trophic_levels=trophic_levels_cached())

        return f"""
Node-Weighted Network Indicators:

  Node-Weighted Connectance (nwC): {indicators['nwC']:.4f}
  Node-Weighted Generality (nwG): {indicators['nwG']:.4f}
  Node-Weighted Vulnerability (nwV): {indicators['nwV']:.4f}
  Node-Weighted Mean TL (nwTL): {indicators['nwTL']:.4f}
        """

    @output
    @render.plot
    @safe_render("plot")
    def biomass_by_group():
        info = current_species_info()
        _, color_map = colors_cached()

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
    @safe_render("plot")
    def biomass_distribution():
        info = current_species_info()
        _, color_map = colors_cached()

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

    @reactive.effect
    @reactive.event(input.calculate_fluxes)
    def _():
        # Calculate fluxes when button is clicked
        G = current_network()
        info = current_species_info()
        temp = input.temperature()
        req(temp is not None)
        bodymasses = info['bodymasses'].values
        req(np.all(np.isfinite(bodymasses)) and np.all(bodymasses > 0))

        # Calculate metabolic losses using allometric scaling
        losses = calculate_losses(
            bodymasses,
            info['met.types'].tolist(),
            temp
        )

        # Get adjacency matrix (rows=prey, cols=predators)
        adj_matrix = nx.to_numpy_array(G, nodelist=info['species'].tolist())
        biomass = info['meanB'].values
        efficiencies = info['efficiencies'].values

        # Calculate fluxes using the fluxweb algorithm (Gauzens et al. 2019).
        # fluxing() raises ValueError on an infeasible (negative-ingestion)
        # system; surface that as a clean notification instead of a traceback.
        bioms_losses_flag = True  # single source of truth for solver + validator
        try:
            flux_matrix = fluxing(
                mat=adj_matrix,
                biomasses=biomass,
                losses=losses,
                efficiencies=efficiencies,
                bioms_prefs=True,
                bioms_losses=bioms_losses_flag,
                ef_level="prey"
            )
        except ValueError as exc:
            logger.warning("Flux calculation failed: %s", exc)
            ui.notification_show(
                f"Flux calculation failed: {exc}",
                type="error",
                duration=8,
            )
            flux_results.set(None)
            return

        # Convert J/sec to kJ/day (multiply by 86.4)
        flux_matrix = flux_matrix * FLUX_CONVERSION_FACTOR

        # Validate equilibrium (optional, for debugging)
        validation = validate_flux_equilibrium(
            flux_matrix / FLUX_CONVERSION_FACTOR,  # Convert back to J/sec for validation
            losses,
            efficiencies,
            biomass,
            bioms_losses=bioms_losses_flag
        )

        flux_results.set({
            'flux_matrix': flux_matrix,
            'losses': losses,
            'validation': validation
        })

    @output
    @render.text
    @safe_render("text")
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
    @safe_render("plot")
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
    @safe_render("ui")
    def flux_network_plot():
        if flux_results() is None:
            return ui.p("Click 'Calculate Fluxes' in the sidebar to generate the flux-weighted network.")
        net = _build_network("flux", height="600px")
        return render_network(net, height="600px", width="100%")

    # ========================================================================
    # KEYSTONENESS ANALYSIS TAB
    # ========================================================================

    @output
    @render.text
    @safe_render("text")
    def keystoneness_summary():
        keystoneness_df = keystoneness_cached()

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
    @safe_render("plot")
    def keystoneness_scatter():
        keystoneness_df = keystoneness_cached()

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
        keystoneness_df = keystoneness_cached()

        # Format for display
        display_df = keystoneness_df.copy()
        display_df['overall_effect'] = display_df['overall_effect'].round(4)
        display_df['relative_biomass'] = display_df['relative_biomass'].round(6)
        display_df['keystoneness'] = display_df['keystoneness'].round(4)

        return render.DataGrid(display_df, width="100%")

    @output
    @render.plot
    @safe_render("plot")
    def mti_heatmap():
        info = current_species_info()

        mti_matrix = mti_cached()
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

    # editable_columns= does not exist on render.DataGrid in this Shiny version
    # (1.7.0), so protect the key columns (species/fg) from edits with a patch
    # function instead: any edit targeting those columns is rejected by handing
    # back the original cell value unchanged.
    @species_info_editor.set_patch_fn
    async def _reject_key_edits(*, patch):
        info = current_species_info()
        columns = list(info.columns)
        col_name = columns[patch["column_index"]] if patch["column_index"] < len(columns) else None
        if col_name in ("species", "fg"):
            return info.iloc[patch["row_index"]][col_name]
        return patch["value"]

    @reactive.effect
    @reactive.event(input.update_species_info)
    def _apply_species_info_edits():
        edited = species_info_editor.data_patched()  # original node order + edits
        if edited is None or edited.empty:
            ui.notification_show("No edited data to apply.", type="warning", duration=4)
            return
        df = edited.copy()
        # DataGrid returns edited cells as strings; coerce numeric columns back.
        for col in ("meanB", "bodymasses", "efficiencies"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        # Reject malformed edits rather than letting NaN crash downstream renders.
        numeric_cols = [c for c in ("meanB", "bodymasses", "efficiencies") if c in df.columns]
        if numeric_cols and df[numeric_cols].isna().any().any():
            ui.notification_show(
                "Some numeric cells are invalid (non-numeric or blank). Fix them and retry.",
                type="error", duration=6,
            )
            return
        if len(df) != current_network().number_of_nodes():
            ui.notification_show(
                "Edited table row count does not match the network; not applied.",
                type="error", duration=6,
            )
            return
        if 'met.types' in df.columns:
            try:
                validate_met_types(df['met.types'].tolist(), context="edited species info")
            except ValueError as exc:
                ui.notification_show(f"Cannot apply edits: {exc}", type="error", duration=6)
                return
        try:
            _assert_aligned(current_network(), df)
        except ValueError as exc:
            ui.notification_show(f"Cannot apply edits: {exc}", type="error", duration=6)
            return
        current_species_info.set(df)
        ui.notification_show("Species info updated.", type="message", duration=4)


# ============================================================================
# CREATE APP WITH STATIC FILE SERVING
# ============================================================================

# Create www directory if it doesn't exist (absolute path required)
www_dir = Path(__file__).parent / "www"
www_dir.mkdir(exist_ok=True)

app = App(app_ui, server, static_assets=www_dir)
