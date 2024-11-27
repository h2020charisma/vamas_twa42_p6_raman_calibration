import pandas as pd
import os.path
import json
from ramanchada2.spectrum import Spectrum
import matplotlib.pyplot as plt 
import numpy as np
from sklearn.cluster import SpectralBiclustering


def load_config(path):
    with open(path, 'r') as file:
        _tmp = json.load(file)
    return _tmp


def get_enabled(key, _config):
    if key in _config['options']:
        return _config['options'][key].get('enable', True)
    else:
        return True

def load_spectrum_df(row):
    print(row["file_name"])
    return Spectrum.from_local_file(row["file_name"])

def read_template(_path_excel, path_spectra=""):
    FRONT_SHEET_NAME = "Front sheet"
    FILES_SHEET_NAME = "Files sheet"

    FILES_SHEET_COLUMNS = "sample,measurement,file_name,background,overexposed,optical_path,laser_power_percent,laser_power_mW,integration_time_ms,humidity,temperature,date,time"
    FRONT_SHEET_COLUMNS = "optical_path,instrument_make,instrument_model,laser_wl,max_laser_power_mW,spectral_range,collection_optics,slit_size,grating,pin_hole_size,collection_fibre_diameter,notes"
    df = pd.read_excel(_path_excel, sheet_name=FILES_SHEET_NAME)
    _FILES_SHEET_COLUMNS = FILES_SHEET_COLUMNS.split(",")
    if len(_FILES_SHEET_COLUMNS) == len(df.columns):
        df.columns = _FILES_SHEET_COLUMNS  # Rename all columns
    else:
        df.columns = _FILES_SHEET_COLUMNS + df.columns[len(_FILES_SHEET_COLUMNS):].tolist()
        # Rename only the first few columns

    df['file_name'] = df['file_name'].apply(lambda f: os.path.join(path_spectra,f))

    df_meta = pd.read_excel(_path_excel, sheet_name=FRONT_SHEET_NAME, skiprows=4)
    print("meta", df_meta.columns)
    df_meta.columns = FRONT_SHEET_COLUMNS.split(",")
    df_merged = pd.merge(df, df_meta, on='optical_path', how='left')

    # Open the Excel file and read specific cells directly
    with pd.ExcelFile(_path_excel) as xls:
        provider = xls.parse(FRONT_SHEET_NAME, usecols="B", nrows=1, header=None).iloc[0, 0]
        investigation = xls.parse(FRONT_SHEET_NAME, usecols="H", nrows=1, header=None).iloc[0, 0]
    df_merged["provider"] = provider
    df_merged["investigation"] = investigation
    return df_merged


# Function to check if an item is in "skip" safely
def is_in_skip(_config, key, filename):
    # Access the "skip" list safely using .get() with a default empty list
    skip_list = _config.get("templates", {}).get(key, {}).get("background", {}).get("skip", [])
    return filename in skip_list


def get_config_units(_config, key, tag="neon"):
    return _config.get("templates", {}).get(key, {}).get("units", {}).get(tag, "cm-1")


def get_config_excludecols(_config, key):
    return _config.get("templates", {}).get(key, {}).get("exclude_cols", [
        "date", "time", "measurement", "source", "file_name", "notes", 
        "laser_power_percent",  "laser_power_mW", "background"
        ])

def get_config_findkw(_config, key, tag="si"):
    print(_config.get("templates", {}).get(key, {}).get("find_kw", {}))
    return _config.get("templates", {}).get(key, {}).get("find_kw", {}).get(tag, {"wlen": 200, "width": 1})



def find_peaks(spe_test, profile="Gaussian", find_kw=None, vary_baseline=False):
    if find_kw is None:
        find_kw = {"wlen": 200, "width": 1, "sharpening" : None}
    find_kw["prominence"] = spe_test.y_noise_MAD() * 3
    cand = spe_test.find_peak_multipeak(**find_kw)
    fit_kw = {}
    return spe_test.fit_peak_multimodel(profile=profile,
                                        candidates=cand,
                                        **fit_kw,
                                        no_fit=False,
                                        bound_centers_to_group=True,
                                        vary_baseline=vary_baseline), cand


def plot_si_peak(spe_sil, spe_sil_calibrated, fitres= None, ax=None):
    if ax is None:
        fig, ax1 = plt.subplots(1, 1, figsize=(15, 3))
    else:
        ax1 = ax    
    if fitres is not None:
        df = fitres.to_dataframe_peaks()
        df = df.sort_values(by="height", ascending=False)
        # print("The Si peak of the calibrated spectrum (Pearson4)", df.iloc[0]["position"])
        ax1.axvline(x=df.iloc[0]["position"], color='black', linestyle=':', linewidth=2, label="Si peak {:.3f} cm-1".format(df.iloc[0]["position"]))
        fitres.plot(ax=ax1.twinx(), label="fit res", color="magenta")

    spe_sil.plot(label="Si original", ax=ax1, color='blue')
    spe_sil_calibrated.plot(ax=ax1, label="Si calibrated", color='orange')
    ax1.set_xlabel('Raman shift (cm⁻¹)')
    ax1.set_ylabel("Intensity (a.u.)")    
    ax1.set_xlim(520-50,520+50)
    # ax1.set_xlim(300, max(spe_sil.x))
    ax1.axvline(x=520.45, color='red', linestyle='-', linewidth=2, label="Reference 520.45 cm-1")
    ax1.legend()
    ax1.grid()


def plot_biclustering(pairwise_distances, identifiers, title='Cosine similarity Heatmap',ax=None):
    
    # Perform biclustering
    model = SpectralBiclustering(n_clusters=(3, 3), method='log', random_state=0)
    model.fit(pairwise_distances)
    
    # Reorder the rows and columns based on the clustering
    fit_data = pairwise_distances[np.argsort(model.row_labels_)]
    fit_data = fit_data[:, np.argsort(model.column_labels_)]

    cax = ax.imshow(fit_data, cmap='YlGnBu', interpolation='nearest', vmin=0, vmax=1)
    plt.colorbar(cax, ax=ax, label='Cosine similarity')
    
    # Set ticks and labels
    ax.set_xticks(np.arange(len(identifiers)))
    ax.set_xticklabels(np.array(identifiers)[np.argsort(model.column_labels_)], rotation=90)
    ax.set_yticks(np.arange(len(identifiers)))
    ax.set_yticklabels(np.array(identifiers)[np.argsort(model.row_labels_)])
    
    # Set title and labels
    ax.set_title(title)

    ax.set_xlabel('Spectra')
    ax.set_ylabel('Spectra')
    