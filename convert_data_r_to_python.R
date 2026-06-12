# Convert BalticFW.Rdata to Python-compatible format
# This script exports the R data to CSV and GraphML formats that can be loaded in Python

library(igraph)
library(jsonlite)

# Load the R data
load("BalticFW.Rdata")

# ============================================================================
# EXPORT NETWORK TO GRAPHML
# ============================================================================

# GraphML is a universal graph format that both igraph (R) and NetworkX (Python) can read
write_graph(net, "BalticFW_network.graphml", format = "graphml")

cat("Network exported to: BalticFW_network.graphml\n")

# ============================================================================
# EXPORT SPECIES INFO TO CSV
# ============================================================================

# Export species info dataframe to CSV
write.csv(info, "BalticFW_species_info.csv", row.names = FALSE)

cat("Species info exported to: BalticFW_species_info.csv\n")

# ============================================================================
# EXPORT ADJACENCY MATRIX TO CSV
# ============================================================================

# Export adjacency matrix
adj_matrix <- as_adjacency_matrix(net, sparse = FALSE)
colnames(adj_matrix) <- V(net)$name
rownames(adj_matrix) <- V(net)$name

write.csv(adj_matrix, "BalticFW_adjacency.csv")

cat("Adjacency matrix exported to: BalticFW_adjacency.csv\n")

# ============================================================================
# EXPORT METADATA TO JSON
# ============================================================================

# Export metadata
metadata <- list(
  n_species = vcount(net),
  n_links = ecount(net),
  is_directed = is_directed(net),
  description = "Gulf of Riga Food Web (1979-2016)",
  source = "Frelat & Kortsch, 2020",
  functional_groups = levels(info$fg),
  color_scheme = c("orange", "darkgrey", "blue", "green", "cyan")
)

write_json(metadata, "BalticFW_metadata.json", pretty = TRUE, auto_unbox = TRUE)

cat("Metadata exported to: BalticFW_metadata.json\n")

# ============================================================================
# PRINT SUMMARY
# ============================================================================

cat("\n")
cat("===================================================\n")
cat("Data Conversion Complete!\n")
cat("===================================================\n")
cat("\n")
cat("Files created:\n")
cat("  1. BalticFW_network.graphml - Network structure\n")
cat("  2. BalticFW_species_info.csv - Species attributes\n")
cat("  3. BalticFW_adjacency.csv - Adjacency matrix\n")
cat("  4. BalticFW_metadata.json - Metadata\n")
cat("\n")
cat("To load in Python:\n")
cat("  import networkx as nx\n")
cat("  import pandas as pd\n")
cat("  G = nx.read_graphml('BalticFW_network.graphml')\n")
cat("  info = pd.read_csv('BalticFW_species_info.csv')\n")
cat("\n")
