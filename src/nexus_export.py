"""Importable helpers for the ``spectranexus_[[key]]`` Ploomber stage.

Deliberately free of module-level side effects (no ``product``/``upstream`` globals, no
I/O at import time) so these functions are unit-testable without the Ploomber DAG — see
docs/nexus_export_plan.md. The stage script (``spectraframe_nexus.py``) is a thin driver
over these.
"""
import math
import os

import numpy as np


def calmodel_filename(key, laser_wl, optical_path):
    """Match the existing ``calmodel_{laser_wl}_{optical_path}.pkl`` naming convention
    (spectraframe_calibrate.py) so files line up across the calmodels/, ycalmodels/ and
    nexus/ sibling directories."""
    return f"{key}_{laser_wl}_{optical_path}_calibration.nxs"


def nexus_sample_filename(key, laser_wl, optical_path, tag):
    return f"{key}_{laser_wl}_{optical_path}_{tag}.nxs"


def parse_calmodel_filename(filename):
    """Inverse of the ``calmodel_{laser_wl}_{optical_path}.pkl`` convention used by
    spectraframe_calibrate.py. Returns (laser_wl: int, optical_path: str) or None if the
    filename doesn't match (e.g. it's the ``_cwa`` sibling)."""
    base = os.path.basename(filename)
    if base.endswith(".pkl"):
        base = base[: -len(".pkl")]
    else:
        return None
    tags = base.split("_")
    if len(tags) < 3 or tags[0] != "calmodel":
        return None
    try:
        laser_wl = int(tags[1])
    except ValueError:
        return None
    optical_path = tags[2]
    return laser_wl, optical_path


def _is_missing(value):
    """True for values that must not be written to HDF5/NeXus: None, NaN, empty string.

    Blank Excel cells arrive as float('nan') via pandas; writing that as an h5py attribute
    would silently produce a meaningless float where a string (or nothing) was intended.
    """
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


# Front-sheet columns (utils.read_template's FRONT_SHEET_COLUMNS) that describe the
# instrument, as opposed to per-file/per-row bookkeeping (file_name, notes, ...).
INSTRUMENT_META_COLUMNS = (
    "instrument_make", "instrument_model", "laser_wl", "max_laser_power_mW",
    "spectral_range", "collection_optics", "slit_size", "grating", "pin_hole_size",
    "collection_fibre_diameter",
)


def nx_meta_from_row(row, columns=INSTRUMENT_META_COLUMNS):
    """Build an ``{attr_name: value}`` dict of instrument metadata from one spectraframe
    row, dropping NaN/None/empty values rather than writing them as meaningless floats or
    empty strings (see ``_is_missing``)."""
    meta = {}
    for col in columns:
        if col not in row:
            continue
        value = row[col]
        if _is_missing(value):
            continue
        meta[col] = value
    return meta


def axis_name_for_units(units):
    return {"cm-1": "raman_shift", "nm": "wavelength", "pixel": "pixel"}.get(units, "x")


def select_neon_spectrum(op_data, neon_tag):
    """Pick the calibrant Neon spectrum exactly as spectraframe_calibrate.py:117-122
    does: prefer the HDR merge if present, else the plain Neon row. Returns None if no
    matching row exists."""
    matching_row = op_data.loc[
        (op_data["sample"] == neon_tag) & (op_data["overexposed"] == "HDR_MERGE")]
    if not matching_row.empty:
        return matching_row["spectrum"].iloc[0], True
    plain = op_data.loc[op_data["sample"] == neon_tag]
    if plain.empty:
        return None, False
    return plain["spectrum"].iloc[0], False


def select_silicon_spectrum(op_data, si_tag):
    matching = op_data.loc[op_data["sample"] == si_tag]
    if matching.empty:
        return None
    return matching["spectrum"].iloc[0]


MANIFEST_COLUMNS = (
    "key", "laser_wl", "optical_path", "tag", "kind", "filename", "n_entries",
    "stages", "status", "error",
)


def manifest_row(key, laser_wl, optical_path, tag, kind, filename, n_entries=0,
                 stages="", status="ok", error=""):
    """One row of the nexus_manifest.csv product — the machine-checkable record of what
    was actually written, since a directory product can look complete after a partial
    failure (see docs/nexus_export_plan.md)."""
    return {
        "key": key, "laser_wl": laser_wl, "optical_path": optical_path, "tag": tag,
        "kind": kind, "filename": filename, "n_entries": n_entries, "stages": stages,
        "status": status, "error": error,
    }


def calibrant_units(config_units_fn, config, key, tag):
    """Thin wrapper documenting the contract: never assume cm-1 for calibrant axes.
    ``config_units_fn`` is utils.get_config_units, injected to avoid importing utils (and
    therefore Ploomber-notebook-adjacent modules) at module import time."""
    return config_units_fn(config, key, tag=tag)


def nan_safe(value):
    """Coerce a pandas/numpy scalar for safe use as an HDF5 attribute value: NaN -> None."""
    if isinstance(value, (float, np.floating)) and math.isnan(value):
        return None
    return value
