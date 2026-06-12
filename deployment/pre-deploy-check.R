#!/usr/bin/env Rscript
# ============================================================================
# EcoNeTool - Pre-Deployment Check Script
# ============================================================================
#
# This script validates the application before deployment
# Run this before deploying to catch common issues
#
# Usage:
#   Rscript pre-deploy-check.R
#
# ============================================================================

cat("================================================================================\n")
cat("EcoNeTool - Pre-Deployment Validation\n")
cat("================================================================================\n\n")

# Set working directory to app root
setwd("..")

# Initialize counters
errors <- 0
warnings <- 0
checks_passed <- 0

# Helper functions
print_check <- function(name, status, message = "") {
  if (status == "PASS") {
    cat(sprintf("✓ %s\n", name))
    checks_passed <<- checks_passed + 1
  } else if (status == "WARN") {
    cat(sprintf("⚠ %s: %s\n", name, message))
    warnings <<- warnings + 1
  } else {
    cat(sprintf("✗ %s: %s\n", name, message))
    errors <<- errors + 1
  }
}

# ============================================================================
# Check 1: Required files exist
# ============================================================================
cat("\n[1] Checking Required Files...\n")

required_files <- c(
  "app.R",
  "plotfw.R",
  "BalticFW.Rdata"
)

for (file in required_files) {
  if (file.exists(file)) {
    print_check(paste("File:", file), "PASS")
  } else {
    print_check(paste("File:", file), "ERROR", "File not found")
  }
}

# Check optional files
optional_files <- c("run_app.R")
for (file in optional_files) {
  if (file.exists(file)) {
    print_check(paste("File:", file, "(optional)"), "PASS")
  } else {
    print_check(paste("File:", file, "(optional)"), "WARN", "File not found")
  }
}

# ============================================================================
# Check 2: Validate data file
# ============================================================================
cat("\n[2] Validating Data File...\n")

if (file.exists("BalticFW.Rdata")) {
  tryCatch({
    load("BalticFW.Rdata")

    # Check for required objects
    if (exists("net")) {
      print_check("Data: net object", "PASS")
    } else {
      print_check("Data: net object", "ERROR", "net not found in BalticFW.Rdata")
    }

    if (exists("info")) {
      print_check("Data: info object", "PASS")

      # Validate info structure
      required_cols <- c("meanB", "fg", "bodymasses", "met.types", "efficiencies")
      missing_cols <- setdiff(required_cols, colnames(info))

      if (length(missing_cols) == 0) {
        print_check("Data: info columns", "PASS")
      } else {
        print_check("Data: info columns", "ERROR",
                   paste("Missing columns:", paste(missing_cols, collapse = ", ")))
      }
    } else {
      print_check("Data: info object", "ERROR", "info not found in BalticFW.Rdata")
    }

  }, error = function(e) {
    print_check("Data file loading", "ERROR", e$message)
  })
} else {
  print_check("BalticFW.Rdata", "ERROR", "Data file not found")
}

# ============================================================================
# Check 3: R package dependencies
# ============================================================================
cat("\n[3] Checking R Package Dependencies...\n")

required_packages <- c(
  "shiny", "bs4Dash", "igraph", "fluxweb", "visNetwork",
  "ggplot2", "DT", "dplyr", "tidyr", "jsonlite"
)

missing_packages <- c()
for (pkg in required_packages) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    # Package available - don't print individual successes to reduce noise
  } else {
    print_check(paste("Package:", pkg), "ERROR", "Not installed")
    missing_packages <- c(missing_packages, pkg)
  }
}

if (length(missing_packages) == 0) {
  print_check("All required packages", "PASS")
  cat(sprintf("   Checked %d packages\n", length(required_packages)))
} else {
  cat(sprintf("\n   Missing packages: %s\n", paste(missing_packages, collapse = ", ")))
  cat("   Run: Rscript deployment/install_dependencies.R\n")
}

# ============================================================================
# Check 4: Validate R syntax
# ============================================================================
cat("\n[4] Checking R Syntax...\n")

r_files <- c("app.R", "plotfw.R")
if (file.exists("run_app.R")) {
  r_files <- c(r_files, "run_app.R")
}

