"""Report calibration-model diagnostics for the persisted pipeline models.

For every calmodel under the active processed_* folder (paths taken from env.yaml), print the
Neon interpolator type, the anchor span, whether the Silicon laser-zeroing peak falls outside
that span (extrapolated), and the solved laser wavelength error. This is a quick health check
of the models the pipeline produced -- inspecting existing artifacts, so loading the .pkl is
fine here. To validate CODE changes, rebuild instead (see validate_calibration_build.py).

Usage:
    uv run python tests/validate_calibration_fix.py
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from ramanchada2.misc.utils.ramanshift_to_wavelength import shift_cm_1_to_abs_nm
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel

from calib_paths import processed_dir

SI_REF_CM1 = 520.45


def diagnostics(pkl):
    laser = int(re.search(r"calmodel_(\d+)_", os.path.basename(pkl)).group(1))
    op = re.search(r"calmodel_\d+_(.+)\.pkl", os.path.basename(pkl))
    op = op.group(1) if op else "?"
    m = CalibrationModel.from_file(pkl)
    neon, si = m.components[0], m.components[1]
    anchor_lo = float(np.min(neon.model.x))
    d = dict(laser=laser, op=op, interp=type(neon.model).__name__,
             anchor_lo=anchor_lo, units=neon.spe_units)
    if neon.spe_units == "pixel":
        # anchors are pixel indices; the nm-based Si/laser diagnostics don't apply
        d.update(si_extrap=None, laser0_err=None)
    else:
        si_nm = shift_cm_1_to_abs_nm(SI_REF_CM1, laser)
        laser0 = 1e7 / (1e7 / si.model + SI_REF_CM1)
        d.update(si_extrap=bool(si_nm < anchor_lo), laser0_err=laser0 - laser)
    return d


def main():
    root = processed_dir()
    pkls = sorted(glob.glob(os.path.join(root, "*", "calmodels-*", "calmodel_*.pkl")))
    if not pkls:
        print(f"No calmodels under {root} -- run the pipeline first.")
        return
    print(f"Persisted models under {os.path.basename(root)}:\n")
    print(f"{'key':10s} {'OP':6s} {'laser':5s} {'interpolator':22s} "
          f"{'units':6s} {'anchorLo':8s} {'Si_extrap':9s} {'laser0_err':10s}")
    for pkl in pkls:
        key = os.path.basename(os.path.dirname(os.path.dirname(pkl)))
        d = diagnostics(pkl)
        if d["laser0_err"] is None:
            l0, extrap, flag = "   n/a", "n/a", "  <-- pixel units"
        else:
            l0 = f"{d['laser0_err']:+8.3f}nm"
            extrap = str(d["si_extrap"])
            flag = "  <-- check" if abs(d["laser0_err"]) > 0.3 else ""
        print(f"{key:10s} {d['op']:6s} {d['laser']:<5d} {d['interp']:22s} "
              f"{d['units']:6s} {d['anchor_lo']:<8.1f} {extrap:9s} {l0}{flag}")


if __name__ == "__main__":
    main()
