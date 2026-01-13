from pathlib import Path
import pandas as pd
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
import ramanchada2.misc.constants as rc2const
from ramanchada2.spectrum import Spectrum
from ramanchada2.misc.utils.ramanshift_to_wavelength import (
    shift_cm_1_to_abs_nm, filter_ref_lines_for_raman
)
import matplotlib.pyplot as plt
import traceback
from utils import (find_peaks, plot_si_peak, get_config_units, 
                   load_config, get_config_findkw)
import os.path
from ramanchada2.protocols.calibration.qmatch import (
    universal_dispersion_calibration, diagnose_matching
    )

from ramanchada2.spectrum import Spectrum

# + tags=["parameters"]
upstream = None
product = None
config_templates = None
config_root = None
key = None
neon_tag = None
si_tag = None
pst_tag = None
apap_tag = None
calcite_tag = None
fit_neon_peaks = None
match_mode = None
interpolator = None
test_offset = 0
demo = True
# -


import matplotlib.pyplot as plt
import numpy as np

def plot_pairs_stems(pairs, ax=None, color='C0', label=None):
    """
    pairs: array of shape (N, 2)
           column 0 = measured coordinate
           column 1 = reference coordinate
    """
    if ax is None:
        fig, ax = plt.subplots()

    x = pairs[:, 0]
    y = pairs[:, 1]

    for xi, yi in zip(x, y):
        ax.plot([xi, xi], [(min(y)), yi], color="gray", alpha=0.7)

    ax.scatter(x, y,  s=10, label=label)
    ax.set_ylabel("Reference coordinate")
    ax.set_xlabel("Measured coordinate")

    if label:
        ax.legend()

    return ax

def test_shift(spe, offset=0):
    if offset == 0:
        return spe
    else:
        spe_shifted = spe.set_new_xaxis(spe.x + offset)
        # print(f"{min(spe.x)}->{min(spe_shifted.x)}")
        return spe_shifted
    

