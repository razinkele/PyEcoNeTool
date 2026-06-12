#!/bin/bash

# ==============================================================================
# EcoNeTool Python Shiny Deployment Script for laguna.ku.lt
# ==============================================================================
# This script deploys the EcoNeTool Python Shiny application to laguna.ku.lt
#
# Usage:
#   ./deploy.sh [options]
#
# Options:
#   --dry-run      Show what would be deployed without actually deploying
#   --no-backup    Skip backup creation
#   --force        Force deployment even if checks fail
#   --help         Show this help message
#
# Prerequisites:
#   - SSH access to laguna.ku.lt configured
#   - rsync installed
#   - Miniconda installed on server with 'shiny' environment
#   - Proper permissions on /srv/shiny-apps/
#
# ==============================================================================

set -e  # Exit on error

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Server configuration
SERVER_HOST="laguna.ku.lt"
SERVER_USER="${SHINY_SERVER_USER:-razinka}"
SERVER_PORT=22

# Paths
SHINY_SERVER_ROOT="/srv/shiny-apps"
APP_NAME="EcoNeTool"
APP_DEPLOY_PATH="${SHINY_SERVER_ROOT}/${APP_NAME}"
BACKUP_DIR="${SHINY_SERVER_ROOT}/backups/${APP_NAME}"

# Miniconda configuration
CONDA_ENV_NAME="shiny"
CONDA_PATH="${CONDA_PATH:-/home/${SERVER_USER}/miniconda3}"

# Local paths
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_ROOT}/deployment_logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_DIR}/deploy_${TIMESTAMP}.log"

# Detect if running on the server
CURRENT_HOSTNAME=$(hostname)
IS_LOCAL_DEPLOYMENT=false

# Check if we're on the server
if [[ "$CURRENT_HOSTNAME" == "laguna" ]] || [[ "$CURRENT_HOSTNAME" == "laguna.ku.lt" ]] || [[ "$(hostname -f 2>/dev/null)" == "$SERVER_HOST" ]]; then
  IS_LOCAL_DEPLOYMENT=true
fi

# Files to deploy
FILES=(
  "app.py"
  "network_analysis.py"
  "network_viz.py"
  "load_data.py"
  "BalticFW.pkl"
  "BalticFW_metadata.json"
  "requirements.txt"
  "README.md"
  "README_PYTHON.md"
  "www/"
  "examples/"
)

# Files/directories to exclude
EXCLUDE_PATTERNS=(
  "*.Rproj"
  ".Rproj.user/*"
  "*.Rhistory"
  ".RData"
  "*.Rdata"
  ".git/*"
  ".gitignore"
  ".claude/*"
  "*backup*"
  "*test*.py"
  "*.pyc"
  "__pycache__/*"
  "deploy.sh"
  "deployment/*"
  "deployment_logs/*"
  "Script.R"
  "app.R"
  "run_app.R"
  "create_example_datasets.R"
  "convert_data_r_to_python.R"
  "*.ewemdb"
  "temp_*.html"
  "*.zip"
)

# Flags
DRY_RUN=false
NO_BACKUP=false
FORCE=false

# ==============================================================================
# COLORS FOR OUTPUT
# ==============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

# Print colored message
print_msg() {
  local color=$1
  shift
  echo -e "${color}$@${NC}"
}

# Log message to file and console
log() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $@"
  echo "$msg" | tee -a "$LOG_FILE"
}

# Log info message
log_info() {
  log "[INFO] $@"
  print_msg "$GREEN" "✓ $@"
}

# Log warning message
log_warn() {
  log "[WARN] $@"
  print_msg "$YELLOW" "⚠ $@"
}

# Log error message
log_error() {
  log "[ERROR] $@"
  print_msg "$RED" "✗ $@"
}

# Print section header
print_header() {
  echo ""
  print_msg "$BLUE" "================================================================"
  print_msg "$BLUE" "$@"
  print_msg "$BLUE" "================================================================"
  echo ""
}

