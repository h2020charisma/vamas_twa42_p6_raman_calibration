import pandas as pd
import numpy as np
import traceback
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
from ramanchada2.protocols.calibration.xcalibration import LazerZeroingComponent, XCalibrationComponent
import ramanchada2.misc.constants as rc2const
from IPython.display import display
from scipy.interpolate import PchipInterpolator


# + tags=["parameters"]
product = None
config_templates = None
config_root = None
key = None
neon_tag = None
upstream = None
# -


def process_neon(spe_neon, neon_wl, title):
    reference_peaks = rc2const.NEON_WL[neon_wl]
    fig, (ax, ax1) = plt.subplots(2,1, figsize=(12, 4))
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
        extrapolate=True,
    )
    #calibration_x.derive_model(
        #find_kw=find_kw, fit_peaks_kw={}, should_fit=False, name="Ne"
    #)
    #calibration_x.plot()
    peaks_df = calibration_x.fit_peaks({}, {}, False)
    print(title)
    #display(peaks_df)
    ref_keys = np.array(list(reference_peaks.keys()), dtype=float)
    matched_peaks, matched_refs, pairs = match_peaks_1to1_skip(peaks_df["center"].values, ref_keys, gap_penalty=0.5)
    print(len(pairs), pairs)
    raw, ref = zip(*pairs)    
    spline = PchipInterpolator(np.array(raw), np.array(ref), extrapolate=False)
    nm_axis = spline(spe_neon.x)
    ax1.twinx().plot(nm_axis, spe_neon.y, label="calibrated")    

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
    ax.plot(np.array(raw), np.array(ref), marker='o')
    plt.show()


def match_peaks_1to1_skip(measured_pixels, ref_wavelengths, gap_penalty=.5):
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
                DP[i,j] = min(DP[i,j], DP[i-1,j-1] + cost)

    # --- Backtrack to get matches ---
    i, j = n, m
    pairs = []
    while i > 0 or j > 0:
        # match
        if i > 0 and j > 0 and DP[i,j] == DP[i-1,j-1] + abs(mp_norm[i-1] - rw_norm[j-1]):
            pairs.append((mp[i-1], rw[j-1]))
            i -= 1
            j -= 1
        # skip measured
        elif i > 0 and DP[i,j] == DP[i-1,j] + gap_penalty:
            i -= 1
        # skip reference
        else:
            j -= 1

    pairs.reverse()
    mp_out, rw_out = zip(*pairs) if pairs else ([], [])

    return np.array(mp_out), np.array(rw_out), pairs


try:
    for key in upstream["spectraframe_*"]:
        df = pd.read_hdf(upstream["spectraframe_*"][key]["h5"], key="templates_read")
        df_bkg_substracted = df.loc[df["background"] == "BACKGROUND_SUBTRACTED"]
        grouped_df = df_bkg_substracted.groupby(["laser_wl", "optical_path"], dropna=False)
        for group_keys, op_data in grouped_df:
            laser_wl = group_keys[0]
            optical_path = group_keys[1]
            participant =key.replace("spectraframe_","")            
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
                process_neon(matching_row["spectrum"].iloc[0], laser_wl, title=title)
            except Exception as err:
                traceback.print_exc()
                continue
    #_config = load_config(os.path.join(config_root, config_templates))
    #_ne_units = get_config_units(_config, key, tag="neon")
    #main(df, _config, _ne_units)
except Exception:
    traceback.print_exc()
