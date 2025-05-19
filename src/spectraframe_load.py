from ramanchada2.spectrum import Spectrum, hdr_from_multi_exposure
from utils import (
    read_template, load_config, is_in_skip, 
    get_config_excludecols
)
import os.path
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd


# + tags=["parameters"]
product = None
config_templates = None
config_root = None
key = None
# -


_config = load_config(os.path.join(config_root, config_templates))
print(key, _config["templates"].keys())

Path(os.path.dirname(product["h5"])).mkdir(parents=True, exist_ok=True)

entry = _config["templates"][key]
entry

_path_excel = os.path.join(config_root, entry["template"])
df = read_template(_path_excel, path_spectra=os.path.join(config_root, entry["path"]))

df['background'] = df['background'].str.upper()
# I have typo in the template and some participants corrected it :) 
df.loc[df["background"] == "BACKGROUND_SUBSTRACTED", "background"] = "BACKGROUND_SUBTRACTED"
df.loc[df["background"] == "BACKGROUND_NOT_SUBSTRACTED", "background"] = "BACKGROUND_NOT_SUBTRACTED"

df["source"] = str(entry)


# this likely will need to be configurable
exclude_cols = get_config_excludecols(_config, key)

print(exclude_cols)

# Get columns to group by

start_col = 'optical_path'  # specify the column you want to start grouping with
groupby_cols = [start_col] + [col for col in df.columns if col not in exclude_cols and col != start_col]

print(groupby_cols)

df["background_file"] = None

grouped_df = df.groupby(groupby_cols, dropna=False)

# figure out background files
for group_keys, sample_data in grouped_df:
    print(sample_data.shape, group_keys)
    fig, ax = plt.subplots(1, 1, figsize=(15, 3))
    ax.title.set_text("{} {}".format(group_keys[0], group_keys[1]))
    _spe = sample_data.apply(lambda row: Spectrum.from_local_file(row["file_name"]) if os.path.isfile(row["file_name"]) else None, axis=1)
    # .trim_axes(method='x-axis', boundaries=(100, 3400))
    sample_data["spectrum"] = _spe
    try:
        sample_data.apply(lambda row: None if row["spectrum"] is None else row["spectrum"].plot(
            ax=ax, label="{} {} ({})".format(os.path.basename(row["file_name"]), row["background"], row["overexposed"])),
            axis=1)
    except Exception as err:
        print(err)
    if sample_data.shape[0] < 2:
        continue
    background_only_file = sample_data.loc[sample_data["background"] == "BACKGROUND_ONLY", "file_name"]
    if not background_only_file.empty:
        if sample_data[sample_data["background"] == "BACKGROUND_NOT_SUBTRACTED"].empty:
            print("No rows found with 'BACKGROUND_NOT_SUBTRACTED'.")
        else:
            # Assign the first "Background_Only" file_name to rows where background is "Background_Not_Subtracted"
            df.loc[
                (df["file_name"].isin(sample_data["file_name"])) &
                (df["background"] == "BACKGROUND_NOT_SUBTRACTED"), 
                "background_file"
            ] = background_only_file.iloc[0]

            print(background_only_file.iloc[0])
    else:
        print("No rows found with 'BACKGROUND_ONLY'.")

df.to_hdf(product["h5"], key='templates_read', mode='w')
df.to_excel(product["xlsx"], sheet_name='templates_read', index=False)    

df_bkg_subtracted = df.loc[df["background"] == "BACKGROUND_SUBTRACTED"]
for index, row in df_bkg_subtracted.iterrows():
    spe = Spectrum.from_local_file(row["file_name"])
    df.loc[df["file_name"] == row["file_name"], "spectrum"] = spe

df_bkg_notsubtracted = df.loc[df["background"] == "BACKGROUND_NOT_SUBTRACTED"]

