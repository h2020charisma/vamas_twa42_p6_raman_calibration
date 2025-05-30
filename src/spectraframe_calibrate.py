from pathlib import Path
import pandas as pd
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
import ramanchada2.misc.constants as rc2const
from ramanchada2.misc.utils.ramanshift_to_wavelength import shift_cm_1_to_abs_nm
import matplotlib.pyplot as plt
import traceback
from utils import (find_peaks, plot_si_peak, get_config_units, 
                   load_config, get_config_findkw)
import os.path
import numpy as np



# + tags=["parameters"]
product = None
config_templates = None
config_root = None
key = None
neon_tag = None
si_tag = None
pst_tag = None
apap_tag = None
fit_neon_peaks = None
match_mode = None
interpolator = None
# -


def get_calibration_boundaries(model_ne):
    model = model_ne.model
    return (model.x.min(), model.x.max())


def plot_calibration(model_ne, xmin_nm, xmax_nm, npoints=2000, ax=None):
    try:
        model = model_ne.model
        x_range = np.linspace(xmin_nm, xmax_nm, npoints)
        predicted_y = model(x_range)
        diffs = np.diff(predicted_y)
        is_nonmonotonic = diffs < 0  # True where decreasing     
        nonmonotonic_count = np.count_nonzero(is_nonmonotonic)        
        if np.any(is_nonmonotonic):
            print(f"*** Number of non-monotonic points: {nonmonotonic_count} ****")

        # Plot monotonic and non-monotonic segments
        for i in range(len(x_range) - 1):
            if is_nonmonotonic[i]:
                continue
            ax.plot(x_range[i:i+2], predicted_y[i:i+2], color='blue')
        if nonmonotonic_count > 0:
            for i in range(len(x_range) - 1):
                if is_nonmonotonic[i]:
                    ax.plot(x_range[i:i+2], predicted_y[i:i+2], color='red')            
        # ax.scatter(x_range, predicted_y)
        ax.set_ylabel("Wavelength/nm")
        ax.set_xlabel("Wavelength/nm")
        if nonmonotonic_count > 0:
            ax.set_title(f"Number of non-monotonic points: {nonmonotonic_count} ")
        ax.grid()
    except Exception as err:
        print(err)


