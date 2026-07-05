"""Compare interpolators (and optionally matchers) by rebuilding models in-process.

Now that the Neon x-calibration honours interpolator_method, the interpolator choice is a
real variable (previously every processed_* folder silently used PCHIP). This script rebuilds
the Ne+Si model for each requested optical path with several interpolators and reports the
resulting PST/CAL sample RMSE (cm-1), so the best option is chosen from evidence.

Matcher and interpolator are independent: the matcher selects/filters Ne<->reference pairs,
the interpolator fits the curve through them. Any matcher works with any interpolator.

Usage:
    uv run python tests/compare_interpolators.py [KEY ...]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from utils import load_config, get_config_units
from calib_paths import config_root, config_templates
from validate_calibration_build import (
    build_model, load_df, apply_one, _load_measured_samples,
    PST_TAG, CAL_TAG, SI_REF,
)

INTERPOLATORS = ["poly", "pchip", "pchipinverse", "pchippolyinverse", "cubic_spline", "rbf"]


def sample_rmse(model, orig_rows, si_units):
    errs = []
    for _, r in orig_rows.iterrows():
        try:
            errs.append(apply_one(model, r["spe"], si_units) - r["reference"])
        except Exception:
            pass
    errs = np.asarray(errs, float)
    errs = errs[np.isfinite(errs)]
    return float(np.sqrt(np.mean(errs ** 2))) if len(errs) else float("nan")


def main(keys):
    orig = _load_measured_samples()
    for key in keys:
        cfg = load_config(os.path.join(config_root(), config_templates()))
        ne_units = get_config_units(cfg, key, tag="neon")
        si_units = get_config_units(cfg, key, tag="si")
        df = load_df(key)
        df = df[df["background"] == "BACKGROUND_SUBTRACTED"]
        print("=" * 78)
        print(f"{key}  sample RMSE (cm-1) per interpolator  [units={ne_units}]")
        print("=" * 78)
        header = f"{'OP':6s} {'laser':5s} " + " ".join(f"{i[:9]:>9s}" for i in INTERPOLATORS)
        print(header)
        for (laser, op), op_data in df.groupby(["laser_wl", "optical_path"], dropna=False):
            row = f"{str(op):6s} {int(laser):<5d} "
            sub = orig[(orig["key"] == key) & (orig["optical_path"] == op) &
                       (orig["laser_wl"] == laser) & (orig["sample"].isin([PST_TAG, CAL_TAG]))]
            for interp in INTERPOLATORS:
                try:
                    model, _ = build_model(op_data, int(laser), cfg, key,
                                           ne_units, si_units, interpolator=interp)
                    r = sample_rmse(model, sub, si_units)
                    row += f"{r:>9.2f} "
                except Exception:
                    row += f"{'ERR':>9s} "
            print(row)


if __name__ == "__main__":
    main(sys.argv[1:] or ["P6_0901"])
