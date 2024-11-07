import pandas as pd
import os.path
import json
from ramanchada2.spectrum import Spectrum

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
    FRONT_SHEET_COLUMNS = "optical_path,instrument_make,instrument_model,wavelength,max_laser_power_mW,spectral_range,collection_optics,slit_size,grating,pin_hole_size,collection_fibre_diameter,notes"
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