# Show help message
show_help() {
  cat << EOF
EcoNeTool Deployment Script

Usage: $0 [options]

Options:
  --dry-run      Show what would be deployed without actually deploying
  --no-backup    Skip backup creation
  --force        Force deployment even if checks fail
  --help         Show this help message

Environment Variables:
  SHINY_SERVER_USER    Username for SSH connection (default: your_username)

Examples:
  # Standard deployment
  ./deploy.sh

  # Dry run to see what would be deployed
  ./deploy.sh --dry-run

  # Deploy without creating backup
  ./deploy.sh --no-backup

  # Force deployment
  SHINY_SERVER_USER=myuser ./deploy.sh --force

Prerequisites:
  1. SSH access to laguna.ku.lt configured with key-based authentication
  2. rsync installed on local machine
  3. Write permissions on ${SHINY_SERVER_ROOT}/
  4. Miniconda installed on laguna.ku.lt with conda environment: ${CONDA_ENV_NAME}
  5. Python Shiny systemd service configured

For more information, see DEPLOYMENT.md

EOF
}

# Parse command line arguments
parse_args() {
  while [[ $# -gt 0 ]]; do
    case $1 in
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --no-backup)
        NO_BACKUP=true
        shift
        ;;
      --force)
        FORCE=true
        shift
        ;;
      --help|-h)
        show_help
        exit 0
        ;;
      *)
        log_error "Unknown option: $1"
        show_help
        exit 1
        ;;
    esac
  done
}

# ==============================================================================
# PRE-DEPLOYMENT CHECKS
# ==============================================================================

