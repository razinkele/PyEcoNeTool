# Trait-based food web (trait research, project 1 of 3) — short design

**Why.** Users need food webs where no diet data exists. The R EcoNeTool
infers feeding links from five coded traits per species; EconetPy has no
equivalent. Projects 2 (trait lookup: WoRMS + FishBase/SeaLifeBase, filling
body mass etc. for imported models) and 3 (auto-coding looked-up traits) build
on this one.

**Goal.** On the Data Import page, upload one CSV/.xlsx of species with trait
codes `MS FS MB EP PR` (as in the R app's `trait_foodweb_*.csv`) and get a
food web loaded into the session like any other import, so every analysis
page runs on it (with the caveats below on what is meaningful). Bundle the
three R example trait files.

**Non-goals.** Trait lookup from databases (project 2), deriving codes from
raw traits (project 3), editing codes in-app, calibrating the probability
tables (ported as-is).

**Anti-goals.** Silently diverging from the R model (same tables, same rule,
same threshold, so the same input gives the same web); inverting the web
(the R core returns `[consumer, resource]`; EconetPy's matrix is rows = prey,
so it is transposed exactly once); presenting placeholder biomasses as data.

## Approaches
- **A. Faithful port of the R trait model into `trait_foodweb.py` (chosen).**
  Same five tables (MS×MS, FS×MS, MB×MB, EP×MS, PR×MS), same exclusions (MS7
  never prey; only MS3–MS6 and non-FS0 consumers; no self-links), link
  probability = minimum of the five, link iff probability > threshold
  (strict; default 0.05). Output goes through `data_import.build_food_web`.
- B. Re-derive link rules (e.g. allometric niche model from body size).
  Rejected for now: diverges from the R app the users know; can come later
  as an option.
- C. Call R. Rejected: no R runtime in the Python deployment.

## Known behaviour of the R model (measured, 2026-11-20)
R model run on the server (`trait_foodweb.R`, sha256 `c6d61a2e…8196`,
modified 2026-10-21) on the three examples, then pushed through
`build_food_web` and every analysis:

| example | species | links | two-way pairs | consumers with no prey | isolated |
|---|---|---|---|---|---|
| simple | 5 | 6 | 1 | Zooplankton | – |
| marine invertebrates | 15 | 84 | 7 | Copepod, Amphipod, Barnacle | – |
| coastal | 35 | 478 | 49 | 9 (Bacteria, Protozoa, Copepod_small, Cladoceran, Amphipod_benthic, Isopod, Bivalve_small, Gastropod_grazer, Seal_grey) | Seal_grey |

- No example is rejected; all analyses run; no trophic-level warnings
  (two-way pairs are fed from producers, so no closed loops).
- **Flaw inherited from the R rules:** only MS3–MS6 can eat, so every MS1/MS2
  consumer (zooplankton, copepods, small grazers/filter feeders) and every
  MS7 species has no prey. They become basal and get **trophic level 1**,
  like producers, and MS7 species are isolated. The R example README itself
  expects Zooplankton as a primary consumer, so this is a model limitation,
  not intent. Topology and trophic-level results are therefore distorted for
  those species. **Decision needed (see the open question).**
- Whatever is decided, the import notes list every non-producer that ends up
  with no prey and every isolated species.
- If the shared checks reject a web (e.g. a closed loop with no producer
  input, possible with user codes), the ValueError is shown as the import
  notification, as for any upload, and nothing is loaded.

## Open question for the user: small and extra-large consumers
- **(a) Faithful port.** Identical links to R; the flaw is listed in the
  notes. Parity is exact.
- **(b) Port + documented extension (recommended).** Add consumer rows for
  MS1, MS2 and MS7, *derived* from the R size table rather than chosen: all
  four R rows follow one diagonal band — peak (0.95) where prey is two classes
  below the consumer, 0.80 one class either side, 0.50 two either side, 0.20
  three below, 0.05 three above (verified in code against every R value).
  Extrapolated: MS1 consumer `[0.50, .05, .05, .05, .05, .05]`; MS2 consumer
  `[0.80, 0.50, .05, .05, .05, .05]`; MS7 consumer `[0.20, 0.20, 0.50, 0.80,
  0.95, 0.80]` (over MS1–MS6). MS7 is still never prey (unchanged R rule).
  Default on, switch to reproduce R exactly; the parity test runs with it
  off. The import note states how many links the extension added and that R
  EcoNeTool gives fewer.
  - Measured with a throwaway port (identical to R's probabilities on all
    three examples with the extension off):

    | example | links R / with (b) | no-prey consumers R → (b) | isolated R → (b) | TL warnings |
    |---|---|---|---|---|
    | simple | 6 / 7 | 1 → 0 (Zooplankton TL 1.0 → 2.0) | – | 0 |
    | marine invertebrates | 84 / 92 | 3 → 1 | – | 0 |
    | coastal | 478 / 551 | 9 → 3 (Seal_grey TL 1.0 → 4.18, Bacteria 1.0 → 2.0) | Seal_grey → none | 0 |
  - The remaining no-prey consumers (Copepod, Copepod_small, Cladoceran,
    Protozoa) are a **data issue in the R example files**, not the size rule:
    they and the phytoplankton are coded `EP4`, which in the current R
    vocabulary (v2) means endobenthic/infaunal, and `EP4 × MS1 = 0.05`. The
    files look written for an older EP scheme. Bundled as-is (parity), with a
    line in the format guide.

## Upstream R issues found (not fixed here; offer to the user)
- Only MS3–MS6 can be consumers, so every MS1/MS2/MS7 consumer has no prey
  in R EcoNeTool's trait food web.
- The three `examples/trait_foodweb_*.csv` code plankton as `EP4`
  (endobenthic in vocabulary v2).

## Filling what a trait file does not carry (builder's call — reviewable)
The analyses also need `fg, meanB, bodymasses, met.types, efficiencies`.
Optional columns with those names in the trait file are used as given
(validated like any upload). A column that is present must be filled for
every species: a partly filled optional column is rejected (no silent mix of
real and estimated values). Missing columns are estimated, and every estimate
is listed in the import notes. `fg` cannot be edited in the Data Editor, so
the note points to adding an `fg` column to the file instead; the other
estimates can be edited there.
- `fg` from codes: FS0 → "Primary producers"; FS2/FS5 with EP3/EP4 →
  "Benthos"; MB2 consumer → "Zooplankton"; MB5 with MS4+ → "Fish"; EP3/EP4 →
  "Benthos"; otherwise "Consumers".
- `bodymasses` (g) from the MS class's length midpoint (0.05, 0.5, 3, 12, 35,
  100, 200 cm) via a generic `W = 0.01·L³` (fish-like; flagged as rough).
