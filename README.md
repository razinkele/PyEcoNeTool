# PyEcoNeTool - Marine Food Web Network Analysis Tool

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Shiny](https://img.shields.io/badge/Shiny-for%20Python-red.svg)](https://shiny.posit.co/py/)
[![GitHub](https://img.shields.io/badge/GitHub-razinkele/PyEcoNeTool-blue)](https://github.com/razinkele/PyEcoNeTool)

**Interactive Python Shiny Dashboard for analyzing trophic interactions, biomass distributions, and energy fluxes in marine ecosystems**

## 📋 Overview

PyEcoNeTool is a Python port of the original R Shiny EcoNeTool, providing comprehensive analysis tools for marine food web networks. Built with Shiny for Python and PyVis, it offers an interactive web interface for understanding food web structure and dynamics through qualitative and quantitative network analysis.

### Key Features

- **📊 Interactive Network Visualization**: PyVis-powered dynamic food web graphs with species-level details
- **🎨 Modern Dashboard UI**: Collapsible sidebar, gradient top bar, and professional footer
- **📈 Topological Metrics**: Connectance, generality, vulnerability, and trophic levels
- **⚖️ Biomass Analysis**: Node-weighted metrics accounting for species abundance
- **⚡ Energy Flux Calculations**: Metabolic theory-based energy flow analysis
- **🔑 Keystoneness Analysis**: Identify keystone species using Mixed Trophic Impact
- **✏️ Internal Data Editor**: Edit species information and network matrices directly
- **💡 Menu Tooltips**: Helpful descriptions when hovering over menu items

## 🚀 Quick Start

### Running Locally

1. **Clone the repository**:
   ```bash
   git clone https://github.com/razinkele/PyEcoNeTool.git
   cd PyEcoNeTool
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python -m shiny run app.py --port 8000
   ```

4. **Access the app** in your browser at: `http://127.0.0.1:8000`

### Development Mode

Run with auto-reload for development:
```bash
python -m shiny run app.py --port 8000 --reload
```

## 📦 Installation

### Prerequisites

- Python (>= 3.10)
- pip package manager

### Installing Dependencies

```bash
pip install -r requirements.txt
```

### Required Python Packages

- shiny>=1.0.0
- networkx>=3.0
- pyvis>=0.3.2
- pandas>=2.0.0
- numpy>=1.24.0
- scipy>=1.10.0
- matplotlib>=3.7.0
- seaborn>=0.12.0
- plotly>=5.14.0
- shinyswatch>=0.4.0

## 📖 Data Format

### Required Data Structure

PyEcoNeTool requires two main input files:

1. **Network GraphML File** - Food web structure (`food_web_network.graphml`)
2. **Species Information CSV** - Species attributes (`species_info.csv`)

### Supported Formats

- **GraphML**: NetworkX-compatible directed graph format
- **CSV**: Species information with biomass and functional groups

### Example Data Structure

```python
# Network: NetworkX DiGraph (stored as GraphML)
import networkx as nx

# Create directed graph
G = nx.DiGraph()
G.add_edges_from([('Species_A', 'Species_B'), ('Species_B', 'Species_C')])
nx.write_graphml(G, 'food_web_network.graphml')

# Species info: Pandas DataFrame (stored as CSV)
import pandas as pd

species_info = pd.DataFrame({
    'Species': ['Species_A', 'Species_B', 'Species_C'],
    'Biomass': [1250.5, 850.2, 2100.0],
    'FunctionalGroup': ['Fish', 'Zooplankton', 'Phytoplankton']
})
species_info.to_csv('species_info.csv', index=False)
```

### File Locations

Place these files in the project root directory:
- `food_web_network.graphml`
- `species_info.csv`

See `examples/` directory for complete example datasets.

## 🔬 Analysis Features

### 1. Network Visualization
- Interactive force-directed network graphs
- Color-coded by functional groups
- Node size proportional to biomass
- Edge width shows interaction strength

### 2. Topological Metrics
- Species richness (S)
- Link density (L/S)
- Connectance (C)
- Mean generality and vulnerability
- Trophic levels

### 3. Biomass-Weighted Analysis
- Node-weighted connectance
- Node-weighted generality/vulnerability
- Biomass-based importance metrics

### 4. Energy Flux Analysis
- Metabolic theory-based flux calculations
- Temperature-adjusted metabolic rates
- Flux-weighted network visualization
- Shannon diversity of energy flows

### 5. Keystoneness Analysis
- Mixed Trophic Impact (MTI) calculations
- Keystoneness index (impact/biomass ratio)
- Identification of keystone species

## 📊 Default Dataset

The application includes the **Gulf of Riga Food Web** dataset:
- **Source**: Frelat, R., & Kortsch, S. (2020)
- **Period**: 1979-2016 (37 years)
- **Taxa**: 34 species across 5 functional groups
- **Links**: 207 trophic interactions

## 🛠️ Deployment

### Server Deployment

Use the included deployment script:

```bash
# Standard deployment to laguna.ku.lt
./deploy.sh

# Dry run (see what would be deployed)
./deploy.sh --dry-run

# Deploy without backup
./deploy.sh --no-backup
```

### Configuration

Edit deployment settings in `deploy.sh`:
- Server host
- Server user
- Deployment paths
- Backup settings

## 📚 Documentation

- **Data Import Guide**: See the "Data Import" tab in the application
- **Format Examples**: Check the `examples/` directory
- **Deployment Guide**: See `deployment/README.md`

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues or pull requests on GitHub.

## 👥 Authors

- **MARBEFES Project Team**
- Klaipėda University, Lithuania

## 📄 License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

Based on the methodology from:

**Kortsch, S., Frelat, R., Pecuchet, L., Olivier, P., Putnis, I., Bonsdorff, E., Ojaveer, H., Jurgensone, I., Strāķe, S., Rubene, G., Krūze, Ē., & Nordström, M.** *Qualitative and quantitative network descriptors reveal complementary patterns of change in temporal food web dynamics.*

This work builds upon the original BalticFoodWeb analysis tools:
- Original tutorial: [BalticFoodWeb](https://rfrelat.github.io/BalticFoodWeb.html)

## 📞 Contact

For questions or support, please open an issue on [GitHub](https://github.com/razinkele/EcoNeTool/issues).

## 🔗 Links

- **GitHub Repository**: https://github.com/razinkele/EcoNeTool
- **MARBEFES Project**: [Horizon Europe MARBEFES](https://cordis.europa.eu/project/id/101060937)
- **Original Work**: [BalticFoodWeb on GitHub](https://github.com/rfrelat/BalticFoodWeb)

---

<a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/"><img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-sa/4.0/80x15.png" /></a><br />This work is licensed under a <a rel="license" href="http://creativecommons.org/licenses/by-sa/4.0/">Creative Commons Attribution-ShareAlike 4.0 International License</a>.
