# EcoNeTool - Python Shiny Version

**Python Shiny Application for Marine Food Web Network Analysis**

This is the Python conversion of the original R Shiny EcoNeTool application, using **PyVis** instead of visNetwork for interactive network visualization.

## 🔄 Conversion Summary

This application has been converted from R Shiny to Python Shiny with the following key changes:

### Technology Mapping

| Component | R Version | Python Version |
|-----------|-----------|----------------|
| **Web Framework** | R Shiny + bs4Dash | Python Shiny |
| **Network Viz** | visNetwork | **PyVis** |
| **Network Analysis** | igraph (R) | NetworkX + igraph (Python) |
| **Data Tables** | DT | Shiny DataGrid |
| **Plotting** | Base R + ggplot2 | Matplotlib + Seaborn |
| **Energy Fluxes** | fluxweb package | Custom Python implementation |

## 📋 Features Implemented

- ✅ Interactive network visualization with PyVis
- ✅ Barnes-Hut physics layout (matching R visNetwork settings)
- ✅ Topological metrics calculation
- ✅ Node-weighted (biomass-based) metrics
- ✅ Trophic level calculation
- ✅ Keystoneness analysis with MTI
- ✅ Flux indicators (Shannon diversity-based)
- ✅ All visualization tabs and plots

## 🚀 Quick Start

### 1. Install Python Dependencies

```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 2. Convert Data from R Format

If you have the R data file (`BalticFW.Rdata`):

```bash
# Step 1: Run R conversion script
Rscript convert_data_r_to_python.R

# Step 2: Load data in Python
python load_data.py
```

This creates `BalticFW.pkl` for fast loading.

### 3. Run the Application

```bash
shiny run app.py
```

Open your browser to `http://localhost:8000`

## 📦 Project Structure

```
EconetPy/
├── app.py                          # Main Python Shiny application
├── network_analysis.py             # Network analysis functions (converted from R)
├── network_viz.py                  # PyVis visualization functions
├── load_data.py                    # Data loading script
├── convert_data_r_to_python.R      # Data conversion from R
├── requirements.txt                # Python dependencies
│
├── BalticFW.Rdata                  # Original R data
├── BalticFW.pkl                    # Converted Python pickle
│
├── BalticFW_network.graphml        # Network in universal format
├── BalticFW_species_info.csv       # Species info
└── BalticFW_metadata.json          # Metadata
```

## 🔧 Module Documentation

### `network_analysis.py`

Core analysis functions converted from R:

```python
# Trophic levels
calculate_trophic_levels(G: nx.DiGraph) -> np.ndarray

# Topological indicators
get_topological_indicators(G: nx.DiGraph) -> Dict[str, float]
# Returns: S, C, G, V, ShortPath, TL, Omni

# Node-weighted indicators
get_node_weighted_indicators(G: nx.DiGraph, biomass: np.ndarray) -> Dict[str, float]
# Returns: nwC, nwG, nwV, nwTL

# Metabolic losses (Brown et al. 2004)
calculate_losses(bodymasses, met_types, temp=3.5) -> np.ndarray

# Flux indicators (Bersier et al. 2002)
calculate_flux_indicators(flux_matrix, loop=False) -> Dict[str, float]
# Returns: lwC, lwG, lwV

# Mixed Trophic Impact
calculate_mti(G: nx.DiGraph) -> np.ndarray

# Keystoneness (Libralato et al. 2006)
calculate_keystoneness(G: nx.DiGraph, biomass: np.ndarray) -> pd.DataFrame
```

### `network_viz.py`

PyVis visualization functions:

```python
# Create topology network
create_topology_network(
    G, species_names, functional_groups,
    biomass, colors, width="100%", height="600px"
) -> Network

# Create flux-weighted network
create_flux_network(
    G, species_names, functional_groups,
    biomass, colors, flux_matrix,
    width="100%", height="600px"
) -> Network

# Get functional group colors
get_functional_group_colors(functional_groups: List[str])
    -> Tuple[List[str], Dict[str, str]]
```

## 🎨 PyVis Network Configuration

The PyVis networks use identical physics settings to the R visNetwork version:

```python
{
    "physics": {
        "solver": "barnesHut",
        "barnesHut": {
            "gravitationalConstant": -3000,
            "centralGravity": 0.05,
            "springLength": 250,
            "springConstant": 0.01,
            "damping": 0.5,
            "avoidOverlap": 0.3
        },
        "stabilization": {
            "iterations": 5000,
            "updateInterval": 25
        }
    }
}
```

### Node Properties

- **Size**: Biomass-scaled (min: 4px, factor: 25)
- **Color**: By functional group (matches R version)
- **Y-position**: By trophic level (fixed Y, physics X)
- **Tooltip**: Species info (name, group, TL, biomass)

### Edge Properties

- **Topology view**: Uniform width
- **Flux view**: Width scaled by energy flux
- **Arrows**: Point from prey to predator
- **Curve**: Curved edges (roundness: 0.2)

## 📊 Data Format

### Network

NetworkX DiGraph where edges represent trophic links (prey → predator).

### Species Info DataFrame

