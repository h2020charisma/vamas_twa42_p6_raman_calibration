from pathlib import Path
import pandas as pd
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
import ramanchada2.misc.constants as rc2const
from ramanchada2.misc.utils.ramanshift_to_wavelength import shift_cm_1_to_abs_nm
import matplotlib.pyplot as plt
import traceback
from utils import (find_peaks, plot_si_peak, get_config_units, 
                   load_config, get_config_findkw, init_logging)
import os.path
import numpy as np
from IPython.display import display


# + tags=["parameters"]
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
# -


logger = init_logging(Path(product["nb"]).parent , f"spectracal_{key}.log")

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
            logger.debug(f"*** Number of non-monotonic points: {nonmonotonic_count} ****")

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
        logger.error(err)


def test_shift(spe):
    if test_offset == 0:
        return spe
    else:
        spe_shifted = spe.set_new_xaxis(spe.x + test_offset)
        # print(f"{min(spe.x)}->{min(spe_shifted.x)}")
        return spe_shifted


def clip_nm_window(spe, win_lo_nm, win_hi_nm):
    # normalize window
    win_lo, win_hi = sorted([win_lo_nm, win_hi_nm])

    x = spe.x
    x_lo, x_hi = min(x), max(x)

    # intersection
    clip_lo = max(win_lo-10, x_lo)
    clip_hi = min(win_hi+10, x_hi)

    # detect no-overlap
    if clip_lo >= clip_hi:
        return spe 
    return spe.trim_axes(method='x-axis',  boundaries=(clip_lo, clip_hi))

