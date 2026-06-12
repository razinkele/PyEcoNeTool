#!/usr/bin/env Rscript
# Create example datasets for EcoNeTool
# This script generates sample food web data files for users to download and test

library(igraph)

# Create examples directory
if (!dir.exists("examples")) {
  dir.create("examples")
}

# ==============================================================================
# 1. SIMPLE 3-SPECIES FOOD CHAIN
# ==============================================================================

cat("Creating Simple 3-Species example...\n")

# Create adjacency matrix (row eats column)
# Zooplankton eats Phytoplankton, Fish eats Zooplankton
adj_simple <- matrix(c(
  0, 0, 0,  # Phytoplankton eats nothing
  1, 0, 0,  # Zooplankton eats Phytoplankton
  0, 1, 0   # Fish eats Zooplankton
), nrow = 3, byrow = TRUE)

species_names_simple <- c("Phytoplankton", "Zooplankton", "Fish")
rownames(adj_simple) <- colnames(adj_simple) <- species_names_simple

# Create network
net <- graph_from_adjacency_matrix(adj_simple, mode = "directed")

# Create species info
info <- data.frame(
  species = species_names_simple,
  fg = factor(c("Phytoplankton", "Zooplankton", "Fish"),
              levels = c("Phytoplankton", "Zooplankton", "Fish", "Benthos", "Detritus")),
  meanB = c(5000, 800, 150),  # Biomass (g/km²)
  bodymasses = c(0.00001, 0.001, 50),  # Body mass (g)
  met.types = c("Other", "invertebrates", "ectotherm vertebrates"),
  efficiencies = c(0.45, 0.75, 0.85),  # Assimilation efficiency
  stringsAsFactors = FALSE
)

# Save as RData
save(net, info, file = "examples/Simple_3Species.Rdata")
cat("  ✓ Saved: examples/Simple_3Species.Rdata\n")

# Save network as CSV
write.csv(adj_simple, "examples/Simple_3Species_network.csv", row.names = TRUE)
cat("  ✓ Saved: examples/Simple_3Species_network.csv\n")

# Save species info as CSV
write.csv(info, "examples/Simple_3Species_info.csv", row.names = FALSE)
cat("  ✓ Saved: examples/Simple_3Species_info.csv\n")

# ==============================================================================
# 2. CARIBBEAN REEF FOOD WEB (10 species)
# ==============================================================================

cat("\nCreating Caribbean Reef example...\n")

# Species: 10 species in a tropical reef food web
species_names_reef <- c(
  "Phytoplankton",      # 1 - Primary producer
  "Macroalgae",         # 2 - Primary producer
  "Zooplankton",        # 3 - Herbivore
  "Sea_Urchin",         # 4 - Herbivore (benthos)
  "Parrotfish",         # 5 - Herbivore fish
  "Damselfish",         # 6 - Planktivore fish
  "Snapper",            # 7 - Carnivore fish
  "Grouper",            # 8 - Top predator fish
  "Octopus",            # 9 - Benthic predator
  "Barracuda"           # 10 - Top predator fish
)

# Create adjacency matrix (10x10)
# Row eats column
adj_reef <- matrix(0, nrow = 10, ncol = 10)
rownames(adj_reef) <- colnames(adj_reef) <- species_names_reef

# Define feeding links
# Zooplankton eats Phytoplankton
adj_reef["Zooplankton", "Phytoplankton"] <- 1

# Sea Urchin eats Macroalgae
adj_reef["Sea_Urchin", "Macroalgae"] <- 1

# Parrotfish eats Macroalgae
adj_reef["Parrotfish", "Macroalgae"] <- 1

# Damselfish eats Zooplankton and Phytoplankton
adj_reef["Damselfish", "Zooplankton"] <- 1
adj_reef["Damselfish", "Phytoplankton"] <- 1

# Snapper eats Damselfish, Zooplankton, Sea_Urchin
adj_reef["Snapper", "Damselfish"] <- 1
adj_reef["Snapper", "Zooplankton"] <- 1
adj_reef["Snapper", "Sea_Urchin"] <- 1

