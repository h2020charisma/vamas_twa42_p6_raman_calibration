"""CWA 18133 §8 / NXcalibration: the calibration workflow as a self-describing NeXus
record — calibrants, processing, and the reconstructable model (curve points, spline
knots / polynomial coefficients, Si zeroing) — per participant key.

See docs/nexus_export_plan.md for the design. Phase 1: the calibration bundle only (Ne/Si
calibrants + x/y calibration models). The raw/x-cal/y-cal sample-spectra triple is phase 2,
gated on extracting shared preprocessing out of calibration_verify.py.
"""
import glob
import os
import traceback
from pathlib import Path

import pandas as pd
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
from ramanchada2.protocols.calibration.serialization import export_nexus_calibration

from nexus_export import (
    calmodel_filename,
    manifest_row,
    nx_meta_from_row,
    parse_calmodel_filename,
    select_neon_spectrum,
    select_silicon_spectrum,
)
from utils import get_config_units, init_logging, load_config

# + tags=["parameters"]
product = None
config_templates = None
config_root = None
key = None
neon_tag = None
si_tag = None
pst_tag = None
apap_tag = None
calcite_tag = None
test_tags = None
match_mode = None
interpolator = None
# -


logger = init_logging(Path(product["nb"]).parent, f"spectranexus_{key}.log")


def _load_ycal_components(ycalmodels_dir, laser_wl, optical_path):
    """Mirror calibration_verify.py's ycalmodel lookup: glob
    ycalmodel_{wl}_{op}_{cert}.pkl and load each with CalibrationModel-independent pickle
    (YCalibrationComponent has no .json portable path of its own here; see
    spectraframe_ycalibrate.py). Returns a list, possibly empty."""
    import pickle
    pattern = os.path.join(ycalmodels_dir, f"ycalmodel_{laser_wl}_{optical_path}_*.pkl")
    components = []
    for pkl_file in glob.glob(pattern):
        try:
            with open(pkl_file, "rb") as f:
                components.append(pickle.load(f))
        except Exception:
            logger.error("failed to load %s", pkl_file)
            traceback.print_exc()
    return components


def export_one_calibration(df, config, calmodels_dir, ycalmodels_dir, nexus_dir,
                           laser_wl, optical_path):
    """Write one <key>_<laser_wl>_<optical_path>_calibration.nxs. Returns a manifest row."""
    out_name = calmodel_filename(key, laser_wl, optical_path)
    out_path = os.path.join(nexus_dir, out_name)

    df_bkg = df.loc[df["background"] == "BACKGROUND_SUBTRACTED"]
    op_data = df_bkg.loc[df_bkg["optical_path"] == optical_path]

    ne_units = get_config_units(config, key, tag="neon")
    si_units = get_config_units(config, key, tag="si")

    spe_neon, used_hdr = select_neon_spectrum(op_data, neon_tag)
    spe_sil = select_silicon_spectrum(op_data, si_tag)

    calmodel_path = os.path.join(calmodels_dir, f"calmodel_{laser_wl}_{optical_path}.pkl")
    calmodel = CalibrationModel.from_file(calmodel_path)

    ycal_components = _load_ycal_components(ycalmodels_dir, laser_wl, optical_path)
    ycal_component = ycal_components[0] if ycal_components else None

    instrument_row = op_data.iloc[0] if not op_data.empty else None
    instrument_meta = nx_meta_from_row(instrument_row) if instrument_row is not None else {}

    export_nexus_calibration(
        calmodel, out_path,
        spectral_range=(100.0, 3500.0), npoints=200,
        metadata={"key": key, "optical_path": optical_path, "laser_wl": laser_wl,
                 "match_method": match_mode, "interpolator": interpolator,
                 "neon_hdr_merge": bool(used_hdr)},
        instrument=instrument_meta,
        ycal_component=ycal_component,
        spe_neon=spe_neon, spe_neon_units=ne_units,
        spe_silicon=spe_sil, spe_silicon_units=si_units,
        title=f"{key} {laser_wl}nm {optical_path} x/y calibration",
        wavelength=laser_wl,
        provider=key,
        investigation="VAMAS TWA42 P6 round robin",
    )

    n_entries = 1 + (1 if ycal_component is not None else 0)
    stages = "x" + (",y" if ycal_component is not None else "")
    return manifest_row(key, laser_wl, optical_path, tag="", kind="calibration",
                        filename=out_name, n_entries=n_entries, stages=stages, status="ok")


def main(df, config, calmodels_dir, ycalmodels_dir, nexus_dir):
    manifest_rows = []
    pkl_files = [f for f in os.listdir(calmodels_dir) if f.endswith(".pkl")]
    pairs = sorted({parsed for f in pkl_files if (parsed := parse_calmodel_filename(f))})

    if not pairs:
        raise RuntimeError(
            f"[{key}] no calmodel_*.pkl found in {calmodels_dir}; nothing to export")

    for laser_wl, optical_path in pairs:
        try:
            manifest_rows.append(export_one_calibration(
                df, config, calmodels_dir, ycalmodels_dir, nexus_dir, laser_wl, optical_path))
        except Exception as err:
            logger.error("[%s] %s %s: %s", key, laser_wl, optical_path, err)
            traceback.print_exc()
            manifest_rows.append(manifest_row(
                key, laser_wl, optical_path, tag="", kind="calibration", filename="",
                status="error", error=str(err)))

    manifest = pd.DataFrame(manifest_rows)
    manifest.to_csv(product["manifest"], index=False)

    ok = (manifest["status"] == "ok").sum()
    logger.info("[%s] wrote %d/%d calibration NeXus files", key, ok, len(manifest))
    if ok == 0:
        # Every existing stage swallows per-item failures (try/except: traceback.print_exc())
        # which can leave an empty product directory behind a green build; this stage
        # instead fails loudly when nothing was actually produced. Partial failures are
        # still recorded (not raised) in the manifest for per-row auditing.
        raise RuntimeError(f"[{key}] zero calibration NeXus files written; see log/manifest")
    return manifest


Path(product["nexus"]).mkdir(parents=True, exist_ok=True)

_df = pd.read_hdf(
    upstream["spectraframe_*"][f"spectraframe_{key}"]["h5"], key="templates_read")
_config = load_config(os.path.join(config_root, config_templates))
_calmodels_dir = upstream["spectracal_*"][f"spectracal_{key}"]["calmodels"]
_ycalmodels_dir = upstream["spectracaly_*"][f"spectracaly_{key}"]["ycalmodels"]

main(_df, _config, _calmodels_dir, _ycalmodels_dir, product["nexus"])
