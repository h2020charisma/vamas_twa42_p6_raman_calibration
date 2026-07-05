"""In-process BUILD validator for the calibration fixes (no pickle loading).

Rebuilds the Neon x-calibration + Si laser-zeroing model for each optical path of a dataset
directly from the loaded spectra, using the CURRENT ramanchada2 code and the active env.yaml
config, then traces the real measured PST/CAL peaks (positions taken from the assessment CSV)
through apply_calibration_x. This mirrors spectraframe_calibrate.main() closely enough to judge
whether calibration moves sample peaks toward their certified values.

Because the model is BUILT here (not loaded from a .pkl produced by older code), this is the
correct way to validate ramanchada2 changes.

Usage:
    uv run python tests/validate_calibration_build.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import ramanchada2.misc.constants as rc2const
from ramanchada2.misc.utils.ramanshift_to_wavelength import shift_cm_1_to_abs_nm
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
from ramanchada2.spectrum import Spectrum

from utils import load_config, get_config_findkw, get_config_units
from calib_paths import load_env, config_root, config_output, config_templates

_ENV = load_env()
# calibration settings come straight from env.yaml (whatever the pipeline is configured with)
MATCH_MODE = _ENV["match_mode"]
INTERPOLATOR = _ENV["interpolator"]
FIT_NE_PEAKS = _ENV["fit_ne_peaks"]
NE_TAG = _ENV.get("ne_tag", "Neon")
SI_TAG = _ENV.get("si_tag", "S0B")
PST_TAG = _ENV.get("pst_tag", "PST")
CAL_TAG = _ENV.get("calcite_tag", "CAL")
SI_REF = 520.45


def load_df(key):
    h5 = glob.glob(os.path.join(config_output(), key, "spectraframe_load*.h5"))[0]
    return pd.read_hdf(h5, key="templates_read")


def build_model(op_data, laser, cfg, key, ne_units, si_units,
                interpolator=None, match_method=None):
    """Reproduce spectraframe_calibrate.main() Ne-curve + Si-zeroing for one OP.

    ``interpolator`` / ``match_method`` default to the env.yaml settings but can be
    overridden to compare options (they are independent of each other).
    """
    interpolator = interpolator or INTERPOLATOR
    match_method = match_method or MATCH_MODE
    hdr = op_data[(op_data["sample"] == NE_TAG) & (op_data["overexposed"] == "HDR_MERGE")]
    grp = op_data[op_data["sample"] == NE_TAG]
    spe_neon = (hdr if not hdr.empty else grp)["spectrum"].iloc[0]

    spe_sil = op_data[op_data["sample"] == SI_TAG]["spectrum"].iloc[0]
    if si_units == "cm-1":
        spe_sil = spe_sil.trim_axes(method="x-axis", boundaries=(SI_REF - 100, SI_REF + 100))
    spe_sil.y = spe_sil.y - np.min(spe_sil.y)
    spe_sil = spe_sil.subtract_baseline_rc1_snip(niter=40)

    cm = CalibrationModel(laser)
    cm.nonmonotonic = "drop"
    cm.prominence_coeff = 3
    find_ne = dict(get_config_findkw(cfg, key, "ne"))
    find_ne["prominence"] = spe_neon.y_noise_MAD() * 3
    model_ne = cm.derive_model_curve(
        spe=spe_neon, ref=rc2const.NEON_WL[laser], spe_units=ne_units, ref_units="nm",
        find_kw=find_ne, fit_peaks_kw={}, should_fit=FIT_NE_PEAKS, name="Neon",
        match_method=match_method, interpolator_method=interpolator, extrapolate=True,
    )
    # Si laser-zeroing on the Ne-calibrated Si spectrum
    spe_sil_nc = model_ne.process(spe_sil, spe_units=si_units, convert_back=False).dropna()
    find_si = dict(get_config_findkw(cfg, key, "si"))
    find_si["prominence"] = spe_sil_nc.y_noise_MAD() * 3
    lo = shift_cm_1_to_abs_nm(SI_REF - 100, laser)
    hi = shift_cm_1_to_abs_nm(SI_REF + 100, laser)
    lo, hi = sorted([lo, hi])
    spe_sil_nc = spe_sil_nc.trim_axes(method="x-axis", boundaries=(lo - 10, hi + 10))
    cm.derive_model_zero(
        spe=spe_sil_nc, ref={SI_REF: 1}, spe_units=model_ne.model_units, ref_units="cm-1",
        find_kw=find_si, fit_peaks_kw={}, should_fit=True, name="Si", profile="Pearson4",
    )
    laser0 = 1e7 / (1e7 / cm.components[1].model + SI_REF)
    anchor_lo = float(np.min(model_ne.model.x))
    return cm, dict(interp=type(model_ne.model).__name__, anchor_lo=anchor_lo,
                    laser0=laser0, laser0_err=laser0 - laser)


def apply_one(model, cm1, units="cm-1"):
    spe = Spectrum(x=np.array([float(cm1)]), y=np.array([1.0]))
    return float(model.apply_calibration_x(spe, spe_units=units).x[0])


def _load_measured_samples():
    """Measured (uncalibrated) sample peak positions from the current pipeline output.

    The ``1.original`` rows of the assessment CSV are calibration-independent, so they give
    the raw measured PST/CAL peaks to trace through freshly-built models.
    """
    from calib_paths import processed_dir
    hits = sorted(glob.glob(os.path.join(processed_dir(), "assessment",
                                          "matched_peaks_samples*.csv")))
    if not hits:
        raise FileNotFoundError(
            "No assessment/matched_peaks_samples*.csv under the processed dir; "
            "run the pipeline first (uv run ploomber build)."
        )
    samp = pd.read_csv(hits[-1])
    samp["before_after"] = samp["before_after"].str.strip()
    return samp[samp["before_after"] == "1.original"]


def main(keys=("P6_0901",)):
    orig = _load_measured_samples()
    for key in keys:
        cfg = load_config(os.path.join(config_root(), config_templates()))
        ne_units = get_config_units(cfg, key, tag="neon")
        si_units = get_config_units(cfg, key, tag="si")
        df = load_df(key)
        df = df[df["background"] == "BACKGROUND_SUBTRACTED"]
        print("=" * 90)
        print(f"{key}  (BUILT in-process: interpolator={INTERPOLATOR}, match={MATCH_MODE})")
        print("=" * 90)
        rows = []
        for (laser, op), op_data in df.groupby(["laser_wl", "optical_path"], dropna=False):
            try:
                model, diag = build_model(op_data, int(laser), cfg, key, ne_units, si_units)
            except Exception as e:
                print(f"  {op} {laser}: build failed: {e}")
                continue
            print(f"  {op} {int(laser)}nm: interp={diag['interp']} anchorLo={diag['anchor_lo']:.1f} "
                  f"Si_extrap={diag['anchor_lo'] > shift_cm_1_to_abs_nm(SI_REF, int(laser))} "
                  f"laser0_err={diag['laser0_err']:+.3f}nm")
            sub = orig[(orig["key"] == key) & (orig["optical_path"] == op) &
                       (orig["laser_wl"] == laser) & (orig["sample"].isin([PST_TAG, CAL_TAG]))]
            for _, r in sub.iterrows():
                new_err = apply_one(model, r["spe"], si_units) - r["reference"]
                rows.append(dict(OP=op, laser=int(laser), sample=r["sample"], ref=r["reference"],
                                 orig_err=round(r["distances"], 2), NEW_err=round(new_err, 2)))
        if rows:
            t = pd.DataFrame(rows)
            pd.set_option("display.width", 200)
            print(t.to_string(index=False))
            for op, g in t.groupby("OP"):
                o = np.sqrt(np.mean(g["orig_err"] ** 2))
                n = np.sqrt(np.mean(g["NEW_err"] ** 2))
                print(f"    {op} RMSE: orig {o:.2f} -> BUILT {n:.2f} cm-1")


if __name__ == "__main__":
    main(keys=("P6_0901", "P6_0101", "P6_01001"))