def main(df, _config, _ne_units):
    # now try calibration 
    df_bkg_substracted = df.loc[df["background"] == "BACKGROUND_SUBTRACTED"]
    #print(df_bkg_substracted.shape)
    grouped_df = df_bkg_substracted.groupby(["laser_wl", "optical_path"], dropna=False)
    for group_keys, op_data in grouped_df:
        _success = False
        fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 3)) 
        laser_wl = group_keys[0]
        optical_path = group_keys[1]

        ax1.set_title(f"{key} {laser_wl}nm {optical_path}")
        
        # Check if a row with "sample" == "Neon" and "overexposed" == "HDR_MERGE" exists
        matching_row = op_data.loc[(op_data["sample"] == neon_tag) & (op_data["overexposed"] == "HDR_MERGE")]
        if not matching_row.empty:
            print("Using HDR merge")
            spe_neon = matching_row["spectrum"].iloc[0]
        else:
            spe_neon = op_data.loc[op_data["sample"] == neon_tag]["spectrum"].iloc[0]

        spe_sil = op_data.loc[op_data["sample"] == si_tag]["spectrum"].iloc[0]
        spe_sil.plot(ax=ax2, label=si_tag)

        spe_sil = spe_sil.trim_axes(method='x-axis', boundaries=(520.45-100, 520.45+100))
        # remove pedestal
        spe_sil.y = spe_sil.y - np.min(spe_sil.y)
        spe_sil = spe_sil.subtract_baseline_rc1_snip(niter=40)
             
        spe_neon.plot(ax=ax1, label=neon_tag)
        ax1.set_xlabel(_ne_units)
        #spe_sil.plot(ax=ax2, label=si_tag)

        # False should be used for testing only . Fitting may take a while .

        neon_wl = rc2const.NEON_WL[laser_wl]
        # these are reference Ne peaks

        try:
            find_kw = {"wlen": 200, "width": 1}
            # options for finding peaks    
            fit_peaks_kw = {}
            # options for fitting peaks

            calmodel1 = CalibrationModel(laser_wl)
            calmodel1.nonmonotonic = "drop"
            # create CalibrationModel class. it does not derive a curve at this moment!
            calmodel1.prominence_coeff = 3
            find_kw["prominence"] = spe_neon.y_noise_MAD() * calmodel1.prominence_coeff

            model_neon1 = calmodel1.derive_model_curve(
                spe=spe_neon,
                ref=neon_wl,
                spe_units=_ne_units,
                ref_units="nm",
                find_kw=find_kw,
                fit_peaks_kw=fit_peaks_kw,
                should_fit=fit_neon_peaks,
                name="Neon calibration",
                match_method="argmin2d" if match_mode is None else match_mode,
                interpolator_method="pchip" if interpolator is None else interpolator,
                extrapolate=True
            )
            # now derive_model_curve finds peaks, fits peaks, matches peaks and derives the calibration curve
            # and model_neon.process() could be applied to Si or other spectra
            print(model_neon1.model)
            # calmodel1.plot(ax=ax2)
            model_neon1.model.plot(ax=ax3)
            _success = True 
        except Exception:
            _success = False
            traceback.print_exc()

        if not _success:
            continue
        ax1.grid()
        ax2.grid()

        # The second step of the X calibration - Laser zeroing

        try:
            fig, (ax, ax1) = plt.subplots(1, 2, figsize=(15, 3))
            find_kw = get_config_findkw(_config, key, "si")
            # options for finding peaks    
            fit_peaks_kw = {}
            # options for fitting peaks       

            if len(spe_sil.x) < 0:
                offset = (max(spe_sil.x)-min(spe_sil.x))/len(spe_sil.x)
                offset = offset / 4
                spe_sil_resampled = spe_sil.resample_spline_filter(
                    (min(spe_sil.x)+offset, max(spe_sil.x)-offset),
                    int(len(spe_sil.x)*4/3), spline='akima', cumulative=False)
            else:
                spe_sil_resampled = spe_sil

            spe_sil_ne_calib = model_neon1.process(
                spe_sil_resampled, spe_units="cm-1", convert_back=False
            )
            spe_sil_ne_calib.plot(ax=ax, label="Si [Ne calibrated only] len={}".
                                format(len(spe_sil_ne_calib.x)), fmt='+-')
            ax.set_xlabel("Wavelength/nm")
            ax.grid()

            if _ne_units == "nm":
                xmin_nm = min(spe_neon.x)
                xmax_nm = max(spe_neon.x)
            else:
                xmin_nm = shift_cm_1_to_abs_nm(min(spe_neon.x), laser_wave_length_nm=laser_wl)
                xmax_nm = shift_cm_1_to_abs_nm(max(spe_neon.x), laser_wave_length_nm=laser_wl)
            plot_calibration(model_neon1, xmin_nm, xmax_nm, ax=ax1)

            calmodel1.prominence_coeff = 3
            # in case there are nans from the calibration curve extrapolation
            spe_sil_ne_calib = spe_sil_ne_calib.dropna()
            find_kw["prominence"] = (
                spe_sil_ne_calib.y_noise_MAD() * calmodel1.prominence_coeff
            )
            model_si = calmodel1.derive_model_zero(
                spe=spe_sil_ne_calib,
                ref={520.45: 1},
                spe_units=model_neon1.model_units,
                ref_units="cm-1",
                find_kw=find_kw,
                fit_peaks_kw=fit_peaks_kw,
                should_fit=True,
                name="Si calibration",
                profile="Pearson4"
                # profile="Gaussian"
            )
            ax.axvline(x=model_si.model, color='black', linestyle='--', linewidth=2, label="Peak found {:.3f} nm".format(model_si.model))
            print(model_si)
            model_si.fit_res.plot(ax=ax, label="fitres",  linestyle='--')
            # print("fit_res", model_si.fit_res)
            print(len(spe_sil_ne_calib.x))
            print("peaks", model_si.peaks)
        except Exception:
            _success = False
            traceback.print_exc()

        if not _success:
            continue
        else:
            calmodel1.save(os.path.join(product["calmodels"],
                                    f"calmodel_{laser_wl}_{optical_path}.pkl"))
                
        # let's check the Si peak with Pearson4 profile
        si_peak = 520.45
        spe_sil_calibrated = calmodel1.apply_calibration_x(spe_sil)
        has_nan = np.any(np.isnan(spe_sil_calibrated.x))
        _w = 50
        spe_test = spe_sil_calibrated.dropna().trim_axes(method='x-axis', boundaries=(si_peak-_w, si_peak+_w))
        # print(spe_test.x, spe_test.y)
        fitres, cand = find_peaks(spe_test,
                                profile="Pearson4",
                                find_kw=get_config_findkw(_config, key, "si"),
                                vary_baseline=False)
        if len(fitres) > 0:
            plot_si_peak(spe_sil, spe_test, fitres)

        fig, (ax_pst, ax_apap) = plt.subplots(1, 2, figsize=(15, 3))
        try:
            spe_pst = op_data.loc[op_data["sample"] == pst_tag]["spectrum"].iloc[0]
            spe_pst.y = spe_pst.y - np.min(spe_pst.y)
            spe_pst_calibrated = calmodel1.apply_calibration_x(spe_pst)
            spe_pst.plot(label=pst_tag, ax=ax_pst)
            spe_pst_calibrated.plot(label=f"calibrated {pst_tag}", ax=ax_pst, 
                                    linestyle='--')
            ax_pst.grid()
        except Exception as err:
            print(err)

        try:
            spe_apap = op_data.loc[op_data["sample"] == apap_tag]["spectrum"].iloc[0]
            # pedestal
            spe_apap.y = spe_apap.y - np.min(spe_apap.y)
            spe_apap_calibrated = calmodel1.apply_calibration_x(spe_apap)
            spe_apap.plot(label=apap_tag, ax=ax_apap)
            spe_apap_calibrated.plot(label=f"calibrated {apap_tag}", 
                                        ax=ax_apap, linestyle='--')
            ax_apap.grid()
        except Exception as err:
            print(err)


Path(product["calmodels"]).mkdir(parents=True, exist_ok=True)

try:
    df = pd.read_hdf(upstream["spectraframe_*"][f"spectraframe_{key}"]["h5"], key="templates_read")
    _config = load_config(os.path.join(config_root, config_templates))
    _ne_units = get_config_units(_config, key, tag="neon")
    main(df, _config, _ne_units)
except Exception as err:
    print(err)