check_prerequisites() {
  print_header "Pre-deployment Checks"

  local checks_passed=true

  # Check if log directory exists
  if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR"
    log_info "Created log directory: $LOG_DIR"
  fi

  if [ "$IS_LOCAL_DEPLOYMENT" = false ]; then
    # Check if rsync is installed
    if ! command -v rsync &> /dev/null; then
      log_error "rsync is not installed. Please install it first."
      checks_passed=false
    else
      log_info "rsync is installed"
    fi

    # Check if SSH is configured
    if ! command -v ssh &> /dev/null; then
      log_error "SSH is not installed"
      checks_passed=false
    else
      log_info "SSH is installed"
    fi

    # Check if server user is set
    if [ "$SERVER_USER" = "your_username" ]; then
      log_error "SERVER_USER not configured. Set SHINY_SERVER_USER environment variable."
      echo "Example: export SHINY_SERVER_USER=myusername"
      checks_passed=false
    else
      log_info "Server user: $SERVER_USER"
    fi

    # Test SSH connection
    log_info "Testing SSH connection to ${SERVER_USER}@${SERVER_HOST}..."
    if ssh -o ConnectTimeout=10 -o BatchMode=yes "${SERVER_USER}@${SERVER_HOST}" "echo 'Connection successful'" &> /dev/null; then
      log_info "SSH connection successful"
    else
      log_error "Cannot connect to server. Please check SSH configuration."
      log_error "Make sure you have:"
      echo "  1. SSH key-based authentication configured"
      echo "  2. Correct username (currently: $SERVER_USER)"
      echo "  3. Server is reachable"
      checks_passed=false
    fi
  else
    log_info "Running in local deployment mode (on server)"
    log_info "Checking write permissions to ${SHINY_SERVER_ROOT}..."
    if [ -w "$SHINY_SERVER_ROOT" ] || [ "$(id -u)" = "0" ]; then
      log_info "Have write permissions to deployment directory"
    else
      log_error "No write permissions to ${SHINY_SERVER_ROOT}. Run with sudo."
      checks_passed=false
    fi
  fi

  # Check if required files exist
  log_info "Checking required files..."
  local missing_files=()
  for file in "${FILES[@]}"; do
    if [ ! -f "$file" ]; then
      log_warn "File not found: $file"
      missing_files+=("$file")
    fi
  done

  if [ ${#missing_files[@]} -gt 0 ]; then
    log_warn "${#missing_files[@]} file(s) missing"
    if [ "$FORCE" != true ]; then
      checks_passed=false
    fi
  else
    log_info "All required files present"
  fi

  if [ "$checks_passed" != true ] && [ "$FORCE" != true ]; then
    log_error "Pre-deployment checks failed. Use --force to override."
    exit 1
  fi

  log_info "Pre-deployment checks completed"
}

# ==============================================================================
# BACKUP FUNCTIONS
# ==============================================================================

create_backup() {
  if [ "$NO_BACKUP" = true ]; then
    log_info "Skipping backup (--no-backup flag set)"
    return 0
  fi

  print_header "Creating Backup"

  local backup_name="${APP_NAME}_${TIMESTAMP}.tar.gz"
  local backup_path="${BACKUP_DIR}/${backup_name}"

  log_info "Creating backup..."

  if [ "$IS_LOCAL_DEPLOYMENT" = true ]; then
    # Local deployment - use direct commands
    mkdir -p "${BACKUP_DIR}" || {
      log_error "Failed to create backup directory"
      return 1
    }

    if [ -d "${APP_DEPLOY_PATH}" ]; then
      log_info "Backing up existing application..."
      cd "${SHINY_SERVER_ROOT}" && tar -czf "${backup_path}" "${APP_NAME}" || {
        log_error "Failed to create backup"
        return 1
      }
      log_info "Backup created: ${backup_name}"

      # Clean old backups (keep last 5)
      log_info "Cleaning old backups (keeping last 5)..."
      cd "${BACKUP_DIR}" && ls -t | tail -n +6 | xargs -r rm || {
        log_warn "Failed to clean old backups"
      }
    else
      log_info "No existing application to backup (first deployment)"
    fi
  else
    # Remote deployment - use SSH
    ssh "${SERVER_USER}@${SERVER_HOST}" "mkdir -p ${BACKUP_DIR}" || {
      log_error "Failed to create backup directory on server"
      return 1
    }

    if ssh "${SERVER_USER}@${SERVER_HOST}" "[ -d ${APP_DEPLOY_PATH} ]"; then
      log_info "Backing up existing application..."
      ssh "${SERVER_USER}@${SERVER_HOST}" "cd ${SHINY_SERVER_ROOT} && tar -czf ${backup_path} ${APP_NAME}" || {
        log_error "Failed to create backup"
        return 1
      }
      log_info "Backup created: ${backup_name}"

      # Clean old backups (keep last 5)
      log_info "Cleaning old backups (keeping last 5)..."
      ssh "${SERVER_USER}@${SERVER_HOST}" "cd ${BACKUP_DIR} && ls -t | tail -n +6 | xargs -r rm" || {
        log_warn "Failed to clean old backups"
      }
    else
      log_info "No existing application to backup (first deployment)"
    fi
  fi

  log_info "Backup completed"
}

# ==============================================================================
# DEPLOYMENT FUNCTIONS
# ==============================================================================

prepare_deployment() {
  print_header "Preparing Deployment"

  # Create deployment directory
  log_info "Creating application directory..."
  if [ "$IS_LOCAL_DEPLOYMENT" = true ]; then
    mkdir -p "${APP_DEPLOY_PATH}" || {
      log_error "Failed to create application directory"
      exit 1
    }
  else
    ssh "${SERVER_USER}@${SERVER_HOST}" "mkdir -p ${APP_DEPLOY_PATH}" || {
      log_error "Failed to create application directory"
      exit 1
    }
  fi

  log_info "Deployment preparation completed"
}

deploy_files() {
  print_header "Deploying Files"

  # Build rsync exclude options
  local exclude_opts=""
  for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    exclude_opts+="--exclude='${pattern}' "
  done

  if [ "$IS_LOCAL_DEPLOYMENT" = true ]; then
    # Local deployment - use local rsync or cp
    local rsync_cmd="rsync -avz --progress --delete"

    if [ "$DRY_RUN" = true ]; then
      rsync_cmd+=" --dry-run"
      log_info "DRY RUN MODE - No files will be transferred"
    fi

    rsync_cmd+=" ${exclude_opts}"
    rsync_cmd+=" ./"
    rsync_cmd+=" ${APP_DEPLOY_PATH}/"

    log_info "Deploying files locally..."
    log_info "Command: $rsync_cmd"

    # Execute rsync
    eval $rsync_cmd || {
      log_error "File deployment failed"
      exit 1
    }
  else
    # Remote deployment - use rsync over SSH
    local rsync_cmd="rsync -avz --progress --delete"

    if [ "$DRY_RUN" = true ]; then
      rsync_cmd+=" --dry-run"
      log_info "DRY RUN MODE - No files will be transferred"
    fi

    rsync_cmd+=" ${exclude_opts}"
    rsync_cmd+=" -e 'ssh -p ${SERVER_PORT}'"
    rsync_cmd+=" ./"
    rsync_cmd+=" ${SERVER_USER}@${SERVER_HOST}:${APP_DEPLOY_PATH}/"

    log_info "Deploying files to server..."
    log_info "Command: $rsync_cmd"

    # Execute rsync
    eval $rsync_cmd || {
      log_error "File deployment failed"
      exit 1
    }
  fi

  if [ "$DRY_RUN" != true ]; then
    log_info "Files deployed successfully"
  else
    log_info "Dry run completed - no files were actually transferred"
  fi
}

install_packages() {
  print_header "Installing Python Packages"

  if [ "$DRY_RUN" = true ]; then
    log_info "DRY RUN MODE - Skipping package installation"
    return 0
  fi

  log_info "Installing required Python packages via conda environment..."

  # Install packages from requirements.txt using conda environment
  local install_cmd="source ${CONDA_PATH}/etc/profile.d/conda.sh && conda activate ${CONDA_ENV_NAME} && pip install -r ${APP_DEPLOY_PATH}/requirements.txt"

  if [ "$IS_LOCAL_DEPLOYMENT" = true ]; then
    bash -c "$install_cmd" || {
      log_warn "Package installation had some issues (may need manual check)"
      log_warn "Try manually: conda activate ${CONDA_ENV_NAME} && pip install -r ${APP_DEPLOY_PATH}/requirements.txt"
    }
  else
    ssh "${SERVER_USER}@${SERVER_HOST}" "$install_cmd" || {
      log_warn "Package installation had some issues (may need manual check)"
      log_warn "Try manually on server: conda activate ${CONDA_ENV_NAME} && pip install -r ${APP_DEPLOY_PATH}/requirements.txt"
    }
  fi

  log_info "Package installation completed"
}

restart_shiny_server() {
  print_header "Restarting Python Shiny App"

  if [ "$DRY_RUN" = true ]; then
    log_info "DRY RUN MODE - Skipping app restart"
    return 0
  fi

  log_info "Restarting Python Shiny application..."

  # Service name for the app (format: shiny-app-econetool)
  local service_name="shiny-app-${APP_NAME,,}"  # Convert to lowercase

  if [ "$IS_LOCAL_DEPLOYMENT" = true ]; then
    # Local restart
    if sudo systemctl restart "${service_name}" 2>/dev/null; then
      log_info "Python Shiny app restarted successfully (systemctl)"
    else
      log_warn "Could not restart Python Shiny app automatically"
      log_warn "You may need to restart it manually with:"
      echo "  sudo systemctl restart ${service_name}"
      echo ""
      log_info "Or run manually in conda environment:"
      echo "  cd ${APP_DEPLOY_PATH}"
      echo "  conda activate ${CONDA_ENV_NAME}"
      echo "  shiny run --host 0.0.0.0 --port 8000 app.py"
    fi
  else
    # Remote restart via SSH
    if ssh "${SERVER_USER}@${SERVER_HOST}" "sudo systemctl restart ${service_name}" 2>/dev/null; then
      log_info "Python Shiny app restarted successfully (systemctl)"
    else
      log_warn "Could not restart Python Shiny app automatically"
      log_warn "You may need to restart it manually on the server:"
      echo "  ssh ${SERVER_USER}@${SERVER_HOST}"
      echo "  sudo systemctl restart ${service_name}"
      echo ""
      log_info "Or run manually in conda environment:"
      echo "  ssh ${SERVER_USER}@${SERVER_HOST}"
      echo "  cd ${APP_DEPLOY_PATH}"
      echo "  conda activate ${CONDA_ENV_NAME}"
      echo "  shiny run --host 0.0.0.0 --port 8000 app.py"
    fi
  fi

  # Wait for server to start
  log_info "Waiting for app to start..."
  sleep 5
}

# ==============================================================================
# POST-DEPLOYMENT VERIFICATION
# ==============================================================================

verify_deployment() {
  print_header "Post-deployment Verification"

  if [ "$DRY_RUN" = true ]; then
    log_info "DRY RUN MODE - Skipping verification"
    return 0
  fi

  # Python Shiny app URL (typically on port 8000 or configured port)
  local app_url="http://${SERVER_HOST}:8000/"

  # Check if files exist
  log_info "Verifying deployed files..."
  if [ "$IS_LOCAL_DEPLOYMENT" = true ]; then
    for file in "${FILES[@]}"; do
      if [ -f "${APP_DEPLOY_PATH}/${file}" ]; then
        echo "  ✓ $file"
      else
        log_warn "File not found: $file"
      fi
    done
  else
    for file in "${FILES[@]}"; do
      if ssh "${SERVER_USER}@${SERVER_HOST}" "[ -f ${APP_DEPLOY_PATH}/${file} ]"; then
        echo "  ✓ $file"
      else
        log_warn "File not found on server: $file"
      fi
    done
  fi

  # Check if app is accessible
  log_info "Checking if application is accessible..."
  log_info "URL: $app_url"

  if command -v curl &> /dev/null; then
    if curl -s -f "$app_url" > /dev/null; then
      log_info "Application is accessible!"
    else
      log_warn "Could not verify application accessibility"
      log_warn "Please check manually: $app_url"
    fi
  else
    log_info "curl not available, please check manually: $app_url"
  fi

  log_info "Verification completed"
}

# ==============================================================================
# MAIN DEPLOYMENT WORKFLOW
# ==============================================================================

main() {
  # Parse command line arguments
  parse_args "$@"

  # Print deployment header
  clear
  print_msg "$BLUE" "================================================================"
  print_msg "$BLUE" "  EcoNeTool Python Shiny Deployment to laguna.ku.lt"
  print_msg "$BLUE" "  Version: 3.0 (Python Shiny + Miniconda)"
  print_msg "$BLUE" "  Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
  print_msg "$BLUE" "================================================================"
  echo ""

  if [ "$DRY_RUN" = true ]; then
    print_msg "$YELLOW" "  *** DRY RUN MODE - No changes will be made ***"
    echo ""
  fi

  if [ "$IS_LOCAL_DEPLOYMENT" = true ]; then
    print_msg "$GREEN" "  *** LOCAL DEPLOYMENT MODE - Running on server ***"
    echo ""
  fi

  # Start logging
  log_info "Deployment started"

  if [ "$IS_LOCAL_DEPLOYMENT" = true ]; then
    log_info "Mode: Local deployment (running on server)"
    log_info "Target: ${APP_DEPLOY_PATH}"
  else
    log_info "Mode: Remote deployment via SSH"
    log_info "Target: ${SERVER_USER}@${SERVER_HOST}:${APP_DEPLOY_PATH}"
  fi

  log_info "Log file: $LOG_FILE"

  # Run deployment steps
  check_prerequisites
  create_backup
  prepare_deployment
  deploy_files
  install_packages
  restart_shiny_server
  verify_deployment

  # Deployment complete
  print_header "Deployment Complete"

  local app_url="http://${SERVER_HOST}:8000/"
  local service_name="shiny-app-${APP_NAME,,}"

  log_info "Deployment completed successfully!"
  echo ""
  print_msg "$GREEN" "Application URL: $app_url"
  echo ""
  print_msg "$BLUE" "Next steps:"
  echo "  1. Visit $app_url in your browser"
  echo "  2. Test all features (Dashboard, Network, Topology, etc.)"
  echo "  3. Check app status: ssh ${SERVER_USER}@${SERVER_HOST} 'sudo systemctl status ${service_name}'"
  echo "  4. Check app logs: ssh ${SERVER_USER}@${SERVER_HOST} 'journalctl -u ${service_name} -f'"
  echo "  5. Review deployment log: $LOG_FILE"
  echo ""
  print_msg "$BLUE" "Conda environment info:"
  echo "  Environment: ${CONDA_ENV_NAME}"
  echo "  Path: ${CONDA_PATH}"
  echo ""
  print_msg "$GREEN" "Deployment successful! 🎉"
  echo ""

  log_info "Deployment workflow completed"
}

# ==============================================================================
# RUN MAIN FUNCTION
# ==============================================================================

main "$@"
