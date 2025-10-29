import pandas as pd
import os.path
from pathlib import Path
from utils import (find_peaks, plot_si_peak, get_config_units, 
                   load_config, get_config_findkw,
                   load_calibration_model)
from ramanchada2.protocols.calibration.ycalibration import (
    YCalibrationComponent, YCalibrationCertificate, CertificatesDict)
import matplotlib.pyplot as plt
import traceback
import pickle


# + tags=["parameters"]
product = None
config_templates = None
config_root = None
key = None
upstream = None
# -


def create_ycal(spe_srm, xcalmodel=None, cert_srm=None, window_length=0):
    if cert_srm is None:
        return None, spe_srm
    srm = spe_srm.trim_axes(method="x-axis", boundaries=cert_srm.raman_shift)
    if xcalmodel is not None:
        srm_calibrated = xcalmodel.apply_calibration_x(srm)
    else:
        srm_calibrated = srm
    if window_length > 0:
        maxy = max(srm_calibrated.y)
        srm_calibrated = srm_calibrated.smoothing_RC1(
            method="savgol", window_length=window_length, polyorder=3)
        srm_calibrated.y = maxy*srm_calibrated.y/max(srm_calibrated.y)
    ycal = YCalibrationComponent(cert_srm.wavelength, srm_calibrated, cert_srm)
    return ycal, srm_calibrated


def main(df, calmodel_path):
    certificates = CertificatesDict()
    df_bkg_substracted = df.loc[df["background"] == "BACKGROUND_SUBTRACTED"]
    grouped_df = df_bkg_substracted.groupby(["laser_wl", "optical_path"], dropna=False)
    for group_keys, op_data in grouped_df:
        laser_wl = group_keys[0]
        optical_path = group_keys[1]
        certs = certificates.get_certificates(wavelength=laser_wl)
        for cert in certs:
            matching_row = op_data.loc[(op_data["sample"] == cert) | (op_data["sample"] == cert.replace("EL0", "ELO")) ]
            if matching_row.empty:
                continue
            print(cert)
            fig, axes = plt.subplots(1, 3, figsize=(15, 3))
            for i in [0, 1, 2]:
                axes[i].grid()
                axes[i].set_xlabel('Wavenumber/cm⁻¹')
            axes[0].set_title(f"[{key}] {laser_wl}nm {optical_path}")
            certs[cert].plot(ax=axes[0], color='pink')
            srm_spe = matching_row["spectrum"].iloc[0]
            try:
                xcalmodel = load_calibration_model(laser_wl, optical_path, calmodel_path)
            except Exception as err:
                traceback.print_exc()
                xcalmodel = None
            ycal, srm_calibrated = create_ycal(
                srm_spe, xcalmodel=xcalmodel, cert_srm=certs[cert], window_length=40)
            # save y model
            with open(os.path.join(product["ycalmodels"],
                                    f"ycalmodel_{laser_wl}_{optical_path}.pkl"), "wb") as f:
                pickle.dump(ycal, f)
        
            srm_spe.plot(ax=axes[0].twinx(), label='measured')
            srm_calibrated.plot(ax=axes[0].twinx(),
                                color='green', fmt='--')
            for index, tag in enumerate(["PST", "APAP"]):
                axes[index+1].set_title(tag)
                matching_row = op_data.loc[(op_data["sample"] == tag)]
                if matching_row.empty:
                    continue
                spe_to_correct = matching_row["spectrum"].iloc[0]
                spe_to_correct = spe_to_correct.trim_axes(method="x-axis", boundaries=certs[cert].raman_shift)
                spe_to_correct.plot(ax=axes[index+1], label='original')
                spe_to_correct = spe_to_correct.subtract_baseline_rc1_snip(niter=40)
                spe_to_correct.plot(ax=axes[index+1],  fmt='--', color = "green", label='baseline')

                spe_ycalibrated = ycal.process(spe_to_correct)
                spe_ycalibrated.plot(ax=axes[index+1].twinx(), fmt='--', color='orange', label='y-calibrated')

Path(product["ycalmodels"]).mkdir(parents=True, exist_ok=True)

try:
    df = pd.read_hdf(upstream["spectraframe_*"][f"spectraframe_{key}"]["h5"], key="templates_read")
    _config = load_config(os.path.join(config_root, config_templates))
    calmodel_path = upstream["spectracal_*"][f"spectracal_{key}"]["calmodels"]
    main(df, calmodel_path)
except Exception as err:
    print(err)