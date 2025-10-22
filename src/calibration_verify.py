import os
import pandas as pd
from IPython.display import display
import matplotlib.pyplot as plt
from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
from utils import (find_peaks, plot_si_peak, load_config, unicode_unit,
                   get_config_findkw, plot_biclustering, plot_spectra_heatmaps)
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import warnings
import traceback


# + tags=["parameters"]
product = None
config_templates = None
config_root = None
validation_tag = None
test_tags = None
si_tag = None
pst_tag = None
calcite_tag = None
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
    if len(spes) == 0:
        return None
    elif len(spes == 1):
        return spes[0]
    for spe in spes:
        if spe_sum is None:
            spe_sum = spe
        else:
            spe_resampled = spe.resample_spline_filter(
                    x_range=(min(spe_sum.x), max(spe_sum.x)),
                    xnew_bins=len(spe_sum.x), spline="akima")
            spe_sum = spe_sum + spe_resampled
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
        spe_sil = average_spe(op_data, si_tag).trim_axes(method='x-axis', 
                                                        boundaries=(520.45-50, 520.45+50))
        if spe_sil is None:
            continue
        plot_model(calmodel, entry, laser_wl, optical_path, [spe_sil])
        fig, (ax, ax1, ax2, ax3) = plt.subplots(1, 4, figsize=(15, 3))
        _id = f"[{entry}] {laser_wl}nm {optical_path}"
        fig.suptitle(_id)
        axes = {pst_tag: ax, validation_tag: ax1, calcite_tag: ax2,
                si_tag: ax3}
        for _tag in test_tags.split(","):
            if _tag not in [pst_tag, validation_tag, calcite_tag, si_tag]:
                axes[_tag] = ax3
        for tag, axis in axes.items():
            try:
                boundaries = (300, 3*1024+300)
                #boundaries = (300, 300+1024)
                bins = 1024 *3
                #bins = 400
                strategy = "minmax"
                spline = "pchip"
                plot_resampled = True

                spe = average_spe(op_data, tag)
                if spe is None:
                    continue
                if tag in ["S0N", "S0B", "Sil","S1N","S0P"]:
                    spe = spe.trim_axes(method='x-axis', boundaries=(520.45-100, 520.45 + 100))
                else:
                    spe = spe.trim_axes(method='x-axis', boundaries=boundaries)

                #print(spe.y_noise_MAD())
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
            except Exception:
                traceback.print_exc()
            axis.grid()

print(upstream["spectracal_*"].keys())

labels = ["original", "x-calibrated"]

for tag in original:
    id_calibrated = calibrated[tag]["id"]
    if len(id_calibrated) <= 1:
        print(f"{tag}: At least 2 optical paths needed to compare calibration results, "
              f"found {len(id_calibrated)}: {id_calibrated}")
        continue

    y_original = np.array(original[tag]["y"])
    y_calibrated = np.array(calibrated[tag]["y"])
    id_original = original[tag]["id"]
    wavelength = original[tag].get("x", np.arange(y_original.shape[1]))  # assume x-values stored here

    if len(y_original) != len(y_calibrated):
        print(f"Warning: {tag} - different number of spectra "
              f"(original={len(y_original)}, calibrated={len(y_calibrated)})")

    ids = [id_original, id_calibrated]

    # make a 3x2 grid; bottom row spans both columns
    fig = plt.figure(figsize=(16, 14))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1])
    ax_hist1 = fig.add_subplot(gs[0, 0])
    ax_biclust1 = fig.add_subplot(gs[0, 1])
    ax_hist2 = fig.add_subplot(gs[1, 0])
    ax_biclust2 = fig.add_subplot(gs[1, 1])

    fig.suptitle(tag)

    for index, (y, ax_hist, ax_biclust) in enumerate(
        [(y_original, ax_hist1, ax_biclust1), (y_calibrated, ax_hist2, ax_biclust2)]
    ):
        try:
            cos_sim_matrix = cosine_similarity(y)
            upper_tri_indices = np.triu_indices_from(cos_sim_matrix, k=1)
            cos_sim_values = cos_sim_matrix[upper_tri_indices]

            bins = np.linspace(0, 1, num=50)
            ax_hist.hist(cos_sim_values, bins=bins, color='blue', edgecolor='black')
            ax_hist.set_xlim(0, 1)
            ax_hist.grid()
            ax_hist.set_xlabel("Cosine similarity")
            ax_hist.set_ylabel("Frequency")

            ax_hist.set_title(
                f"{labels[index]} — Cosine similarity [min={np.min(cos_sim_values):.2f} | "
                f"median={np.median(cos_sim_values):.2f} | max={np.max(cos_sim_values):.2f}]"
            )

            try:
                plot_biclustering(cos_sim_matrix, ids[index],
                                  title=labels[index], ax=ax_biclust)
                fig.tight_layout(rect=[0, 0, 1, 0.95])  # leave space for title
            except Exception as e:
                print(f"Biclustering plot failed for {tag} ({labels[index]}): {e}")

        except Exception as e:
            print(f"Error computing cosine similarity for tag {tag} ({labels[index]}): {e}")
            traceback.print_exc()

        # --- spectra overlay plot ---
    plot_spectra_heatmaps(y_original, y_calibrated, wavelength, id_original, tag)
    try:
        # y_original and y_calibrated are [n_spectra × n_wavelengths]
        n_spectra = y_original.shape[0]
        ncols = min(n_spectra, 4)  # up to 6 spectra per row
        nrows = int(np.ceil(n_spectra / ncols))

        fig_spec, axes = plt.subplots(nrows, ncols, figsize=(4*ncols, 3*nrows), sharex=True, sharey=True)
        axes = np.atleast_1d(axes).flatten()

        for i in range(n_spectra):
            ax = axes[i]
            ax.plot(wavelength, y_original[i, :], color='blue', alpha=0.7, label='original')
            ax.plot(wavelength, y_calibrated[i, :], color='orange', alpha=0.7, label='calibrated')
            ax.set_title(id_original[i] if i < len(id_original) else f"Spectrum {i+1}")
            ax.grid(True)
            if i % ncols == 0:
                ax.set_ylabel("Intensity (a.u.)")
            if i >= (nrows - 1) * ncols:
                ax.set_xlabel(f"{unicode_unit('cm-1')}")

        # Hide any unused axes
        for j in range(i + 1, len(axes)):
            fig_spec.delaxes(axes[j])

        # Shared legend outside
        handles, labels_ = axes[0].get_legend_handles_labels()
        fig_spec.legend(handles, labels_, loc='upper center', ncol=2, frameon=False)
        fig_spec.suptitle(f"{tag}: Original vs Calibrated Spectra", fontsize=14)
        fig_spec.tight_layout(rect=[0, 0, 1, 0.95])

        plt.show()

    except Exception as e:
        print(f"Failed to plot spectra for {tag}: {e}")