for (file in r_files) {
  if (file.exists(file)) {
    result <- tryCatch({
      parse(file)
      TRUE
    }, error = function(e) {
      print_check(paste("Syntax:", file), "ERROR", e$message)
      FALSE
    })
    if (result) {
      print_check(paste("Syntax:", file), "PASS")
    }
  }
}

# ============================================================================
# Check 5: Validate app structure
# ============================================================================
cat("\n[5] Validating App Structure...\n")

# Check if app.R contains required functions
if (file.exists("app.R")) {
  app_content <- paste(readLines("app.R"), collapse = "\n")

  # Check for key components
  if (grepl("calculate_losses", app_content)) {
    print_check("Function: calculate_losses", "PASS")
  } else {
    print_check("Function: calculate_losses", "WARN", "Not found")
  }

  if (grepl("get_fluxweb_results", app_content)) {
    print_check("Function: get_fluxweb_results", "PASS")
  } else {
    print_check("Function: get_fluxweb_results", "ERROR", "Not found")
  }

  if (grepl("trophiclevels", app_content)) {
    print_check("Function: trophiclevels", "PASS")
  } else {
    print_check("Function: trophiclevels", "ERROR", "Not found")
  }

  if (grepl("dashboardPage", app_content)) {
    print_check("UI: dashboardPage", "PASS")
  } else {
    print_check("UI: dashboardPage", "ERROR", "Not found")
  }

  if (grepl("server.*function", app_content)) {
    print_check("Server: server function", "PASS")
  } else {
    print_check("Server: server function", "ERROR", "Not found")
  }

  if (grepl("shinyApp", app_content)) {
    print_check("App: shinyApp call", "PASS")
  } else {
    print_check("App: shinyApp call", "ERROR", "Not found")
  }
}

# ============================================================================
# Check 6: Check for common issues
# ============================================================================
cat("\n[6] Checking for Common Issues...\n")

# Check for temporary files
temp_patterns <- c("*~", "*.tmp", "*.log", ".Rhistory", ".RData")
temp_found <- FALSE
for (pattern in temp_patterns) {
  temp_files <- list.files(pattern = glob2rx(pattern), recursive = FALSE)
  if (length(temp_files) > 0) {
    if (!temp_found) {
      print_check("Temporary files", "WARN", "Found temporary files in root")
      temp_found <- TRUE
    }
  }
}
if (!temp_found) {
  print_check("Temporary files", "PASS")
}

# Check for backup files
backup_files <- list.files(pattern = ".*backup.*\\.R$", ignore.case = TRUE)
if (length(backup_files) > 0) {
  print_check("Backup files", "WARN",
             sprintf("Found %d backup files", length(backup_files)))
} else {
  print_check("Backup files", "PASS")
}

# Check data file size
if (file.exists("BalticFW.Rdata")) {
  file_size_mb <- file.size("BalticFW.Rdata") / 1024 / 1024
  if (file_size_mb > 50) {
    print_check("Data file size", "WARN",
               sprintf("Large file: %.1f MB", file_size_mb))
  } else {
    print_check("Data file size", "PASS")
  }
}

# ============================================================================
# Summary
# ============================================================================
cat("\n================================================================================\n")
cat("Pre-Deployment Check Summary\n")
cat("================================================================================\n\n")

total_checks <- checks_passed + warnings + errors

cat(sprintf("Total Checks: %d\n", total_checks))
cat(sprintf("✓ Passed: %d\n", checks_passed))
if (warnings > 0) {
  cat(sprintf("⚠ Warnings: %d\n", warnings))
}
if (errors > 0) {
  cat(sprintf("✗ Errors: %d\n", errors))
}

cat("\n")

if (errors > 0) {
  cat("❌ DEPLOYMENT NOT RECOMMENDED\n")
  cat("   Please fix the errors above before deploying.\n\n")
  quit(status = 1)
} else if (warnings > 0) {
  cat("⚠️  DEPLOYMENT POSSIBLE WITH WARNINGS\n")
  cat("   Review warnings before deploying to production.\n\n")
  quit(status = 0)
} else {
  cat("✅ ALL CHECKS PASSED\n")
  cat("   Application is ready for deployment!\n\n")
  quit(status = 0)
}
