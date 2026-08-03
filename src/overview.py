from utils import (
    load_config
)
import os.path
from pathlib import Path
from IPython.display import display, HTML
import json
from utils import (
    toc, toc_anchor, toc_entry, toc_link, toc_heading, toc_collapsible
    )
from utils import read_template, get_config_excludecols, parse_numeric_value
import traceback
import pandas as pd
from ramanchada2.spectrum import Spectrum


# + tags=["parameters"]
product = None
config_templates = None
config_root = None
config_output = None
path_output = None
keys = None
resolution = None
# -


import warnings
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module="openpyxl.worksheet._reader"
)

_config_path = os.path.join(config_root, config_templates)
_config = load_config(_config_path)

Path(os.path.dirname(product["nb"])).mkdir(parents=True, exist_ok=True)

templates = _config["templates"]

# --- Table of Contents ---
toc_heading(_config.get("title", "Overview"),"h1")
toc_link(os.path.relpath(config_root, config_output), label="The data is in the folder:")
toc_link(os.path.relpath(_config_path, config_output), label="The configuration is in this file:")
toc_link(os.path.relpath(config_output, config_output),label="The processing results will be in the folder:")
toc(templates.keys())

all_dfs = []
# --- Detailed Entries ---
for index, (_entry, data) in enumerate(templates.items()):
    toc_anchor(index, _entry)
    toc_link(os.path.relpath(os.path.join(config_root, data["template"]), config_output), label="Template")
    toc_link(os.path.relpath(os.path.join(config_root, data["path"]), config_output), label="path")
    if data.get("subfolders") is not None:
        toc_entry("subfolders", data)
    toc_entry("notes", data)

    _path_excel = os.path.join(config_root, data["template"])
    df = read_template(_path_excel,
                       path_spectra=os.path.join(config_root, data["path"]),
                       subfolders=data.get("subfolders", {}), cleanup=False)
    toc_heading(f"Metadata table shape: rows {df.shape[0]} columns {df.shape[1]}", "h4")
    # show only cols used for grouping / identifying background
    exclude_cols = get_config_excludecols(_config, _entry)
    start_col = 'optical_path'  # specify the column you want to start grouping with
    groupby_cols = [start_col] + [col for col in df.columns if col not in exclude_cols and col != start_col]
    # summary
    sample_col = "sample"
    path_col = "optical_path"
    bg_col = "background"
    laser_col = "laser_power_percent"
    laser_wl_col = "laser_wl"
    file_col = "file_name"
    itime_col = "integration_time_ms"
    humidity_col = "humidity"
    temperature_col = "temperature"
    overexposed_col = "overexposed"
    provider_col = "provider"
    for col in [humidity_col, temperature_col]:
        df[col] = df[col].apply(parse_numeric_value)
    df["file_extension"] = (
        df["file_name"]
        .astype(str)
        .str.extract(r"\.([^.]+)$")[0]   # capture text after the last '.'
        .str.lower()
    )     
    print(df.columns)
    #display(df[["sample", "laser_wl", "provider"]])   
    df["id"] = _entry
    all_dfs.append(df[["id", "provider", 'instrument_make', 'instrument_model',  "optical_path", "laser_wl", "sample", "file_name"] ])
    #print(_entry)
    #print(data)
    try:
        summary = (
            df.groupby("sample")
            .agg({
                path_col: lambda x: ", ".join(sorted(x.dropna().unique())),
                bg_col:   lambda x: ", ".join(sorted(x.dropna().unique())),
                laser_wl_col: lambda x: ", ".join(str(v) for v in sorted(x.dropna().unique())),
                laser_col: lambda x: ", ".join(str(v) for v in sorted(x.dropna().unique())),
                itime_col: lambda x: ", ".join(str(v) for v in sorted(x.dropna().unique())),
                overexposed_col: lambda x: ", ".join(str(v) for v in sorted(x.dropna().unique())),
#                humidity_col: lambda x: ", ".join(str(v) for v in sorted(x.dropna().unique())),
#                temperature_col: lambda x: ", ".join(str(v) for v in sorted(x.dropna().unique())),
                humidity_col: lambda x: f"{x.mean():.1f} ± {x.std():.1f}" if len(x.dropna()) > 0 else "NA",
                temperature_col: lambda x: f"{x.mean():.1f} ± {x.std():.1f}" if len(x.dropna()) > 0 else "NA",
                "file_extension": lambda x: ", ".join(sorted(x.dropna().unique())),
                file_col:  "count",
                provider_col: lambda x: ", ".join(sorted(x.dropna().unique())),
            })
            .rename(columns={
            path_col: "optical_paths",
            bg_col: "background_status",
            laser_wl_col: "laser_wavelenght_nm",
            laser_col: "laser_powers_%",
            itime_col: "integration_times_ms",
            overexposed_col: "overexposed",
            humidity_col: "humidity_%",
            temperature_col: "temperature_C",
            "file_extension": "file_extensions",
            file_col: "n_files"
            })
            .reset_index()
        )
        display(summary)
    except Exception:
        traceback.print_exc()


    # collapsible table
    toc_collapsible(summary="Preview of grouped metadata", content=df[groupby_cols].head().to_html(index=False))

    # optional nested dicts
    msg = ""
    for field in ["background", "units", "preprocess", "find_kw"]:
        if field in data:
            content = json.dumps(data[field], indent=2)
            msg = msg + f"<h4>{field.capitalize()}:</h4><pre>{content}</pre>"
    if msg != "":
        toc_collapsible(summary="Other settings", content=msg)
    # excluded columns
    excl = data.get("exclude_cols", [])
    if excl:
        excl_html = "<ul>" + "".join(f"<li>{c}</li>" for c in excl) + "</ul>"
        #display(HTML("<h4>Excluded Columns:</h4>" + excl_html))
    
    toc_heading("The results from initial data load in the folder:","h4")
    toc_link(os.path.relpath(f"{config_output}/{_entry}", config_output))
    toc_heading("The results from calibration in the folder:","h4")
    toc_link(os.path.relpath(f"{path_output}/{_entry}", config_output))

    display(HTML('<p><a href="#top">Back to top</a></p>'))

all_df = pd.concat(all_dfs, ignore_index=True)
for idx, row in all_df.iterrows():
    try:
        if resolution and not row["sample"].startswith("T"):
            spe = Spectrum.from_local_file(row["file_name"])
            all_df.at[idx, "status"] = "OK"
            all_df.at[idx, "resolution"] = len(spe.x)
            all_df.at[idx, "x_min"] = min(spe.x)
            all_df.at[idx, "x_max"] = max(spe.x)
    except Exception as err:
        all_df.at[idx, "status"] = "error"
        all_df.at[idx, "error"] = err

summary_counts = (
    all_df
    .groupby(["id", "provider", 'instrument_make', 'instrument_model',  "optical_path", "laser_wl", "sample"] )
    .size()
    .reset_index(name="count")
)
display(summary_counts)

all_df.to_excel(product["data"], index=False)


with pd.ExcelWriter(
    product["data"],
    engine="openpyxl",
    mode="a",
    if_sheet_exists="replace"  # or "overlay"
) as writer:
    summary_counts.to_excel(
        writer,
        sheet_name="Summary",
        index=False
    )

display(HTML('<p><a href="#top">Back to top</a></p>'))
