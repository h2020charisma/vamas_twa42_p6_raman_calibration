import pandas as pd
import os.path
import json
from ramanchada2.spectrum import Spectrum
import matplotlib.pyplot as plt 
import numpy as np
from sklearn.cluster import SpectralBiclustering
from IPython.display import display, Markdown, HTML
import re


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
    fname = row["file_name"]
    if not os.path.isfile(fname):
        print(f"⚠️ File not found: {fname}")
        return None        
    else:
        return Spectrum.from_local_file(fname)


def build_path(row, base_path, subfolders={}):
    subfolder = subfolders.get("optical_paths", {}).get(row["optical_path"], None)
    if subfolder is None:
        return os.path.join(base_path, row['file_name'])
    else:
        return os.path.join(base_path, subfolder, row['file_name'])


def read_template(_path_excel, path_spectra="", subfolders={}, cleanup=False):
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
    df['file_name'] = df['file_name'].str.strip()
    #df['file_name'] = df['file_name'].apply(lambda f: os.path.join(path_spectra,f))
    df['file_name'] = df.apply(
        lambda row: build_path(row, path_spectra, subfolders),
        axis=1
    )

    df_meta = pd.read_excel(_path_excel, sheet_name=FRONT_SHEET_NAME, skiprows=4)
    # print("meta", df_meta.columns)
    df_meta.columns = FRONT_SHEET_COLUMNS.split(",")
    df_merged = pd.merge(df, df_meta, on='optical_path', how='left')

    # Open the Excel file and read specific cells directly
    with pd.ExcelFile(_path_excel) as xls:
        provider = xls.parse(FRONT_SHEET_NAME, usecols="B", nrows=1, header=None).iloc[0, 0]
        investigation = xls.parse(FRONT_SHEET_NAME, usecols="H", nrows=1, header=None).iloc[0, 0]
    df_merged["provider"] = provider
    df_merged["investigation"] = investigation

    return metadata_cleanup(df_merged) if cleanup else df_merged


def metadata_cleanup(df_merged):
    df_merged['background'] = df_merged['background'].str.upper()
    # I have typo in the template and some participants corrected it :) 
    df_merged.loc[df_merged["background"] == "BACKGROUND_SUBSTRACTED", "background"] = "BACKGROUND_SUBTRACTED"
    df_merged.loc[df_merged["background"] == "BACKGROUND_NOT_SUBSTRACTED", "background"] = "BACKGROUND_NOT_SUBTRACTED"

    df_merged['sample'] = df_merged['sample'].str.replace('_bkg', '')
    # we are not parsing pictures
    df_merged = df_merged[~df_merged['file_name'].str.lower().str.endswith('.jpg')]    
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
        ax1.axvline(x=df.iloc[0]["position"], color='black', linestyle=':', linewidth=2, label="Si peak {:.3f} cm⁻¹".format(df.iloc[0]["position"]))
        fitres.plot(ax=ax1.twinx(), label="fit res", color="magenta")

    spe_sil.plot(label="Si original", ax=ax1, color='blue')
    spe_sil_calibrated.plot(ax=ax1, label="Si calibrated", color='orange')
    ax1.set_xlabel('Wavenumber/cm⁻¹')
    ax1.set_ylabel("") #Raman intensity/Arbitr.Units")    
    ax1.set_xlim(520-50,520+50)
    # ax1.set_xlim(300, max(spe_sil.x))
    ax1.axvline(x=520.45, color='red', linestyle='-', linewidth=2, label="Reference 520.45 cm⁻¹")
    ax1.legend()
    ax1.grid()


def plot_biclustering(pairwise_distances, identifiers, title='original',ax=None):
    
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
    #ax.set_title(title)
    ax.set_title("")

    ax.set_xlabel(f'{title} spectra')
    ax.set_ylabel(f'{title} spectra')


def to_camel_case(s: str) -> str:
    parts = s.split('_')
    return parts[0].lower() + ''.join(word.capitalize() for word in parts[1:])


def toc_heading(title, h="h3"):
    display(HTML(f"<{h}>{title}</{h}>"))


def toc(keys, title=None):
    if title is not None:
        toc_heading(title, "h1")
    toc = "<h2>Table of Contents</h2>"
    for index, _entry in enumerate(keys):
        toc += f'<a href="#{_entry}">{index+1}. {_entry}</a><br/>'
    toc += ""
    display(HTML(f'<div id="top">{toc}</div>'))


def toc_anchor(index, key):
    display(HTML(f'<h2 id="{key}">{index+1}. {key}</h2>'))


def toc_entry(key, data):
    if key is None:
        display(HTML(f"<p>{data}</p>"))
    else:
        display(HTML(f"<p><b>{key.capitalize()}:</b> {data.get(key,'')}</p>"))


def toc_link(link, data=None, target='blank'):
    display(HTML(f"<a href='{link}' target='{target}'>{link if data is None else data}</a>"))


def parse_numeric_value(v):
    """Try to convert values like '45-50' or '45 – 50' to a float (average), else NaN."""
    if pd.isna(v):
        return np.nan
    if isinstance(v, (int, float)):
        return float(v)
    v = str(v).strip()
    # Match numeric ranges like 45-50, 45–50, 45 — 50
    match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*$", v)
    if match:
        low, high = map(float, match.groups())
        return (low + high) / 2
    # Try normal float conversion
    try:
        return float(v)
    except ValueError:
        return np.nan
    

