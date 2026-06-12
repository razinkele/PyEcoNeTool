# EcoNeTool Example Datasets

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
- `met.types` - Metabolic type ("invertebrates", "ectotherm vertebrates", "Other")
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

