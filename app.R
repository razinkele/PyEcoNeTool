# app.R
# Shiny app for Baltic Food Web analysis
library(shiny)
library(bs4Dash)
library(igraph)
library(fluxweb)
library(visNetwork)
library(DT)

source("plotfw.R")

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

# Color scheme for functional groups (Benthos, Detritus, Fish, Phytoplankton, Zooplankton)
COLOR_SCHEME <- c("orange", "darkgrey", "blue", "green", "cyan")

# Trophic level calculation parameters
TROPHIC_LEVEL_MAX_ITER <- 100      # Maximum iterations for convergence
TROPHIC_LEVEL_CONVERGENCE <- 0.0001  # Convergence threshold

# Flux calculation parameters
FLUX_CONVERSION_FACTOR <- 86.4     # Convert J/sec to kJ/day
FLUX_LOG_EPSILON <- 0.00001        # Small value to avoid log(0)

# Visualization parameters
NODE_SIZE_SCALE <- 25              # Scaling factor for node size by biomass
NODE_SIZE_MIN <- 4                 # Minimum node size
EDGE_WIDTH_SCALE <- 15             # Scaling factor for edge width by flux
EDGE_WIDTH_MIN <- 0.1              # Minimum edge width
EDGE_ARROW_SIZE_TOPOLOGY <- 0.3    # Arrow size for topology networks
EDGE_ARROW_SIZE_FLUX <- 0.05       # Arrow size for flux networks

# Data file path
DATA_FILE <- "BalticFW.Rdata"

# ============================================================================
# DATA LOADING WITH VALIDATION
# ============================================================================

# Load data and prepare variables
if (!file.exists(DATA_FILE)) {
  stop(paste("Data file not found:", DATA_FILE,
             "\nPlease ensure BalticFW.Rdata is in the working directory."))
}

tryCatch({
  # Load data into a separate environment to avoid overwriting functions
  # BalticFW.Rdata contains functions (trophiclevels, plotfw, fluxind) that
  # would overwrite our own function definitions if loaded into GlobalEnv
  suppressMessages({
    data_env <- new.env()
    load(DATA_FILE, envir = data_env)

    # Validate required objects exist
    if (!exists("net", envir = data_env)) stop("'net' object not found in data file")
    if (!exists("info", envir = data_env)) stop("'info' object not found in data file")

    # Extract only the data objects (not functions) from the loaded environment
    net <<- data_env$net
    info <<- data_env$info

    # Validate network structure
    if (!igraph::is_igraph(net)) stop("'net' must be an igraph object")

    # Upgrade igraph object if needed
    net <<- igraph::upgrade_graph(net)
  })

  if (vcount(net) == 0) stop("Network contains no vertices")
  if (ecount(net) == 0) warning("Network contains no edges")

  # Validate info data frame
  required_cols <- c("meanB", "fg", "bodymasses", "met.types", "efficiencies")
  missing_cols <- setdiff(required_cols, colnames(info))
  if (length(missing_cols) > 0) {
    stop(paste("Missing required columns in info:", paste(missing_cols, collapse=", ")))
  }

  # Validate biomass values
  if (any(info$meanB < 0, na.rm = TRUE)) {
    stop("Biomass values must be non-negative")
  }
  if (all(is.na(info$meanB))) {
    stop("All biomass values are NA")
  }

  # Validate functional groups
  if (nlevels(info$fg) != length(COLOR_SCHEME)) {
    warning(paste("Number of functional groups (", nlevels(info$fg),
                  ") does not match color scheme length (", length(COLOR_SCHEME), ")",
                  sep=""))
  }

}, error = function(e) {
  stop(paste("Error loading data:", e$message))
})

# ============================================================================
# HELPER FUNCTIONS WITH DOCUMENTATION
# ============================================================================

#' Calculate trophic levels for a food web
#'
#' Computes trophic levels using an iterative algorithm. Basal species
#' (no prey) are assigned TL = 1. Consumer species have TL = 1 + mean(TL of prey).
#' The algorithm iterates until convergence or maximum iterations reached.
#'
#' @param net An igraph object representing the food web (directed graph)
#'
#' @return A numeric vector of trophic levels for each species/node
#'
#' @details
#' The algorithm uses fixed-point iteration:
#' - Initialize all species to TL = 1
#' - Iterate: for each consumer, TL = 1 + mean(prey TL)
#' - Stop when max change < TROPHIC_LEVEL_CONVERGENCE or max iterations reached
#'
#' @examples
#' tl <- trophiclevels(net)
#' mean(tl)  # Mean trophic level of the food web
#'
#' @references
#' Williams, R. J., & Martinez, N. D. (2004). Limits to trophic levels and
#' omnivory in complex food webs. Proceedings of the Royal Society B, 271(1540), 549-556.
trophiclevels <- function(net) {
  # Input validation
  if (!igraph::is_igraph(net)) {
    stop("Input 'net' must be an igraph object")
  }

  n <- vcount(net)
  if (n == 0) {
    stop("Network contains no vertices")
  }

  tl <- rep(1, n)  # Initialize all to 1
  adj <- as_adjacency_matrix(net, sparse = FALSE)

  # Iterate until convergence
  converged <- FALSE
  for (iter in 1:TROPHIC_LEVEL_MAX_ITER) {
    tl_old <- tl
    for (i in 1:n) {
      # Find prey of species i (incoming edges)
      prey_indices <- which(adj[i, ] > 0)
      if (length(prey_indices) > 0) {
        # TL = 1 + mean TL of prey
        tl[i] <- 1 + mean(tl[prey_indices])
      } else {
        # Basal species
        tl[i] <- 1
      }
    }
    # Check for convergence
    if (max(abs(tl - tl_old)) < TROPHIC_LEVEL_CONVERGENCE) {
      converged <- TRUE
      break
    }
  }

  if (!converged) {
    warning(paste("Trophic level calculation did not converge after",
                  TROPHIC_LEVEL_MAX_ITER, "iterations"))
  }

  return(tl)
}

#' Calculate topological (qualitative) indicators for a food web
#'
#' Computes structural properties of the food web network without considering
#' node weights (biomass). These are purely topological metrics.
#'
#' @param net An igraph object representing the food web
#'
#' @return A list containing:
#' \describe{
#'   \item{S}{Species richness (number of taxa)}
#'   \item{C}{Connectance (proportion of realized links)}
#'   \item{G}{Generality (mean number of prey per predator)}
#'   \item{V}{Vulnerability (mean number of predators per prey)}
#'   \item{ShortPath}{Mean shortest path length}
#'   \item{TL}{Mean trophic level}
#'   \item{Omni}{Omnivory index (mean SD of prey trophic levels)}
#' }
#'
#' @details
#' Formulas:
#' - C = L / (S * (S-1)) where L is number of links
#' - G = sum(in-degree for predators) / number of predators
#' - V = sum(out-degree for prey) / number of prey
#' - Omnivory = mean(SD of prey TL for each consumer)
#'
#' @references
#' Williams, R. J., & Martinez, N. D. (2000). Simple rules yield complex food webs.
#' Nature, 404(6774), 180-183.
get_topological_indicators <- function(net) {
  # Input validation
  if (!igraph::is_igraph(net)) {
    stop("Input 'net' must be an igraph object")
  }

  tryCatch({
    S <- vcount(net)
    if (S <= 1) {
      warning("Network has only one or zero species. Metrics may be undefined.")
    }

    C <- ecount(net)/(S*(S-1))
    pred <- degree(net, mode="in")>0
    G <- sum(degree(net, mode="in")[pred])/sum(pred)
    prey <- degree(net, mode="out")>0
    V <- sum(degree(net, mode="out")[prey])/sum(prey)
    sp <- distances(net)
    ShortPath <- mean(sp[upper.tri(sp)])
    tlnodes <- trophiclevels(net)
    TL <- mean(tlnodes)
    netmatrix <- as_adjacency_matrix(net, sparse=F)
    webtl <- netmatrix*tlnodes
    webtl[webtl==0] <- NA
    omninodes <- apply(webtl,2,sd, na.rm=TRUE)
    Omni <- mean(omninodes, na.rm=TRUE)

    list(S=S, C=C, G=G, V=V, ShortPath=ShortPath, TL=TL, Omni=Omni)

  }, error = function(e) {
    stop(paste("Error calculating topological indicators:", e$message))
  })
}

#' Calculate node-weighted (quantitative) indicators for a food web
#'
#' Computes network metrics weighted by node biomass. These metrics account
#' for the relative importance of species based on their biomass.
#'
#' @param net An igraph object representing the food web
#' @param info Data frame containing species information with 'meanB' column for biomass
#'
#' @return A list containing:
#' \describe{
#'   \item{nwC}{Node-weighted connectance}
#'   \item{nwG}{Node-weighted generality}
#'   \item{nwV}{Node-weighted vulnerability}
#'   \item{nwTL}{Node-weighted mean trophic level}
#' }
#'
#' @details
#' Node-weighted metrics give more importance to high-biomass species.
#' - nwC = sum(degree * biomass) / (2 * sum(biomass) * (S-1))
#' - nwG = sum(in-degree * biomass for predators) / sum(predator biomass)
#' - nwV = sum(out-degree * biomass for prey) / sum(prey biomass)
#' - nwTL = sum(TL * biomass) / sum(biomass)
#'
#' @references
#' Olivier, P., et al. (2019). Exploring the temporal variability of a food web
#' using long-term biomonitoring data. Ecography, 42(11), 2107-2121.
get_node_weighted_indicators <- function(net, info) {
  # Input validation
  if (!igraph::is_igraph(net)) {
    stop("Input 'net' must be an igraph object")
  }
  if (!is.data.frame(info)) {
    stop("Input 'info' must be a data frame")
  }
  if (!"meanB" %in% colnames(info)) {
    stop("'info' must contain 'meanB' column for biomass")
  }
  if (nrow(info) != vcount(net)) {
    stop("Number of rows in 'info' must match number of vertices in 'net'")
  }

  tryCatch({
    biomass <- info$meanB

    # Check for NA or negative biomass
    if (any(is.na(biomass))) {
      warning("NA values found in biomass, results may be unreliable")
    }
    if (any(biomass < 0, na.rm = TRUE)) {
      stop("Biomass values must be non-negative")
    }

    tlnodes <- trophiclevels(net)
    nwC <- sum(degree(net)*biomass)/(2*sum(biomass)*(vcount(net)-1))
    pred <- degree(net, mode="in")>0
    nwG <- sum((degree(net, mode="in")*biomass)[pred])/(sum(biomass[pred]))
    prey <- degree(net, mode="out")>0
    nwV <- sum((degree(net, mode="out")*biomass)[prey])/(sum(biomass[prey]))
    nwTL <- sum(tlnodes*biomass)/sum(biomass)

    list(nwC=nwC, nwG=nwG, nwV=nwV, nwTL=nwTL)

  }, error = function(e) {
    stop(paste("Error calculating node-weighted indicators:", e$message))
  })
}

#' Calculate link-weighted flux indicators
#'
#' Computes Shannon diversity-based indicators from an energy flux matrix.
#' These metrics account for the distribution of energy flows across trophic links.
#'
#' @param fluxes Numeric matrix of energy fluxes between species (from fluxing())
#' @param loop Logical, whether to include self-loops in connectance calculation
#'
#' @return A list containing:
#' \describe{
#'   \item{lwC}{Link-weighted connectance}
#'   \item{lwG}{Link-weighted generality (effective number of prey)}
#'   \item{lwV}{Link-weighted vulnerability (effective number of predators)}
#' }
#'
#' @details
#' Uses Shannon diversity indices to calculate effective numbers of trophic
#' interactions. Higher values indicate more evenly distributed energy flows.
#'
#' @references
#' Bersier, L. F., et al. (2002). Quantitative descriptors of food web matrices.
#' Ecology, 83(9), 2394-2407.
fluxind <- function(fluxes, loop = FALSE) {
  res <- list()

  # The flux matrix
  W.net <- as.matrix(fluxes)

  ### Taxon-specific Shannon indices of inflows
  # sum of k species inflows --> colsums
  sum.in <- apply(W.net, 2, sum)

  # Diversity of k species inflows
  # columns divided by the total col sum
  H.in.mat <- t(t(W.net)/sum.in)*t(log(t(W.net)/sum.in))
  H.in.mat[!is.finite(H.in.mat)] <- 0  # converts NaN to 0's
  H.in <- apply(H.in.mat, 2, sum)*-1

  # Effective number of prey or resources = N(R,k)
  # The reciprocal of H(R,k) --> N (R,k) is the equivalent number of prey for species k
  N.res <- ifelse(sum.in==0, H.in, exp(H.in))

  ### Taxon-specific Shannon indices of outflows
  # sum of k species outflows --> rowsums
  sum.out <- apply(W.net, 1, sum)

  # Diversity of k species outflows
  # rows divided by the total row sum
  H.out.mat <- (W.net/sum.out)*log(W.net/sum.out)
  H.out.mat[!is.finite(H.out.mat)] <- 0  # converts NaN to 0's
  H.out <- apply(H.out.mat, 1, sum)*-1

  # Effective number of predators or consumers = N(C,k)
  # The reciprocal of H(C,k) --> N (C,k) is the equivalent number of predators for species k
  N.con <- ifelse(sum.out==0, H.out, exp(H.out))

  ### Quantitative Weighted connectance
  no.species <- ncol(W.net)

  # The weighted link density (LDw) is:
  # In the weighted version the effective number of predators for species i is weighted by i's
  # contribution to the total outflow the same is the case for the inflows
  tot.mat <- sum(W.net)
  # LD.w <- (sum((sum.in/tot.mat)*N.res) + sum((sum.out/tot.mat)*N.con))/2
  # equivalent to next formula, but next one is closer to manuscript
  LD <- 1/(2*tot.mat)*(sum(sum.in*N.res) + sum(sum.out*N.con))

  # Weighted connectance
  res$lwC <- LD/ifelse(loop, no.species, no.species-1)

  # positional.index
  pos.ind <- sum.in*N.res/(sum.in*N.res+sum.out*N.con)  # positional index
  basal.sp <- pos.ind[pos.ind==0]  # basal species = 0
  top.sp <- pos.ind[pos.ind==1]  # definition according to Bersier et al. 2002 top species = [0.99, 1]

  con.sp <- length(pos.ind)-length(basal.sp)  # all consumer taxa except basal
  # weighted quantitative Generality
  res$lwG <- sum(sum.in*N.res/sum(W.net))

  res.sp <- length(pos.ind)-length(top.sp)
  # weighted quantitative Vulnerability
  res$lwV <- sum(sum.out*N.con/sum(W.net))

  return(res)
}

