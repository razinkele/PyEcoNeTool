# EcoNeTool Python Shiny Deployment Guide

## Deployment to laguna.ku.lt

This guide explains how to deploy the EcoNeTool Python Shiny application to the laguna.ku.lt server using Miniconda.

## Prerequisites

### On Your Local Machine
1. SSH access to laguna.ku.lt configured with key-based authentication
2. rsync installed
3. Set the `SHINY_SERVER_USER` environment variable to your username

### On laguna.ku.lt Server
1. Miniconda installed (typically in `/home/[username]/miniconda3`)
2. Conda environment named `shiny` created and configured
3. Write permissions on `/srv/shiny-apps/`
4. Systemd service configured for the app

## Initial Server Setup

### 1. Install Miniconda on Server (if not already installed)

SSH into the server and run:

```bash
ssh razinka@laguna.ku.lt

# Download Miniconda installer
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh

# Install Miniconda
bash Miniconda3-latest-Linux-x86_64.sh

# Initialize conda
~/miniconda3/bin/conda init bash
source ~/.bashrc
```

### 2. Create Conda Environment

```bash
# Create conda environment named 'shiny'
conda create -n shiny python=3.11 -y

# Activate the environment
conda activate shiny

# Install base packages
pip install shiny
```

### 3. Create Application Directory

```bash
# Create directory for shiny apps
sudo mkdir -p /srv/shiny-apps
sudo chown razinka:razinka /srv/shiny-apps

# Create backup directory
sudo mkdir -p /srv/shiny-apps/backups
```

### 4. Set Up Systemd Service

Copy the service file to systemd:

```bash
# Copy service file (after deployment)
sudo cp /srv/shiny-apps/EcoNeTool/econetool.service /etc/systemd/system/shiny-app-econetool.service

# Edit the service file if needed (update paths/user)
sudo nano /etc/systemd/system/shiny-app-econetool.service

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable shiny-app-econetool

# Start the service
sudo systemctl start shiny-app-econetool

# Check status
sudo systemctl status shiny-app-econetool
```

## Deployment from Local Machine

### 1. Configure Environment

Set your SSH username:

```bash
export SHINY_SERVER_USER=razinka
```

Or set it in your `~/.bashrc` or `~/.zshrc`:

```bash
echo 'export SHINY_SERVER_USER=razinka' >> ~/.bashrc
source ~/.bashrc
```

### 2. Run Deployment Script

#### Standard Deployment
```bash
./deploy.sh
```

#### Dry Run (Test without deploying)
```bash
./deploy.sh --dry-run
```

#### Deploy without Backup
```bash
./deploy.sh --no-backup
```

#### Force Deployment (Skip checks)
```bash
./deploy.sh --force
```

### 3. Verify Deployment

After deployment completes:

1. Visit http://laguna.ku.lt:8000/ in your browser
2. Test all features:
   - Dashboard
   - Food Web Network
   - Topological Metrics
   - Biomass Analysis
   - Energy Fluxes
   - Keystoneness Analysis

## Manual Deployment (Alternative)

If the deployment script doesn't work, you can deploy manually:

### 1. Copy Files to Server

```bash
rsync -avz --progress --delete \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  ./ razinka@laguna.ku.lt:/srv/shiny-apps/EcoNeTool/
```

### 2. Install Dependencies

SSH into server and run:

```bash
ssh razinka@laguna.ku.lt
cd /srv/shiny-apps/EcoNeTool
conda activate shiny
pip install -r requirements.txt
```

### 3. Restart Service

```bash
sudo systemctl restart shiny-app-econetool
```

## Troubleshooting

### Check Application Status

```bash
ssh razinka@laguna.ku.lt
sudo systemctl status shiny-app-econetool
```

### View Application Logs

```bash
# Follow live logs
ssh razinka@laguna.ku.lt
journalctl -u shiny-app-econetool -f

# View recent logs
journalctl -u shiny-app-econetool -n 100
```

### Restart Application

```bash
ssh razinka@laguna.ku.lt
sudo systemctl restart shiny-app-econetool
```

### Check if App is Running

```bash
# Check if port 8000 is listening
ssh razinka@laguna.ku.lt
netstat -tlnp | grep 8000

# Or use curl to test
curl http://localhost:8000
```

### Common Issues

#### 1. Port Already in Use

If port 8000 is already in use, edit the service file:

```bash
sudo nano /etc/systemd/system/shiny-app-econetool.service
# Change --port 8000 to another port like 8001
sudo systemctl daemon-reload
sudo systemctl restart shiny-app-econetool
```

#### 2. Permission Denied

Ensure the app directory has correct permissions:

```bash
sudo chown -R razinka:razinka /srv/shiny-apps/EcoNeTool
```

#### 3. Missing Python Packages

Install packages manually:

```bash
conda activate shiny
cd /srv/shiny-apps/EcoNeTool
pip install -r requirements.txt
```

#### 4. Conda Environment Not Found

Create the environment:

```bash
conda create -n shiny python=3.11 -y
conda activate shiny
pip install shiny
```

## Running the App Manually (for Testing)

If you want to test the app without systemd:

```bash
ssh razinka@laguna.ku.lt
cd /srv/shiny-apps/EcoNeTool
conda activate shiny
shiny run --host 0.0.0.0 --port 8000 app.py
```

Press Ctrl+C to stop the app.

## Firewall Configuration

If you can't access the app from outside the server, you may need to open the port:

```bash
# For UFW (Ubuntu Firewall)
sudo ufw allow 8000/tcp

# For firewalld (CentOS/RHEL)
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

## Reverse Proxy Configuration (Optional)

For production, it's recommended to use Nginx or Apache as a reverse proxy:

### Nginx Example

```nginx
server {
    listen 80;
    server_name laguna.ku.lt;

    location /econetool/ {
        proxy_pass http://localhost:8000/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

## Backup and Rollback

### Backups

The deployment script automatically creates backups in `/srv/shiny-apps/backups/EcoNeTool/`.

Backups are named: `EcoNeTool_YYYYMMDD_HHMMSS.tar.gz`

The script keeps the 5 most recent backups.

### Rollback to Previous Version

```bash
ssh razinka@laguna.ku.lt
cd /srv/shiny-apps/backups/EcoNeTool

# List available backups
ls -lh

# Extract a backup
tar -xzf EcoNeTool_20251210_120000.tar.gz -C /srv/shiny-apps/

# Restart the service
sudo systemctl restart shiny-app-econetool
```

## Updating the Application

To update the application after making changes:

1. Commit your changes to git (optional but recommended)
2. Run the deployment script:
   ```bash
   ./deploy.sh
   ```
3. The script will:
   - Create a backup of the current version
   - Deploy new files
   - Install/update Python packages
   - Restart the application

## Monitoring

### Set Up Log Rotation

Create a logrotate configuration:

```bash
sudo nano /etc/logrotate.d/econetool
```

Add:

```
/var/log/econetool/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 razinka razinka
    sharedscripts
    postrotate
        systemctl reload shiny-app-econetool > /dev/null 2>&1 || true
    endscript
}
```

## Security Considerations

1. **Firewall**: Only open port 8000 to trusted networks
2. **HTTPS**: Use a reverse proxy with SSL/TLS certificates
3. **Authentication**: Consider adding authentication layer if needed
4. **Updates**: Regularly update Python packages for security patches

## Support

For issues or questions:
- Check logs: `journalctl -u shiny-app-econetool -f`
- Review deployment log: `deployment_logs/deploy_*.log`
- GitHub Issues: [Link to your repository]
