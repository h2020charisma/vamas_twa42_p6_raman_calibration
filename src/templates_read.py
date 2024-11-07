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
from utils import read_template, load_config, get_enabled


_config = load_config(os.path.join(config_root, config_templates))
Path(os.path.dirname(product["h5"])).mkdir(parents=True, exist_ok=True)
df_merged_list = []

for key, entry in _config["templates"].items():
    _path_excel = os.path.join(config_root, entry["template"])
    df_merged = read_template(_path_excel, path_spectra=os.path.join(config_root, entry["path"]))
    df_merged["source"] = str(entry)
    df_merged_list.append(df_merged)

final_df = pd.concat(df_merged_list, axis=0)
final_df['enabled'] = final_df['optical_path'].apply(lambda x: get_enabled(x, _config))

final_df.to_hdf(product["h5"], key='templates_read', mode='w')
final_df.to_excel(product["xlsx"], sheet_name='templates_read',index=False)