def main(df, _config, _ne_units, _si_units, test_offset=0):
    # now try calibration 
    df_bkg_substracted = df.loc[df["background"] == "BACKGROUND_SUBTRACTED"]
    #print(df_bkg_substracted.shape)
    grouped_df = df_bkg_substracted.groupby(["laser_wl", "optical_path"], dropna=False)
    find_kw = get_config_findkw(_config, key, "ne")
    #print(find_kw)
    # options for finding peaks    
    fit_peaks_kw = {}    
    for group_keys, op_data in grouped_df:
        _success = False

        laser_wl = group_keys[0]
        optical_path = group_keys[1]
        nist_peaks = filter_ref_lines_for_raman(ref_wavelengths=rc2const.ne_peaks_cwa[0],
                                                laser_wl_nm=laser_wl,
                                                raman_shift_range_cm_1=(-500, 4000))

        print("NIST peaks wl_max range ", min(nist_peaks), max(nist_peaks))
        
        
        # Check if a row with "sample" == "Neon" and "overexposed" == "HDR_MERGE" exists
        matching_row = op_data.loc[(op_data["sample"] == neon_tag) & (op_data["overexposed"] == "HDR_MERGE")]
        if not matching_row.empty:
            print("Using HDR merge")
            spe_neon = matching_row["spectrum"].iloc[0]
        else:
            spe_neon = op_data.loc[op_data["sample"] == neon_tag]["spectrum"].iloc[0]

        fig, (ax_spe, ax_cal) = plt.subplots(1,2, figsize=(15, 3))  
        ax_cal.vlines(
            nist_peaks,
            ymin=0,
            ymax=-0.25 * np.max(np.abs(spe_neon.y)),
            colors="gray",
            label="NIST"
        )   
        for offset in [0, 3, 5, 10]:
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 5))   
            ax1.set_title(f"{key} {laser_wl}nm {optical_path}  offset{offset}")
            spe_neon.plot(label="original", ax=ax1)          
            spe = test_shift(spe_neon, offset)
            spe.plot(label=f"{offset}", ax=ax1)     
            spe.plot(label=f"{offset}", ax=ax_spe)                          
            if find_kw is None:
                find_kw = {"sharpening": None}
            if fit_peaks_kw is None:
                fit_peaks_kw = {}
            # convert to ref_units
            cand = spe.find_peak_multipeak(**find_kw)
            fit_res = spe.fit_peak_multimodel(
                profile="Gaussian", candidates=cand, **fit_peaks_kw, no_fit=not fit_neon_peaks,
                bound_centers_to_group=True
            )
            center_err_threshold = 0.5
            if fit_neon_peaks:
                pos, amp = fit_res.center_amplitude(threshold=center_err_threshold)
                ax1.stem(
                    pos,
                    amp,
                    linefmt="g-",
                    basefmt="k-",
                    label=f"peaks (measured)",
                    markerfmt="bo"
                )                 
                spe_pos_dict = dict(zip(pos, amp))
            else:
                spe_pos_dict = cand.get_pos_ampl_dict()        
            measured = list(spe_pos_dict.keys())           

            diagnose_matching(np.array(measured), nist_peaks, laser_wl, 
                              use_quantile_map=_ne_units!="nm" )
            calibration = universal_dispersion_calibration(np.array(measured), nist_peaks,     
                                median_limit=None,  # Auto
                                n_sigma_match=6.0,
                                use_quantile_map=_ne_units!="nm" )
            plot_pairs_stems(calibration["pairs_inliers"], ax=ax3, label=f"offset {offset} #{len(calibration["pairs_inliers"])}")
            raman_axis = calibration["forward"](spe.x)

            dx = np.diff(raman_axis, prepend=raman_axis[0])
            print("min dx:", dx.min())
            print("any non-positive dx:", np.any(dx <= 0))
            mask = dx > 0
            x_clean = raman_axis[mask]
            y_clean = spe.y[mask]
            #x_clean = raman_axis
            #y_clean = spe.y
            spe_ne_calibrated = Spectrum(x_clean, y_clean)

            interp = (raman_axis >= min(nist_peaks)) & (raman_axis <= max(nist_peaks))
            spe_ne_calibrated = spe_ne_calibrated.trim_axes(method='x-axis', boundaries=(laser_wl, max(nist_peaks)))
            spe_ne_calibrated.plot(ax=ax2, label=f"{offset}")
            spe_ne_calibrated.plot(ax=ax_cal,label=f"{offset}")
            ax3.scatter(spe.x[interp], raman_axis[interp], s=1)

            #spe_ne_calibrated = Spectrum(raman_axis, spe.y)
            #spe_ne_calibrated.plot(label=f"calibrated {offset}", ax=ax2)
            #spe_resampled = spe_ne_calibrated.resample_spline_filter(
            #        x_range=(min(spe_ne_calibrated.x),max(spe_ne_calibrated.x)), 
            #        xnew_bins=len(spe.x), spline="pchip")
            _cand = spe_ne_calibrated.find_peak_multipeak(**find_kw)
            #print(_cand)
            _fit_res = spe_ne_calibrated.fit_peak_multimodel(
                profile="Gaussian", candidates=_cand, **fit_peaks_kw, no_fit=False,
                bound_centers_to_group=True
            )
            pos, amp = _fit_res.center_amplitude(threshold=center_err_threshold)
            ax2.stem(
                pos,
                amp,
                linefmt="g-",
                basefmt="k-",
                label=f"peaks (measured)",
                markerfmt="bo"
            )
            ax2.stem(
                calibration["pairs_inliers"][:,1],
                np.full_like(calibration["pairs_inliers"][:,1], 
                             fill_value=-0.25 * np.max(np.abs(spe_ne_calibrated.y))),
                linefmt="r-",
                basefmt="k-",
                label=f"NIST",
                markerfmt="ro"
            )    
            ax2.vlines(
                nist_peaks,
                ymin=0,
                ymax=-0.25 * np.max(np.abs(spe_ne_calibrated.y)),
                colors="gray",
                label="NIST"
            )                
                    
       

                


if demo:
    # measured peak positions (pixels)
    pixels = np.array([120, 345, 512, 689, 842, 1030, 1210, 1390])

    # known Ne lines (cm⁻1 or nm — doesn't matter)
    ne_lines = rc2const.ne_peaks_cwa[0] #np.array([540.1, 585.2, 614.3, 640.2, 703.2, 724.5, 743.9, 748.8])

    calibration = universal_dispersion_calibration(pixels, ne_lines)

    for key in calibration:
        print(key, calibration[key])

    plot_pairs_stems(calibration["pairs_inliers"])

    # convert full spectrum
    pixel_axis = np.arange(1600)
    raman_axis = calibration["forward"](pixel_axis)

    spe = Spectrum(pixel_axis, raman_axis)
    spe.plot()
else:
    #Path(product["calmodels"]).mkdir(parents=True, exist_ok=True)
    try:
        df = pd.read_hdf(upstream["spectraframe_*"][f"spectraframe_{key}"]["h5"], key="templates_read")
        _config = load_config(os.path.join(config_root, config_templates))
        _ne_units = get_config_units(_config, key, tag="neon")
        _si_units = get_config_units(_config, key, tag="si")
        main(df, _config, _ne_units, _si_units, test_offset)
    except Exception as err:
        traceback.print_exc()