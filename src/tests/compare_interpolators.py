"""Compare interpolators AND matchers by rebuilding models in-process.

Now that the Neon x-calibration honours interpolator_method, the interpolator choice is a
real variable (previously every processed_* folder silently used PCHIP). This script rebuilds
the Ne+Si model for each requested optical path with several interpolators and reports the
resulting PST/CAL sample RMSE (cm-1), so the best option is chosen from evidence.

Matcher and interpolator are independent: the matcher selects/filters Ne<->reference pairs,
the interpolator fits the curve through them. Any matcher works with any interpolator.
``--matchers`` sweeps the full match_method x interpolator matrix and adds per-matcher anchor
diagnostics (inlier count, span vs the Si laser-zeroing wavelength, residual scatter and a
bimodality gap -- the P6_01002 OP1 doublet-alternation signature).

Usage:
    uv run python tests/compare_interpolators.py [KEY ...]
    uv run python tests/compare_interpolators.py --matchers --lasers 532 P6_0901 P6_0301 P6_01002
    uv run python tests/compare_interpolators.py --matchers all --ops OP1,OP3 P6_0901
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from ramanchada2.misc.utils.ramanshift_to_wavelength import shift_cm_1_to_abs_nm

from utils import load_config, get_config_units
from calib_paths import config_root, config_templates
from validate_calibration_build import (
    build_model, load_df, apply_one, _load_measured_samples,
    PST_TAG, CAL_TAG, SI_REF,
)

INTERPOLATORS = ["poly", "pchip", "pchipinverse", "pchippolyinverse", "cubic_spline", "rbf"]
MATCHERS = ["qargmin2d", "argmin2d", "cluster", "assignment", "monotonic", "dynamicp"]
# default subset for the (slow) matcher sweep: the production-relevant interpolators
SWEEP_INTERPOLATORS = ["poly", "pchipinverse", "pchippolyinverse"]


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


def anchor_diagnostics(cm, laser):
    """Per-matcher anchor stats from the Ne x-calibration component's matched_peaks.

    Independent of the interpolator: the matcher + robust filter decide the anchor set.
    Returns inlier/total counts, whether the Si wavelength is inside the inlier span, the
    widest internal gap around Si, residual MAD and a bimodality gap (nm): the largest split
    of the sorted inlier residuals into two >=3-point clusters separated by more than
    3x the within-cluster scatter (0 when unimodal).
    """
    df = cm.components[0].matched_peaks
    if df is None or "inlier_mask" not in df:
        return None
    inl = df[df["inlier_mask"].astype(bool)]
    x = np.sort(np.asarray(inl["spe"], float))
    r = np.asarray(inl["distances"], float)
    si_wl = shift_cm_1_to_abs_nm(SI_REF, laser)
    out = dict(n_in=len(inl), n_tot=len(df), lo=x.min() if len(x) else np.nan,
               hi=x.max() if len(x) else np.nan, si_wl=si_wl)
    # anchor gap straddling the Si wavelength (inf when Si is outside the span)
    i = np.searchsorted(x, si_wl)
    lo_n = x[i - 1] if i >= 1 else -np.inf
    hi_n = x[i] if i < len(x) else np.inf
    out["si_gap"] = hi_n - lo_n
    out["mad"] = float(np.median(np.abs(r - np.median(r)))) if len(r) else np.nan
    # bimodality: best 2-split of sorted residuals
    out["bimodal"] = 0.0
    rs = np.sort(r)
    for k in range(3, len(rs) - 2):
        a, b = rs[:k], rs[k:]
        gap = b.min() - a.max()
        scatter = max(np.median(np.abs(a - np.median(a))),
                      np.median(np.abs(b - np.median(b))), 0.02)
        if gap > 3 * scatter and gap > out["bimodal"]:
            out["bimodal"] = float(gap)
    return out


def orig_rmse(sub):
    e = np.asarray(sub["distances"], float)
    e = e[np.isfinite(e)]
    return float(np.sqrt(np.mean(e ** 2))) if len(e) else float("nan")


def main(keys, matchers=None, interpolators=None, ops=None, lasers=None):
    interpolators = interpolators or (SWEEP_INTERPOLATORS if matchers else INTERPOLATORS)
    orig = _load_measured_samples()
    for key in keys:
        cfg = load_config(os.path.join(config_root(), config_templates()))
        ne_units = get_config_units(cfg, key, tag="neon")
        si_units = get_config_units(cfg, key, tag="si")
        df = load_df(key)
        df = df[df["background"] == "BACKGROUND_SUBTRACTED"]
        print("=" * 96)
        print(f"{key}  sample RMSE (cm-1)  [units={ne_units}]")
        print("=" * 96)
        for (laser, op), op_data in df.groupby(["laser_wl", "optical_path"], dropna=False):
            if ops and str(op) not in ops:
                continue
            if lasers and int(laser) not in lasers:
                continue
            sub = orig[(orig["key"] == key) & (orig["optical_path"] == op) &
                       (orig["laser_wl"] == laser) & (orig["sample"].isin([PST_TAG, CAL_TAG]))]
            print(f"-- {op} {int(laser)}nm  orig RMSE {orig_rmse(sub):.2f}  "
                  f"(Si wl {shift_cm_1_to_abs_nm(SI_REF, int(laser)):.2f} nm)")
            header = (f"   {'matcher':11s} {'anchors':>7s} {'span(nm)':>11s} {'siGap':>6s} "
                      f"{'MAD':>5s} {'bimod':>6s} "
                      + " ".join(f"{i[:9]:>9s}" for i in interpolators))
            print(header)
            for matcher in (matchers or [None]):
                diag_txt = ""
                row = ""
                for j, interp in enumerate(interpolators):
                    try:
                        model, _ = build_model(op_data, int(laser), cfg, key,
                                               ne_units, si_units, interpolator=interp,
                                               match_method=matcher)
                        if j == 0:
                            d = anchor_diagnostics(model, int(laser))
                            if d:
                                diag_txt = (f"{d['n_in']}/{d['n_tot']:>3d} "
                                            f"{d['lo']:5.0f}-{d['hi']:<5.0f} "
                                            f"{d['si_gap']:6.1f} {d['mad']:5.2f} "
                                            f"{d['bimodal']:6.2f}")
                        r = sample_rmse(model, sub, si_units)
                        row += f"{r:>9.2f} "
                    except Exception as e:
                        row += f"{'ERR':>9s} "
                        if j == 0:
                            diag_txt = str(e)[:36]
                print(f"   {matcher or 'env':11s} {diag_txt:<38s} {row}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", default=["P6_0901"])
    ap.add_argument("--matchers", nargs="?", const=",".join(MATCHERS),
                    help="comma list of match methods to sweep (or 'all'); "
                         "omit flag = interpolator-only comparison with env.yaml matcher")
    ap.add_argument("--interpolators", help="comma list of interpolators to use")
    ap.add_argument("--ops", help="comma list of optical paths to include")
    ap.add_argument("--lasers", help="comma list of laser wavelengths to include")
    a = ap.parse_args()
    matchers = None
    if a.matchers:
        matchers = MATCHERS if a.matchers == "all" else a.matchers.split(",")
    main(a.keys or ["P6_0901"],
         matchers=matchers,
         interpolators=a.interpolators.split(",") if a.interpolators else None,
         ops=a.ops.split(",") if a.ops else None,
         lasers=[int(x) for x in a.lasers.split(",")] if a.lasers else None)
