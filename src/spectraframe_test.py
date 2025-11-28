import pandas as pd
import numpy as np
import traceback
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
from ramanchada2.protocols.calibration.xcalibration import LazerZeroingComponent, XCalibrationComponent
import ramanchada2.misc.constants as rc2const
from ramanchada2.spectrum import Spectrum
from IPython.display import display
import os.path
import json
from utils import (get_config_units, load_config)
from scipy.signal import savgol_filter
from numpy.polynomial import Polynomial
from matchpeaks import (
    match_peaks_1to1_skip, match_peaks_position_intensity,match_peaks_auto_k,
    match_peaks_ready, 
    model_fit, model_predict
)


# + tags=["parameters"]
product = None
config_templates = None
config_root = None
key = None
neon_tag = None
si_tag = None
upstream = None
should_fit = None
extrapolate = None
interpolator = None
enabled = None
# -


def process_si(spe_si,  spline, spe_units, laser_wl ):
    fig, (ax, ax1, ax2) = plt.subplots(3,1, figsize=(12, 6))
    spe_si.plot(ax=ax, label=si_tag)
    if spe_units == "cm-1":
        spe_si = spe_si.trim_axes(method='x-axis', boundaries=(520.45-50, 520.45+50))        
        spe_si = spe_si.shift_cm_1_to_abs_nm_filter(laser_wave_length_nm=laser_wl )
        spe_units = "nm"
    spe_si_necalibrated = Spectrum(model_predict(spline, spe_si.x, interpolator), spe_si.y)
    spe_si_necalibrated.plot(ax=ax1)
    find_kw = {"prominence" :
        spe_si_necalibrated.y_noise_MAD() * 3
    }
    calibration_shift = LazerZeroingComponent(
        laser_wl, spe_si_necalibrated, "nm"
    )    
    calibration_shift.derive_model(
        find_kw=find_kw, fit_peaks_kw={}, should_fit=True, name=""
    )    
    print(calibration_shift)
    spe_si_zero = calibration_shift.process(spe_si_necalibrated)
    spe_si_zero.plot(ax=ax2)
    #calibration_shift.plot()
    return calibration_shift

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
    find_kw["prominence"] = spe_neon.y_noise_MAD() * 3
    peaks_df = calibration_x.fit_peaks(find_kw, {}, should_fit=should_fit)
    peaks_df = peaks_df.sort_values(by="center", ascending=True).reset_index(drop=True)
    print(f"{title} peaks {peaks_df.shape[0]}")
    #display(peaks_df[["center","amplitude","height","fwhm"]])
    ref_keys = np.array(list(reference_peaks.keys()), dtype=float)
    ref_intensities = np.array(list(reference_peaks.values()), dtype=float)
    ref_intensities = ref_intensities/max(ref_intensities)
    measured_intensities = peaks_df["height"].values
    #measured_intensities = measured_intensities/max(measured_intensities)
    median_step = np.median(np.diff(np.sort(ref_keys)))
    #tolerance = median_step / (ref_keys.max() - ref_keys.min())    
    #print(f"tolerance {tolerance}")
    #matched_peaks, matched_refs, pairs, DP, paths = match_peaks_1to1_skip(
    matched_peaks, matched_refs, pairs, DP, paths, k = match_peaks_ready(
        
            peaks_df["center"].values, ref_keys,
            # measured_intensities=None, ref_intensities=None,
            measured_intensities=measured_intensities,
            #gap_penalty=None, tolerance=1, beta=0
            #alpha=.1, tolerance = tolerance,
            gamma=0.1,
            normalize = neon_units=="pixel"
            )
    #print(f"k={k}")
    print(len(pairs), pairs)
    raw, ref = zip(*pairs)    
    try:
        x = np.array(raw) 
        #spline = RBFInterpolator(x[:, None], np.array(ref), kernel="thin_plate_spline", smoothing=1e-3)
        spline = model_fit(x, np.array(ref), interpolator, extrapolate)
        #wavelengths_smooth = savgol_filter(np.array(ref), window_length=3, polyorder=2)
        #spline = PchipInterpolator(np.array(raw), wavelengths_smooth, extrapolate=extrapolate)
        #spline = Polynomial.fit(np.array(raw), np.array(ref), deg=3)  # returns a Polynomial object
        #spline = Polynomial.fit(np.array(raw), np.array(ref), deg=3)  # returns a Polynomial object
        #spline1 = RBFInterpolator(np.array(ref), np.array(raw), kernel="thin_plate_spline", smoothing=1e-3)
        #residual = spline1(np.array(ref)) - np.array(raw)
        #spline2 = RBFInterpolator(np.array(raw), residual, kernel="thin_plate_spline", smoothing=1e-3)
        nm_axis = model_predict(spline, spe_neon.x, interpolator, extrapolate)
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
        ax.plot(spe_neon.x, model_predict(spline, spe_neon.x, "rbf"), color='red', linestyle="dashed")
    plot_dp_with_path(DP, paths, fig, ax1)
    plt.show()
    return spline


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


def load_config(path):
    with open(path, 'r') as file:
        _tmp = json.load(file)
    return _tmp


_config = load_config(os.path.join(config_root, config_templates))

if enabled:
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
                    spline = process_neon(matching_row["spectrum"].iloc[0], _ne_units, laser_wl, title=title)
                except Exception as err:
                    traceback.print_exc()
                    continue
                if not spline:
                    continue
                try:
                    matching_row = op_data.loc[op_data["sample"] == si_tag]
                    if matching_row.empty:
                        print(f"No {si_tag} in {title}, skipping")
                        continue
                    _si_units = get_config_units(_config, participant, tag="si")
                    calibration_shift = process_si(matching_row["spectrum"].iloc[0], spline, _si_units, laser_wl)
                except Exception as err:
                    traceback.print_exc()
                    continue
        #_config = load_config(os.path.join(config_root, config_templates))
        #_ne_units = get_config_units(_config, key, tag="neon")
        #main(df, _config, _ne_units)
    except Exception:
        traceback.print_exc()