#' Calculate metabolic losses for species
#'
#' Computes species-specific metabolic losses using the allometric equation
#' from metabolic theory of ecology (Brown et al. 2004).
#'
#' @param info Data frame with columns: bodymasses (body mass in grams),
#'        met.types (metabolic type: "invertebrates", "ectotherm vertebrates", or "Other")
#' @param temp Temperature in degrees Celsius (default = 3.5°C for Gulf of Riga spring)
#'
#' @return Numeric vector of metabolic losses (J/sec) for each species
#'
#' @details
#' Uses the classic allometric equation:
#' X_i = exp((a * log(M_i) + x0) - E/(k*T))
#'
#' Where:
#' - M_i is body mass of species i (grams)
#' - a = -0.29 (allometric scaling constant for biomass)
#' - x0 is normalization constant (17.17 for invertebrates, 18.47 for vertebrates)
#' - E = 0.69 (activation energy)
#' - k = 0.00008617343 (Boltzmann constant)
#' - T is temperature in Kelvin
#'
#' Note: Use a = 0.71 when using abundance instead of biomass (0.71 = 1 - 0.29)
#'
#' @references
#' Brown, J. H., et al. (2004). Toward a metabolic theory of ecology.
#' Ecology, 85(7), 1771-1789.
calculate_losses <- function(info, temp = 3.5) {
  # Input validation
  if (!is.data.frame(info)) {
    stop("Input 'info' must be a data frame")
  }

  required_cols <- c("bodymasses", "met.types")
  missing_cols <- setdiff(required_cols, colnames(info))
  if (length(missing_cols) > 0) {
    stop(paste("Missing required columns in info:", paste(missing_cols, collapse=", ")))
  }

  # Constants from metabolic theory
  boltz <- 0.00008617343  # Boltzmann constant
  a <- -0.29              # Allometric scaling (for biomass)
  E <- 0.69               # Activation energy

  # Normalization constants (intercept of body-mass metabolism scaling relationship)
  losses_param <- list(
    "invertebrates" = 17.17,
    "ectotherm vertebrates" = 18.47,
    "Other" = 0
  )

  # Get x0 for each species based on metabolic type
  x0 <- unlist(losses_param[info$met.types])

  # Calculate losses using allometric equation
  # Formula: exp((a * log(M_i) + x0) - E/(k*(T+273.15)))
  losses <- exp((a * log(info$bodymasses) + x0) - E/(boltz * (273.15 + temp)))

  return(losses)
}

#' Calculate energy fluxes using metabolic theory
#'
#' Computes biomass fluxes between species using the fluxweb package,
#' which applies metabolic theory of ecology. Returns both flux matrix
#' and weighted network.
#'
#' @param net An igraph object representing the food web
#' @param info Data frame with columns: meanB (biomass), bodymasses (body mass),
#'        met.types (metabolic type), efficiencies (assimilation efficiencies)
#' @param temp Temperature in degrees Celsius (default = 3.5°C for Gulf of Riga)
#'
#' @return A list containing:
#' \describe{
#'   \item{fluxes}{Matrix of energy fluxes (kJ/day/km²) between species}
#'   \item{netLW}{Weighted igraph object with flux as edge weights}
#'   \item{losses}{Calculated metabolic losses (J/sec) for each species}
#' }
#'
#' @details
#' Uses allometric scaling based on metabolic theory:
#' X_i = exp((a * log(M_i) + x0) - E/(k*T))
#'
#' Losses are calculated from body mass and metabolic type, then used with
#' prey-level assimilation efficiencies to compute energy fluxes.
#' Fluxes are converted from J/sec to kJ/day (multiply by FLUX_CONVERSION_FACTOR).
#'
#' @references
#' Brown, J. H., et al. (2004). Toward a metabolic theory of ecology.
#' Ecology, 85(7), 1771-1789.
#'
#' Gauzens, B., et al. (2019). fluxweb: An R package to easily estimate energy
#' fluxes in food webs. Methods in Ecology and Evolution, 10(2), 270-279.
get_fluxweb_results <- function(net, info, temp = 3.5) {
  # Input validation
  if (!igraph::is_igraph(net)) {
    stop("Input 'net' must be an igraph object")
  }
  if (!is.data.frame(info)) {
    stop("Input 'info' must be a data frame")
  }

  required_cols <- c("meanB", "bodymasses", "met.types", "efficiencies")
  missing_cols <- setdiff(required_cols, colnames(info))
  if (length(missing_cols) > 0) {
    stop(paste("Missing required columns in info:", paste(missing_cols, collapse=", ")))
  }

  if (nrow(info) != vcount(net)) {
    stop("Number of rows in 'info' must match number of vertices in 'net'")
  }

  tryCatch({
    netmatrix <- as_adjacency_matrix(net, sparse=F)
    biomass <- info$meanB

    # Validate inputs
    if (any(is.na(biomass))) {
      warning("NA values in biomass, flux calculations may fail")
    }
    if (any(biomass < 0, na.rm = TRUE)) {
      stop("Biomass values must be non-negative")
    }

    # Calculate metabolic losses from body mass and metabolic type
    # Following Brown et al. (2004) metabolic theory
    losses <- calculate_losses(info, temp)

    # Calculate fluxes using fluxweb package
    # Uses prey-level assimilation efficiencies
    fluxes <- fluxing(netmatrix, biomass, losses, info$efficiencies, ef.level="prey")

    # Convert J/sec to kJ/day
    fluxes <- fluxes * FLUX_CONVERSION_FACTOR

    # Create weighted network
    netLW <- graph_from_adjacency_matrix(fluxes, weighted=TRUE)

    list(fluxes=fluxes, netLW=netLW, losses=losses)

  }, error = function(e) {
    stop(paste("Error calculating fluxweb results:", e$message))
  })
}

#' Calculate Mixed Trophic Impact (MTI) matrix
#'
#' Computes the direct and indirect impacts of each species on all others
#' using the ECOPATH approach. MTI represents the net effect of increasing
#' the biomass of one species on all other species in the food web.
#'
#' @param net An igraph object representing the food web
#' @param info Data frame with 'meanB' column for biomass
#'
#' @return A matrix where MTI[i,j] represents the impact of species j on species i
#'
#' @details
#' The MTI is calculated using the equation:
#' MTI = -I * (DC + FC)^(-1) * DC
#'
#' Where:
#' - DC (Diet Composition) = consumption matrix normalized by total consumption
#' - FC (Fishery Catch) = assumed zero for natural systems
#' - I = identity matrix
#'
#' Positive MTI values indicate a positive impact (increase in impactor increases impacted)
#' Negative MTI values indicate a negative impact (increase in impactor decreases impacted)
#'
#' @references
#' Ulanowicz, R. E., & Puccia, C. J. (1990). Mixed trophic impacts in ecosystems.
#' Coenoses, 5(1), 7-16.
#'
#' Libralato, S., et al. (2006). A method for identifying keystone species in
#' food web models. Ecological Modelling, 195(3-4), 153-171.
calculate_mti <- function(net, info) {
  # Input validation
  if (!igraph::is_igraph(net)) {
    stop("Input 'net' must be an igraph object")
  }
  if (!is.data.frame(info)) {
    stop("Input 'info' must be a data frame")
  }
  if (!"meanB" %in% colnames(info)) {
    stop("'info' must contain 'meanB' column for biomass")
  }
  if (nrow(info) != vcount(net)) {
    stop("Number of rows in 'info' must match number of vertices in 'net'")
  }

  tryCatch({
    n <- vcount(net)
    adj_matrix <- as_adjacency_matrix(net, sparse = FALSE)

    # Create Diet Composition (DC) matrix
    # DC[i,j] = proportion of predator i's diet that is prey j
    # Rows = predators, Columns = prey
    DC <- matrix(0, nrow = n, ncol = n)
    rownames(DC) <- colnames(DC) <- V(net)$name

    # Calculate row sums (total consumption per predator)
    row_sums <- rowSums(adj_matrix)

    # Normalize each row by its sum (if non-zero)
    for (i in 1:n) {
      if (row_sums[i] > 0) {
        DC[i, ] <- adj_matrix[i, ] / row_sums[i]
      }
    }

    # Create identity matrix
    I <- diag(n)

    # Calculate (I - DC)^(-1)
    # This represents direct and indirect effects through the food web
    I_minus_DC <- I - DC

    # Check if matrix is invertible
    if (abs(det(I_minus_DC)) < 1e-10) {
      warning("Diet composition matrix is singular or near-singular. MTI calculation may be unstable.")
      # Use pseudo-inverse
      I_minus_DC_inv <- MASS::ginv(I_minus_DC)
    } else {
      I_minus_DC_inv <- solve(I_minus_DC)
    }

    # Calculate MTI matrix
    # MTI = - (I - DC)^(-1) * DC
    MTI <- -I_minus_DC_inv %*% DC

    # Set diagonal to 0 (species doesn't impact itself in this analysis)
    diag(MTI) <- 0

    rownames(MTI) <- colnames(MTI) <- V(net)$name

    return(MTI)

  }, error = function(e) {
    stop(paste("Error calculating Mixed Trophic Impact:", e$message))
  })
}

#' Calculate Keystoneness Index
#'
#' Computes the keystoneness index for each species based on their
#' overall impact on the ecosystem and their relative biomass.
#'
#' @param net An igraph object representing the food web
#' @param info Data frame with 'meanB' column for biomass
#'
#' @return A data frame with columns:
#' \describe{
#'   \item{species}{Species name}
#'   \item{overall_effect}{Total impact on the ecosystem (sum of absolute MTI values)}
#'   \item{relative_biomass}{Biomass relative to total ecosystem biomass}
#'   \item{keystoneness}{Keystoneness index (high values = keystone species)}
#'   \item{keystone_status}{Classification: "Keystone", "Dominant", or "Rare"}
#' }
#'
#' @details
#' The keystoneness index (KS) is calculated as:
#' KS_i = log(1 + OE_i) / log(1 + RB_i)
#'
#' Where:
#' - OE_i = Overall Effect of species i (sum of absolute MTI values)
#' - RB_i = Relative Biomass of species i (as proportion of total biomass)
#'
#' High keystoneness values indicate species with large ecosystem impacts
#' relative to their biomass (classic keystone species).
#'
#' Classification:
#' - Keystone: High impact, low biomass (KS > 1, RB < 0.05)
#' - Dominant: High impact, high biomass (KS > 0, RB >= 0.05)
#' - Rare: Low impact, low biomass (KS <= 1, RB < 0.05)
#'
#' @references
#' Libralato, S., et al. (2006). A method for identifying keystone species in
#' food web models. Ecological Modelling, 195(3-4), 153-171.
calculate_keystoneness <- function(net, info) {
  # Calculate MTI matrix
  MTI <- calculate_mti(net, info)

  # Calculate overall effect (sum of absolute MTI values for each impactor)
  # This represents the total impact a species has on the ecosystem
  overall_effect <- colSums(abs(MTI))

  # Calculate relative biomass
  total_biomass <- sum(info$meanB, na.rm = TRUE)
  relative_biomass <- info$meanB / total_biomass

  # Calculate keystoneness index
  # KS = log(1 + overall_effect) / log(1 + relative_biomass)
  # High KS means high impact relative to biomass
  keystoneness <- log(1 + overall_effect) / log(1 + relative_biomass)

  # Handle infinite or undefined values
  keystoneness[is.infinite(keystoneness)] <- NA
  keystoneness[is.nan(keystoneness)] <- NA

  # Classify species
  keystone_status <- sapply(1:length(keystoneness), function(i) {
    if (is.na(keystoneness[i])) return("Undefined")
    if (keystoneness[i] > 1 && relative_biomass[i] < 0.05) return("Keystone")
    if (keystoneness[i] > 0 && relative_biomass[i] >= 0.05) return("Dominant")
    return("Rare")
  })

  # Create results data frame
  results <- data.frame(
    species = V(net)$name,
    overall_effect = overall_effect,
    relative_biomass = relative_biomass,
    keystoneness = keystoneness,
    keystone_status = keystone_status,
    stringsAsFactors = FALSE
  )

  # Sort by keystoneness (descending)
  results <- results[order(-results$keystoneness), ]

  return(results)
}

# ============================================================================
# UI - BS4DASH DASHBOARD
# ============================================================================

