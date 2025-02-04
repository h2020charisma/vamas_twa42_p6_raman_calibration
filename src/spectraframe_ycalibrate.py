import pandas as pd
import os.path
from utils import (find_peaks, plot_si_peak, get_config_units, 
                   load_config, get_config_findkw)
from ramanchada2.protocols.calibration.ycalibration import (
    YCalibrationComponent, YCalibrationCertificate, CertificatesDict)
import matplotlib.pyplot as plt


# + tags=["parameters"]
product = None
config_templates = None
config_root = None
key = None
# -

#tags = ["LED532_EL0-9001","NIST532_SRM2242a","NIR785_EL0-9002A","NIST785_SRM2241"]

def main(df, _config):
    certificates = CertificatesDict()
    df_bkg_substracted = df.loc[df["background"] == "BACKGROUND_SUBTRACTED"]
    grouped_df = df_bkg_substracted.groupby(["laser_wl", "optical_path"], dropna=False)
    for group_keys, op_data in grouped_df:
        laser_wl = group_keys[0]
        optical_path = group_keys[1]
        certs = certificates.get_certificates(wavelength=laser_wl)
        for cert in certs:
            matching_row = op_data.loc[(op_data["sample"] == cert)]
            if matching_row.empty:
                continue
            fig, axes = plt.subplots(1, 3, figsize=(15, 3))
            axes[0].set_title(f"[{key}] {laser_wl}nm {optical_path}")
            certs[cert].plot(ax=axes[0])
            srm_spe = matching_row["spectrum"].iloc[0]
            srm_spe.plot(ax=axes[0].twinx())
            ycal = YCalibrationComponent(laser_wl, srm_spe, certs[cert])
                        
            for index, tag in enumerate(["PST", "APAP"]):
                axes[index+1].set_title(tag)
                matching_row = op_data.loc[(op_data["sample"] == tag)]
                if matching_row.empty:
                    continue
                spe_to_correct = matching_row["spectrum"].iloc[0]
                spe_to_correct.plot(ax=axes[index+1], label='original')
                spe_ycalibrated = ycal.process(spe_to_correct)
                spe_ycalibrated.plot(ax=axes[index+1].twinx(), fmt='--', color='orange', label='ycal')


try:
    df = pd.read_hdf(upstream["spectraframe_*"][f"spectraframe_{key}"]["h5"], key="templates_read")
    _config = load_config(os.path.join(config_root, config_templates))
    main(df, _config)
except Exception as err:
    print(err)