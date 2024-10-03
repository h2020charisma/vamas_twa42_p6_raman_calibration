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
    print(key)
    _path = os.path.join(config_root,key)
    df = pd.read_excel(_path, sheet_name='Files')
    df.columns = ['sample', 'measurement', 'filename', 'optical_path', 'laser_power_percent','laser_power_mw', 'integration_time_ms',
              'humidity', 'temperature', 'date', 'time']
    df_meta = pd.read_excel(_path, sheet_name='Front sheet', skiprows=4)
    df_meta.columns = ['optical_path', 'instrument_make', 'instrument_model', 'wavelength','collection_optics','slit_size','grating','pin_hole_size','collection_fibre_diameter','notes','max_laser_power_mw']    
    df_merged = pd.merge(df, df_meta, on='optical_path', how='left')

    # Open the Excel file and read specific cells directly
    with pd.ExcelFile(_path) as xls:
        provider = xls.parse('Front sheet', usecols="B", nrows=1, header=None).iloc[0, 0]
        investigation = xls.parse('Front sheet', usecols="F", nrows=1, header=None).iloc[0, 0]
    df_merged["provider"] = provider
    df_merged["investigation"] = investigation
    df_merged["source"] = key
    df_merged_list.append(df_merged)

final_df = pd.concat(df_merged_list, axis=0)
final_df['enabled'] = final_df['optical_path'].apply(get_enabled)

final_df.to_hdf(product["h5"], key='templates_read', mode='w')
final_df.to_excel(product["xlsx"], sheet_name='templates_read',index=False)