- `met.types`: "ectotherm vertebrates" for the Fish fg, else "invertebrates".
- `efficiencies`: 0.77 for FS0 (producers as resources), else 0.906 (Baltic
  convention).
- `meanB`: **1.0 for every species when absent**. Biomass-weighted results
  (biomass page, node-weighted indicators, fluxes, keystoneness) are then not
  meaningful. Because those results appear on other pages, the import note
  alone is not enough: a warning banner ("Biomass values are placeholders
  (1.0 for every species) — these results are not meaningful") is shown at
  the top of every page that uses `meanB` for results: Biomass Analysis
  (node-weighted indicators, biomass plots; `app.py:1422,1436,1460`), Energy
  Fluxes (`:1505`) and Keystoneness (`:1012`). The network pages use `meanB`
  only for node size (all nodes equal size), covered by the import note. A
  session flag drives the banner: set by a trait import without `meanB`,
  cleared by any other import or reset, and cleared when the Data Editor
  applies edits that change `meanB` (the user has entered real biomass).

## UI
New card "Trait-based food web" on the Data Import page: file input (CSV or
.xlsx), threshold input (default 0.05), example picker (simple /
marine invertebrates / coastal), Load button. Format guide gains a short
trait-code table (labels from the R vocabulary).

## Validation (ValueError, user-readable)
Required columns `species MS FS MB EP PR`; codes must be in the vocabulary
(MS1–7, FS0–7, MB1–5, EP1–4, PR0–8); blank codes allowed and role-aware as in
R (a species missing a consumer trait cannot eat; missing a resource trait
cannot be eaten; listed in notes); duplicate species rejected; then the
shared checks (no links, closed loops, size limits).

## Tests
Probability function against hand-computed cases from the R tables; each
R example file → expected structure (FS0 species basal, MS7 never prey, no
self-links); orientation (a grazer FS4 eats phytoplankton MS1 → edge
phyto → grazer); every example runs through all analyses.
**R parity:** fixtures are R's full probability matrices
(`construct_trait_foodweb(..., threshold = 0, return_probs = TRUE)`) for the
three examples, generated on the server by R, never by the Python port, with
the R file's sha256 and date recorded beside them. The test compares
probabilities (not just links at 0.05), so any threshold is covered; with
option (b) chosen, it runs with the extension switched off.
