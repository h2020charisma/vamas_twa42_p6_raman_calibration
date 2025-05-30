import pandas as pd
from IPython.display import display


# + tags=["parameters"]
product = None
upstream = None
config_templates = None
config_root = None
# -

tips_ps = "TiPS_PS"
tips_ti = "TiPS_Ti"


def process(df, tag = None):
    return df.loc[df["sample"] == tag]

try:
    cfg = upstream["spectraframe_*"]
    for key in cfg.keys():
        print(key)
        df = pd.read_hdf(cfg[key]["h5"], key="templates_read")
        _df_ps = process(df,tips_ps)
        display(_df_ps)
        _df_ti = process(df,tips_ti)
        display(_df_ti)
except Exception as err:
    print(err)
