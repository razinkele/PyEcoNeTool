# Data Import (v1) — short design

**Why.** EconetPy can only show the bundled Baltic (Gulf of Riga) food web
(`load_data.py`, `app.py:350`). Every analysis page is useless for anyone
with their own data. This is the first gap in the R-parity work and blocks
everything after it (trait research included).

**Goal (v1).** A user can, within their own session:
1. upload a food-web adjacency CSV + a species-info CSV,
2. load one of the bundled examples (`examples/`),
3. return to the Baltic default,
4. read a short format guide in-app.

**Non-goals (v1).** ECOPATH native `.ewemdb` / ECOPATH exports, RData, Excel,
persisting uploads server-side, editing the adjacency matrix in-app.

**Anti-goals.** Loading untrusted pickle/RData (code execution); an upload
that silently builds an inverted web; an upload that crashes a page
instead of being rejected up front; touching module globals or the shared
`BalticFW.pkl` cache (one user's upload must never leak to another session).

## Approaches considered
- **A. Pure parser module + one new "Data Import" page (chosen).**
  `data_import.py` exposes `parse_food_web(network_src, info_src) -> (G, info)`
  raising `ValueError` with a user-readable message. The server handler only
  calls it, catches `ValueError`, and on success sets the session's
  `current_network` / `current_species_info` and clears `flux_results`.
  Testable without Shiny; every page already reads the session values.
- B. Port the R five-tab import menu wholesale. Rejected: ECOPATH needs an
  Access-DB reader on a Linux server; several projects in one.
- C. Upload inside the Data Editor page. Rejected: the editor is per-cell
  attribute editing; mixing in dataset replacement muddies both.

## Format (matches `examples/README.md`, Baltic export)
- **Network CSV:** square matrix, first column = row labels, header = same
  names in the same set. `M[prey, predator] = 1` (rows = prey). Edges are
  built prey → predator via `nx.from_pandas_adjacency`.
- **Species CSV:** required `species, fg, meanB, bodymasses, met.types,
  efficiencies`; extra columns kept. Rows reordered to matrix order.

## Validation (all → `ValueError`, message shown as notification)
size cap (2 MB per file, ≤ 500 species); separator sniffed (`,` / `;` / tab),
UTF-8 BOM tolerated, decimal comma accepted for `;`-separated files;
non-UTF-8 files fall back to cp1257 (Lithuanian-locale Excel);
square matrix; row labels == column labels as sets (columns are reordered
to row order); unique
names; matrix values in {0, 1}; species set == matrix set; required columns
present; numeric columns finite, `meanB`/`bodymasses` > 0, `efficiencies`
in (0, 1]; `met.types` valid (`validate_met_types`); final `_assert_aligned`-
equivalent order check.

## Builder's calls
- Matrix diagonal (cannibalism) allowed and kept (Baltic itself has none).
- A matrix with no links at all is rejected (nothing to analyse), which is
  why `Template_*` is not in the example picker.
- Accepted `met.types` are exactly `flux_calculations.ACCEPTED_MET_TYPES`.
- Weighted (non-0/1) matrices rejected in v1 rather than binarised silently.
- Example picker reads the same CSV pairs through the same parser, so the
  examples double as acceptance tests.
- Acceptance: all three non-empty datasets (Simple, Caribbean, Baltic
  round-trip) run through both TL methods, topological + node-weighted
  indicators, `fluxing`, MTI, keystoneness without error. Template (all
  zeros, no links) must either work or be rejected with a clear message.
