"""Import an Ecopath with Ecosim (EwE) native model database as a food web.

Reads the two tables every EwE 6 database has -- ``EcopathGroup`` (one row per
functional group) and ``EcopathDietComp`` (long table: PredID, PreyID, Diet) --
from a ``.ewemdb`` / ``.eweaccdb`` (Microsoft Access) file and turns them into
the ``(G, info)`` pair the app analyses, via ``data_import.build_food_web`` so
it passes exactly the same validation as a CSV upload.

Orientation: ``Diet`` is the share of the predator's diet made up by the prey,
so every ``Diet > 0`` row is a prey -> predator link (rows = prey in the
adjacency matrix). No transpose.

What EwE does not record, and is therefore estimated (and reported in the
returned notes): the functional group (from the EwE ``Type`` code and the group
name), body mass, metabolic type and assimilation efficiency (per-group
defaults following the Baltic dataset's conventions). ``GroupIsFish`` /
``GroupIsInvert`` are not used: real models set them to 1 for every group.

Readers: ``mdbtools`` (``mdb-tables`` / ``mdb-export``, Linux/macOS; present
on the server) or, failing that, the Microsoft Access ODBC driver via
``pyodbc`` (Windows). Both get the file path as an argument -- no shell.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from data_import import build_food_web

ACCEPTED_EXTENSIONS = (".ewemdb", ".eweaccdb", ".mdb", ".accdb")
MAX_DB_BYTES = 50 * 1024 * 1024
GROUP_TABLE, DIET_TABLE = "EcopathGroup", "EcopathDietComp"

# fg -> (body mass in g, met.types, assimilation efficiency). Body masses are
# the Baltic dataset's per-group medians where it has the group; efficiencies
# and met.types follow its conventions (animals 0.906, producers 0.77,
# detritus 0.4; producers use the invertebrate allometry, detritus "Other").
FG_DEFAULTS = {
    "Phytoplankton": (1.19e-8, "invertebrates", 0.77),
    "Macrophytes": (1.0, "invertebrates", 0.77),
    "Detritus": (1.0, "Other", 0.4),
    "Zooplankton": (1.7e-5, "invertebrates", 0.906),
    "Benthos": (1.35e-2, "invertebrates", 0.906),
    "Invertebrates": (1.35e-2, "invertebrates", 0.906),
    "Fish": (51.0, "ectotherm vertebrates", 0.906),
    # No endotherm metabolic type exists in the flux model: approximated.
    "Birds & mammals": (1000.0, "ectotherm vertebrates", 0.906),
    # Consumer whose name matched nothing: treated as an invertebrate, and listed.
    "Unclassified consumers": (1.35e-2, "invertebrates", 0.906),
}

_RX = lambda words: re.compile("|".join(words), re.IGNORECASE)  # noqa: E731
# Stems, not whole words: EwE group names are often truncated (e.g. Mar Menor's
# 7-letter "Polycha", "Seagras", "Apendic").
_MACROPHYTE = _RX([r"macrophyt", r"seagras", r"eelgras", r"zostera", r"posidonia",
                   r"macroalga", r"phytobenth", r"seaweed", r"kelp", r"charophyt",
                   r"benthic alga", r"rhodoph", r"phaeoph", r"caulerp", r"fucus"])
_BIRD_MAMMAL = _RX([r"bird", r"cormorant", r"\bgulls?\b", r"\blarus\b", r"duck",
                    r"\bterns?\b", r"eider", r"merganser", r"goosander", r"scoter",
                    r"grebe", r"heron", r"\bswans?\b", r"\bgeese\b", r"\bgoose\b",
                    r"\bcoots?\b", r"\bauks?\b", r"guillemot", r"razorbill", r"puffin",
                    r"\bloons?\b", r"pelican", r"\bshags?\b", r"osprey", r"eagle",
                    r"kingfisher", r"wader", r"sandpiper", r"\bseals?\b", r"sea lion",
                    r"walrus", r"porpoise", r"dolphin", r"whale", r"mammal", r"\botters?\b",
                    r"manatee", r"dugong"])
_BENTHOS = _RX([r"benth", r"polych", r"bivalv", r"mussel", r"\bclams?\b", r"oyster",
                r"oligoch", r"amphip", r"isopod", r"\bcrabs?\b", r"shrimp", r"prawn",
                r"gastrop", r"snail", r"chiron", r"\bworms?\b", r"echinoderm",
                r"starfish", r"urchin", r"brittle star", r"lobster", r"crayfish",
                r"shellfish", r"crustacea", r"decapod", r"saduria", r"macoma",
                r"mytilus", r"nematod", r"tanaid", r"cirrip", r"barnacle", r"ascidi",
                r"porifer", r"sponge", r"bryozo", r"foramin", r"pycnogo", r"cumace", r"ostraco",
                r"meiofauna", r"infauna", r"epifauna", r"filtrator", r"deposit feeder"])
_FISH_ORDERS = (r"(perci|cyprini|gadi|clupei|pleuronecti|salmoni|gasterostei|"
                r"scorpaeni|anguilli|syngnathi|mugili|atherini|osmeri|esoci|siluri|"
                r"beloni|tetraodonti|lophii|zei|beryci|gobii|blenni)formes")
_FISH = _RX([r"(?<!jelly)(?<!star)(?<!shell)(?<!cuttle)(?<!cray)fish", _FISH_ORDERS,
             r"herring", r"sprat", r"\bcod\b", r"flounder", r"plaice", r"\bsole\b",
             r"turbot", r"perch", r"\bpike", r"bream", r"roach", r"vimba", r"smelt",
             r"salmon", r"trout", r"\beels?\b", r"gob(y|ies)", r"gobiid", r"stickleback",
             r"sand-?eel", r"\bshad\b", r"eelpout", r"ruffe", r"whiting", r"haddock",
             r"mackerel", r"tuna", r"sardine", r"anchov", r"sculpin", r"lumpfish",
             r"garfish", r"burbot", r"whitefish", r"vendace", r"\bcarp", r"zander",
             r"clupeid", r"gadoid", r"flatfish", r"shark", r"\brays?\b", r"skate",
             r"\bhake", r"pollock", r"saithe", r"\bdab\b", r"grouper", r"snapper",
             r"wrasse", r"blenny", r"pipefish", r"seahorse", r"mullet", r"silverside",
             r"capelin", r"\bsand lance",
             r"\((juv|adult|ad\.|sub-?adult|larva)"])  # EwE multi-stanza groups are fish
_ZOO = _RX([r"zooplank", r"copepod", r"cladocer", r"rotifer", r"mysid", r"krill",
            r"jellyfish", r"medusa", r"aurelia", r"ctenophor", r"appendic", r"apendic",
            r"chaetognath", r"ciliat", r"tintin", r"oligotr", r"protozo", r"flagel",
            r"nauplii", r"veliger", r"ichthyopl", r"microzoo", r"mesozoo"])


def classify_group(name: str, ewe_type: float) -> str:
    """Functional group from the EwE Type code (0 consumer, 1 producer,
    2 detritus, 0<t<1 mixotroph) and the group name."""
    if ewe_type >= 2:
        return "Detritus"
    if ewe_type > 0:  # producer or mixotroph
        return "Macrophytes" if _MACROPHYTE.search(name) else "Phytoplankton"
    if re.search(r"jellyfish", name, re.IGNORECASE):
        return "Zooplankton"
    if re.search(r"cuttlefish|squid|octopus|cephalopod", name, re.IGNORECASE):
        return "Invertebrates"
    for rx, fg in ((_BIRD_MAMMAL, "Birds & mammals"), (_ZOO, "Zooplankton"),
                   (_BENTHOS, "Benthos"), (_FISH, "Fish")):
        if rx.search(name):
            return fg
    return "Unclassified consumers"


def _pick(df: pd.DataFrame, wanted: list[str], table: str) -> pd.DataFrame:
    lower = {c.lower(): c for c in df.columns}
    missing = [w for w in wanted if w.lower() not in lower]
    if missing:
        raise ValueError(f"The {table} table is missing column(s): {', '.join(missing)}.")
    return df[[lower[w.lower()] for w in wanted]].set_axis(wanted, axis=1)


def ecopath_tables_to_food_web(groups: pd.DataFrame, diet: pd.DataFrame, *,
                               biomass_source: str = "the Ecopath input biomass (t/km²)",
                               where: str = "in the database"):
    """Convert EwE ``EcopathGroup`` + ``EcopathDietComp`` tables into
    ``(G, info, notes)``. ``biomass_source`` and ``where`` word the notes for
    the route the tables came from. Raises ``ValueError`` (user-readable)."""
    g = _pick(groups, ["GroupID", "GroupName", "Type", "Biomass"], GROUP_TABLE).copy()
    extra = {c.lower(): c for c in groups.columns}
    g["Sequence"] = pd.to_numeric(groups[extra["sequence"]], errors="coerce") \
        if "sequence" in extra else np.arange(len(g))
    for col in ("ProdBiom", "ConsBiom"):
        if col.lower() in extra:
            g[col] = pd.to_numeric(groups[extra[col.lower()]], errors="coerce")
    d = _pick(diet, ["PredID", "PreyID", "Diet"], DIET_TABLE)

    g["GroupID"] = pd.to_numeric(g["GroupID"], errors="coerce")
    g["Type"] = pd.to_numeric(g["Type"], errors="coerce")
    g["Biomass"] = pd.to_numeric(g["Biomass"], errors="coerce")
    g["GroupName"] = g["GroupName"].astype(str).str.strip()
    g = g[g["GroupID"].notna() & (g["GroupName"] != "") & g["Type"].notna()]
    g = g.sort_values(["Sequence", "GroupID"]).reset_index(drop=True)
    if g.empty:
        raise ValueError("The Ecopath model has no groups.")
    # Duplicate names cannot key the network: disambiguate by ID.
    dup = g["GroupName"].duplicated(keep=False)
    g.loc[dup, "GroupName"] = g.loc[dup].apply(
        lambda r: f"{r['GroupName']} (ID {int(r['GroupID'])})", axis=1)

    notes = []
    no_biomass = ~(np.isfinite(g["Biomass"]) & (g["Biomass"] > 0))
    if no_biomass.any():
        dropped = g.loc[no_biomass, "GroupName"].tolist()
        notes.append(
            f"Left out {len(dropped)} group(s) with no input biomass {where} "
            f"(Ecopath estimates these during mass balance): {', '.join(dropped)}.")
        g = g[~no_biomass].reset_index(drop=True)
    if g.empty:
        raise ValueError("No Ecopath group has an input biomass.")

    d = d.apply(pd.to_numeric, errors="coerce").dropna()
    id_to_name = dict(zip(g["GroupID"].astype(int), g["GroupName"]))
    d = d[(d["Diet"] > 0) & d["PredID"].astype(int).isin(id_to_name)
          & d["PreyID"].astype(int).isin(id_to_name)]
    if d.empty:
        raise ValueError("The Ecopath model has no usable feeding links "
                         "(no diet entries > 0 between groups with a biomass).")

    names = g["GroupName"].tolist()
    M = pd.DataFrame(0, index=names, columns=names, dtype=int)
    for prey, pred in zip(d["PreyID"].astype(int), d["PredID"].astype(int)):
        M.at[id_to_name[prey], id_to_name[pred]] = 1  # rows = prey

    fg = [classify_group(n, t) for n, t in zip(g["GroupName"], g["Type"])]
    bodymass, met, eff = zip(*(FG_DEFAULTS[f] for f in fg))
    info = pd.DataFrame({
        "species": names, "fg": fg, "meanB": g["Biomass"].astype(float).to_numpy(),
        "bodymasses": bodymass, "met.types": met, "efficiencies": eff,
        "ewe.type": g["Type"].to_numpy(),
    })
    for col, out in (("ProdBiom", "PB"), ("ConsBiom", "QB")):
        if col in g:
            info[out] = g[col].where(g[col] > 0).to_numpy()

    unclassified = [n for n, f in zip(names, fg) if f == "Unclassified consumers"]
    if unclassified:
        notes.append(
            f"{len(unclassified)} consumer group(s) could not be classified from their "
            "names and use invertebrate defaults (check body mass and metabolic type "
            f"in the Data Editor): {', '.join(unclassified)}.")
    endo = [n for n, f in zip(names, fg) if f == "Birds & mammals"]
    if endo:
        notes.append(
            "The flux model has no endotherm metabolic type, so birds and mammals "
            f"are approximated as ectotherm vertebrates: {', '.join(endo)}.")
    notes.insert(0,
        "Functional groups were assigned from each group's Ecopath type and name; "
        "body masses, metabolic types and assimilation efficiencies are defaults "
        "per functional group (edit them in the Data Editor). Biomass is "
        f"{biomass_source}.")

    try:
        G, info = build_food_web(M, info)
    except ValueError as exc:
        if no_biomass.any():
            raise ValueError(f"{exc} (Groups without an input biomass had been left "
                             "out first; see the import notes.)") from None
        raise
    return G, info, notes


# --- reading the Access database ----------------------------------------------

def _mdb_tables(path: Path) -> list[str]:
    r = subprocess.run(["mdb-tables", "-1", str(path)], capture_output=True, timeout=60)
    if r.returncode != 0:
        raise ValueError("The file is not a readable Ecopath (Access) database.")
    return [t for t in r.stdout.decode("utf-8", "replace").splitlines() if t.strip()]


def _mdb_export(path: Path, table: str) -> pd.DataFrame:
    r = subprocess.run(["mdb-export", str(path), table], capture_output=True, timeout=120)
    if r.returncode != 0:
        raise ValueError(f"Could not read the {table} table from the database.")
    return pd.read_csv(io.StringIO(r.stdout.decode("utf-8", "replace")))


def _odbc_read(path: Path, tables: list[str]) -> dict[str, pd.DataFrame]:
    try:
        import pyodbc
    except ImportError:
        pyodbc = None
    drivers = [d for d in (pyodbc.drivers() if pyodbc else []) if "Access Driver" in d and "mdb" in d]
    if not drivers:
        raise ValueError("Reading Ecopath databases needs mdbtools (Linux/macOS) or the "
                         "Microsoft Access ODBC driver with pyodbc (Windows).")
    try:
        conn = pyodbc.connect(f"DRIVER={{{drivers[0]}}};DBQ={path};READONLY=1", autocommit=True)
    except pyodbc.Error:
        raise ValueError("The file is not a readable Ecopath (Access) database.") from None
    try:
        cur = conn.cursor()
        present = {t.table_name for t in cur.tables(tableType="TABLE")}
        _require_tables(present)
        out = {}
        for t in tables:
            cur.execute(f"SELECT * FROM [{t}]")
            cols = [c[0] for c in cur.description]
            out[t] = pd.DataFrame.from_records([tuple(r) for r in cur.fetchall()], columns=cols)
        return out
    finally:
        conn.close()


def _require_tables(present) -> None:
    missing = [t for t in (GROUP_TABLE, DIET_TABLE) if t not in present]
    if missing:
        raise ValueError(
            "This does not look like an Ecopath with Ecosim model database: "
            f"table(s) {', '.join(missing)} not found.")


def read_ecopath_tables(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if shutil.which("mdb-export") and shutil.which("mdb-tables"):
        _require_tables(set(_mdb_tables(path)))
        return _mdb_export(path, GROUP_TABLE), _mdb_export(path, DIET_TABLE)
    t = _odbc_read(path, [GROUP_TABLE, DIET_TABLE])
    return t[GROUP_TABLE], t[DIET_TABLE]


def parse_ecopath_db(path, name: str | None = None):
    """Read an EwE model database file and return ``(G, info, notes)``.

    ``name`` is the user's original file name (for the extension check), if
    ``path`` is a temporary upload path. Raises ``ValueError``.
    """
    path = Path(path)
    ext = Path(name or path.name).suffix.lower()
    if ext not in ACCEPTED_EXTENSIONS:
        raise ValueError(f"Expected an Ecopath database file ({', '.join(ACCEPTED_EXTENSIONS)}); "
                         f"got extension {ext or '(none)'!r}.")
    if path.stat().st_size > MAX_DB_BYTES:
        raise ValueError(f"The database is too large (limit {MAX_DB_BYTES // 1024 // 1024} MB).")
    try:
        groups, diet = read_ecopath_tables(path)
    except subprocess.TimeoutExpired:
        raise ValueError("Reading the database timed out.") from None
    return ecopath_tables_to_food_web(groups, diet)


# --- EwE GUI exports (CSV / Excel) ---------------------------------------------
# EwE 6 writes "<model>-Basic estimates.csv" (or "-Basic input.csv") and
# "<model>-Diet composition.csv": an unnamed group-number column, the group
# name, then values. Names are often NOT quoted even when they contain the
# separator, e.g. ``7,Macrozoobenthos omnivoroes (<9,9mm),0,...``, so a plain
# CSV reader shifts the columns. Rows are therefore split by position: first
# field = number, last K fields = values (K from the header), the rest = name.

_DIET_CORNER = re.compile(r"prey\s*\\\s*predator", re.IGNORECASE)
_DIET_SUMMARY = {"import", "sum", "(1 - sum)", "1 - sum"}


def _export_rows(src, what: str) -> tuple[list[list[str]], bool]:
    """Read an export into rows of strings; also return whether numbers use a
    decimal comma (semicolon-separated CSV)."""
    import csv
    from data_import import _XLSX_MAGIC, _decode, _read_bytes, _read_excel, _sniff_sep

    data = _read_bytes(src, what)
    if data[:4] == _XLSX_MAGIC:
        df = _read_excel(data, what)
        return [[str(v).strip() for v in row] for row in df.itertuples(index=False)], False
    text = _decode(data, what)
    sep = _sniff_sep(text)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=sep) if any(c.strip() for c in r)]
    if not rows:
        raise ValueError(f"The {what} file is empty.")
    width = len(rows[0])
    fixed = [[c.strip() for c in rows[0]]]
    for r in rows[1:]:
        if len(r) > width and len(r) >= 3:
            extra = len(r) - width
            r = [r[0], sep.join(r[1:2 + extra])] + r[2 + extra:]
        fixed.append([c.strip() for c in r])
    return fixed, sep == ";"


def _num(cell: str, decimal_comma: bool):
    """float, NaN for a blank cell, or None for a non-number."""
    cell = (cell or "").strip()
    if cell == "":
        return np.nan
    if decimal_comma:
        cell = cell.replace(",", ".")
    try:
        return float(cell)
    except ValueError:
        return None


def _find_col(header: list[str], test) -> int | None:
    for i, h in enumerate(header):
        if test(h.lower()):
            return i
    return None


def _unit(header_cell: str) -> str:
    m = re.search(r"\(([^()]*/[^()]*)\)\s*$", header_cell)
    return m.group(1) if m else ""


def _read_basic(src):
    rows, dc = _export_rows(src, "Basic estimates")
    header = rows[0]
    if any(_DIET_CORNER.search(h) for h in header):
        raise ValueError("The Basic estimates and Diet composition files look swapped: "
                         "the first file is a diet matrix.")
    name_i = _find_col(header, lambda h: h == "group name")
    bt_i = _find_col(header, lambda h: h.startswith("biomass ("))
    bh_i = _find_col(header, lambda h: h.startswith("biomass in habitat area"))
    area_i = _find_col(header, lambda h: h.startswith("habitat area"))
    pb_i = _find_col(header, lambda h: h.startswith("production / biomass"))
    qb_i = _find_col(header, lambda h: h.startswith("consumption / biomass"))
    if name_i is None or (bt_i is None and bh_i is None):
        raise ValueError("This does not look like an EwE Basic estimates (or Basic input) "
                         "export: it needs a 'Group name' and a 'Biomass' column.")
    unit = _unit(header[bt_i if bt_i is not None else bh_i])
    recs = []
    for r in rows[1:]:
        r = r + [""] * (len(header) - len(r))
        gid = _num(r[0], False)
        if gid is None or not np.isfinite(gid) or not r[name_i]:
            continue

        def val(i):
            return np.nan if i is None else _num(r[i], dc)

        if bt_i is not None:
            b = val(bt_i)
        else:
            bh, area = val(bh_i), val(area_i)
            area = 1.0 if area is None or not np.isfinite(area) else area
            b = None if bh is None else bh * area
        pb, qb = val(pb_i), val(qb_i)
        if b is None or pb is None or qb is None:
            raise ValueError(f"The Basic estimates file has a non-numeric value in the row "
                             f"for {r[name_i]!r} (decimals must use '.' in a "
                             "comma-separated file).")
        recs.append((int(gid), r[name_i], b, pb, qb))
    if not recs:
        raise ValueError("The Basic estimates file has no group rows.")
    g = pd.DataFrame(recs, columns=["GroupID", "GroupName", "Biomass", "ProdBiom", "ConsBiom"])
    return g, unit, bt_i is None


def _read_diet(src):
    rows, dc = _export_rows(src, "Diet composition")
    header = rows[0]
    if len(header) < 3 or not _DIET_CORNER.search(header[1]):
        if _find_col(header, lambda h: h == "group name") is not None:
            raise ValueError("The Basic estimates and Diet composition files look swapped: "
                             "the second file is a Basic estimates table.")
        raise ValueError("This does not look like an EwE Diet composition export: its "
                         "header should start with 'Prey \\ predator'.")
    pred_cols = []
    for j, h in enumerate(header[2:], start=2):
        v = _num(h, False)
        if v is not None and np.isfinite(v):
            pred_cols.append((j, int(v)))
    names, links, bad = {}, [], []
    for r in rows[1:]:
        gid = _num(r[0], False) if r else None
        if gid is None or not np.isfinite(gid) or len(r) < 2:
            continue
        if r[1].strip().lower() in _DIET_SUMMARY:
            continue
        names[int(gid)] = r[1]
        for j, pred in pred_cols:
            if j >= len(r):
                continue
            v = _num(r[j], dc)
            if v is None:
                bad.append(r[j])
            elif np.isfinite(v) and v > 0:
                links.append((pred, int(gid), v))
    if bad:
        raise ValueError(f"The Diet composition file has {len(bad)} non-numeric cell(s), e.g. "
                         f"{bad[0]!r} (decimals must use '.' in a comma-separated file).")
    return pd.DataFrame(links, columns=["PredID", "PreyID", "Diet"]), names


def parse_ecopath_exports(basic_src, diet_src):
    """Read an EwE GUI export pair -- "Basic estimates" (or "Basic input") and
    "Diet composition", CSV or .xlsx -- and return ``(G, info, notes)``.

    Groups are joined by their EwE group number. Exports carry no group Type,
    so it is inferred: a group with a Q/B or with diet entries is a consumer,
    one with only a P/B a producer, one with neither detritus. Biomass is the
    overall "Biomass" column (what the EwE database stores); a Basic input
    export has only "Biomass in habitat area", which is multiplied by the
    habitat area fraction. Raises ``ValueError`` (user-readable).
    """
    g, unit, from_habitat = _read_basic(basic_src)
    diet, diet_names = _read_diet(diet_src)

    by_id = dict(zip(g["GroupID"], g["GroupName"]))
    clash = [(i, by_id[i], n) for i, n in diet_names.items() if i in by_id and by_id[i] != n]
    if clash:
        i, a, b = clash[0]
        more = f" (+{len(clash) - 1} more)" if len(clash) > 1 else ""
        raise ValueError("The two files look like exports of different models: group "
                         f"{i} is {a!r} in Basic estimates but {b!r} in Diet "
                         f"composition{more}.")
    if not set(diet_names) & set(by_id):
        raise ValueError("The two files look like exports of different models: no group "
                         "number appears in both.")

    eaters = set(diet["PredID"])

    def has(x):
        return np.isfinite(x) and x > 0

    g["Type"] = [0 if (gid in eaters or has(qb)) else 1 if has(pb) else 2
                 for gid, pb, qb in zip(g["GroupID"], g["ProdBiom"], g["ConsBiom"])]
    g["Sequence"] = g["GroupID"]

    kind = "Basic input" if from_habitat else "Basic estimates"
    src = f"from the EwE {kind} export" + (f" ({unit})" if unit else "")
    if from_habitat:
        src += ", biomass in habitat area × habitat area fraction"
    G, info, notes = ecopath_tables_to_food_web(
        g, diet, biomass_source=src, where=f"in the {kind} export")
    notes.insert(1, "Group types (producer, consumer, detritus) were inferred from the "
                    "export: a Q/B or diet entries mean consumer, only a P/B producer, "
                    "neither detritus (exports do not record the EwE type).")
    return G, info, notes


__all__ = ["parse_ecopath_db", "parse_ecopath_exports", "ecopath_tables_to_food_web", "classify_group",
           "ACCEPTED_EXTENSIONS", "FG_DEFAULTS"]