def main(df, _config, _ne_units, _si_units, test_offset=0):
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
            logger.info("Using HDR merge")
            spe_neon = matching_row["spectrum"].iloc[0]
        else:
            spe_neon = op_data.loc[op_data["sample"] == neon_tag]["spectrum"].iloc[0]

        spe_neon = test_shift(spe_neon)

        spe_sil = op_data.loc[op_data["sample"] == si_tag]["spectrum"].iloc[0]
        spe_sil = test_shift(spe_sil)

        spe_sil.plot(ax=ax2, label=si_tag)
        ax2.set_xlabel(_si_units)

        if _si_units == "cm-1":
            spe_sil = spe_sil.trim_axes(method='x-axis', boundaries=(520.45-100, 520.45+100))
           

        # remove pedestal
        spe_sil.y = spe_sil.y - np.min(spe_sil.y)
        spe_sil = spe_sil.subtract_baseline_rc1_snip(niter=40)
        #spe_sil.plot(label="Si")
             
        spe_neon.plot(ax=ax1, label=neon_tag)
        ax1.set_xlabel(_ne_units)
        #spe_sil.plot(ax=ax2, label=si_tag)

        # False should be used for testing only . Fitting may take a while .

        neon_wl = rc2const.NEON_WL[laser_wl]
        logger.debug(neon_wl)
        # these are reference Ne peaks

        try:
            #find_kw = {"wlen": 200, "width": 1}
            find_kw = get_config_findkw(_config, key, "ne")
            logger.debug(find_kw)
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
            logger.info(model_neon1.model)
            model_neon1.model.plot(ax=ax3)
            plt.show()
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
            logger.debug(find_kw)
            # options for finding peaks    
            fit_peaks_kw = {}
            # options for fitting peaks       

            spe_sil_resampled = spe_sil

            spe_sil_ne_calib = model_neon1.process(
                spe_sil_resampled, spe_units=_si_units, convert_back=False
            )
            spe_sil_ne_calib.plot(ax=ax, label="Si [Ne calibrated only] len={}".
                                format(len(spe_sil_ne_calib.x)), fmt='+-')
            ax.set_xlabel("Wavelength/nm")
            ax.grid()
            #ay = ax.twiny()
            #ay.set_xlabel(_si_units)
            #spe_sil_resampled.plot(ax = ay, label="original", color="red")

            ne_calib = model_neon1.process(
                spe_neon, spe_units=_ne_units, convert_back=False
            )        
            # ne_calib.plot(ax=ax1, label="Ne calib")
            # spe_sil_ne_calib.plot(ax=ax1, label="Si")
            plot_calibration(model_neon1, min(ne_calib.x), max(ne_calib.x), ax=ax1)

            calmodel1.prominence_coeff = 3
            # in case there are nans from the calibration curve extrapolation
            spe_sil_ne_calib = spe_sil_ne_calib.dropna()
            find_kw["prominence"] = (
                spe_sil_ne_calib.y_noise_MAD() * calmodel1.prominence_coeff
            )

            lo_nm = shift_cm_1_to_abs_nm(520.45-100, laser_wl)
            hi_nm = shift_cm_1_to_abs_nm(520.45+100, laser_wl)
            si_peak_nm_left, si_peak_nm_right = sorted([lo_nm, hi_nm])
            spe_sil_ne_calib = clip_nm_window(spe_sil_ne_calib, si_peak_nm_left, si_peak_nm_right )

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
            logger.info(model_si)
            model_si.fit_res.plot(ax=ax, label="fitres",  linestyle='--')
            # print("fit_res", model_si.fit_res)
            logger.debug(len(spe_sil_ne_calib.x))
            display(model_si.peaks)
        except Exception:
            _success = False
            traceback.print_exc()

        if not _success:
            continue
        else:
            calmodel1.save(os.path.join(product["calmodels"],
                                    f"calmodel_{laser_wl}_{optical_path}.pkl"))
                
            calmodel1.plot()      
        # let's check the Si peak with Pearson4 profile
        si_peak = 520.45
        spe_sil_calibrated = calmodel1.apply_calibration_x(spe_sil, spe_units=_si_units)
        #has_nan = np.any(np.isnan(spe_sil_calibrated.x))
        _w = 50
        spe_test = spe_sil_calibrated.dropna().trim_axes(method='x-axis', boundaries=(si_peak-_w, si_peak+_w))
        # print(spe_test.x, spe_test.y)
        fitres, cand = find_peaks(spe_test,
                                profile="Pearson4",
                                find_kw=get_config_findkw(_config, key, "si"),
                                vary_baseline=False)
        if len(fitres) > 0:
            plot_si_peak(spe_sil, spe_test, fitres)

        tags = [neon_tag, si_tag, pst_tag, apap_tag, calcite_tag]


        # Calculate subplot grid dimensions
        n_plots = len(tags)
        n_cols = min(3, n_plots)  # Maximum 3 columns
        n_rows = int(np.ceil(n_plots / n_cols))

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(6*n_cols, 4*n_rows))

        # Flatten axes array for easy iteration
        axes = np.array(axes).flatten()

        for idx, (ax, tag) in enumerate(zip(axes[:n_plots], tags)):
            try:
                spe_match = op_data.loc[op_data["sample"] == tag, "spectrum"]
                if spe_match.empty:
                    continue
                spe = spe_match.iloc[0]
                spe = test_shift(spe)
                spe.y = spe.y - np.min(spe.y)
                spe_units=get_config_units(_config, key, 
                                                    tag="si" if tag in ["S0B","S0N"] else "ne" if tag in ["Neon"] else tag.lower())
                spe_cal = calmodel1.apply_calibration_x(
                    spe, spe_units=spe_units)
                if spe_units == "pixel":
                    spe.plot(label=f"{tag} [{spe_units}]", ax=ax.twinx())
                else:
                    spe.plot(label=tag, ax=ax)
                spe_cal.plot(label=f"calibrated {tag}", ax=ax, linestyle='--', color="orange")
                ax.grid()
                ax.legend()
                ax.set_title(tag)
            except Exception as err:
                traceback.print_exc()
                logger.error(f"Error processing {tag}: {err}")

        # Hide any unused subplots
        for idx in range(n_plots, len(axes)):
            axes[idx].set_visible(False)

        plt.tight_layout()
        plt.show()


Path(product["calmodels"]).mkdir(parents=True, exist_ok=True)

try:
    df = pd.read_hdf(upstream["spectraframe_*"][f"spectraframe_{key}"]["h5"], key="templates_read")
    _config = load_config(os.path.join(config_root, config_templates))
    _ne_units = get_config_units(_config, key, tag="neon")
    _si_units = get_config_units(_config, key, tag="si")
    main(df, _config, _ne_units, _si_units, test_offset)
except Exception as err:
    logger.error(err)