Required columns:

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `species` | str | Species name | "Cod" |
| `fg` | str | Functional group | "Fish" |
| `meanB` | float | Mean biomass | 125.5 |
| `bodymasses` | float | Body mass (g) | 50.0 |
| `met.types` | str | Metabolic type | "ectotherm vertebrates" |
| `efficiencies` | float | Assimilation efficiency | 0.85 |

## 🔬 Analysis Tabs

### 1. Dashboard
- Network statistics
- Functional group legend
- Value boxes (species, links, groups)

### 2. Food Web Network
- Toggle Topology / Flux-weighted view
- Adjustable height
- Download network HTML
- Adjacency matrix heatmap

### 3. Topological Metrics
- Qualitative indicators (S, C, G, V, TL, Omni)
- Trophic level histogram
- Species TL table

### 4. Biomass Analysis
- Node-weighted indicators
- Biomass by functional group
- Species biomass distribution

### 5. Energy Fluxes
- Calculate fluxes (with temperature parameter)
- Flux-based indicators (lwC, lwG, lwV)
- Flux matrix heatmap
- Flux-weighted network

### 6. Keystoneness Analysis
- Keystoneness summary
- Keystoneness vs Biomass scatter plot
- Species rankings table
- MTI matrix heatmap

### 7. Data Editor
- Edit species information
- Update network (experimental)

## ⚠️ Known Limitations

### 1. Energy Flux Calculation

The Python version uses a **simplified flux approximation**. The original R version uses the `fluxweb` package which implements the full metabolic theory algorithm.

**Workaround options:**
1. Implement full algorithm in Python
2. Use `rpy2` to call R's `fluxweb::fluxing()` from Python
3. Pre-calculate fluxes in R and import

### 2. UI Framework

Python Shiny doesn't have a direct equivalent to R's `bs4Dash`. The Python version uses standard Shiny layouts with similar functionality but different styling.

### 3. Not Yet Implemented

- ⏳ Data upload UI (Excel, CSV, RData)
- ⏳ Live data editor with network regeneration
- ⏳ All export options
- ⏳ ECOPATH format support

## 🔄 Differences from R Version

### Visual Differences

| Aspect | R visNetwork | Python PyVis |
|--------|-------------|--------------|
| Legend | Built-in legend widget | Manual HTML legend |
| Controls | visInteraction options | PyVis navigation buttons |
| Node selection | Dropdown selector | PyVis default |
| Physics UI | Hidden | Visible in some configs |

### Functional Differences

1. **Network Rendering**: PyVis generates standalone HTML that's embedded in Shiny UI
2. **Reactivity**: Python Shiny uses different reactive patterns than R
3. **Data Tables**: Different interactive table library
4. **Plotting**: Uses Matplotlib/Seaborn instead of ggplot2

## 🛠️ Troubleshooting

### Network not displaying

**Problem**: Blank network area or JavaScript errors

**Solution**:
1. Check browser console for errors
2. Ensure PyVis HTML is being generated correctly
3. Try different browser

### Data conversion failed

**Problem**: Error loading R data

**Solution**:
1. Ensure `BalticFW.Rdata` exists
2. Check R and Python are both installed
3. Verify all R packages are installed
4. Check file paths in scripts

### Import errors

**Problem**: ModuleNotFoundError

**Solution**:
```bash
pip install --upgrade -r requirements.txt
```

### Slow network rendering

**Problem**: Network takes long to stabilize

**Solution**:
1. Reduce `stabilization.iterations` in `network_viz.py`
2. Decrease network size
3. Set `physics = False` for large networks

## 🚀 Future Enhancements

### High Priority

1. **Full fluxweb implementation**: Port or wrap R's fluxweb package
2. **Data upload UI**: Support Excel, CSV, RData uploads
3. **Live data editing**: Real-time network updates

### Medium Priority

4. **Enhanced UI**: More bs4Dash-like styling
5. **Export options**: Download all analyses
6. **Performance**: Optimize for large networks

### Low Priority

7. **ECOPATH support**: Native .mdb/.ewemdb reading
8. **Additional layouts**: Force-directed alternatives
9. **Temporal analysis**: Time-series food webs

## 📚 References

### Methods

- **Trophic Levels**: Williams & Martinez (2004)
- **Network Metrics**: Williams & Martinez (2000)
- **Metabolic Theory**: Brown et al. (2004)
- **Flux Indicators**: Bersier et al. (2002)
- **Keystoneness**: Libralato et al. (2006)
- **MTI**: Ulanowicz & Puccia (1990)

### Data

- **Source**: Frelat & Kortsch (2020)
- **Period**: 1979-2016 (Gulf of Riga)
- **Species**: 34 taxa, 207 links

## 👥 Contributing

Contributions welcome! Priority areas:

1. Fluxweb algorithm implementation
2. UI enhancements
3. Performance optimization
4. Documentation improvements

## 📄 License

GPL-3.0 (same as R version)

## 🙏 Acknowledgments

- Original R Shiny app by MARBEFES Project Team
- visNetwork R package developers → PyVis Python package developers
- Shiny for Python team at Posit
- NetworkX and igraph communities

## 📞 Contact

For Python-specific issues, please document:
- Python version
- OS and browser
- Error messages
- Steps to reproduce

---

**Version**: 1.0.0 (Initial Python conversion)
**Date**: 2025-12-02
**Converter**: Claude Code
