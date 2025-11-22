import pandas as pd
import numpy as np
import traceback
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
from ramanchada2.protocols.calibration.xcalibration import LazerZeroingComponent, XCalibrationComponent
import ramanchada2.misc.constants as rc2const
from IPython.display import display
from scipy.interpolate import PchipInterpolator, RBFInterpolator
import os.path
import json
from utils import (get_config_units, load_config)
from scipy.signal import savgol_filter
from numpy.polynomial import Polynomial


# + tags=["parameters"]
product = None
config_templates = None
config_root = None
key = None
neon_tag = None
upstream = None
should_fit = None
extrapolate = None
# -


def process_neon(spe_neon, neon_units, neon_wl, title):
    if neon_units == "cm-1":
        spe_neon = spe_neon.shift_cm_1_to_abs_nm_filter(laser_wave_length_nm=neon_wl )
        neon_units = "nm"
    spe_neon.y = spe_neon.y / max(spe_neon.y)

    reference_peaks = rc2const.NEON_WL[neon_wl]
    fig, (ax, ax1) = plt.subplots(2,1, figsize=(12, 6))
    ax.set_xlabel(neon_units)
    ax1.set_xlabel("nm")
    spe_neon.plot(label = "Ne original", ax=ax)
    plt.suptitle(title)

    calibration_x = XCalibrationComponent(
        neon_wl,
        spe=spe_neon,
        spe_units="pixel",
        ref=reference_peaks,
        ref_units="nm",
        match_method="monotonic",
        interpolator_method="pchip",
        extrapolate=extrapolate
    )
    #calibration_x.derive_model(
        #find_kw=find_kw, fit_peaks_kw={}, should_fit=False, name="Ne"
    #)
    #calibration_x.plot()
    find_kw = {}
    find_kw["prominence"] = spe_neon.y_noise_MAD() * 20
    peaks_df = calibration_x.fit_peaks(find_kw, {}, should_fit=should_fit)
    peaks_df = peaks_df.sort_values(by="center", ascending=True).reset_index(drop=True)
    print(f"{title} peaks {peaks_df.shape[0]}")
    display(peaks_df[["center","amplitude","height"]])
    ref_keys = np.array(list(reference_peaks.keys()), dtype=float)
    ref_intensities = np.array(list(reference_peaks.values()), dtype=float)
    ref_intensities = ref_intensities/max(ref_intensities)
    measured_intensities = peaks_df["amplitude"].values
    measured_intensities = measured_intensities/max(measured_intensities)
    matched_peaks, matched_refs, pairs, DP, paths = match_peaks_1to1_skip(
            peaks_df["center"].values, ref_keys,
            # measured_intensities=None, ref_intensities=None,
            # measured_intensities=measured_intensities, ref_intensities=ref_intensities, 
            gap_penalty=None, tolerance=1)
    print(len(pairs), pairs)
    raw, ref = zip(*pairs)    
    try:
        x = np.array(raw) 
        spline = RBFInterpolator(x[:, None], np.array(ref), kernel="thin_plate_spline", smoothing=1e-3)
        #wavelengths_smooth = savgol_filter(np.array(ref), window_length=3, polyorder=2)
        #spline = PchipInterpolator(np.array(raw), wavelengths_smooth, extrapolate=extrapolate)
        #spline = Polynomial.fit(np.array(raw), np.array(ref), deg=3)  # returns a Polynomial object
        #spline = Polynomial.fit(np.array(raw), np.array(ref), deg=3)  # returns a Polynomial object
        #spline1 = RBFInterpolator(np.array(ref), np.array(raw), kernel="thin_plate_spline", smoothing=1e-3)
        #residual = spline1(np.array(ref)) - np.array(raw)
        #spline2 = RBFInterpolator(np.array(raw), residual, kernel="thin_plate_spline", smoothing=1e-3)
        nm_axis = spline(spe_neon.x[:, None])
        ax1.twinx().plot(nm_axis, spe_neon.y, label="calibrated")    
    except Exception:
        traceback.print_exc()
        spline = None
        nm_axis = None

    max_y = 1.1 * max(spe_neon.y)
    for i, mp in enumerate(matched_peaks, start=1):
        ax.vlines(mp, 0, max_y, color='r' , linestyles='dashed')  # vertical line from 0 to intensity    
        ax.text(mp, 0, str(i),
                ha='center', va='bottom',
                fontsize=8, rotation=0)                  

    pixels = np.array(list(reference_peaks.keys()))
    intensities = np.array(list(reference_peaks.values()))    
    max_y = 1.1 * max(intensities)
    min_y = -0.1 * max(intensities)
    for x, y in zip(pixels, intensities):
        ax1.vlines(x,0,y, color='black')
      
    for i, mp in enumerate(matched_refs, start=1):
        ax1.vlines(mp, 0, max_y, color='r' , linestyles='dashed')  
        ax1.text(mp, 0, str(i),
                ha='center', va='bottom',
                fontsize=8, rotation=0)          
    proxy = Line2D([0], [0], color='black')
    ax1.legend([proxy], ["Reference peaks"])
    #ax1.relim()
    #ax1.autoscale()    
    plt.show()
    fig, (ax, ax1) = plt.subplots(1,2, figsize=(12, 4))
    ax.plot(np.array(raw), np.array(ref), marker='x')
    if spline:
        ax.plot(spe_neon.x, spline(spe_neon.x[:,None]), color='red', linestyle="dashed")
    plot_dp_with_path(DP, paths, fig, ax1)
    plt.show()