ui <- dashboardPage(
  # ============================================================================
  # HEADER
  # ============================================================================
  header = dashboardHeader(
    title = dashboardBrand(
      title = "EcoNeTool",
      color = "primary",
      href = "https://github.com",
      image = "img/marbefes.png"
    ),
    skin = "light",
    status = "white",
    border = TRUE,
    sidebarIcon = icon("bars"),
    controlbarIcon = icon("info-circle"),
    fixed = FALSE,
    leftUI = tagList(
      h4("Food Web Explorer", style = "margin: 10px; color: #007bff;")
    ),
    rightUI = tagList(
      dropdownMenu(
        type = "messages",
        badgeStatus = "info",
        icon = icon("question-circle"),
        messageItem(
          from = "About",
          message = "Gulf of Riga Food Web (1979-2016)",
          icon = icon("fish"),
          time = "34 taxa"
        ),
        messageItem(
          from = "Data Source",
          message = "Frelat & Kortsch, 2020",
          icon = icon("database"),
          time = "207 links"
        )
      )
    )
  ),

  # ============================================================================
  # SIDEBAR
  # ============================================================================
  sidebar = dashboardSidebar(
    skin = "light",
    status = "primary",
    elevation = 3,
    sidebarMenu(
      id = "sidebar_menu",

      sidebarHeader("Navigation"),

      menuItem(
        text = "Dashboard",
        tabName = "dashboard",
        icon = icon("home")
      ),

      menuItem(
        text = "Data Import",
        tabName = "import",
        icon = icon("upload")
      ),

      menuItem(
        text = "Food Web Network",
        tabName = "network",
        icon = icon("project-diagram")
      ),

      menuItem(
        text = "Topological Metrics",
        tabName = "topological",
        icon = icon("chart-line")
      ),

      menuItem(
        text = "Biomass Analysis",
        tabName = "biomass",
        icon = icon("weight")
      ),

      menuItem(
        text = "Energy Fluxes",
        tabName = "fluxes",
        icon = icon("bolt")
      ),

      menuItem(
        text = "Keystoneness Analysis",
        tabName = "keystoneness",
        icon = icon("key")
      ),

      menuItem(
        text = "Internal Data Editor",
        tabName = "dataeditor",
        icon = icon("table")
      ),

      sidebarHeader("Information"),

      tags$div(
        style = "padding: 15px; font-size: 12px; color: #6c757d;",
        tags$p(tags$strong("EcoNeTool")),
        tags$p("Interactive analysis of marine food web networks."),
        tags$p(
          tags$i(class = "fas fa-fish"), " 34 species", tags$br(),
          tags$i(class = "fas fa-link"), " 207 trophic links", tags$br(),
          tags$i(class = "fas fa-layer-group"), " 5 functional groups"
        ),
        tags$p(style = "margin-top: 10px;", tags$small("Data: Frelat & Kortsch, 2020"))
      )
    )
  ),

  # ============================================================================
  # BODY
  # ============================================================================
  body = dashboardBody(
    tabItems(

      # ========================================================================
      # DASHBOARD TAB
      # ========================================================================
      tabItem(
        tabName = "dashboard",

        fluidRow(
          box(
            title = "Welcome to EcoNeTool",
            status = "primary",
            solidHeader = TRUE,
            width = 12,
            collapsible = FALSE,
            HTML("
              <h4>Food Web Explorer</h4>
              <p>This interactive dashboard allows you to explore and analyze marine food web networks.
              The tool integrates qualitative and quantitative network analysis approaches to understand
              food web structure and dynamics.</p>

              <h5>Current Dataset:</h5>
              <ul>
                <li><strong>Source:</strong> Gulf of Riga food web (Frelat & Kortsch, 2020)</li>
                <li><strong>Period:</strong> 1979-2016 (37 years)</li>
                <li><strong>Taxa:</strong> 34 species across 5 functional groups</li>
                <li><strong>Links:</strong> 207 trophic interactions</li>
              </ul>

              <h5>Features:</h5>
              <ul>
                <li><strong>Data Import:</strong> Upload your own food web data (Excel, CSV, RData)</li>
                <li><strong>Food Web Network:</strong> Interactive visualization of species interactions</li>
                <li><strong>Topological Metrics:</strong> Qualitative indicators (Connectance, Generality, Vulnerability, etc.)</li>
                <li><strong>Biomass Analysis:</strong> Node-weighted metrics accounting for species biomass</li>
                <li><strong>Energy Fluxes:</strong> Metabolic theory-based energy flow calculations</li>
              </ul>

              <h5>Navigation:</h5>
              <p>Use the sidebar menu to navigate through different analysis sections. Start with <strong>Data Import</strong>
              to learn about supported formats or use the default Gulf of Riga dataset.</p>
            ")
          )
        ),

        fluidRow(
          valueBox(
            value = 34,
            subtitle = "Taxa / Species",
            icon = icon("fish"),
            color = "primary",
            width = 3
          ),
          valueBox(
            value = 207,
            subtitle = "Trophic Links",
            icon = icon("link"),
            color = "success",
            width = 3
          ),
          valueBox(
            value = 5,
            subtitle = "Functional Groups",
            icon = icon("layer-group"),
            color = "info",
            width = 3
          ),
          valueBox(
            value = "1979-2016",
            subtitle = "Time Period",
            icon = icon("calendar"),
            color = "warning",
            width = 3
          )
        ),

        fluidRow(
          box(
            title = "Functional Groups",
            status = "info",
            solidHeader = TRUE,
            width = 6,
            HTML("
              <div style='padding: 10px;'>
                <p><span style='color: orange; font-size: 20px;'>●</span> <strong>Benthos</strong> - Bottom-dwelling organisms</p>
                <p><span style='color: darkgrey; font-size: 20px;'>●</span> <strong>Detritus</strong> - Organic matter</p>
                <p><span style='color: blue; font-size: 20px;'>●</span> <strong>Fish</strong> - Fish species</p>
                <p><span style='color: green; font-size: 20px;'>●</span> <strong>Phytoplankton</strong> - Primary producers</p>
                <p><span style='color: cyan; font-size: 20px;'>●</span> <strong>Zooplankton</strong> - Small drifting organisms</p>
              </div>
            ")
          ),
          box(
            title = "Quick Start",
            status = "success",
            solidHeader = TRUE,
            width = 6,
            HTML("
              <div style='padding: 10px;'>
                <ol>
                  <li><strong>Food Web Network:</strong> Explore the interactive network visualization</li>
                  <li><strong>Topological Metrics:</strong> View structural properties of the food web</li>
                  <li><strong>Biomass Analysis:</strong> Examine biomass-weighted metrics</li>
                  <li><strong>Energy Fluxes:</strong> Analyze energy flow patterns</li>
                </ol>
                <p style='margin-top: 15px;'><em>Click on the sidebar menu items to navigate!</em></p>
              </div>
            ")
          )
        )
      ),

      # ========================================================================
      # DATA IMPORT TAB
      # ========================================================================
      tabItem(
        tabName = "import",

        fluidRow(
          box(
            title = "Data Import",
            status = "primary",
            solidHeader = TRUE,
            width = 12,
            HTML("
              <h4>Import Your Own Food Web Data</h4>
              <p>EcoNeTool supports multiple data formats. Choose the import method that best suits your data source.</p>
            ")
          )
        ),

        fluidRow(
          tabBox(
            width = 12,
            id = "import_tabs",

            # TAB 1: General Import (RData/CSV/Excel)
            tabPanel(
              title = "General Import",
              icon = icon("upload"),

              br(),
              fluidRow(
                column(6,
                  box(
                    title = "Upload Your Data",
                    status = "success",
                    solidHeader = TRUE,
                    width = 12,
                    fileInput(
                      "data_file",
                      "Choose File (Excel, CSV, or RData)",
                      accept = c(
                        ".xlsx", ".xls",
                        ".csv",
                        ".Rdata", ".rda"
                      ),
                      multiple = FALSE
                    ),
                    helpText("Maximum file size: 10 MB"),
                    br(),
                    actionButton("load_data", "Load Data", icon = icon("upload"), class = "btn-primary"),
                    hr(),
                    verbatimTextOutput("data_upload_status")
                  )
                ),
                column(6,
                  box(
                    title = "Data Validation",
                    status = "warning",
                    solidHeader = TRUE,
                    width = 12,
                    HTML("
                      <h5>Data Requirements:</h5>
                      <ul>
                        <li>✓ Species names must match between network and info</li>
                        <li>✓ Network must be square (same row/column names)</li>
                        <li>✓ Biomass values must be positive</li>
                        <li>✓ Functional groups should be consistent</li>
                        <li>✓ Losses and efficiencies: 0-1 range</li>
                        <li>✓ At least 3 species recommended</li>
                      </ul>
                      <h5>After Upload:</h5>
                      <p>Once your data is loaded, all analysis tabs will automatically use your uploaded data.</p>
                      <h5>Reset to Default:</h5>
                      <p>Refresh the page to reload the default Gulf of Riga dataset.</p>
                    ")
                  )
                )
              )
            ),

            # TAB 2: ECOPATH Native Database
            tabPanel(
              title = "ECOPATH Native",
              icon = icon("database"),

              br(),
              fluidRow(
                column(6,
                  box(
                    title = "Import ECOPATH Native Database",
                    status = "primary",
                    solidHeader = TRUE,
                    width = 12,
                    HTML("
                      <h5>Import ECOPATH Native Files (.ewemdb, .mdb)</h5>
                      <p>Upload your ECOPATH with Ecosim database file directly.</p>
                      <p style='font-size: 12px;'><em>Example: 'coast 2011-04-10 10.00.ewemdb'</em></p>
                    "),
                    fileInput(
                      "ecopath_native_file",
                      "ECOPATH Database File",
                      accept = c(".ewemdb", ".mdb", ".eiidb", ".accdb"),
                      multiple = FALSE
                    ),
                    actionButton("load_ecopath_native", "Import Native Database", icon = icon("database"), class = "btn-primary"),
                    hr(),
                    verbatimTextOutput("ecopath_native_status")
                  )
                ),
                column(6,
                  box(
                    title = "Native Database Guide",
                    status = "info",
                    solidHeader = TRUE,
                    width = 12,
                    HTML("
                      <h5>Installation Requirements</h5>
                      <p><strong>Linux/Mac:</strong></p>
                      <pre style='background: #f8f9fa; padding: 5px; font-size: 11px;'>sudo apt-get install mdbtools
install.packages('Hmisc')</pre>
                      <p><strong>Windows:</strong> Use ECOPATH CSV/Excel Export tab instead</p>
                      <hr>
                      <h5>Supported Files</h5>
                      <ul style='font-size: 12px;'>
                        <li>.ewemdb - ECOPATH 6.x</li>
                        <li>.mdb - ECOPATH 5.x</li>
                        <li>.eiidb - Alternative format</li>
                      </ul>
                      <p style='font-size: 12px;'>The database contains all model data including Basic Input, Diet Matrix, and parameters.</p>
                    ")
                  )
                )
              )
            ),

            # TAB 3: ECOPATH CSV/Excel Export
            tabPanel(
              title = "ECOPATH CSV/Excel",
              icon = icon("file-excel"),

              br(),
              fluidRow(
                column(6,
                  box(
                    title = "Import ECOPATH CSV/Excel Exports",
                    status = "success",
                    solidHeader = TRUE,
                    width = 12,
                    HTML("
                      <h5>Alternative: Import Exported Files</h5>
                      <p>Upload CSV/Excel exports from ECOPATH. <strong>Recommended for Windows users.</strong></p>
                    "),
                    fileInput(
                      "ecopath_file",
                      "1. Basic Estimates File (.xlsx, .csv)",
                      accept = c(".xlsx", ".xls", ".csv"),
                      multiple = FALSE
                    ),
                    fileInput(
                      "ecopath_diet_file",
                      "2. Diet Composition Matrix (.xlsx, .csv)",
                      accept = c(".xlsx", ".xls", ".csv"),
                      multiple = FALSE
                    ),
                    actionButton("load_ecopath", "Import Exported Files", icon = icon("upload"), class = "btn-primary"),
                    hr(),
                    verbatimTextOutput("ecopath_upload_status")
                  )
                ),
                column(6,
                  box(
                    title = "ECOPATH Export Guide",
                    status = "info",
                    solidHeader = TRUE,
                    width = 12,
                    HTML("
                      <h5>Required Files from ECOPATH</h5>
                      <h6>1. Basic Estimates</h6>
                      <p><strong>Export:</strong> File → Export → Basic Estimates</p>
                      <p>Required columns:</p>
                      <ul style='font-size: 12px;'>
                        <li><strong>Group name</strong> - Species/group name</li>
                        <li><strong>Biomass</strong> - Biomass (t/km²)</li>
                        <li><strong>P/B</strong> - Production/Biomass ratio</li>
                        <li><strong>Q/B</strong> - Consumption/Biomass ratio</li>
                      </ul>
                      <h6>2. Diet Composition</h6>
                      <p><strong>Export:</strong> File → Export → Diet Composition</p>
                      <p>Matrix format:</p>
                      <ul style='font-size: 12px;'>
                        <li>Rows = Prey species</li>
                        <li>Columns = Predator species</li>
                        <li>Values = Diet proportion (0-1)</li>
                      </ul>
                    ")
                  )
                )
              )
            ),

            # TAB 4: Format Guide
            tabPanel(
              title = "Format Guide",
              icon = icon("book"),

              br(),
              box(
                title = "Supported File Formats",
                status = "info",
            solidHeader = TRUE,
            width = 12,
            collapsible = TRUE,
            HTML("
              <h5>1. Excel Format (.xlsx, .xls)</h5>
              <p>Excel files should contain the following sheets:</p>

              <h6><strong>Sheet 1: Network (Adjacency Matrix)</strong></h6>
              <p>A square matrix where rows and columns represent species:</p>
              <table class='table table-sm table-bordered' style='width: auto; margin: 10px 0;'>
                <thead><tr><th></th><th>Species_A</th><th>Species_B</th><th>Species_C</th></tr></thead>
                <tbody>
                  <tr><td><strong>Species_A</strong></td><td>0</td><td>1</td><td>0</td></tr>
                  <tr><td><strong>Species_B</strong></td><td>0</td><td>0</td><td>1</td></tr>
                  <tr><td><strong>Species_C</strong></td><td>0</td><td>0</td><td>0</td></tr>
                </tbody>
              </table>
              <p><em>Value = 1 means Species A eats Species B (row → column)</em></p>

              <h6><strong>Sheet 2: Species_Info</strong></h6>
              <p>Species attributes (one row per species):</p>
              <table class='table table-sm table-bordered' style='width: auto; margin: 10px 0;'>
                <thead><tr><th>species</th><th>fg</th><th>meanB</th><th>losses</th><th>efficiencies</th></tr></thead>
                <tbody>
                  <tr><td>Species_A</td><td>Fish</td><td>1250.5</td><td>0.12</td><td>0.85</td></tr>
                  <tr><td>Species_B</td><td>Zooplankton</td><td>850.2</td><td>0.08</td><td>0.75</td></tr>
                  <tr><td>Species_C</td><td>Phytoplankton</td><td>2100.0</td><td>0.05</td><td>0.40</td></tr>
                </tbody>
              </table>

              <h5>Required Columns:</h5>
              <ul>
                <li><strong>species:</strong> Species name (must match network row/column names)</li>
                <li><strong>fg:</strong> Functional group (e.g., Fish, Benthos, Phytoplankton, Zooplankton, Detritus)</li>
                <li><strong>meanB:</strong> Mean biomass (g/km² or your preferred unit)</li>
                <li><strong>losses:</strong> Metabolic losses (J/sec) for flux calculations</li>
                <li><strong>efficiencies:</strong> Assimilation efficiencies (0-1) for flux calculations</li>
              </ul>

              <h5>Optional Columns:</h5>
              <ul>
                <li><strong>bodymasses:</strong> Average body mass (g)</li>
                <li><strong>taxon:</strong> Taxonomic classification</li>
                <li><strong>nbY:</strong> Number of years recorded</li>
              </ul>

              <hr>

              <h5>2. CSV Format (.csv)</h5>
              <p>Two CSV files required:</p>

              <h6><strong>File 1: network.csv (Adjacency Matrix)</strong></h6>
              <pre style='background: #f8f9fa; padding: 10px; border-radius: 5px;'>
species,Species_A,Species_B,Species_C
Species_A,0,1,0
Species_B,0,0,1
Species_C,0,0,0</pre>

              <h6><strong>File 2: species_info.csv</strong></h6>
              <pre style='background: #f8f9fa; padding: 10px; border-radius: 5px;'>
species,fg,meanB,losses,efficiencies
Species_A,Fish,1250.5,0.12,0.85
Species_B,Zooplankton,850.2,0.08,0.75
Species_C,Phytoplankton,2100.0,0.05,0.40</pre>

              <hr>

              <h5>3. RData Format (.Rdata, .rda)</h5>
              <p>R workspace containing two objects:</p>
              <ul>
                <li><strong>net:</strong> igraph object with food web network</li>
                <li><strong>info:</strong> data.frame with species information (columns as above)</li>
              </ul>

              <p><strong>Example R code to create:</strong></p>
              <pre style='background: #f8f9fa; padding: 10px; border-radius: 5px;'>
library(igraph)

# Create adjacency matrix
adj_matrix <- matrix(c(0,1,0, 0,0,1, 0,0,0), nrow=3, byrow=TRUE)
rownames(adj_matrix) <- colnames(adj_matrix) <- c('Species_A', 'Species_B', 'Species_C')

# Create network
net <- graph_from_adjacency_matrix(adj_matrix, mode='directed')

# Create species info
info <- data.frame(
  species = c('Species_A', 'Species_B', 'Species_C'),
  fg = factor(c('Fish', 'Zooplankton', 'Phytoplankton')),
  meanB = c(1250.5, 850.2, 2100.0),
  losses = c(0.12, 0.08, 0.05),
  efficiencies = c(0.85, 0.75, 0.40)
)

# Save
save(net, info, file='my_foodweb.Rdata')</pre>
            ")
              )
            ),

            # TAB 5: Example Datasets
            tabPanel(
              title = "Example Datasets",
              icon = icon("download"),

              br(),
              box(
                title = "Example Datasets",
            status = "info",
            solidHeader = TRUE,
            width = 12,
            collapsible = TRUE,
            collapsed = FALSE,

            fluidRow(
              column(4,
                h5("1. Simple 3-Species Chain"),
                p("Perfect for testing - basic linear food chain"),
                tags$ul(
                  tags$li("3 species (Phytoplankton → Zooplankton → Fish)"),
                  tags$li("2 trophic links"),
                  tags$li("Ideal for learning the format")
                ),
                downloadButton("download_simple_rdata", "Download RData", class = "btn-sm btn-primary"),
                downloadButton("download_simple_csv_net", "Network CSV", class = "btn-sm btn-secondary"),
                downloadButton("download_simple_csv_info", "Info CSV", class = "btn-sm btn-secondary")
              ),
              column(4,
                h5("2. Caribbean Reef"),
                p("Realistic tropical reef food web"),
                tags$ul(
                  tags$li("10 species across 4 functional groups"),
                  tags$li("18 trophic interactions"),
                  tags$li("Multiple trophic levels")
                ),
                downloadButton("download_reef_rdata", "Download RData", class = "btn-sm btn-primary"),
                downloadButton("download_reef_csv_net", "Network CSV", class = "btn-sm btn-secondary"),
                downloadButton("download_reef_csv_info", "Info CSV", class = "btn-sm btn-secondary")
              ),
              column(4,
                h5("3. Empty Template"),
                p("Start from scratch with proper structure"),
                tags$ul(
                  tags$li("3 placeholder species"),
                  tags$li("Correct file format"),
                  tags$li("Modify for your own data")
                ),
                downloadButton("download_template_rdata", "Download RData", class = "btn-sm btn-primary"),
                downloadButton("download_template_csv_net", "Network CSV", class = "btn-sm btn-secondary"),
                downloadButton("download_template_csv_info", "Info CSV", class = "btn-sm btn-secondary")
              )
            ),

            hr(),

            HTML("
              <h5>How to Use Example Files:</h5>
              <ol>
                <li><strong>Download</strong> one of the example RData files above</li>
                <li><strong>Upload</strong> it using the file input above</li>
                <li><strong>Click</strong> 'Load Data' button</li>
                <li><strong>Explore</strong> the food web in other tabs</li>
              </ol>

              <h5>File Formats:</h5>
              <p><strong>RData:</strong> Ready to upload directly to EcoNeTool<br>
              <strong>CSV files:</strong> Open in Excel to view/modify structure (2 files needed: network + info)</p>

              <p style='margin-top: 15px;'><em>See the examples/README.md file for detailed format documentation.</em></p>
            ")
              )
            )
          )
        )
      ),

      # ========================================================================
      # FOOD WEB NETWORK TAB
      # ========================================================================
      tabItem(
        tabName = "network",

        fluidRow(
          tabBox(
            width = 12,
            id = "network_tabs",

            # TAB 1: Interactive Network
            tabPanel(
              title = "Interactive Network",
              icon = icon("project-diagram"),

              br(),
              box(
                title = "Interactive Food Web Network",
                status = "primary",
                solidHeader = TRUE,
                width = 12,
                collapsible = TRUE,
                maximizable = TRUE,
                visNetworkOutput("foodweb_visnet", height = "600px")
              ),

              fluidRow(
                column(6,
                  box(
                    title = "Basal Species",
                    status = "success",
                    solidHeader = TRUE,
                    width = 12,
                    icon = icon("seedling"),
                    verbatimTextOutput("basal_species")
                  )
                ),
                column(6,
                  box(
                    title = "Top Predators",
                    status = "danger",
                    solidHeader = TRUE,
                    width = 12,
                    icon = icon("crown"),
                    verbatimTextOutput("top_predators")
                  )
                )
              )
            ),

            # TAB 2: Adjacency Matrix
            tabPanel(
              title = "Adjacency Matrix",
              icon = icon("th"),

              br(),
              box(
                title = "Adjacency Matrix Heatmap",
                status = "info",
                solidHeader = TRUE,
                width = 12,
                collapsible = TRUE,
                maximizable = TRUE,
                plotOutput("adjacency_heatmap", height = "600px")
              )
            )
          )
        )
      ),

      # ========================================================================
      # TOPOLOGICAL INDICATORS TAB
      # ========================================================================
      tabItem(
        tabName = "topological",

        fluidRow(
          box(
            title = "Topological Indicators (Qualitative Metrics)",
            status = "primary",
            solidHeader = TRUE,
            width = 12,
            HTML("
              <p>These metrics describe the structural properties of the food web network without
              considering node weights (biomass).</p>
              <ul>
                <li><strong>S:</strong> Species richness (number of taxa)</li>
                <li><strong>C:</strong> Connectance (proportion of realized links)</li>
                <li><strong>G:</strong> Generality (mean number of prey per predator)</li>
                <li><strong>V:</strong> Vulnerability (mean number of predators per prey)</li>
                <li><strong>ShortPath:</strong> Mean shortest path length</li>
                <li><strong>TL:</strong> Mean trophic level</li>
                <li><strong>Omni:</strong> Omnivory index (mean SD of prey trophic levels)</li>
              </ul>
            ")
          )
        ),

        fluidRow(
          box(
            title = "Calculated Metrics",
            status = "info",
            solidHeader = TRUE,
            width = 12,
            verbatimTextOutput("topo_indicators")
          )
        )
      ),

      # ========================================================================
      # BIOMASS ANALYSIS TAB
      # ========================================================================
      tabItem(
        tabName = "biomass",

        fluidRow(
          box(
            title = "Biomass Distribution by Functional Group",
            status = "primary",
            solidHeader = TRUE,
            width = 6,
            collapsible = TRUE,
            plotOutput("biomass_boxplot", height = "400px")
          ),
          box(
            title = "Biomass Percentage by Functional Group",
            status = "success",
            solidHeader = TRUE,
            width = 6,
            collapsible = TRUE,
            plotOutput("biomass_barplot", height = "400px")
          )
        ),

        fluidRow(
          box(
            title = "Food Web with Biomass-Scaled Nodes",
            status = "info",
            solidHeader = TRUE,
            width = 12,
            collapsible = TRUE,
            maximizable = TRUE,
            plotOutput("foodweb_biomass_plot", height = "600px")
          )
        ),

        fluidRow(
          box(
            title = "Node-weighted Indicators (Quantitative Metrics)",
            status = "warning",
            solidHeader = TRUE,
            width = 12,
            HTML("
              <p>These metrics account for the relative importance of species based on their biomass.</p>
              <ul>
                <li><strong>nwC:</strong> Node-weighted connectance</li>
                <li><strong>nwG:</strong> Node-weighted generality</li>
                <li><strong>nwV:</strong> Node-weighted vulnerability</li>
                <li><strong>nwTL:</strong> Node-weighted mean trophic level</li>
              </ul>
            "),
            verbatimTextOutput("node_weighted_indicators")
          )
        )
      ),

      # ========================================================================
      # ENERGY FLUXES TAB
      # ========================================================================
      tabItem(
        tabName = "fluxes",

        fluidRow(
          box(
            title = "Energy Flux Analysis",
            status = "primary",
            solidHeader = TRUE,
            width = 12,
            HTML("
              <p>Energy fluxes are calculated using metabolic theory of ecology. Fluxes represent
              biomass flow between species based on allometric scaling and temperature-adjusted
              metabolic rates (T=3.5°C, Gulf of Riga spring conditions).</p>
              <p><strong>Units:</strong> kJ/day/km²</p>
              <p><strong>Note:</strong> Flux values span many orders of magnitude (10<sup>-10</sup> to 10<sup>-1</sup>),
              reflecting the wide range of interaction strengths in the food web.</p>
            ")
          )
        ),

        fluidRow(
          tabBox(
            width = 12,
            id = "fluxes_tabs",

            # TAB 1: Flux Network
            tabPanel(
              title = "Flux-weighted Network",
              icon = icon("bolt"),

              br(),
              box(
                title = "Flux-weighted Network",
                status = "warning",
                solidHeader = TRUE,
                width = 12,
                collapsible = TRUE,
                maximizable = TRUE,
                HTML("<p>Edge widths proportional to energy flux magnitude. Hover over edges to see exact values.</p>"),
                visNetworkOutput("flux_network_plot", height = "600px")
              )
            ),

            # TAB 2: Flux Heatmap
            tabPanel(
              title = "Flux Matrix Heatmap",
              icon = icon("fire"),

              br(),
              box(
                title = "Flux Matrix Heatmap (Log-transformed)",
                status = "danger",
                solidHeader = TRUE,
                width = 12,
                collapsible = TRUE,
                maximizable = TRUE,
                HTML("<p>Color intensity shows log-transformed flux values. Darker colors indicate stronger energy flows.</p>"),
                plotOutput("flux_heatmap", height = "500px")
              )
            ),

            # TAB 3: Flux Indicators
            tabPanel(
              title = "Flux Indicators",
              icon = icon("chart-bar"),

              br(),
              box(
                title = "Link-weighted Flux Indicators",
                status = "info",
                solidHeader = TRUE,
                width = 12,
                HTML("
                  <p>Shannon diversity indices calculated from energy flux distributions.</p>
                  <ul>
                    <li><strong>Flux diversity:</strong> Distribution evenness of energy flows</li>
                    <li><strong>Effective number of fluxes:</strong> Equivalent number of equally strong flows</li>
                  </ul>
                "),
                verbatimTextOutput("flux_indicators")
              )
            )
          )
        )
      ),

      # ========================================================================
      # KEYSTONENESS ANALYSIS TAB
      # ========================================================================
      tabItem(
        tabName = "keystoneness",

        fluidRow(
          box(
            title = "Keystoneness Analysis (ECOPATH Method)",
            status = "primary",
            solidHeader = TRUE,
            width = 12,
            HTML("
              <h4>Identifying Keystone Species</h4>
              <p>Keystoneness analysis identifies species with disproportionately large effects on ecosystem
              structure and function relative to their biomass. This analysis follows the ECOPATH methodology
              using Mixed Trophic Impact (MTI) calculations.</p>

              <h5>Key Concepts:</h5>
              <ul>
                <li><strong>Mixed Trophic Impact (MTI):</strong> Measures direct and indirect effects of one species on all others</li>
                <li><strong>Overall Effect:</strong> Sum of absolute MTI values (total ecosystem impact)</li>
                <li><strong>Keystoneness Index:</strong> Ratio of impact to biomass (high values = keystone species)</li>
              </ul>

              <h5>Species Classifications:</h5>
              <ul>
                <li><strong>Keystone:</strong> High impact, low biomass (KS > 1, biomass < 5% of total)</li>
                <li><strong>Dominant:</strong> High impact, high biomass (KS > 0, biomass ≥ 5% of total)</li>
                <li><strong>Rare:</strong> Low impact, low biomass</li>
              </ul>

              <p><em>Reference: Libralato et al. (2006). Ecological Modelling, 195(3-4), 153-171.</em></p>
            ")
          )
        ),

        fluidRow(
          box(
            title = "Keystoneness Index Rankings",
            status = "success",
            solidHeader = TRUE,
            width = 6,
            icon = icon("ranking-star"),
            DT::dataTableOutput("keystoneness_table"),
            helpText("Species ranked by keystoneness index (highest to lowest)")
          ),
          box(
            title = "Keystoneness vs Biomass Plot",
            status = "info",
            solidHeader = TRUE,
            width = 6,
            collapsible = TRUE,
            plotOutput("keystoneness_plot", height = "400px"),
            helpText("Keystone species appear in upper-left (high impact, low biomass)")
          )
        ),

        fluidRow(
          box(
            title = "Mixed Trophic Impact (MTI) Heatmap",
            status = "warning",
            solidHeader = TRUE,
            width = 12,
            collapsible = TRUE,
            maximizable = TRUE,
            plotOutput("mti_heatmap", height = "600px"),
            HTML("
              <p><strong>How to read:</strong></p>
              <ul style='font-size: 12px;'>
                <li>Rows = Impacted species</li>
                <li>Columns = Impacting species (impactor)</li>
                <li>Red = Negative impact (impactor decreases impacted)</li>
                <li>Blue = Positive impact (impactor increases impacted)</li>
                <li>Values represent net effect through direct and indirect pathways</li>
              </ul>
            ")
          )
        ),

        fluidRow(
          box(
            title = "Top Keystone Species Details",
            status = "danger",
            solidHeader = TRUE,
            width = 12,
            collapsible = TRUE,
            verbatimTextOutput("keystone_summary")
          )
        )
      ),

      # ========================================================================
      # INTERNAL DATA EDITOR TAB
      # ========================================================================
      tabItem(
        tabName = "dataeditor",

        fluidRow(
          box(
            title = "Internal Data Editor",
            status = "primary",
            solidHeader = TRUE,
            width = 12,
            HTML("
              <h4>Edit Internal Datasheets</h4>
              <p>This tab allows you to directly edit the two main internal datasheets:</p>
              <ul>
                <li><strong>Species Information:</strong> Species attributes including biomass, functional groups, body masses, and metabolic parameters</li>
                <li><strong>Network Adjacency Matrix:</strong> The food web structure showing who eats whom</li>
              </ul>
              <p><strong>Note:</strong> Changes are applied in real-time. Use the 'Update Network' button to refresh all visualizations after editing.</p>
            ")
          )
        ),

        fluidRow(
          tabBox(
            width = 12,
            id = "dataeditor_tabs",

            tabPanel(
              title = "Species Information Table",
              icon = icon("table"),
              HTML("
                <p>Edit species attributes. Double-click cells to edit values.</p>
                <p><em>Required columns: meanB, fg, bodymasses, met.types, efficiencies</em></p>
                <details style='margin-bottom: 10px;'>
                  <summary style='cursor: pointer; color: #337ab7;'><strong>Column Descriptions (click to expand)</strong></summary>
                  <ul style='font-size: 12px; margin-top: 5px;'>
                    <li><strong>species:</strong> Species name or identifier</li>
                    <li><strong>meanB:</strong> Mean biomass of the species (g/km²)</li>
                    <li><strong>fg:</strong> Functional group (Fish, Benthos, Phytoplankton, Zooplankton, Detritus)</li>
                    <li><strong>bodymasses:</strong> Average body mass of individual organism (grams)</li>
                    <li><strong>met.types:</strong> Metabolic type (invertebrates, ectotherm vertebrates, Other)</li>
                    <li><strong>efficiencies:</strong> Assimilation efficiency (0-1, proportion of consumed energy assimilated)</li>
                    <li><strong>taxon:</strong> Taxonomic classification</li>
                    <li><strong>nbY:</strong> Number of years recorded in the dataset</li>
                    <li><strong>losses:</strong> Metabolic losses (J/sec) calculated from body mass and temperature</li>
                    <li><strong>org.type:</strong> Organism type classification</li>
                  </ul>
                </details>
              "),
              DT::dataTableOutput("species_info_table"),
              br(),
              actionButton("save_species_info", "Save Species Info", icon = icon("save"), class = "btn-success"),
              verbatimTextOutput("species_info_status")
            ),

            tabPanel(
              title = "Network Adjacency Matrix",
              icon = icon("project-diagram"),
              HTML("
                <p>Edit the food web structure. Values should be 0 (no interaction) or 1 (predator eats prey).</p>
                <p><strong>Tip:</strong> Hover over species names (underlined) to see their role in the food web.</p>
                <p><em>Rows = Predators, Columns = Prey. Value of 1 in row i, column j means species i eats species j.</em></p>
              "),
              DT::dataTableOutput("network_matrix_table"),
              br(),
              actionButton("save_network_matrix", "Save Network Matrix", icon = icon("save"), class = "btn-success"),
              actionButton("update_network", "Update Network from Matrix", icon = icon("refresh"), class = "btn-primary"),
              verbatimTextOutput("network_matrix_status")
            )
          )
        )
      )
    )
  ),

  # ============================================================================
  # CONTROLBAR (optional - for additional info/settings)
  # ============================================================================
  controlbar = dashboardControlbar(
    skin = "light",
    pinned = FALSE,
    overlay = TRUE,
    controlbarMenu(
      id = "controlbar_menu",
      controlbarItem(
        title = "Information",
        HTML("
          <div style='padding: 15px;'>
            <h5>EcoNeTool</h5>
            <p><strong>Version:</strong> 2.1</p>
            <p><strong>License:</strong> GPL-3.0</p>

            <h5>About</h5>
            <p>Generic food web analysis tool supporting custom data import in multiple formats (Excel, CSV, RData).</p>

            <h5>Default Dataset</h5>
            <p><strong>Gulf of Riga Food Web</strong><br>
            Frelat, R., & Kortsch, S. (2020).<br>
            34 species, 207 links<br>
            Period: 1979-2016</p>

            <h5>Data Import</h5>
            <p>Upload your own food web data using the <strong>Data Import</strong> tab. Supported formats:</p>
            <ul style='font-size: 12px; margin-left: -15px;'>
              <li>Excel (.xlsx, .xls)</li>
              <li>CSV files</li>
              <li>RData (.Rdata, .rda)</li>
            </ul>

            <h5>Color Scheme</h5>
            <p><strong>Default Functional Groups:</strong><br>
            <span style='color: orange;'>●</span> Benthos<br>
            <span style='color: darkgrey;'>●</span> Detritus<br>
            <span style='color: blue;'>●</span> Fish<br>
            <span style='color: green;'>●</span> Phytoplankton<br>
            <span style='color: cyan;'>●</span> Zooplankton</p>

            <h5>References</h5>
            <p style='font-size: 11px;'>
            Williams & Martinez (2004). Limits to trophic levels. Proc. R. Soc. B.<br><br>
            Olivier et al. (2019). Temporal variability. Ecography.<br><br>
            Brown et al. (2004). Metabolic theory of ecology. Ecology.
            </p>
          </div>
        ")
      )
    )
  ),

  # Dashboard footer
  footer = dashboardFooter(
    left = tagList(
      "EcoNeTool - Food Web Explorer | ",
      tags$a(href = "https://github.com/razinkele/EcoNeTool", icon("github"), " GitHub", target = "_blank")
    ),
    right = "Powered by bs4Dash & Shiny"
  ),

  # Dashboard options
  title = "EcoNeTool - Food Web Explorer",
  skin = "light",
  freshTheme = NULL,
  help = NULL,
  dark = NULL,
  scrollToTop = TRUE
)

# ============================================================================
# SERVER LOGIC
# ============================================================================

server <- function(input, output, session) {
  # Assign colors to functional groups
  info$colfg <- COLOR_SCHEME[as.numeric(info$fg)]

  # ============================================================================
  # ECOPATH PARSER FUNCTION
  # ============================================================================

  #' Parse ECOPATH data and convert to EcoNeTool format
  #'
  #' @param basic_est_file Path to Basic Estimates file (Excel or CSV)
  #' @param diet_file Path to Diet Composition file (Excel or CSV)
  #' @return List with 'net' (igraph object) and 'info' (data.frame)
  parse_ecopath_data <- function(basic_est_file, diet_file) {
    # Read Basic Estimates file
    basic_ext <- tools::file_ext(basic_est_file)
    if (basic_ext %in% c("xlsx", "xls")) {
      if (!requireNamespace("readxl", quietly = TRUE)) {
        stop("Package 'readxl' required for Excel files. Install with: install.packages('readxl')")
      }
      basic_data <- readxl::read_excel(basic_est_file)
    } else if (basic_ext == "csv") {
      basic_data <- read.csv(basic_est_file, stringsAsFactors = FALSE)
    } else {
      stop("Unsupported file format for Basic Estimates")
    }

    # Read Diet Composition file
    diet_ext <- tools::file_ext(diet_file)
    if (diet_ext %in% c("xlsx", "xls")) {
      if (!requireNamespace("readxl", quietly = TRUE)) {
        stop("Package 'readxl' required for Excel files. Install with: install.packages('readxl')")
      }
      diet_data <- readxl::read_excel(diet_file)
    } else if (diet_ext == "csv") {
      diet_data <- read.csv(diet_file, stringsAsFactors = FALSE, check.names = FALSE)
    } else {
      stop("Unsupported file format for Diet Composition")
    }

    # Clean column names (handle variations in ECOPATH export formats)
    basic_colnames <- tolower(colnames(basic_data))
    colnames(basic_data) <- basic_colnames

    # Find key columns (flexible matching)
    group_col <- which(grepl("group.*name|^name$|^group$", basic_colnames))[1]
    biomass_col <- which(grepl("biomass|^b$", basic_colnames))[1]
    pb_col <- which(grepl("p/b|pb|production", basic_colnames))[1]
    qb_col <- which(grepl("q/b|qb|consumption", basic_colnames))[1]

    if (is.na(group_col) || is.na(biomass_col)) {
      stop("Could not find required columns in Basic Estimates file. Need: Group name, Biomass")
    }

    # Extract species names and biomass
    species_names <- as.character(basic_data[[group_col]])
    species_names <- species_names[!is.na(species_names) & species_names != ""]

    # Remove any summary rows (like "Sum", "Total", etc.)
    valid_rows <- !grepl("^sum$|^total$|^import$|^export$|^detritus$",
                         tolower(species_names))
    species_names <- species_names[valid_rows]
    basic_data <- basic_data[valid_rows, ]

    biomass_values <- as.numeric(basic_data[[biomass_col]])

    # Get P/B and Q/B if available
    pb_values <- if (!is.na(pb_col)) as.numeric(basic_data[[pb_col]]) else rep(0.5, length(species_names))
    qb_values <- if (!is.na(qb_col)) as.numeric(basic_data[[qb_col]]) else rep(1.5, length(species_names))

    # Process Diet Composition matrix
    # First column is prey names, rest are predators
    diet_matrix <- as.matrix(diet_data[, -1])
    rownames(diet_matrix) <- as.character(diet_data[[1]])

    # Match species names between basic and diet files
    common_species <- intersect(species_names, rownames(diet_matrix))
    if (length(common_species) < 2) {
      stop("Species names in Basic Estimates and Diet Composition do not match sufficiently")
    }

    # Filter to common species only
    species_idx <- match(common_species, species_names)
    basic_data <- basic_data[species_idx, ]
    species_names <- common_species
    biomass_values <- biomass_values[species_idx]
    pb_values <- pb_values[species_idx]
    qb_values <- qb_values[species_idx]

    # Subset and reorder diet matrix
    diet_matrix <- diet_matrix[common_species, common_species, drop = FALSE]

    # Convert diet proportions to binary adjacency matrix
    # In ECOPATH: columns are predators, rows are prey
    # In our format: rows are predators, columns are prey
    # So we need to transpose
    adjacency_matrix <- t(diet_matrix > 0) * 1

    # Create igraph network
    net <- graph_from_adjacency_matrix(adjacency_matrix, mode = "directed")

    # Assign functional groups based on species characteristics
    # Simple heuristic: use P/B ratio and position in food web
    assign_functional_group <- function(sp_name, pb, indegree, outdegree) {
      sp_lower <- tolower(sp_name)
      if (grepl("phyto|algae|plant|diatom", sp_lower)) return("Phytoplankton")
      if (grepl("zoo|copepod|cladocer|rotifer", sp_lower)) return("Zooplankton")
      if (grepl("fish|cod|herring|sprat|flounder", sp_lower)) return("Fish")
      if (grepl("benthos|benthic|mussel|clam|worm|shrimp", sp_lower)) return("Benthos")
      if (grepl("detritus|det\\.|debris", sp_lower)) return("Detritus")

      # Heuristic based on network position
      if (indegree == 0 && pb > 1) return("Phytoplankton")
      if (indegree > 0 && outdegree == 0) return("Fish")
      if (indegree > 0 && outdegree > 0) return("Benthos")

      return("Fish")  # Default
    }

    # Calculate degrees for functional group assignment
    indegrees <- degree(net, mode = "in")
    outdegrees <- degree(net, mode = "out")

    functional_groups <- sapply(1:length(species_names), function(i) {
      assign_functional_group(species_names[i], pb_values[i], indegrees[i], outdegrees[i])
    })

    # Estimate body masses (rough heuristic based on functional group)
    estimate_body_mass <- function(fg) {
      # Very rough estimates in grams
      if (fg == "Phytoplankton") return(0.00001)
      if (fg == "Zooplankton") return(0.001)
      if (fg == "Benthos") return(1.0)
      if (fg == "Fish") return(100.0)
      if (fg == "Detritus") return(0.0001)
      return(1.0)
    }

    body_masses <- sapply(functional_groups, estimate_body_mass)

    # Assign metabolic types
    met_types <- sapply(functional_groups, function(fg) {
      if (fg %in% c("Fish")) return("ectotherm vertebrates")
      return("invertebrates")
    })

    # Calculate efficiencies (based on functional group)
    efficiencies <- sapply(functional_groups, function(fg) {
      if (fg == "Phytoplankton") return(0.4)
      if (fg == "Zooplankton") return(0.75)
      if (fg == "Benthos") return(0.7)
      if (fg == "Fish") return(0.85)
      if (fg == "Detritus") return(0.2)
      return(0.7)
    })

    # Create info data frame
    info <- data.frame(
      meanB = biomass_values,
      fg = factor(functional_groups, levels = c("Benthos", "Detritus", "Fish", "Phytoplankton", "Zooplankton")),
      bodymasses = body_masses,
      met.types = met_types,
      efficiencies = efficiencies,
      PB = pb_values,
      QB = qb_values,
      row.names = species_names,
      stringsAsFactors = FALSE
    )

    return(list(net = net, info = info))
  }

  #' Parse ECOPATH native database file (.ewemdb, .mdb)
  #'
  #' Reads ECOPATH with Ecosim native database files using mdbtools
  #' @param db_file Path to ECOPATH database file
  #' @return List with 'net' (igraph object) and 'info' (data.frame)
  parse_ecopath_native <- function(db_file) {
    # Check if file exists
    if (!file.exists(db_file)) {
      stop("Database file not found: ", db_file)
    }

    # Try using Hmisc package to read MDB file
    if (!requireNamespace("Hmisc", quietly = TRUE)) {
      stop("Package 'Hmisc' required for reading ECOPATH databases.\nInstall with: install.packages('Hmisc')")
    }

    tryCatch({
      # List tables in the database
      # ECOPATH databases typically contain tables like:
      # - EcopathGroup (basic input data)
      # - EcopathDietComp (diet composition)
      # - EcopathGroupInput (additional parameters)

      # Try to read using mdb.get from Hmisc
      # This requires mdbtools to be installed on Linux/Mac
      tables <- tryCatch({
        Hmisc::mdb.get(db_file, tables = TRUE)
      }, error = function(e) {
        # Check if it's an mdb-tables error
        if (grepl("mdb-tables|mdbtools|not found", e$message, ignore.case = TRUE)) {
          stop("Error parsing ECOPATH database: Could not read database. Ensure mdbtools is installed (Linux: sudo apt-get install mdbtools). Error: '", e$message, "'")
        } else {
          stop("Error parsing ECOPATH database: ", e$message)
        }
      })

      # Read the main ECOPATH tables
      # Try different common table names
      group_table_names <- c("EcopathGroup", "stanzaEcopathGroup", "Group", "Groups", "BasicInput")
      diet_table_names <- c("EcopathDietComp", "DietComposition", "Diet")

      group_table <- NULL
      diet_table <- NULL

      # Find group table
      for (tname in group_table_names) {
        if (tname %in% tables) {
          group_table <- Hmisc::mdb.get(db_file, tables = tname)
          break
        }
      }

      # Find diet table
      for (tname in diet_table_names) {
        if (tname %in% tables) {
          diet_table <- Hmisc::mdb.get(db_file, tables = tname)
          break
        }
      }

      if (is.null(group_table)) {
        stop(paste("Could not find group/basic input table. Available tables:", paste(tables, collapse=", ")))
      }

      if (is.null(diet_table)) {
        stop(paste("Could not find diet composition table. Available tables:", paste(tables, collapse=", ")))
      }

      # Extract species/group information
      # ECOPATH column names may vary, so we try different common names
      col_names <- tolower(colnames(group_table))

      # Find group name column
      name_col <- which(grepl("group.*name|^name$|groupname", col_names))[1]
      if (is.na(name_col)) name_col <- 1  # Default to first column

      # Find biomass column
      biomass_col <- which(grepl("^biomass$|^b$|trophic|habitat", col_names))[1]

      # Find P/B column
      pb_col <- which(grepl("p/b|pb|production", col_names))[1]

      # Find Q/B column
      qb_col <- which(grepl("q/b|qb|consumption", col_names))[1]

      # Extract data
      species_names <- as.character(group_table[[name_col]])
      biomass_values <- if (!is.na(biomass_col)) as.numeric(group_table[[biomass_col]]) else rep(1, length(species_names))
      pb_values <- if (!is.na(pb_col)) as.numeric(group_table[[pb_col]]) else rep(0.5, length(species_names))
      qb_values <- if (!is.na(qb_col)) as.numeric(group_table[[qb_col]]) else rep(1.5, length(species_names))

      # Remove NA, empty, or "Import" and "Export" groups (common in ECOPATH)
      valid_idx <- !is.na(species_names) & species_names != "" &
                   !grepl("^import$|^export$|^fleet", tolower(species_names))

      species_names <- species_names[valid_idx]
      biomass_values <- biomass_values[valid_idx]
      pb_values <- pb_values[valid_idx]
      qb_values <- qb_values[valid_idx]

      n_species <- length(species_names)

      # Process diet composition
      # ECOPATH diet tables usually have: Predator, Prey, DietComp (proportion)
      diet_cols <- tolower(colnames(diet_table))

      pred_col <- which(grepl("predator|consumer", diet_cols))[1]
      prey_col <- which(grepl("prey|resource", diet_cols))[1]
      diet_col <- which(grepl("diet|proportion|comp", diet_cols))[1]

      if (is.na(pred_col) || is.na(prey_col) || is.na(diet_col)) {
        stop("Could not identify predator, prey, and diet columns in diet table")
      }

      # Create diet matrix
      diet_matrix <- matrix(0, nrow = n_species, ncol = n_species)
      rownames(diet_matrix) <- colnames(diet_matrix) <- species_names

      # Fill diet matrix
      for (i in 1:nrow(diet_table)) {
        pred_name <- as.character(diet_table[[pred_col]][i])
        prey_name <- as.character(diet_table[[prey_col]][i])
        diet_prop <- as.numeric(diet_table[[diet_col]][i])

        if (!is.na(pred_name) && !is.na(prey_name) && !is.na(diet_prop) &&
            pred_name %in% species_names && prey_name %in% species_names) {
          pred_idx <- which(species_names == pred_name)
          prey_idx <- which(species_names == prey_name)
          diet_matrix[prey_idx, pred_idx] <- diet_prop
        }
      }

      # Convert to binary adjacency matrix (transpose for our format)
      # In ECOPATH: columns are predators eating rows (prey)
      # In our format: rows are predators eating columns (prey)
      adjacency_matrix <- t(diet_matrix > 0) * 1

      # Create network
      net <- graph_from_adjacency_matrix(adjacency_matrix, mode = "directed")
      net <- igraph::upgrade_graph(net)

      # Assign functional groups (same heuristics as before)
      assign_functional_group <- function(sp_name, pb, indegree, outdegree) {
        sp_lower <- tolower(sp_name)
        if (grepl("phyto|algae|plant|diatom", sp_lower)) return("Phytoplankton")
        if (grepl("zoo|copepod|cladocer|rotifer", sp_lower)) return("Zooplankton")
        if (grepl("fish|cod|herring|sprat|flounder|shark|ray", sp_lower)) return("Fish")
        if (grepl("benthos|benthic|mussel|clam|worm|shrimp|crab", sp_lower)) return("Benthos")
        if (grepl("detritus|det\\.|debris", sp_lower)) return("Detritus")

        if (indegree == 0 && pb > 1) return("Phytoplankton")
        if (indegree > 0 && outdegree == 0) return("Fish")
        if (indegree > 0 && outdegree > 0) return("Benthos")

        return("Fish")
      }

      indegrees <- degree(net, mode = "in")
      outdegrees <- degree(net, mode = "out")

      functional_groups <- sapply(1:n_species, function(i) {
        assign_functional_group(species_names[i], pb_values[i], indegrees[i], outdegrees[i])
      })

      # Estimate body masses
      estimate_body_mass <- function(fg) {
        if (fg == "Phytoplankton") return(0.00001)
        if (fg == "Zooplankton") return(0.001)
        if (fg == "Benthos") return(1.0)
        if (fg == "Fish") return(100.0)
        if (fg == "Detritus") return(0.0001)
        return(1.0)
      }

      body_masses <- sapply(functional_groups, estimate_body_mass)

      # Assign metabolic types
      met_types <- sapply(functional_groups, function(fg) {
        if (fg %in% c("Fish")) return("ectotherm vertebrates")
        return("invertebrates")
      })

      # Calculate efficiencies
      efficiencies <- sapply(functional_groups, function(fg) {
        if (fg == "Phytoplankton") return(0.4)
        if (fg == "Zooplankton") return(0.75)
        if (fg == "Benthos") return(0.7)
        if (fg == "Fish") return(0.85)
        if (fg == "Detritus") return(0.2)
        return(0.7)
      })

      # Create info data frame
      info <- data.frame(
        meanB = biomass_values,
        fg = factor(functional_groups, levels = c("Benthos", "Detritus", "Fish", "Phytoplankton", "Zooplankton")),
        bodymasses = body_masses,
        met.types = met_types,
        efficiencies = efficiencies,
        PB = pb_values,
        QB = qb_values,
        row.names = species_names,
        stringsAsFactors = FALSE
      )

      return(list(net = net, info = info))

    }, error = function(e) {
      stop(paste("Error parsing ECOPATH database:", e$message))
    })
  }

  # ============================================================================
  # DATA IMPORT HANDLER
  # ============================================================================

  # Output status message for data upload
  output$data_upload_status <- renderPrint({
    if (is.null(input$data_file)) {
      cat("No file uploaded yet.\n\n")
      cat("Current dataset: Gulf of Riga (default)\n")
      cat("  - 34 species\n")
      cat("  - 207 trophic links\n")
      cat("  - 5 functional groups\n")
    } else {
      cat("File selected:", input$data_file$name, "\n")
      cat("File size:", round(input$data_file$size / 1024, 2), "KB\n\n")
      cat("Click 'Load Data' button to import.\n")
    }
  })

  # Handle file upload when button clicked
  observeEvent(input$load_data, {
    req(input$data_file)

    tryCatch({
      file_path <- input$data_file$datapath
      file_ext <- tools::file_ext(input$data_file$name)

      # Update status
      output$data_upload_status <- renderPrint({
        cat("Processing file:", input$data_file$name, "\n")
        cat("Format:", toupper(file_ext), "\n\n")
        cat("Loading...")
      })

      # Load based on file type
      if (file_ext %in% c("Rdata", "rda")) {
        # Load RData file into separate environment
        # (to avoid overwriting app functions if RData contains them)
        env <- new.env()
        load(file_path, envir = env)

        # Validate required objects
        if (!exists("net", envir = env)) {
          stop("RData file must contain 'net' object (igraph network)")
        }
        if (!exists("info", envir = env)) {
          stop("RData file must contain 'info' data frame")
        }

        # Extract only data objects (not functions) from loaded environment
        # This ensures we use the app's function definitions, not ones from the RData file
        net <<- env$net
        info <<- env$info

        # Upgrade igraph if needed
        net <<- igraph::upgrade_graph(net)

        # Assign colors
        info$colfg <<- COLOR_SCHEME[as.numeric(info$fg)]

        # Refresh data editor tables
        refresh_data_editor()

        output$data_upload_status <- renderPrint({
          cat("✓ SUCCESS: Data loaded!\n\n")
          cat("Network: ", vcount(net), "species,", ecount(net), "links\n")
          cat("Species info:", nrow(info), "rows\n")
          cat("\nAll analysis tabs now use your uploaded data.\n")
          cat("Navigate to other tabs to explore.\n")
        })

      } else if (file_ext %in% c("xlsx", "xls")) {
        # Excel file - require readxl package
        if (!requireNamespace("readxl", quietly = TRUE)) {
          stop("Package 'readxl' required for Excel files.\nInstall with: install.packages('readxl')")
        }

        output$data_upload_status <- renderPrint({
          cat("✗ ERROR: Excel import not yet implemented.\n\n")
          cat("For now, please use:\n")
          cat("  - RData format (.Rdata), or\n")
          cat("  - Convert your Excel file to CSV\n\n")
          cat("Excel import coming in next version!\n")
        })

      } else if (file_ext == "csv") {
        output$data_upload_status <- renderPrint({
          cat("✗ ERROR: CSV import not yet implemented.\n\n")
          cat("For now, please use RData format (.Rdata)\n\n")
          cat("CSV import coming in next version!\n")
        })

      } else {
        stop("Unsupported file format")
      }

    }, error = function(e) {
      output$data_upload_status <- renderPrint({
        cat("✗ ERROR loading data:\n\n")
        cat(e$message, "\n\n")
        cat("Please check:\n")
        cat("  - File format is correct\n")
        cat("  - Required objects/sheets are present\n")
        cat("  - Data matches expected structure\n")
      })
    })
  })

  # ============================================================================
  # ECOPATH DATA IMPORT HANDLER
  # ============================================================================

  # Output status message for ECOPATH upload
  output$ecopath_upload_status <- renderPrint({
    if (is.null(input$ecopath_file) && is.null(input$ecopath_diet_file)) {
      cat("No ECOPATH files uploaded yet.\n\n")
      cat("Please upload both:\n")
      cat("  1. Basic Estimates file\n")
      cat("  2. Diet Composition matrix\n")
    } else if (is.null(input$ecopath_file)) {
      cat("Missing: Basic Estimates file\n")
    } else if (is.null(input$ecopath_diet_file)) {
      cat("Missing: Diet Composition file\n")
    } else {
      cat("Files selected:\n")
      cat("  Basic Estimates:", input$ecopath_file$name, "\n")
      cat("  Diet Composition:", input$ecopath_diet_file$name, "\n\n")
      cat("Click 'Import ECOPATH Data' button to process.\n")
    }
  })

  # Handle ECOPATH import when button clicked
  observeEvent(input$load_ecopath, {
    req(input$ecopath_file, input$ecopath_diet_file)

    tryCatch({
      basic_file <- input$ecopath_file$datapath
      diet_file <- input$ecopath_diet_file$datapath

      # Update status
      output$ecopath_upload_status <- renderPrint({
        cat("Processing ECOPATH files...\n\n")
        cat("Basic Estimates:", input$ecopath_file$name, "\n")
        cat("Diet Composition:", input$ecopath_diet_file$name, "\n\n")
        cat("Parsing and converting to EcoNeTool format...\n")
      })

      # Parse ECOPATH data
      result <- parse_ecopath_data(basic_file, diet_file)

      # Update global variables
      net <<- result$net
      info <<- result$info

      # Upgrade igraph if needed
      net <<- igraph::upgrade_graph(net)

      # Assign colors based on functional groups
      info$colfg <<- COLOR_SCHEME[as.numeric(info$fg)]

      # Refresh data editor tables
      refresh_data_editor()

      output$ecopath_upload_status <- renderPrint({
        cat("✓ SUCCESS: ECOPATH data imported!\n\n")
        cat("Conversion complete:\n")
        cat("  - Species/groups:", vcount(net), "\n")
        cat("  - Trophic links:", ecount(net), "\n")
        cat("  - Functional groups:", nlevels(info$fg), "\n\n")

        cat("Functional group distribution:\n")
        fg_table <- table(info$fg)
        for (fg_name in names(fg_table)) {
          cat("  ", fg_name, ":", fg_table[fg_name], "\n")
        }

        cat("\n⚠ Note: Default values assigned for:\n")
        cat("  - Body masses (based on functional groups)\n")
        cat("  - Metabolic types\n")
        cat("  - Assimilation efficiencies\n\n")
        cat("Use the 'Internal Data Editor' tab to refine these values.\n")
        cat("Navigate to other tabs to explore your ECOPATH model.\n")
      })

    }, error = function(e) {
      output$ecopath_upload_status <- renderPrint({
        cat("✗ ERROR importing ECOPATH data:\n\n")
        cat(e$message, "\n\n")
        cat("Common issues:\n")
        cat("  - Species names don't match between files\n")
        cat("  - Missing required columns (Group name, Biomass)\n")
        cat("  - File format not recognized\n")
        cat("  - Diet matrix structure incorrect\n\n")
        cat("Please check your ECOPATH export files.\n")
      })
    })
  })

  # ============================================================================
  # ECOPATH NATIVE DATABASE IMPORT HANDLER
  # ============================================================================

  # Output status message for ECOPATH native upload
  output$ecopath_native_status <- renderPrint({
    if (is.null(input$ecopath_native_file)) {
      cat("No ECOPATH database file uploaded yet.\n\n")
      cat("Accepted formats:\n")
      cat("  - .ewemdb (ECOPATH 6.x)\n")
      cat("  - .mdb (ECOPATH 5.x)\n")
      cat("  - .eiidb (Alternative format)\n\n")
      cat("Example: 'coast 2011-04-10 10.00.ewemdb'\n")
    } else {
      cat("File selected:", input$ecopath_native_file$name, "\n")
      cat("File size:", round(input$ecopath_native_file$size / 1024, 2), "KB\n\n")
      cat("Click 'Import Native Database' button to process.\n")
    }
  })

  # Handle ECOPATH native import when button clicked
  observeEvent(input$load_ecopath_native, {
    req(input$ecopath_native_file)

    tryCatch({
      db_file <- input$ecopath_native_file$datapath

      # Update status
      output$ecopath_native_status <- renderPrint({
        cat("Processing ECOPATH native database...\n\n")
        cat("File:", input$ecopath_native_file$name, "\n")
        cat("Size:", round(input$ecopath_native_file$size / 1024, 2), "KB\n\n")
        cat("Reading database tables...\n")
      })

      # Parse ECOPATH native database
      result <- parse_ecopath_native(db_file)

      # Update global variables
      net <<- result$net
      info <<- result$info

      # Upgrade igraph if needed
      net <<- igraph::upgrade_graph(net)

      # Assign colors based on functional groups
      info$colfg <<- COLOR_SCHEME[as.numeric(info$fg)]

      # Refresh data editor tables
      refresh_data_editor()

      output$ecopath_native_status <- renderPrint({
        cat("✓ SUCCESS: ECOPATH native database imported!\n\n")
        cat("Database:", input$ecopath_native_file$name, "\n\n")

        cat("Conversion complete:\n")
        cat("  - Species/groups:", vcount(net), "\n")
        cat("  - Trophic links:", ecount(net), "\n")
        cat("  - Functional groups:", nlevels(info$fg), "\n\n")

        cat("Functional group distribution:\n")
        fg_table <- table(info$fg)
        for (fg_name in names(fg_table)) {
          cat("  ", fg_name, ":", fg_table[fg_name], "\n")
        }

        cat("\nP/B and Q/B ratios:\n")
        if ("PB" %in% colnames(info)) {
          cat("  Mean P/B:", round(mean(info$PB, na.rm = TRUE), 3), "\n")
        }
        if ("QB" %in% colnames(info)) {
          cat("  Mean Q/B:", round(mean(info$QB, na.rm = TRUE), 3), "\n")
        }

        cat("\n⚠ Note: Default values assigned for:\n")
        cat("  - Body masses (based on functional groups)\n")
        cat("  - Metabolic types (vertebrates vs invertebrates)\n")
        cat("  - Assimilation efficiencies\n\n")

        cat("✓ P/B and Q/B ratios preserved from ECOPATH model\n\n")

        cat("Use the 'Internal Data Editor' tab to refine these values.\n")
        cat("Navigate to other tabs to explore your ECOPATH model.\n")
        cat("\nFor keystoneness analysis, go to 'Keystoneness Analysis' tab.\n")
      })

    }, error = function(e) {
      output$ecopath_native_status <- renderPrint({
        cat("✗ ERROR importing ECOPATH native database:\n\n")
        cat(e$message, "\n\n")

        cat("==================================================\n")
        cat("SOLUTION:\n")
        cat("==================================================\n\n")

        # Detect operating system
        os <- Sys.info()["sysname"]

        if (os == "Windows") {
          cat("⚠ WINDOWS USERS:\n")
          cat("ECOPATH native database import requires mdbtools,\n")
          cat("which is difficult to install on Windows.\n\n")
          cat("RECOMMENDED SOLUTION:\n")
          cat("  1. Open your ECOPATH model\n")
          cat("  2. Export data to CSV or Excel format:\n")
          cat("     - File > Export > Basic Estimates\n")
          cat("     - File > Export > Diet Composition\n")
          cat("  3. Use 'Import ECOPATH CSV/Excel Exports' section above\n\n")
          cat("This is the easiest and most reliable method on Windows!\n\n")
        } else {
          cat("LINUX/MAC USERS:\n")
          cat("Install mdbtools package:\n")
          cat("  Linux: sudo apt-get install mdbtools\n")
          cat("  Mac:   brew install mdbtools\n\n")
        }

        cat("--------------------------------------------------\n")
        cat("Alternative solutions:\n")
        cat("--------------------------------------------------\n\n")

        cat("1. Missing Hmisc package:\n")
        cat("   Solution: install.packages('Hmisc')\n\n")

        cat("2. Use CSV/Excel exports instead (all platforms):\n")
        cat("   - Export from ECOPATH: File > Export\n")
        cat("   - Use 'Import ECOPATH CSV/Excel Exports' above\n\n")

        cat("3. Corrupted database file:\n")
        cat("   Solution: Re-export from ECOPATH software\n")
      })
    })
  })

  # ============================================================================
  # VISUALIZATION OUTPUTS
  # ============================================================================

  # Food Web Visualization (visNetwork)
  output$foodweb_visnet <- renderVisNetwork({
    tryCatch({
      # Calculate trophic levels for hierarchical layout
      tl <- trophiclevels(net)

      # Prepare nodes data frame
      # Set Y positions based on trophic level (higher TL = higher Y position)
      # This guides the initial layout but physics will still apply
      y_pos <- (max(tl) - tl) * -200  # Negative Y values put higher TL at top

      nodes <- data.frame(
        id = 1:vcount(net),
        label = V(net)$name,
        group = as.character(info$fg),
        color = info$colfg,
        value = info$meanB,
        y = y_pos,  # Initial Y position based on trophic level
        fixed = list(y = TRUE),  # Fix Y position based on trophic level
        physics = TRUE,  # Allow physics to move nodes horizontally
        shape = "dot",  # Circular nodes
        title = paste0("<b>", V(net)$name, "</b><br>",
                      "Functional Group: ", info$fg, "<br>",
                      "Trophic Level: ", round(tl, 2), "<br>",
                      "Biomass: ", round(info$meanB, 2)),
        stringsAsFactors = FALSE
      )

      # Map node names to IDs for edges
      name_to_id <- setNames(nodes$id, nodes$label)
      edgelist <- as.data.frame(as_edgelist(net))
      colnames(edgelist) <- c("from", "to")
      edgelist$from <- name_to_id[edgelist$from]
      edgelist$to <- name_to_id[edgelist$to]

      # Create network visualization with gravity-based physics
      vis <- visNetwork(nodes, edgelist, width = "100%", height = "600px") %>%
        visEdges(arrows = "to", smooth = list(type = "curvedCW", roundness = 0.2)) %>%
        visNodes(
          shape = "dot",
          size = 15,
          font = list(size = 12)
        ) %>%
        visOptions(
          highlightNearest = list(enabled = TRUE, degree = 1, hover = TRUE),
          nodesIdSelection = TRUE
        ) %>%
        visInteraction(
          navigationButtons = TRUE,
          keyboard = TRUE
        )

      # Configure each functional group with dot shape for legend
      fg_levels <- levels(info$fg)
      for (i in seq_along(fg_levels)) {
        vis <- vis %>%
          visGroups(groupname = fg_levels[i],
                   shape = "dot",
                   color = COLOR_SCHEME[i])
      }

      # Add gravity-based physics layout with high damping to prevent circling
      vis <- vis %>%
        visPhysics(
          enabled = TRUE,
          solver = "barnesHut",
          barnesHut = list(
            gravitationalConstant = -3000,
            centralGravity = 0.05,
            springLength = 250,
            springConstant = 0.01,
            damping = 0.5,
            avoidOverlap = 0.3
          ),
          stabilization = list(
            enabled = TRUE,
            iterations = 5000,
            updateInterval = 25,
            onlyDynamicEdges = FALSE,
            fit = TRUE
          ),
          minVelocity = 0.5,
          maxVelocity = 20
        ) %>%
        visLegend(
          useGroups = TRUE,
          width = 0.2,
          position = "right",
          main = list(text = "Functional Groups", style = "font-size:14px;font-weight:bold;")
        )

      vis
    }, error = function(e) {
      # Return empty network on error
      visNetwork(data.frame(id=1, label="Error", title=e$message),
                 data.frame(from=integer(0), to=integer(0)))
    })
  })

  output$basal_species <- renderPrint({
    tryCatch({
      basal <- V(net)$name[degree(net, mode="in")==0]
      cat("Basal species:\n", paste(basal, collapse=", "))
    }, error = function(e) {
      cat("Error identifying basal species:", e$message)
    })
  })

  output$top_predators <- renderPrint({
    tryCatch({
      top_pred <- V(net)$name[degree(net, mode="out")==0]
      cat("Top predators:\n", paste(top_pred, collapse=", "))
    }, error = function(e) {
      cat("Error identifying top predators:", e$message)
    })
  })

  output$adjacency_heatmap <- renderPlot({
    tryCatch({
      netmatrix <- as_adjacency_matrix(net, sparse=F)
      heatmap(netmatrix, Rowv=NA, Colv=NA, scale="none")
    }, error = function(e) {
      plot.new()
      text(0.5, 0.5, paste("Error creating adjacency heatmap:", e$message))
    })
  })

  # Topological Indicators
  output$topo_indicators <- renderPrint({
    tryCatch({
      ind <- get_topological_indicators(net)
      print(ind)
    }, error = function(e) {
      cat("Error calculating topological indicators:", e$message)
    })
  })

  output$node_weighted_indicators <- renderPrint({
    tryCatch({
      ind <- get_node_weighted_indicators(net, info)
      print(ind)
    }, error = function(e) {
      cat("Error calculating node-weighted indicators:", e$message)
    })
  })

  # Node-weighted Indicators
  output$biomass_boxplot <- renderPlot({
    tryCatch({
      boxplot(info$meanB~info$fg, las=2, col=COLOR_SCHEME,
              ylab="Biomass (g/day/km2)", xlab="")
    }, error = function(e) {
      plot.new()
      text(0.5, 0.5, paste("Error creating biomass boxplot:", e$message))
    })
  })

  output$biomass_barplot <- renderPlot({
    tryCatch({
      percB <- tapply(info$meanB, info$fg, sum)/sum(info$meanB)*100
      barplot(as.matrix(percB), col=COLOR_SCHEME, ylab="%")
    }, error = function(e) {
      plot.new()
      text(0.5, 0.5, paste("Error creating biomass barplot:", e$message))
    })
  })

  output$foodweb_biomass_plot <- renderPlot({
    tryCatch({
      nodmax <- max(info$meanB)
      sizeB <- (info$meanB/nodmax)*NODE_SIZE_SCALE + NODE_SIZE_MIN
      plotfw(net, col=info$colfg, size=sizeB,
             edge.width=EDGE_ARROW_SIZE_TOPOLOGY,
             edge.arrow.size=EDGE_ARROW_SIZE_TOPOLOGY)
    }, error = function(e) {
      plot.new()
      text(0.5, 0.5, paste("Error creating biomass plot:", e$message))
    })
  })

  # Fluxweb Analysis
  output$flux_heatmap <- renderPlot({
    tryCatch({
      res <- get_fluxweb_results(net, info)
      heatmap(log(res$fluxes + FLUX_LOG_EPSILON), Rowv=NA, Colv=NA, scale="none")
    }, error = function(e) {
      plot.new()
      text(0.5, 0.5, paste("Error creating flux heatmap:", e$message))
    })
  })

  output$flux_network_plot <- renderVisNetwork({
    tryCatch({
      # Get flux results
      res <- get_fluxweb_results(net, info)

      # Calculate trophic levels for layout
      tl <- trophiclevels(net)

      # Set Y positions based on trophic level
      y_pos <- (max(tl) - tl) * -200

      # Prepare nodes data frame
      nodes <- data.frame(
        id = 1:vcount(net),
        label = V(net)$name,
        group = as.character(info$fg),
        color = info$colfg,
        value = info$meanB,
        y = y_pos,
        fixed = list(y = TRUE),  # Fix Y position based on trophic level
        physics = TRUE,
        shape = "dot",
        title = paste0("<b>", V(net)$name, "</b><br>",
                      "Functional Group: ", info$fg, "<br>",
                      "Trophic Level: ", round(tl, 2), "<br>",
                      "Biomass: ", round(info$meanB, 2)),
        stringsAsFactors = FALSE
      )

      # Map node names to IDs for edges
      name_to_id <- setNames(nodes$id, nodes$label)
      edgelist <- as.data.frame(as_edgelist(res$netLW))
      colnames(edgelist) <- c("from", "to")
      edgelist$from <- name_to_id[edgelist$from]
      edgelist$to <- name_to_id[edgelist$to]

      # Add edge weights (flux values) and calculate widths
      flux_weights <- E(res$netLW)$weight
      edge_widths <- EDGE_WIDTH_MIN + (flux_weights/max(flux_weights) * EDGE_WIDTH_SCALE)

      # Format flux values for display (use scientific notation for small values)
      flux_display <- sapply(flux_weights, function(x) {
        if (x >= 0.01) {
          sprintf("%.4f", x)
        } else if (x >= 0.0001) {
          sprintf("%.6f", x)
        } else {
          sprintf("%.2e", x)
        }
      })

      edgelist$width <- edge_widths
      edgelist$value <- flux_weights
      edgelist$title <- paste0("Flux: ", flux_display, " kJ/day/km²")

      # Create network visualization with gravity-based physics
      vis <- visNetwork(nodes, edgelist, width = "100%", height = "600px") %>%
        visEdges(
          arrows = "to",
          smooth = list(type = "curvedCW", roundness = 0.2),
          scaling = list(min = EDGE_WIDTH_MIN, max = EDGE_WIDTH_SCALE)
        ) %>%
        visNodes(
          shape = "dot",
          size = 15,
          font = list(size = 12)
        ) %>%
        visOptions(
          highlightNearest = list(enabled = TRUE, degree = 1, hover = TRUE),
          nodesIdSelection = TRUE
        ) %>%
        visInteraction(
          navigationButtons = TRUE,
          keyboard = TRUE
        )

      # Configure each functional group
      fg_levels <- levels(info$fg)
      for (i in seq_along(fg_levels)) {
        vis <- vis %>%
          visGroups(groupname = fg_levels[i],
                   shape = "dot",
                   color = COLOR_SCHEME[i])
      }

      # Add gravity-based physics layout with high damping to prevent circling
      vis <- vis %>%
        visPhysics(
          enabled = TRUE,
          solver = "barnesHut",
          barnesHut = list(
            gravitationalConstant = -3000,
            centralGravity = 0.05,
            springLength = 250,
            springConstant = 0.01,
            damping = 0.5,
            avoidOverlap = 0.3
          ),
          stabilization = list(
            enabled = TRUE,
            iterations = 5000,
            updateInterval = 25,
            onlyDynamicEdges = FALSE,
            fit = TRUE
          ),
          minVelocity = 0.5,
          maxVelocity = 20
        ) %>%
        visLegend(
          useGroups = TRUE,
          width = 0.2,
          position = "right",
          main = list(text = "Functional Groups", style = "font-size:14px;font-weight:bold;")
        )

      vis
    }, error = function(e) {
      # Return empty network on error
      visNetwork(data.frame(id=1, label="Error", title=e$message),
                 data.frame(from=integer(0), to=integer(0)))
    })
  })

  output$flux_indicators <- renderPrint({
    tryCatch({
      res <- get_fluxweb_results(net, info)
      print(fluxind(res$fluxes))
    }, error = function(e) {
      cat("Error calculating flux indicators:", e$message)
    })
  })

  # ============================================================================
  # KEYSTONENESS ANALYSIS OUTPUTS
  # ============================================================================

  # Keystoneness table
  output$keystoneness_table <- DT::renderDataTable({
    tryCatch({
      ks_results <- calculate_keystoneness(net, info)

      # Format for display
      ks_display <- ks_results
      ks_display$overall_effect <- round(ks_display$overall_effect, 4)
      ks_display$relative_biomass <- round(ks_display$relative_biomass, 4)
      ks_display$keystoneness <- round(ks_display$keystoneness, 3)

      DT::datatable(
        ks_display,
        options = list(
          pageLength = 15,
          scrollX = TRUE,
          order = list(list(3, 'desc'))  # Sort by keystoneness
        ),
        rownames = FALSE
      ) %>%
        DT::formatStyle(
          'keystone_status',
          backgroundColor = DT::styleEqual(
            c('Keystone', 'Dominant', 'Rare', 'Undefined'),
            c('#ffcccc', '#cce5ff', '#e6e6e6', '#fff9cc')
          )
        )
    }, error = function(e) {
      DT::datatable(data.frame(Error = paste("Error calculating keystoneness:", e$message)))
    })
  })

  # Keystoneness vs Biomass plot
  output$keystoneness_plot <- renderPlot({
    tryCatch({
      ks_results <- calculate_keystoneness(net, info)

      # Create color mapping for status
      status_colors <- c(
        "Keystone" = "#ff4444",
        "Dominant" = "#4444ff",
        "Rare" = "#999999",
        "Undefined" = "#ffcc00"
      )

      plot(
        ks_results$relative_biomass,
        ks_results$keystoneness,
        col = status_colors[ks_results$keystone_status],
        pch = 19,
        cex = 1.5,
        xlab = "Relative Biomass (proportion of total)",
        ylab = "Keystoneness Index",
        main = "Keystoneness vs Relative Biomass",
        log = "x"  # Log scale for biomass
      )

      # Add reference lines
      abline(h = 1, lty = 2, col = "gray50")
      abline(v = 0.05, lty = 2, col = "gray50")

      # Add labels for top keystone species
      top_n <- min(5, nrow(ks_results))
      top_species <- ks_results[1:top_n, ]

      text(
        top_species$relative_biomass,
        top_species$keystoneness,
        labels = top_species$species,
        pos = 4,
        cex = 0.7,
        col = "black"
      )

      # Add legend
      legend(
        "topright",
        legend = names(status_colors),
        col = status_colors,
        pch = 19,
        cex = 0.8,
        title = "Status"
      )

      # Add text annotations
      text(0.001, 1, "Keystone threshold", pos = 3, cex = 0.7, col = "gray50")
      text(0.05, max(ks_results$keystoneness, na.rm = TRUE) * 0.9,
           "5% biomass threshold", pos = 4, cex = 0.7, col = "gray50")

    }, error = function(e) {
      plot.new()
      text(0.5, 0.5, paste("Error creating plot:", e$message))
    })
  })

  # MTI Heatmap
  output$mti_heatmap <- renderPlot({
    tryCatch({
      mti_matrix <- calculate_mti(net, info)

      # Create color palette (red = negative, blue = positive)
      colors <- colorRampPalette(c("red", "white", "blue"))(100)

      # Determine symmetric color scale around zero
      max_abs <- max(abs(mti_matrix), na.rm = TRUE)
      breaks <- seq(-max_abs, max_abs, length.out = 101)

      # Create heatmap
      heatmap(
        mti_matrix,
        Rowv = NA,
        Colv = NA,
        scale = "none",
        col = colors,
        breaks = breaks,
        margins = c(8, 8),
        main = "Mixed Trophic Impact Matrix",
        xlab = "Impacting Species (impactor)",
        ylab = "Impacted Species",
        cexRow = 0.7,
        cexCol = 0.7
      )

    }, error = function(e) {
      plot.new()
      text(0.5, 0.5, paste("Error creating MTI heatmap:", e$message))
    })
  })

  # Keystone summary
  output$keystone_summary <- renderPrint({
    tryCatch({
      ks_results <- calculate_keystoneness(net, info)

      cat("=== KEYSTONENESS ANALYSIS SUMMARY ===\n\n")

      # Overall statistics
      cat("Total species analyzed:", nrow(ks_results), "\n")
      cat("Keystone species:", sum(ks_results$keystone_status == "Keystone", na.rm = TRUE), "\n")
      cat("Dominant species:", sum(ks_results$keystone_status == "Dominant", na.rm = TRUE), "\n")
      cat("Rare species:", sum(ks_results$keystone_status == "Rare", na.rm = TRUE), "\n\n")

      # Top 5 keystone species
      cat("=== TOP 5 KEYSTONE SPECIES ===\n\n")
      top_5 <- ks_results[1:min(5, nrow(ks_results)), ]

      for (i in 1:nrow(top_5)) {
        cat(sprintf("%d. %s\n", i, top_5$species[i]))
        cat(sprintf("   Keystoneness Index: %.3f\n", top_5$keystoneness[i]))
        cat(sprintf("   Overall Effect: %.4f\n", top_5$overall_effect[i]))
        cat(sprintf("   Relative Biomass: %.4f (%.2f%%)\n",
                    top_5$relative_biomass[i],
                    top_5$relative_biomass[i] * 100))
        cat(sprintf("   Status: %s\n", top_5$keystone_status[i]))
        cat("\n")
      }

      # Interpretation
      cat("=== INTERPRETATION ===\n\n")
      cat("Keystone species have high ecosystem impact relative to their biomass.\n")
      cat("These species play critical roles in maintaining ecosystem structure.\n")
      cat("Their removal could lead to disproportionate ecosystem changes.\n\n")

      cat("MTI values indicate:\n")
      cat("  - Positive: Increase in impactor increases impacted species\n")
      cat("  - Negative: Increase in impactor decreases impacted species\n")
      cat("  - Magnitude: Strength of direct + indirect effects\n")

    }, error = function(e) {
      cat("Error generating keystoneness summary:", e$message)
    })
  })

  # ============================================================================
  # DOWNLOAD HANDLERS FOR EXAMPLE DATASETS
  # ============================================================================

  # Simple 3-Species downloads
  output$download_simple_rdata <- downloadHandler(
    filename = function() { "Simple_3Species.Rdata" },
    content = function(file) {
      file.copy("examples/Simple_3Species.Rdata", file)
    }
  )

  output$download_simple_csv_net <- downloadHandler(
    filename = function() { "Simple_3Species_network.csv" },
    content = function(file) {
      file.copy("examples/Simple_3Species_network.csv", file)
    }
  )

  output$download_simple_csv_info <- downloadHandler(
    filename = function() { "Simple_3Species_info.csv" },
    content = function(file) {
      file.copy("examples/Simple_3Species_info.csv", file)
    }
  )

  # Caribbean Reef downloads
  output$download_reef_rdata <- downloadHandler(
    filename = function() { "Caribbean_Reef.Rdata" },
    content = function(file) {
      file.copy("examples/Caribbean_Reef.Rdata", file)
    }
  )

  output$download_reef_csv_net <- downloadHandler(
    filename = function() { "Caribbean_Reef_network.csv" },
    content = function(file) {
      file.copy("examples/Caribbean_Reef_network.csv", file)
    }
  )

  output$download_reef_csv_info <- downloadHandler(
    filename = function() { "Caribbean_Reef_info.csv" },
    content = function(file) {
      file.copy("examples/Caribbean_Reef_info.csv", file)
    }
  )

  # Template downloads
  output$download_template_rdata <- downloadHandler(
    filename = function() { "Template_Empty.Rdata" },
    content = function(file) {
      file.copy("examples/Template_Empty.Rdata", file)
    }
  )

  output$download_template_csv_net <- downloadHandler(
    filename = function() { "Template_network.csv" },
    content = function(file) {
      file.copy("examples/Template_network.csv", file)
    }
  )

  output$download_template_csv_info <- downloadHandler(
    filename = function() { "Template_info.csv" },
    content = function(file) {
      file.copy("examples/Template_info.csv", file)
    }
  )

  # ============================================================================
  # INTERNAL DATA EDITOR HANDLERS
  # ============================================================================

  # Reactive values to store editable data
  # Initialize directly with data
  species_data <- reactiveVal({
    info_copy <- info[, !names(info) %in% c("colfg"), drop = FALSE]
    info_copy
  })

  network_matrix_data <- reactiveVal({
    adj_matrix <- as.matrix(as_adjacency_matrix(net, sparse = FALSE))
    adj_matrix
  })

  # Function to refresh data editor tables
  refresh_data_editor <- function() {
    tryCatch({
      info_copy <- info[, !names(info) %in% c("colfg"), drop = FALSE]
      species_data(info_copy)

      adj_matrix <- as.matrix(as_adjacency_matrix(net, sparse = FALSE))
      network_matrix_data(adj_matrix)

      cat("Data editor tables refreshed\n")
    }, error = function(e) {
      cat("Error refreshing data editor:", e$message, "\n")
    })
  }

  # Render Species Info Table (editable with tooltips)
  output$species_info_table <- DT::renderDataTable({
    species_df <- species_data()

    cat("Rendering species_info_table. Data is:", ifelse(is.null(species_df), "NULL", "present"), "\n")
    if (!is.null(species_df)) {
      cat("  Rows:", nrow(species_df), "Columns:", ncol(species_df), "\n")
    }

    req(species_df)

    # Round numeric columns to 2 decimal places for display
    species_display <- species_df
    numeric_cols <- sapply(species_display, is.numeric)
    species_display[numeric_cols] <- lapply(species_display[numeric_cols], function(x) round(x, 2))

    DT::datatable(
      species_display,
      editable = TRUE,
      options = list(
        pageLength = 20,
        scrollX = TRUE,
        scrollY = "500px",
        dom = 'tp'
      ),
      rownames = TRUE
    ) %>%
      DT::formatRound(columns = which(numeric_cols), digits = 2)
  })

  # Handle Species Info Table edits
  observeEvent(input$species_info_table_cell_edit, {
    species_data_df <- species_data()
    info_edit <- input$species_info_table_cell_edit
    species_data_df[info_edit$row, info_edit$col] <- info_edit$value
    species_data(species_data_df)
  })

  # Save Species Info button
  observeEvent(input$save_species_info, {
    tryCatch({
      # Update global info variable
      edited_info <- species_data()

      # Validate required columns exist
      required_cols <- c("meanB", "fg", "bodymasses", "met.types", "efficiencies")
      missing_cols <- setdiff(required_cols, colnames(edited_info))
      if (length(missing_cols) > 0) {
        stop(paste("Missing required columns:", paste(missing_cols, collapse=", ")))
      }

      # Update global info
      info <<- edited_info

      # Reassign colors based on functional groups
      info$colfg <<- COLOR_SCHEME[as.numeric(info$fg)]

      output$species_info_status <- renderPrint({
        cat("✓ SUCCESS: Species information saved!\n")
        cat("Updated", nrow(info), "species records.\n")
        cat("\nNavigate to other tabs to see updated visualizations.\n")
      })
    }, error = function(e) {
      output$species_info_status <- renderPrint({
        cat("✗ ERROR saving species info:\n")
        cat(e$message, "\n")
      })
    })
  })

  # Render Network Adjacency Matrix Table (editable with tooltips)
  output$network_matrix_table <- DT::renderDataTable({
    matrix_df <- network_matrix_data()

    cat("Rendering network_matrix_table. Data is:", ifelse(is.null(matrix_df), "NULL", "present"), "\n")
    if (!is.null(matrix_df)) {
      cat("  Rows:", nrow(matrix_df), "Columns:", ncol(matrix_df), "\n")
    }

    req(matrix_df)

    DT::datatable(
      matrix_df,
      editable = TRUE,
      extensions = 'FixedColumns',
      options = list(
        pageLength = 34,
        scrollX = TRUE,
        scrollY = "500px",
        dom = 't',
        fixedColumns = list(leftColumns = 1)
      ),
      rownames = TRUE
    )
  })

  # Handle Network Matrix Table edits
  observeEvent(input$network_matrix_table_cell_edit, {
    matrix_data <- network_matrix_data()
    matrix_edit <- input$network_matrix_table_cell_edit
    matrix_data[matrix_edit$row, matrix_edit$col] <- as.numeric(matrix_edit$value)
    network_matrix_data(matrix_data)
  })

  # Save Network Matrix button
  observeEvent(input$save_network_matrix, {
    tryCatch({
      output$network_matrix_status <- renderPrint({
        cat("✓ Network matrix saved to memory.\n")
        cat("Click 'Update Network from Matrix' to apply changes to the network object.\n")
      })
    }, error = function(e) {
      output$network_matrix_status <- renderPrint({
        cat("✗ ERROR saving network matrix:\n")
        cat(e$message, "\n")
      })
    })
  })

  # Update Network from Matrix button
  observeEvent(input$update_network, {
    tryCatch({
      # Get edited matrix
      edited_matrix <- network_matrix_data()

      # Validate matrix is square
      if (nrow(edited_matrix) != ncol(edited_matrix)) {
        stop("Adjacency matrix must be square (same number of rows and columns)")
      }

      # Validate matrix contains only 0s and 1s
      if (!all(edited_matrix %in% c(0, 1))) {
        stop("Adjacency matrix must contain only 0 (no link) or 1 (link exists)")
      }

      # Create new network from adjacency matrix
      net <<- graph_from_adjacency_matrix(edited_matrix, mode = "directed")

      # Upgrade if needed
      net <<- igraph::upgrade_graph(net)

      output$network_matrix_status <- renderPrint({
        cat("✓ SUCCESS: Network updated from matrix!\n")
        cat("Network now has:\n")
        cat("  - Species:", vcount(net), "\n")
        cat("  - Links:", ecount(net), "\n")
        cat("\nAll visualizations will now use the updated network.\n")
        cat("Navigate to other tabs to see the changes.\n")
      })
    }, error = function(e) {
      output$network_matrix_status <- renderPrint({
        cat("✗ ERROR updating network:\n")
        cat(e$message, "\n")
      })
    })
  })
}
shinyApp(ui, server)