new_rows = []
for index, row in df_bkg_notsubtracted.iterrows():
    if row["background_file"] is None:
        continue
    fig, (ax, tax) = plt.subplots(2, 1, figsize=(15, 4))
    ax.title.set_text(os.path.basename(row["file_name"])) 
    print(row["file_name"], row["background_file"])    
    new_row = row.copy()
    if os.path.isfile(row["background_file"]):
        spe_bkg = Spectrum.from_local_file(row["background_file"])
        spe_bkg.plot(label="BACKGROUND_ONLY", ax=tax, linestyle='-', color='red')
        spe_bkg_nospikes = spe_bkg.recover_spikes()
        spe_bkg_nospikes.plot(label="Background_only_nospikes", ax=tax, linestyle='--', color='gray')
    else:
        spe_bkg_nospikes = None
    if not os.path.isfile(row["file_name"]):
        print("Can't find file {}".format(row["file_name"]))
        ax.title.set_text("Can't find file {}".format(os.path.basename(row["file_name"]))) 
        continue
    spe = Spectrum.from_local_file(row["file_name"])
    spe.plot(label="BACKGROUND_NOT_SUBTRACTED {} ({})".format(row["sample"], row["optical_path"]), ax=ax)    

    new_spe = spe if is_in_skip(_config, key, filename=os.path.basename(row["background_file"])) or spe_bkg_nospikes is None else spe - spe_bkg_nospikes
    # new_spe.y[new_spe.y < 0] = 0
    # remove pedestal
    # new_spe.y = new_spe.y - np.min(new_spe.y)
    # new_spe = new_spe.recover_spikes()

    new_row["spectrum"] = new_spe
    new_spe.plot(label="Background_Substracted {} ({})".format(row["sample"], 
                                    row["optical_path"]), ax=ax.twinx(), linestyle='--', color='orange')
    new_row["background"] = "BACKGROUND_SUBTRACTED"
    new_rows.append(new_row)
    #plt.close(fig)

if new_rows:  # Only concatenate if there are new rows to add
    new_df = pd.DataFrame(new_rows)  # Convert list of rows to DataFrame
    df = pd.concat([df, new_df], ignore_index=True)  # Append all at once

df.to_hdf(product["h5"], key='templates_read', mode='w')
df.to_excel(product["xlsx"], sheet_name='templates_read', index=False)    

hdr_added = False
df_ne = df.loc[(df["background"] == "BACKGROUND_SUBTRACTED") & (df["sample"] == "Neon")]
grouped_df = df_ne.groupby(["laser_wl", "optical_path"], dropna=False)

# HDR merge on all groups that have integraiton time - not only Ne 
for group_keys, op_data in grouped_df:
    if 'integration_time_ms' not in op_data.columns or op_data['integration_time_ms'].dropna().empty:
        # Skip this group if integration_time_ms is missing or empty
        continue
    if len(op_data) > 1:
        fig, (axes) = plt.subplots(len(op_data)+2, 1, figsize=(15, 12)) 
        laser_wl = group_keys[0]
        optical_path = group_keys[1]
        axes[0].set_title(f"{key} [{laser_wl}nm] {optical_path}")
        axes[0].set_yscale("log")
        max_row = op_data.loc[op_data["integration_time_ms"].idxmax()]
        yaxis_max = 0.9 * max(max_row["spectrum"].y)
        spe_ne = []
        ix = 2
        spe_ne_len = []
        min_x = None
        max_x = None
        for _, row in op_data.iterrows():
            integration_time_ms = row["integration_time_ms"]
            spe = Spectrum(row["spectrum"].x, row["spectrum"].y,
                        metadata=dict(integration_time_ms=integration_time_ms,
                                        yaxis_max=yaxis_max))
            spe.plot(ax=axes[ix], fmt='--', label=f"{integration_time_ms} ms")
            spe_ne.append(spe)
            spe_ne_len.append(len(spe.x))
            min_x = min(spe.x) if min_x is None or min_x > min(spe.x) else min_x
            max_x = max(spe.x) if max_x is None or max_x < min(spe.x) else max_x
            #plt.yscale('log')
            #axes[ix].set_yscale("log")
            ix = ix+1
        if min(spe_ne_len) != max(spe_ne_len):
            # resample - check if this can be improved
            for i, _spe in enumerate(spe_ne):
                spe_ne[i] = _spe.resample_spline_filter(
                    x_range=(min_x, max_x),
                    xnew_bins=max(spe_ne_len), spline="akima")

        hdr = hdr_from_multi_exposure(spe_ne,
                                    meta_exposure_time='integration_time_ms',
                                    meta_ymax='yaxis_max')
        twax = axes[0].twinx()
        twax.set_yscale("log")
        max_row["spectrum"].plot(ax=twax, label=max_row["integration_time_ms"])
        max_row["spectrum"].plot(ax=axes[1].twinx(), label=max_row["integration_time_ms"])        
        hdr.plot(ax=axes[0], fmt='--', color='red', label='HDR')
        hdr.plot(ax=axes[1], fmt='--', color='red', label='HDR')

        hdr_row = max_row.copy()
        hdr_row["spectrum"] = hdr
        hdr_row["overexposed"] = "HDR_MERGE"
        df = pd.concat([df, pd.DataFrame([hdr_row])], ignore_index=True)
        hdr_added = True
        #plt.yscale('log')

if hdr_added:
    print("HDR merged Ne added")
    df.to_hdf(product["h5"], key='templates_read', mode='w')
    df.to_excel(product["xlsx"], sheet_name='templates_read', index=False)