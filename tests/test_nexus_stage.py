"""Unit tests for the pure helpers in src/nexus_export.py — synthetic data, no DAG, no
real spectra. See docs/nexus_export_plan.md."""
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nexus_export import (  # noqa: E402
    INSTRUMENT_META_COLUMNS,
    MANIFEST_COLUMNS,
    axis_name_for_units,
    calmodel_filename,
    manifest_row,
    nan_safe,
    nexus_sample_filename,
    nx_meta_from_row,
    parse_calmodel_filename,
    select_neon_spectrum,
    select_silicon_spectrum,
)


def test_calmodel_filename_matches_pkl_convention():
    assert calmodel_filename("P6_0301", 785, "OP1") == "P6_0301_785_OP1_calibration.nxs"


def test_nexus_sample_filename():
    assert nexus_sample_filename("P6_0301", 785, "OP1", "PST") == "P6_0301_785_OP1_PST.nxs"


@pytest.mark.parametrize("filename,expected", [
    ("calmodel_785_OP1.pkl", (785, "OP1")),
    ("calmodel_532_OP2.pkl", (532, "OP2")),
    ("calmodel_785_OP1_cwa.csv", None),  # not a .pkl
    ("calmodel_785_OP1.json", None),  # not a .pkl
    ("ycalmodel_785_OP1_NIST785_SRM2241.pkl", None),  # wrong prefix
    ("not_a_calmodel.pkl", None),
])
def test_parse_calmodel_filename(filename, expected):
    assert parse_calmodel_filename(filename) == expected


def test_nx_meta_from_row_drops_nan():
    """Blank Excel cells arrive as float('nan') via pandas; writing that as an HDF5
    attribute would silently produce a meaningless float where a string was intended."""
    row = pd.Series({
        "instrument_make": "TestCo",
        "instrument_model": float("nan"),
        "grating": "",
        "laser_wl": 785,
        "notes": "not an instrument field",
    })
    meta = nx_meta_from_row(row)
    assert meta["instrument_make"] == "TestCo"
    assert meta["laser_wl"] == 785
    assert "instrument_model" not in meta
    assert "grating" not in meta
    assert "notes" not in meta  # not in INSTRUMENT_META_COLUMNS


def test_nx_meta_from_row_missing_column_skipped():
    row = pd.Series({"instrument_make": "TestCo"})
    meta = nx_meta_from_row(row)
    assert meta == {"instrument_make": "TestCo"}
    assert set(meta) <= set(INSTRUMENT_META_COLUMNS)


@pytest.mark.parametrize("units,expected", [
    ("cm-1", "raman_shift"), ("nm", "wavelength"), ("pixel", "pixel"), ("bogus", "x"),
])
def test_axis_name_for_units(units, expected):
    assert axis_name_for_units(units) == expected


def _op_data(rows):
    return pd.DataFrame(rows)


def test_select_neon_spectrum_prefers_hdr_merge():
    op_data = _op_data([
        {"sample": "Neon", "overexposed": "NO", "spectrum": "plain"},
        {"sample": "Neon", "overexposed": "HDR_MERGE", "spectrum": "hdr"},
    ])
    spe, used_hdr = select_neon_spectrum(op_data, "Neon")
    assert spe == "hdr"
    assert used_hdr is True


def test_select_neon_spectrum_falls_back_without_hdr():
    op_data = _op_data([{"sample": "Neon", "overexposed": "NO", "spectrum": "plain"}])
    spe, used_hdr = select_neon_spectrum(op_data, "Neon")
    assert spe == "plain"
    assert used_hdr is False


def test_select_neon_spectrum_missing_tag_returns_none():
    op_data = _op_data([{"sample": "PST", "overexposed": "NO", "spectrum": "x"}])
    spe, used_hdr = select_neon_spectrum(op_data, "Neon")
    assert spe is None
    assert used_hdr is False


def test_select_silicon_spectrum_missing_tag_returns_none():
    op_data = _op_data([{"sample": "PST", "spectrum": "x"}])
    assert select_silicon_spectrum(op_data, "S0B") is None


def test_select_silicon_spectrum_found():
    op_data = _op_data([{"sample": "S0B", "spectrum": "sil"}])
    assert select_silicon_spectrum(op_data, "S0B") == "sil"


def test_manifest_row_schema():
    row = manifest_row("P6_0301", 785, "OP1", "", "calibration", "f.nxs", n_entries=2,
                       stages="x,y", status="ok")
    assert set(row) == set(MANIFEST_COLUMNS)
    assert row["status"] == "ok"


def test_manifest_columns_build_valid_dataframe():
    rows = [
        manifest_row("K", 785, "OP1", "", "calibration", "a.nxs", status="ok"),
        manifest_row("K", 532, "OP2", "", "calibration", "", status="error", error="boom"),
    ]
    df = pd.DataFrame(rows)
    assert list(df.columns) == list(MANIFEST_COLUMNS)
    assert (df["status"] == "ok").sum() == 1


def test_nan_safe():
    assert nan_safe(float("nan")) is None
    assert nan_safe(1.5) == 1.5
    assert nan_safe("text") == "text"
    assert math.isnan(float("nan"))  # sanity on the fixture itself