def plot_dp_with_path(DP, path, fig, ax):
    df = pd.DataFrame(DP)

    cax = ax.imshow(df.values, origin='lower')
    fig.colorbar(cax, ax=ax, label="Cost")

    # ---- unpack path coordinates ----
    pi = [p[0] for p in path]
    pj = [p[1] for p in path]

    # ---- overlay the path ----
    ax.plot(pj, pi, linewidth=2)

    ax.set_xlabel("Reference index (j)")
    ax.set_ylabel("Measured index (i)")
    ax.set_title("DP Cost Matrix with Matched Path")

    plt.show()


def match_peaks_1to1_skip_no_intensity(measured_pixels, ref_wavelengths, gap_penalty=.5):
    """
    Monotonic alignment:
      - one-to-one matches only
      - skipping allowed
      - no DTW-style many-to-one mapping

    gap_penalty: cost of skipping a peak (pixel or reference).
    """

    mp = np.array(measured_pixels, dtype=float)
    rw = np.array(ref_wavelengths, dtype=float)

    # ---- Rough linear normalization so distances are comparable ----
    mp_norm = (mp - mp.min()) / (mp.max() - mp.min())
    rw_norm = (rw - rw.min()) / (rw.max() - rw.min())

    tolerance = 0.3
    k=.75
    gap_penalty = k * np.median(np.abs(np.diff(rw_norm)))
    print(f"gap_penalty {gap_penalty}")

    n, m = len(mp_norm), len(rw_norm)
    DP = np.full((n+1, m+1), np.inf)
    DP[0,0] = 0

    # --- Dynamic Programming table ---
    for i in range(n+1):
        for j in range(m+1):
            if i > 0:
                DP[i,j] = min(DP[i,j], DP[i-1,j] + gap_penalty)  # skip measured
            if j > 0:
                DP[i,j] = min(DP[i,j], DP[i,j-1] + gap_penalty)  # skip reference
            if i > 0 and j > 0:
                cost = abs(mp_norm[i-1] - rw_norm[j-1])         # match cost
                if cost > tolerance:
                    cost = 1   # force skip
                #cost = (mp_norm[i-1] - rw_norm[j-1])**2
                DP[i,j] = min(DP[i,j], DP[i-1,j-1] + cost)

    # --- Backtrack to get matches ---
    i, j = n, m
    pairs = []
    path = []
    while i > 0 or j > 0:
        # match
        #if i > 0 and j > 0 and DP[i,j] == DP[i-1,j-1] + abs(mp_norm[i-1] - rw_norm[j-1]):
        cost = abs(mp_norm[i-1] - rw_norm[j-1]) 
        if cost > tolerance:
            cost = 1   # force skip
        if i > 0 and j > 0 and DP[i,j] == DP[i-1,j-1] + cost:
            pairs.append((mp[i-1], rw[j-1]))
            path.append((i, j))  # DP coordinates
            i -= 1
            j -= 1
        # skip measured
        elif i > 0 and DP[i,j] == DP[i-1,j] + gap_penalty:
            i -= 1
        # skip reference
        else:
            j -= 1

    #display(pd.DataFrame(DP))
    path.append((0, 0))
    path = path[::-1]
    pairs.reverse()
    mp_out, rw_out = zip(*pairs) if pairs else ([], [])

    return np.array(mp_out), np.array(rw_out), pairs, DP, path


