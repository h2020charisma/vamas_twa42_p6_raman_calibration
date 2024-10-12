# + tags=["parameters"]
upstream = []
product = None
config_templates = None
config_root = None

# -

import json
import os.path
import pandas as pd
from pathlib import Path

FRONT_SHEET_NAME = "Front sheet"
FILES_SHEET_NAME = "Files sheet"

FILES_SHEET_COLUMNS = "sample,measurement,filename,background,overexposed,optical_path,laser_power_percent,laser_power_mw,integration_time_ms,humidity,temperature,date,time"
FRONT_SHEET_COLUMNS = "optical_path,instrument_make,instrument_model,wavelength,max_laser_power_mW,spectral_range,collection_optics,slit_size,grating,pin_hole_size,collection_fibre_diameter,notes"


def load_config(path):
    with open(path , 'r') as file:
        _tmp = json.load(file)
    return _tmp

    
_config = load_config(os.path.join(config_root,config_templates))

def get_enabled(key):
    if key in _config['options']:
        return _config['options'][key].get('enable', True)
    else:
        return True 


Path(os.path.dirname(product["h5"])).mkdir(parents=True, exist_ok=True)

df_merged_list = []

for key in _config["templates"]:
    
    _path_excel = os.path.join(config_root,key["template"])

    df = pd.read_excel(_path_excel, sheet_name=FILES_SHEET_NAME)
    print(key,df.columns)
    df.columns = FILES_SHEET_COLUMNS.split(",")
    df['filename'] = df['filename'].apply(lambda f: os.path.join(config_root,key["path"],f))

    df_meta = pd.read_excel(_path_excel, sheet_name=FRONT_SHEET_NAME, skiprows=4)
    print("meta",df_meta.columns)
    df_meta.columns = FRONT_SHEET_COLUMNS.split(",")
    df_merged = pd.merge(df, df_meta, on='optical_path', how='left')



    # Open the Excel file and read specific cells directly
    with pd.ExcelFile(_path_excel) as xls:
        provider = xls.parse(FRONT_SHEET_NAME, usecols="B", nrows=1, header=None).iloc[0, 0]
        investigation = xls.parse(FRONT_SHEET_NAME, usecols="F", nrows=1, header=None).iloc[0, 0]
    df_merged["provider"] = provider
    df_merged["investigation"] = investigation
    df_merged["source"] = key
    df_merged_list.append(df_merged)

final_df = pd.concat(df_merged_list, axis=0)
final_df['enabled'] = final_df['optical_path'].apply(get_enabled)

final_df.to_hdf(product["h5"], key='templates_read', mode='w')
final_df.to_excel(product["xlsx"], sheet_name='templates_read',index=False)
