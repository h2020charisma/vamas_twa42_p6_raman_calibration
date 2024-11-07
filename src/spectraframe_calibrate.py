# + tags=["parameters"]
upstream = ["spectraframe_01", "spectraframe_04", "spectraframe_07"]
product = None
config_templates: "{{config_templates}}"
config_root: "{{config_root}}"
key = None
neon_tag = None
si_tag = None
pst_tag = None
fit_neon_peaks = None
# -

from pathlib import Path
import pandas as pd
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
import ramanchada2.misc.constants as rc2const
import matplotlib.pyplot as plt
import traceback
from utils import find_peaks, plot_si_peak, get_config_units, load_config
import os.path

Path(product["calmodels"]).mkdir(parents=True, exist_ok=True)
df = pd.read_hdf(upstream[f"spectraframe_{key}"]["h5"], key="templates_read")

_config = load_config(os.path.join(config_root, config_templates))
_ne_units = get_config_units(_config, key, tag="neon")

# now try calibration 
df_bkg_substracted = df.loc[df["background"] == "BACKGROUND_SUBTRACTED"]
print(df_bkg_substracted.shape)
grouped_df = df_bkg_substracted.groupby(["laser_wl", "optical_path"], dropna=False)
for group_keys, op_data in grouped_df:
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 5)) 
    laser_wl = group_keys[0]
    optical_path = group_keys[1]

    spe_neon = op_data.loc[op_data["sample"] == neon_tag]["spectrum"].iloc[0]
    spe_sil = op_data.loc[op_data["sample"] == si_tag]["spectrum"].iloc[0]

    spe_sil = spe_sil.trim_axes(method='x-axis', boundaries=(520.45-50, 520.45+50))
    spe_neon.plot(ax=ax1, label=neon_tag)
    spe_sil.plot(ax=ax2, label=si_tag)

    # False should be used for testing only . Fitting may take a while .

    neon_wl = rc2const.NEON_WL[laser_wl]
    # these are reference Ne peaks

    try:
        find_kw = {"wlen": 200, "width": 1}
        # options for finding peaks    
        fit_peaks_kw = {}
        # options for fitting peaks

        calmodel1 = CalibrationModel(laser_wl)
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
            match_method="argmin2d",
            interpolator_method="pchip",
            extrapolate=False
        )
        # now derive_model_curve finds peaks, fits peaks, matches peaks and derives the calibration curve
        # and model_neon.process() could be applied to Si or other spectra
        print(model_neon1)
        #calmodel1.plot(ax=ax2)
        model_neon1.model.plot(ax=ax3)        
    except Exception as err:
        traceback.print_exc()

    # The second step of the X calibration - Laser zeroing
    # 
    try:           
        find_kw = {"wlen": 200, "width": 1}
        # options for finding peaks    
        fit_peaks_kw = {}
        # options for fitting peaks         
        spe_sil_ne_calib = model_neon1.process(
            spe_sil, spe_units="cm-1", convert_back=False
        )
        calmodel1.prominence_coeff = 3
        find_kw["prominence"] = (
            spe_sil_ne_calib.y_noise_MAD() * calmodel1.prominence_coeff
        )
        calmodel1.derive_model_zero(
            spe=spe_sil_ne_calib,
            ref={520.45: 1},
            spe_units=model_neon1.model_units,
            ref_units="cm-1",
            find_kw=find_kw,
            fit_peaks_kw=fit_peaks_kw,
            should_fit=True,
            name="Si calibration",
            profile="Pearson4"
        )
    except Exception as err:
        traceback.print_exc()

    # let's check the Si peak with Pearson4 profile
    si_peak = 520.45
    spe_sil_calibrated = calmodel1.apply_calibration_x(spe_sil)
    _w = 50
    spe_test = spe_sil_calibrated.trim_axes(method='x-axis',boundaries=(si_peak-_w, si_peak+_w))
    fitres, cand = find_peaks(spe_test, profile="Pearson4", vary_baseline=True)
    plot_si_peak(calmodel1, spe_sil, fitres)
    calmodel1.save(os.path.join(product["calmodels"], f"calmodel_{laser_wl}_{optical_path}.pkl"))

    spe_pst = op_data.loc[op_data["sample"] == pst_tag]["spectrum"].iloc[0]
    spe_pst_calibrated = calmodel1.apply_calibration_x(spe_pst)
    fig, ax = plt.subplots(1, 1, figsize=(15, 3))
    spe_pst.plot(label=pst_tag, ax=ax)
    spe_pst_calibrated.plot(label=f"calibrated {pst_tag}", ax=ax ,linestyle='--')
    ax.grid()
