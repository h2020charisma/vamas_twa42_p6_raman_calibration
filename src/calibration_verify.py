import os
import pandas as pd
from IPython.display import display
import matplotlib.pyplot as plt
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
from utils import (find_peaks, plot_si_peak, load_config, 
                   get_config_findkw, plot_biclustering)
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import warnings


# + tags=["parameters"]
product = None
config_templates = None
config_root = None
# -

_config = load_config(os.path.join(config_root, config_templates))
warnings.filterwarnings('ignore')


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
    print(len(spes))
    return spe_sum/len(spes)


def plot_distances(pairwise_distances, identifiers):
    plt.figure(figsize=(8, 6))
    plt.imshow(pairwise_distances, cmap='YlGnBu', interpolation='nearest')
    plt.colorbar(label='Cosine similarity')
    plt.xticks(ticks=np.arange(len(identifiers)), labels=identifiers, rotation=90)
    plt.yticks(ticks=np.arange(len(identifiers)), labels=identifiers)
    plt.title('Cosine Distance Heatmap')
    plt.xlabel('Spectra')
    plt.ylabel('Spectra')
    plt.show()


original = {}
calibrated = {}
for key in upstream["spectracal_*"].keys():
    # print(key)
    entry = key.replace("spectracal_","")
    if entry == "x01001":
        continue
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
        fig, (ax, ax1, ax2, ax3) = plt.subplots(1, 4, figsize=(15, 3))
        _id = f"[{entry}] {laser_wl}nm {optical_path}"
        fig.suptitle(_id)
        axes = {"PST": ax, "APAP": ax1, "CAL": ax2 , "S0N" : ax3, "S0B" : ax3}
        for tag, axis in axes.items():
            try:
                boundaries = (200, 3*1024+200)
                #boundaries = (400, 800)
                bins = 3*1024
                #bins = 400
                strategy = "L2"
                spline = "pchip"
                plot_resampled = True

                spe = average_spe(op_data, tag)
                if tag in ["S0N", "S0B"]:
                    spe = spe.trim_axes(method='x-axis', boundaries=(520.45-100, 520.45 + 100))
                else:
                    spe = spe.trim_axes(method='x-axis', boundaries=boundaries)

                print(spe.y_noise_MAD())
                # remove pedestal
                spe.y = spe.y - np.min(spe.y)
                # remove baseline
                spe = spe.subtract_baseline_rc1_snip(niter=40)
                spe_calibrated = calmodel.apply_calibration_x(spe)

                spe_resampled = spe.resample_spline_filter(
                    x_range=boundaries, xnew_bins=bins, spline=spline)
                #spe_resampled = spe_resampled.subtract_baseline_rc1_snip(niter=40).normalize(strategy=strategy)
                spe_resampled = spe_resampled.normalize(strategy=strategy)

                spe_cal_resampled = spe_calibrated.resample_spline_filter(
                    x_range=boundaries, xnew_bins=bins, spline=spline)
                #spe_cal_resampled = spe_cal_resampled.subtract_baseline_rc1_snip(niter=40).normalize(strategy=strategy)
                spe_cal_resampled = spe_cal_resampled.normalize(
                    strategy=strategy)

                if plot_resampled:
                    spe_resampled.plot(ax=axis, label=tag)                
                    spe_cal_resampled.plot(ax=axis, label=f"{tag} x-calibrated", linestyle='--', linewidth=1)
                    axis.set_xlabel('Wavenumber/cm⁻¹')
                else:
                    spe.plot(ax=axis, label=tag)
                    spe_calibrated.plot(ax=axis, label=f"{tag} x-calibrated", 
                                        linestyle='--', linewidth=1)
                    axis.set_xlabel('Wavenumber/cm⁻¹')

                if tag not in original:
                    original[tag] = {"y": [], "id": []}
                original[tag]["y"].append(spe_resampled.y)
                original[tag]["id"].append(_id)
                if tag not in calibrated:
                    calibrated[tag] = {"y": [], "id": []}
                calibrated[tag]["y"].append(spe_cal_resampled.y)                    
                calibrated[tag]["id"].append(_id)
            except Exception as err:
                print(err)
            axis.grid()

for tag in original:

    label = ["original", "x-calibrated"]
    y_original = original[tag]["y"]
    y_calibrated = calibrated[tag]["y"]
    id_original = original[tag]["id"]
    id_calibrated = calibrated[tag]["id"]
    ids = [id_original, id_calibrated]
    fig, ax = plt.subplots(2, 2, figsize=(16,12))  
    fig.suptitle(tag)
    for index, y in enumerate([y_original, y_calibrated]):
        cos_sim_matrix = cosine_similarity(y)
        upper_tri_indices = np.triu_indices_from(cos_sim_matrix, k=1)
        cos_sim_values = cos_sim_matrix[upper_tri_indices]
        # Step 3: Plot the distribution
        bins = np.linspace(0, 1, num=50)
        ax[index, 0].hist(cos_sim_values, bins=bins, color='blue', edgecolor='black')
        ax[index, 0].set_xlim(0, 1)
        ax[index, 0].grid() 
        ax[index, 0].set_xlabel("Cosine similarity")
        #plt.title('Distribution of Cosine Similarities ({} spectra)'.format(label[index]))
        plt.xlabel('Cosine Similarity')
        plt.ylabel('Frequency')
        plot_biclustering(cos_sim_matrix, ids[index], title=label[index], ax=ax[index, 1])
        ax[index, 0].set_title("{} [min={:.2f}|median={:.2f}|max={:.2f}]".format("Cosine similarity histogram", np.min(cos_sim_matrix), np.median(cos_sim_matrix), np.max(cos_sim_matrix)))
    fig.tight_layout()        
    plt.show()
