"""
Data Loading Script for EcoNeTool

This script loads the converted data files (GraphML and CSV) and creates
a pickle file for fast loading in the Shiny app.

Run this script after converting the R data using convert_data_r_to_python.R
"""

import networkx as nx
import pandas as pd
import pickle
import json
from pathlib import Path


def load_baltic_data(base_dir: Path | None = None):
    """
    Load Baltic Food Web data from converted files.

    Args:
        base_dir: Directory holding the tracked GraphML/CSV/JSON sources.
                  Defaults to this module's own directory (never the cwd).

    Returns:
        tuple: (network, species_info)
    """
    base_dir = Path(base_dir) if base_dir is not None else Path(__file__).parent
    # Check if converted files exist
    network_file = base_dir / "BalticFW_network.graphml"
    info_file = base_dir / "BalticFW_species_info.csv"
    metadata_file = base_dir / "BalticFW_metadata.json"

    if not network_file.exists():
        raise FileNotFoundError(
            "BalticFW_network.graphml not found. "
            "Please run convert_data_r_to_python.R first."
        )

    if not info_file.exists():
        raise FileNotFoundError(
            "BalticFW_species_info.csv not found. "
            "Please run convert_data_r_to_python.R first."
        )

    # Load network from GraphML
    print("Loading network from GraphML...")
    G = nx.read_graphml(network_file)

    # Convert to DiGraph if not already
    if not isinstance(G, nx.DiGraph):
        G = nx.DiGraph(G)

    # Load species info from CSV
    print("Loading species info from CSV...")
    info = pd.read_csv(info_file)

    # Key the node<->row join by species name. GraphML nodes carry a 'name'
    # attribute (n0->'Synchaeta', ...); relabel the graph to those names so the
    # node IDs ARE the species, not positional 'n0..nN' accidents.
    names = nx.get_node_attributes(G, 'name')
    if names and len(names) == G.number_of_nodes():
        if len(set(names.values())) != len(names):
            raise ValueError("Duplicate species names in GraphML 'name' attrs; "
                             "cannot key the join by name.")
        G = nx.relabel_nodes(G, names)

    # Reindex info to the graph's node order, then require an exact match.
    node_list = list(G.nodes())
    if set(node_list) == set(info['species']):
        info = info.set_index('species').loc[node_list].reset_index()
    if list(G.nodes()) != info['species'].tolist():
        raise ValueError(
            "Network nodes do not align with species rows by name "
            f"(nodes={node_list[:3]}..., species={info['species'].tolist()[:3]}...)."
        )

    # Load metadata if available
    if metadata_file.exists():
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        print(f"\nMetadata:")
        print(f"  Description: {metadata.get('description', 'N/A')}")
        print(f"  Source: {metadata.get('source', 'N/A')}")

    # Check for required columns BEFORE referencing any of them.
    required_cols = ['species', 'fg', 'meanB', 'bodymasses', 'met.types', 'efficiencies']
    missing_cols = [col for col in required_cols if col not in info.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    from flux_calculations import validate_met_types
    validate_met_types(info['met.types'].tolist(), context="load_baltic_data")

    # Verify data integrity
    print(f"\nData Summary:")
    print(f"  Network nodes: {len(G.nodes())}")
    print(f"  Network edges: {len(G.edges())}")
    print(f"  Species info rows: {len(info)}")
    if 'fg' in info.columns:
        print(f"  Functional groups: {info['fg'].nunique()}")

    return G, info


def save_to_pickle(network, species_info, output_file="BalticFW.pkl"):
    """
    Save network and species info to a pickle file for fast loading.

    Args:
        network: NetworkX DiGraph
        species_info: pandas DataFrame
        output_file: Output pickle file name
    """
    data = {
        'network': network,
        'info': species_info
    }

    with open(output_file, 'wb') as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"\nData saved to: {output_file}")
    print(f"File size: {Path(output_file).stat().st_size / 1024:.2f} KB")


def main():
    """Main conversion process."""
    print("=" * 60)
    print("EcoNeTool Data Loading Script")
    print("=" * 60)
    print()

    try:
        # Load data
        network, species_info = load_baltic_data()

        # Save to pickle
        save_to_pickle(network, species_info)

        print("\n" + "=" * 60)
        print("Data conversion successful!")
        print("=" * 60)
        print("\nYou can now run the Shiny app:")
        print("  shiny run app.py")

    except FileNotFoundError as e:
        print(f"\nError: {e}")
        print("\nPlease follow these steps:")
        print("1. Make sure BalticFW.Rdata is in this directory")
        print("2. Run: Rscript convert_data_r_to_python.R")
        print("3. Run this script again: python load_data.py")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
