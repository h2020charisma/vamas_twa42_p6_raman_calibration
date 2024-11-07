# + tags=["parameters"]
upstream = []
product = None
config_templates = None
config_root = None
key = None
# -

from ramanchada2.protocols.spectraframe import SpectraFrame
from ramanchada2.spectrum import Spectrum
from utils import read_template, load_config, load_spectrum_df
import os.path
from pathlib import Path


_config = load_config(os.path.join(config_root, config_templates))
Path(os.path.dirname(product["h5"])).mkdir(parents=True, exist_ok=True)

entry = _config["templates"][key]
_path_excel = os.path.join(config_root, entry["template"])
df = read_template(_path_excel, path_spectra=os.path.join(config_root, entry["path"]))
df["source"] = str(entry)

df.to_hdf(product["h5"], key='templates_read', mode='w')
df.to_excel(product["xlsx"], sheet_name='templates_read', index=False)

grouped_df = df.groupby(['optical_path', 'sample'])
trim_left = 100
for group_keys, sample_data in grouped_df:
    optical_path = group_keys[0]
    sample = group_keys[1]
    sample_data["spectrum"] = sample_data.apply(lambda row: Spectrum.from_local_file(row["file_name"]), axis=1)
    try:
        sample_data.apply(lambda row: row["spectrum"].plot(label="{} {}".format(row["sample"], row["background"])),axis=1)
    except Exception as err:
        print(err)