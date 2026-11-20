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

### 4. Trait-based food webs (`trait_foodweb_*.csv`)
**Description:** Species with five trait codes each (MS size, FS foraging
strategy, MB mobility, EP environmental position, PR protection); EconetPy
infers the feeding links from the codes. Copied verbatim from R EcoNeTool's
examples.
- `trait_foodweb_simple.csv` — 5 species
- `trait_foodweb_marine_invertebrates.csv` — 15 species
- `trait_foodweb_coastal_ecosystem.csv` — 35 species (Baltic/North Sea coastal)

Load them from the **Trait-based food web** card on the Data Import page, or
upload your own file in the same format (CSV or .xlsx). Optional columns
`fg, meanB, bodymasses, met.types, efficiencies` are used when present and
filled for every species; otherwise they are estimated. Without `meanB`,
every species gets a placeholder biomass of 1.0 and the Biomass, Energy
Fluxes and Keystoneness pages show a warning banner.

The **extension** switch (on by default) lets small (MS1–MS2) and
extra-large (MS7) species eat; R EcoNeTool's model does not, so it leaves
them without prey. Switch it off to reproduce R exactly. Note: these files
code plankton as `EP4`, which in the current trait vocabulary means
endobenthic, so a few plankton feeders still find no prey.

## How to Use

### Using CSV files (Python app, EconetPy)
1. Download both `*_network.csv` and `*_info.csv` files
2. Modify them in Excel or any spreadsheet software
3. Save as CSV (comma, semicolon or tab separated; UTF-8 preferred)
4. In the app, open **Data Import**, choose both files and click **Load uploaded data**
5. Navigate to the other pages to explore the network

The Simple 3-species and Caribbean reef examples can also be loaded directly
from the **Example datasets** card, without downloading anything. Uploaded
data lives only in your browser session.

### Using RData files (R app only)
The `.Rdata` files are for the R version of EcoNeTool (**Data Import** →
**Choose File** → **Load Data**). The Python app does not read RData.

## File Formats

### Network CSV (Adjacency Matrix)
- Square matrix where rows and columns are species
- Value = 1 means row species (prey) is eaten by column species (predator)
- Value = 0 means no feeding link
- This matches the rows=prey, columns=predator convention used throughout EcoNeTool

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
4. Set feeding links (1 = row species is eaten by column species, 0 = no link)
5. Fill in species attributes (biomass, body mass, etc.)
6. Save and upload to EcoNeTool

## Questions?

For more information on data formats, see the **Data Import** tab in EcoNeTool.

