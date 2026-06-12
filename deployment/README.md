# EcoNeTool Deployment Guide

This directory contains deployment scripts and configuration files for deploying the EcoNeTool Shiny application.

## 📋 Contents

- **`deploy.sh`** - Main deployment script (supports Docker and Shiny Server)
- **`pre-deploy-check.R`** - Pre-deployment validation script
- **`install_dependencies.R`** - R package installation script
- **`shiny-server.conf`** - Shiny Server configuration file

## 🚀 Quick Start

### Deploy to Shiny Server (Recommended)

```bash
cd deployment
sudo ./deploy.sh --shiny-server
```

This will:
1. Run pre-deployment checks
2. Install R package dependencies
3. Copy application files to `/srv/shiny-server/econetool`
4. Configure and restart Shiny Server

### Deploy with Docker

```bash
cd deployment
./deploy.sh --docker
```

## 📝 Pre-Deployment Checks

Before deploying, you can run validation checks:

```bash
cd deployment
Rscript pre-deploy-check.R
```

This validates:
- Required files exist (app.R, plotfw.R, BalticFW.Rdata)
- Data file structure (net and info objects)
- R package dependencies
- R syntax in all scripts
- App structure and functions

## 📦 Manual Package Installation

If you need to install R packages manually:

```bash
cd deployment
Rscript install_dependencies.R
```

Required packages:
- **Shiny**: shiny, bs4Dash, shinyjs, shinyWidgets
- **Data**: dplyr, tidyr, readr, tibble, stringr
- **Network**: igraph, visNetwork, fluxweb
- **Visualization**: ggplot2, plotly, DT
- **Utilities**: jsonlite, openxlsx, readxl

## 🔧 Configuration

### Shiny Server Configuration

The deployment script automatically configures Shiny Server. The config file (`shiny-server.conf`) includes:

- Server listens on port **3838**
- App location: `/srv/shiny-server/econetool`
- Logs: `/var/log/shiny-server`
- URL: `http://your-server:3838/econetool`

To manually edit configuration:
```bash
sudo nano /etc/shiny-server/shiny-server.conf
sudo systemctl restart shiny-server
```

## 📊 Application Structure

Files deployed to production:

```
/srv/shiny-server/econetool/
├── app.R              # Main Shiny application
├── plotfw.R           # Plotting functions
├── BalticFW.Rdata     # Food web data
└── run_app.R          # Optional: App runner
```

## 🛠️ Troubleshooting

### Check Shiny Server Status

```bash
sudo systemctl status shiny-server
```

### View Application Logs

```bash
sudo tail -f /var/log/shiny-server.log
```

### Restart Shiny Server

```bash
sudo systemctl restart shiny-server
```

### Check for Errors in Pre-Deployment

If pre-deployment checks fail:

1. **Missing packages**: Run `Rscript install_dependencies.R`
2. **Syntax errors**: Check the error messages in validation output
3. **Missing data**: Ensure `BalticFW.Rdata` exists in the app directory
4. **Data structure**: Verify `net` and `info` objects with correct columns

### Common Issues

**Issue**: "Shiny Server failed to start"
```bash
# Check detailed logs
sudo journalctl -u shiny-server -n 50

# Check port availability
sudo netstat -tulpn | grep 3838
```

**Issue**: "Package installation failed"
```bash
# Install system dependencies first
sudo apt-get install libcurl4-openssl-dev libssl-dev libxml2-dev
```

**Issue**: "Permission denied"
```bash
# Ensure correct ownership
sudo chown -R shiny:shiny /srv/shiny-server/econetool
```

## 🔄 Updating the Application

To update an already-deployed application:

```bash
cd deployment
sudo ./deploy.sh --shiny-server
```

The script will:
- Backup the current configuration
- Remove old files
- Deploy new version
- Restart the server

## 🐳 Docker Deployment

### Prerequisites

- Docker installed
- Docker Compose installed

### Build and Run

```bash
cd deployment
./deploy.sh --docker
```

### Docker Commands

```bash
# View logs
docker-compose logs -f

# Stop application
docker-compose down

# Restart
docker-compose restart
```

## 📚 System Requirements

### Minimum Requirements

- **OS**: Ubuntu 18.04+ (or compatible Linux distribution)
- **R**: Version 4.0+
- **RAM**: 2GB minimum, 4GB recommended
- **Disk**: 500MB for application + dependencies

### Shiny Server Requirements

- **Port 3838** must be available
- **User**: shiny (created automatically by Shiny Server)
- **Directory**: `/srv/shiny-server` with proper permissions

## 🔐 Security Considerations

1. **Firewall**: Ensure port 3838 is accessible
2. **SSL/HTTPS**: Consider using nginx reverse proxy for HTTPS
3. **Access Control**: Configure Shiny Server authentication if needed
4. **Updates**: Regularly update R packages and system dependencies

## 📖 Additional Resources

- [Shiny Server Documentation](https://docs.posit.co/shiny-server/)
- [EcoNeTool GitHub Repository](https://github.com/your-repo)
- [Food Web Network Analysis](https://cran.r-project.org/package=fluxweb)

## 📞 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review application logs
3. Run pre-deployment checks
4. Contact the development team

---

**Version**: 1.0
**Last Updated**: 2025-01-28
**Maintainer**: EcoNeTool Development Team