def toc_collapsible(summary="expand", content=""):
    # collapsible table
    html = f"""
    <details>
    <summary><b>{summary}</b></summary>
    {content}
    </details>
    """
    display(HTML(html))


superscripts = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def unicode_unit(unit):
    return unit.translate(superscripts)


def get_xunit(sample, config):
    return config.get("units", {}).get(sample.lower(), "cm-1")


def get_boundaries(sample, config):
    return config.get("preprocess", {}).get("trim_axes", {}).get("boundaries", [100,3500])


def plot_spectra_heatmaps1(y_original, y_calibrated, wavelength, ids, tag):
    """
    Plot original and calibrated spectra as heatmaps.
    
    Parameters
    ----------
    y_original : ndarray [n_spectra × n_wavelengths]
    y_calibrated : ndarray [n_spectra × n_wavelengths]
    wavelength : ndarray [n_wavelengths]
    ids : list of spectrum identifiers
    tag : str
    """
    n_spectra = y_original.shape[0]

    # Normalize intensities for better color scaling
    vmin = min(y_original.min(), y_calibrated.min())
    vmax = max(y_original.max(), y_calibrated.max())

    fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True, sharey=True)
    plt.subplots_adjust(hspace=0.1)

    # --- Original spectra heatmap ---
    im0 = axes[0].imshow(
        y_original, 
        aspect='auto',
        interpolation='nearest',
        extent=[wavelength.min(), wavelength.max(), 0, n_spectra],
        origin='lower',
        vmin=vmin, vmax=vmax,
        cmap='viridis'
    )
    axes[0].set_title("Original spectra")
    axes[0].set_ylabel("Spectrum ID")

    # Label each spectrum
    for i, sid in enumerate(ids):
        axes[0].text(wavelength.min(), i + 0.5, f"{sid}", va='center', ha='right', fontsize=8)

    # --- Calibrated spectra heatmap ---
    im1 = axes[1].imshow(
        y_calibrated, 
        aspect='auto',
        interpolation='nearest',
        extent=[wavelength.min(), wavelength.max(), 0, n_spectra],
        origin='lower',
        vmin=vmin, vmax=vmax,
        cmap='viridis'
    )
    axes[1].set_title("Calibrated spectra")
    axes[1].set_xlabel("Wavelength (nm)")
    axes[1].set_ylabel("Spectrum ID")

    for i, sid in enumerate(ids):
        axes[1].text(wavelength.min(), i + 0.5, f"{sid}", va='center', ha='right', fontsize=8)

    # --- Colorbar ---
    cbar = fig.colorbar(im1, ax=axes, orientation='vertical', fraction=0.02, pad=0.02)
    cbar.set_label("Intensity (a.u.)")

    fig.suptitle(f"{tag}: Spectra Heatmaps (Original vs Calibrated)", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()


def plot_spectra_heatmaps(y_original, y_calibrated, wavelength, ids, tag):
    n_spectra = y_original.shape[0]
    vmin = min(y_original.min(), y_calibrated.min())
    vmax = max(y_original.max(), y_calibrated.max())

    # Make figure taller for readability
    fig, axes = plt.subplots(2, 1, figsize=(12, max(4, n_spectra * 0.4)), sharex=True, sharey=True)
    plt.subplots_adjust(hspace=0.15)

    # --- Shorten long IDs ---
    short_ids = [id_.replace(" ", "").split("_")[0] for id_ in ids]  # keep concise prefix
    if len(short_ids) > 20:  # if too many spectra
        step = max(1, len(short_ids)//15)
        yticks = np.arange(0.5, n_spectra, step)
        yticklabels = [short_ids[i] for i in range(0, n_spectra, step)]
    else:
        yticks = np.arange(0.5, n_spectra)
        yticklabels = short_ids

    # --- Original spectra heatmap ---
    im0 = axes[0].imshow(
        y_original, aspect='auto', origin='lower',
        extent=[wavelength.min(), wavelength.max(), 0, n_spectra],
        vmin=vmin, vmax=vmax, cmap='viridis'
    )
    axes[0].set_title("Original spectra")
    axes[0].set_ylabel("Spectrum ID")
    axes[0].set_yticks(yticks)
    axes[0].set_yticklabels(yticklabels, fontsize=8)

    # --- Calibrated spectra heatmap ---
    im1 = axes[1].imshow(
        y_calibrated, aspect='auto', origin='lower',
        extent=[wavelength.min(), wavelength.max(), 0, n_spectra],
        vmin=vmin, vmax=vmax, cmap='viridis'
    )
    axes[1].set_title("Calibrated spectra")
    axes[1].set_xlabel("Wavelength (nm)")
    axes[1].set_ylabel("Spectrum ID")
    axes[1].set_yticks(yticks)
    axes[1].set_yticklabels(yticklabels, fontsize=8)

    # --- Shared colorbar ---
    cbar = fig.colorbar(im1, ax=axes, orientation='vertical', fraction=0.025, pad=0.02)
    cbar.set_label("Intensity (a.u.)")

    fig.suptitle(f"{tag}: Spectra Heatmaps (Original vs Calibrated)", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()
