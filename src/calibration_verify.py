import os
import pandas as pd
from IPython.display import display
import matplotlib.pyplot as plt
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
from utils import (find_peaks, plot_si_peak, load_config, get_config_findkw)

# + tags=["parameters"]
product = None
config_templates: "{{config_templates}}"
config_root: "{{config_root}}"
# -

_config = load_config(os.path.join(config_root, config_templates))


def plot_model(calmodel, entry, laser_wl, optical_path, spe_sils=None):
    fig, (ax, ax1, ax2) = plt.subplots(1, 3, figsize=(15, 3))
    # print(modelfile, tags)
    calmodel.components[0].model.plot(ax=ax)
    fig.suptitle(f"[{entry}] {laser_wl}nm {optical_path}")
    calmodel.plot(ax=ax1)
    ax1.grid()
    si_peak = calmodel.components[1].model
    ax1.axvline(x=si_peak, color='black', linestyle='--', linewidth=2, label="Si peak {:.3f} nm".format(si_peak))    
    if spe_sils is not None:
        for spe_sil in spe_sils:
            sil_calibrated = calmodel.apply_calibration_x(spe_sil)
            try:
                fitres, cand = find_peaks(sil_calibrated,
                                          profile="Pearson4",
                                          find_kw=get_config_findkw(_config, 
                                                                    entry, "si")
                                          )
            except Exception as err:
                fitres = None
                print(err)
            plot_si_peak(spe_sil, sil_calibrated, fitres=fitres, ax=ax2)


def average_spe(df, tag):
    spe_sum = None
    spes = df.loc[df["sample"] == tag]["spectrum"].values
    for spe_sil in spes:
        spe_sum = spe_sil if spe_sum is None else spe_sum+spe_sil
    return spe_sum/len(spes)


for key in upstream["spectracal_*"].keys():
    # print(key)
    entry = key.replace("spectracal_","")
    key_frame = key.replace("spectracal","spectraframe")
    data_file = upstream["spectraframe_*"][key_frame]["h5"]
    spectra_frame = pd.read_hdf(data_file, key="templates_read")
    df_bkg_substracted = spectra_frame.loc[spectra_frame["background"] == "BACKGROUND_SUBTRACTED"]

    folder_path = upstream["spectracal_*"][key]["calmodels"]
    pkl_files = [file for file in os.listdir(folder_path) if file.endswith(".pkl")]
    for modelfile in pkl_files:
        tags = os.path.basename(modelfile).replace(".pkl", "").split("_")
        optical_path = tags[2]
        laser_wl = int(tags[1])        
        calmodel = CalibrationModel.from_file(os.path.join(folder_path, modelfile))        
        op_data = df_bkg_substracted.loc[df_bkg_substracted["optical_path"] == optical_path]
        spe_sum = None
        spe_sil = average_spe(op_data, "S0B").trim_axes(method='x-axis', 
                                                        boundaries=(520.45-50, 520.45+50))
        plot_model(calmodel, entry, laser_wl, optical_path, [spe_sil])
        fig, (ax, ax1, ax2) = plt.subplots(1, 3, figsize=(15, 3))
        fig.suptitle(f"[{entry}] {laser_wl}nm {optical_path}")
        axes = {"PST": ax, "APAP": ax1, "CAL": ax2}
        for tag, axis in axes.items():
            axis.grid()
            try:
                spe = average_spe(op_data, tag)
                spe.plot(ax=axis, label=tag)
                spe_calibrated = calmodel.apply_calibration_x(spe)
                spe_calibrated.plot(ax=axis, label=f"{tag} calibrated",linestyle='--', linewidth=1)
            except Exception:
                pass