def match_peaks_1to1_skip(measured_pixels, ref_wavelengths,
                          measured_intensities=None, ref_intensities=None,
                          gap_penalty=None, k=0.75, tolerance=0.3,
                          alpha=1.0, beta=1.0):
    """
    Monotonic alignment: one-to-one matches only, skipping allowed.
    
    Intensity logic:
    - Strong peaks get match priority (lower match cost).
    - Weak peaks are cheap to skip.
    - Strong peaks are expensive to skip.
    
    alpha: controls match weighting strength
    beta: controls skip penalty inflation for strong peaks
    """

    mp = np.array(measured_pixels, dtype=float)
    rw = np.array(ref_wavelengths, dtype=float)

    n, m = len(mp), len(rw)

    # ---- Rough normalization to make distances comparable ----
    mp_norm = (mp - mp.min()) / (mp.max() - mp.min()) if n > 1 else np.zeros_like(mp)
    rw_norm = (rw - rw.min()) / (rw.max() - rw.min()) if m > 1 else np.zeros_like(rw)

    # Default gap penalty
    if gap_penalty is None:
        gap_penalty = k * np.median(np.abs(np.diff(rw_norm))) if m > 1 else k

    # DP table
    DP = np.full((n+1, m+1), np.inf)
    DP[0,0] = 0.0

    # ---- Normalize intensities ----
    if measured_intensities is not None:
        mi_norm = np.array(measured_intensities, dtype=float)
        mi_norm = mi_norm / (mi_norm.max() + 1e-12)
    if ref_intensities is not None:
        ri_norm = np.array(ref_intensities, dtype=float)
        ri_norm = ri_norm / (ri_norm.max() + 1e-12)

    # ---- Dynamic Programming ----
    for i in range(n+1):
        for j in range(m+1):

            # ======== skip measured ========
            if i > 0:
                gp = gap_penalty
                if measured_intensities is not None:
                    gp *= (1 + beta * mi_norm[i-1])     # strong peaks expensive to skip
                DP[i,j] = min(DP[i,j], DP[i-1,j] + gp)

            # ======== skip reference ========
            if j > 0:
                gp = gap_penalty
                if ref_intensities is not None:
                    gp *= (1 + beta * ri_norm[j-1])
                DP[i,j] = min(DP[i,j], DP[i,j-1] + gp)

            # ======== match i,j ========
            if i > 0 and j > 0:
                cost = abs(mp_norm[i-1] - rw_norm[j-1])
                if cost > tolerance:
                    cost = 1.0  # enforce skip path

                # strong peaks → lower match cost
                if measured_intensities is not None:
                    cost /= (1 + alpha * mi_norm[i-1])
                if ref_intensities is not None:
                    cost /= (1 + alpha * ri_norm[j-1])

                DP[i,j] = min(DP[i,j], DP[i-1,j-1] + cost)

    # ---- Backtrack ----
    i, j = n, m
    pairs = []
    path = []

    while i > 0 or j > 0:

        # match
        if i > 0 and j > 0:
            cost = abs(mp_norm[i-1] - rw_norm[j-1])
            if cost > tolerance:
                cost = 1.0
            if measured_intensities is not None:
                cost /= (1 + alpha * mi_norm[i-1])
            if ref_intensities is not None:
                cost /= (1 + alpha * ri_norm[j-1])

            if DP[i,j] == DP[i-1,j-1] + cost:
                pairs.append((mp[i-1], rw[j-1]))
                path.append((i,j))
                i -= 1
                j -= 1
                continue

        # skip measure
        if i > 0:
            gp = gap_penalty
            if measured_intensities is not None:
                gp *= (1 + beta * mi_norm[i-1])
            if DP[i,j] == DP[i-1,j] + gp:
                i -= 1
                continue

        # skip reference
        if j > 0:
            gp = gap_penalty
            if ref_intensities is not None:
                gp *= (1 + beta * ri_norm[j-1])
            if DP[i,j] == DP[i,j-1] + gp:
                j -= 1
                continue

    path.append((0,0))
    path = path[::-1]
    pairs.reverse()

    mp_out, rw_out = zip(*pairs) if pairs else ([], [])

    return np.array(mp_out), np.array(rw_out), pairs, DP, path


def load_config(path):
    with open(path, 'r') as file:
        _tmp = json.load(file)
    return _tmp


_config = load_config(os.path.join(config_root, config_templates))

try:
    for key in upstream["spectraframe_*"]:
        participant =key.replace("spectraframe_","")                    
        _ne_units = get_config_units(_config, participant, tag="neon")
        df = pd.read_hdf(upstream["spectraframe_*"][key]["h5"], key="templates_read")
        df_bkg_substracted = df.loc[df["background"] == "BACKGROUND_SUBTRACTED"]
        grouped_df = df_bkg_substracted.groupby(["laser_wl", "optical_path"], dropna=False)
        for group_keys, op_data in grouped_df:
            laser_wl = group_keys[0]
            optical_path = group_keys[1]
            
            title=f"{participant} {laser_wl} {optical_path}"
            matching_row = op_data.loc[(op_data["sample"] == neon_tag) & (op_data["overexposed"] == "HDR_MERGE")]
            if not matching_row.empty:
                title=f"{participant} {laser_wl} {optical_path} HDR"
                matching_row["spectrum"]
            else:
                title=f"{participant} {laser_wl} {optical_path}"
                matching_row = op_data.loc[op_data["sample"] == neon_tag]
            if matching_row.empty:
                print(f"No {neon_tag} in {title}, skipping")
                continue

            try:    
                process_neon(matching_row["spectrum"].iloc[0], _ne_units, laser_wl, title=title)
            except Exception as err:
                traceback.print_exc()
                continue
    #_config = load_config(os.path.join(config_root, config_templates))
    #_ne_units = get_config_units(_config, key, tag="neon")
    #main(df, _config, _ne_units)
except Exception:
    traceback.print_exc()