# Grouper eats Parrotfish, Damselfish, Snapper, Octopus
adj_reef["Grouper", "Parrotfish"] <- 1
adj_reef["Grouper", "Damselfish"] <- 1
adj_reef["Grouper", "Snapper"] <- 1
adj_reef["Grouper", "Octopus"] <- 1

# Octopus eats Sea_Urchin, Damselfish
adj_reef["Octopus", "Sea_Urchin"] <- 1
adj_reef["Octopus", "Damselfish"] <- 1

# Barracuda eats Snapper, Parrotfish, Damselfish, Grouper
adj_reef["Barracuda", "Snapper"] <- 1
adj_reef["Barracuda", "Parrotfish"] <- 1
adj_reef["Barracuda", "Damselfish"] <- 1
adj_reef["Barracuda", "Grouper"] <- 1

# Create network
net <- graph_from_adjacency_matrix(adj_reef, mode = "directed")

# Create species info
info <- data.frame(
  species = species_names_reef,
  fg = factor(c(
    "Phytoplankton", "Phytoplankton", "Zooplankton",
    "Benthos", "Fish", "Fish", "Fish", "Fish", "Benthos", "Fish"
  ), levels = c("Benthos", "Detritus", "Fish", "Phytoplankton", "Zooplankton")),
  meanB = c(
    8000,   # Phytoplankton
    3500,   # Macroalgae
    1200,   # Zooplankton
    600,    # Sea Urchin
    450,    # Parrotfish
    800,    # Damselfish
    250,    # Snapper
    180,    # Grouper
    150,    # Octopus
    120     # Barracuda
  ),
  bodymasses = c(
    0.00001,  # Phytoplankton (g)
    0.1,      # Macroalgae
    0.001,    # Zooplankton
    80,       # Sea Urchin
    500,      # Parrotfish
    50,       # Damselfish
    1500,     # Snapper
    5000,     # Grouper
    2000,     # Octopus
    8000      # Barracuda
  ),
  met.types = c(
    "Other", "Other", "invertebrates",
    "invertebrates", "ectotherm vertebrates", "ectotherm vertebrates",
    "ectotherm vertebrates", "ectotherm vertebrates",
    "invertebrates", "ectotherm vertebrates"
  ),
  efficiencies = c(
    0.40,  # Phytoplankton
    0.45,  # Macroalgae
    0.70,  # Zooplankton
    0.60,  # Sea Urchin
    0.75,  # Parrotfish
    0.80,  # Damselfish
    0.85,  # Snapper
    0.85,  # Grouper
    0.80,  # Octopus
    0.85   # Barracuda
  ),
  stringsAsFactors = FALSE
)

# Save as RData
save(net, info, file = "examples/Caribbean_Reef.Rdata")
cat("  ✓ Saved: examples/Caribbean_Reef.Rdata\n")

# Save network as CSV
write.csv(adj_reef, "examples/Caribbean_Reef_network.csv", row.names = TRUE)
cat("  ✓ Saved: examples/Caribbean_Reef_network.csv\n")

# Save species info as CSV
write.csv(info, "examples/Caribbean_Reef_info.csv", row.names = FALSE)
cat("  ✓ Saved: examples/Caribbean_Reef_info.csv\n")

# ==============================================================================
# 3. CREATE EMPTY TEMPLATE
# ==============================================================================

cat("\nCreating empty template...\n")

# Empty template with proper structure
species_template <- c("Species_A", "Species_B", "Species_C")

adj_template <- matrix(0, nrow = 3, ncol = 3)
rownames(adj_template) <- colnames(adj_template) <- species_template

net <- graph_from_adjacency_matrix(adj_template, mode = "directed")

info <- data.frame(
  species = species_template,
  fg = factor(c("Fish", "Zooplankton", "Phytoplankton"),
              levels = c("Benthos", "Detritus", "Fish", "Phytoplankton", "Zooplankton")),
  meanB = c(100, 500, 2000),
  bodymasses = c(50, 0.01, 0.00001),
  met.types = c("ectotherm vertebrates", "invertebrates", "Other"),
  efficiencies = c(0.85, 0.75, 0.45),
  stringsAsFactors = FALSE
)

save(net, info, file = "examples/Template_Empty.Rdata")
cat("  ✓ Saved: examples/Template_Empty.Rdata\n")

