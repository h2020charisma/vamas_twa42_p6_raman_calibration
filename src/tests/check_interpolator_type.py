"""Check the ACTUAL Ne-calibration interpolator type as built (not loaded from pkl).

Loading a saved calmodel goes through CustomPolyInterpolator/CustomPChipInterpolator.from_dict,
which could normalise the type -- so inspecting a .pkl is not proof of what derive_model built.
This script builds the Neon calibration curve in-process from the real P6_0901 OP1 Neon spectrum,
for each requested `interpolator_method`, and prints the concrete interpolator class immediately.

Usage:
    uv run python tests/check_interpolator_type.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # src/ for utils

import ramanchada2.misc.constants as rc2const
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
import pandas as pd

from utils import load_config, get_config_findkw, get_config_units
from calib_paths import config_root, config_output, config_templates

KEY = "P6_0901"


def get_neon_op1():
    import glob
    hits = glob.glob(os.path.join(config_output(), KEY, "spectraframe_load*.h5"))
    df = pd.read_hdf(hits[0], key="templates_read")
    df = df.loc[df["background"] == "BACKGROUND_SUBTRACTED"]
    grp = df[(df["optical_path"] == "OP1") & (df["sample"] == "Neon")]
    hdr = grp.loc[grp["overexposed"] == "HDR_MERGE"]
    spe = (hdr if not hdr.empty else grp)["spectrum"].iloc[0]
    laser = int(grp["laser_wl"].iloc[0])
    return spe, laser


def main():
    _config = load_config(os.path.join(CONFIG_ROOT, CONFIG_TEMPLATES))
    ne_units = get_config_units(_config, KEY, tag="neon")
    find_kw = get_config_findkw(_config, KEY, "ne")
    spe_neon, laser = get_neon_op1()
    neon_wl = rc2const.NEON_WL[laser]
    print(f"{KEY} OP1  laser={laser}nm  ne_units={ne_units}  n_ref={len(neon_wl)}")
    for interp in ["poly", "pchip", "pchipinverse", "rbf"]:
        cm = CalibrationModel(laser)
        cm.nonmonotonic = "drop"
        cm.prominence_coeff = 3
        fk = dict(find_kw)
        fk["prominence"] = spe_neon.y_noise_MAD() * 3
        model_ne = cm.derive_model_curve(
            spe=spe_neon, ref=neon_wl, spe_units=ne_units, ref_units="nm",
            find_kw=fk, fit_peaks_kw={}, should_fit=True, name="Neon",
            match_method="qargmin2d", interpolator_method=interp, extrapolate=True,
        )
        built = type(model_ne.model).__name__
        print(f"  requested interpolator_method={interp:13s} -> BUILT {built}")


if __name__ == "__main__":
    main()