write.csv(adj_template, "examples/Template_network.csv", row.names = TRUE)
cat("  ✓ Saved: examples/Template_network.csv\n")

write.csv(info, "examples/Template_info.csv", row.names = FALSE)
cat("  ✓ Saved: examples/Template_info.csv\n")

# ==============================================================================
# CREATE README FOR EXAMPLES
# ==============================================================================

cat("\nCreating examples README...\n")

readme_content <- "# EcoNeTool Example Datasets

This directory contains example food web datasets for testing and learning how to use EcoNeTool.

## Available Examples

### 1. Simple_3Species.Rdata
**Description:** A basic linear food chain with 3 species
- **Species:** 3 (Phytoplankton → Zooplankton → Fish)
- **Links:** 2 trophic interactions
- **Purpose:** Perfect for testing and understanding the basic structure
- **Files:**
  - `Simple_3Species.Rdata` - R data file
  - `Simple_3Species_network.csv` - Adjacency matrix
  - `Simple_3Species_info.csv` - Species information

### 2. Caribbean_Reef.Rdata
**Description:** A tropical reef food web with multiple trophic levels
- **Species:** 10 species across 4 functional groups
- **Links:** 18 trophic interactions
- **Purpose:** More complex example showing realistic food web structure
- **Functional Groups:** Phytoplankton, Zooplankton, Fish, Benthos
- **Files:**
  - `Caribbean_Reef.Rdata` - R data file
  - `Caribbean_Reef_network.csv` - Adjacency matrix
  - `Caribbean_Reef_info.csv` - Species information

### 3. Template_Empty.Rdata
**Description:** Empty template you can modify for your own data
- **Species:** 3 placeholder species
- **Purpose:** Starting point for creating your own food web
- **Files:**
  - `Template_Empty.Rdata` - R data file
  - `Template_network.csv` - Adjacency matrix template
  - `Template_info.csv` - Species information template

## How to Use

### Using RData files
1. Download the `.Rdata` file
2. In EcoNeTool, go to **Data Import** tab
3. Click **Choose File** and select the `.Rdata` file
4. Click **Load Data**
5. Navigate to other tabs to explore the network

### Using CSV files
1. Download both `*_network.csv` and `*_info.csv` files
2. Modify them in Excel or any spreadsheet software
3. Save as CSV
4. Upload to EcoNeTool (CSV import coming soon)

## File Formats

### Network CSV (Adjacency Matrix)
- Square matrix where rows and columns are species
- Value = 1 means row species eats column species
- Value = 0 means no feeding link

### Species Info CSV
Required columns:
- `species` - Species name (must match network)
- `fg` - Functional group (Benthos, Detritus, Fish, Phytoplankton, Zooplankton)
- `meanB` - Mean biomass (g/km²)
- `bodymasses` - Average body mass (g)
- `met.types` - Metabolic type (\"invertebrates\", \"ectotherm vertebrates\", \"Other\")
- `efficiencies` - Assimilation efficiency (0-1)

## Creating Your Own Dataset

1. Start with Template files
2. Modify species names in both network and info files
3. Add/remove species (keep matrix square!)
4. Set feeding links (1 = eats, 0 = no link)
5. Fill in species attributes (biomass, body mass, etc.)
6. Save and upload to EcoNeTool

## Questions?

For more information on data formats, see the **Data Import** tab in EcoNeTool.
"

writeLines(readme_content, "examples/README.md")
cat("  ✓ Saved: examples/README.md\n")

cat("\n✓ All example datasets created successfully!\n")
cat("\nCreated files:\n")
cat("  - examples/Simple_3Species.Rdata\n")
cat("  - examples/Simple_3Species_network.csv\n")
cat("  - examples/Simple_3Species_info.csv\n")
cat("  - examples/Caribbean_Reef.Rdata\n")
cat("  - examples/Caribbean_Reef_network.csv\n")
cat("  - examples/Caribbean_Reef_info.csv\n")
cat("  - examples/Template_Empty.Rdata\n")
cat("  - examples/Template_network.csv\n")
cat("  - examples/Template_info.csv\n")
cat("  - examples/README.md\n")
