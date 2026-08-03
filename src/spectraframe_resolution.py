"""CWA 18133:2024 Figure 2, Sections 3 & 4.

Section 3: spectral distribution curve (Raman shift width per pixel of the
calibrated x-axis) and pixel resolution curve (Gaussian-fit neon peak FWHM vs
position on the calibrated Raman shift axis).
Section 4: spectral resolution from the calcite ~1085.91 cm-1 peak FWHM
(Voigt fit, ASTM E2529 formula), spectral resolution curve and SpeD:SRes curve.

The per-spectrum computation now lives in ramanchada2
(``ramanchada2.protocols.calibration.resolution``), so there is a single
implementation shared with the SpectraStream app; this Ploomber task selects the
spectra per optical path, tabulates the products and plots them. Uses the
x-calibration models (calmodels) produced by spectracal_[[key]] only;
y-calibration is intentionally not applied (CWA sections 3-4 are x-axis only).
"""
import os.path
import traceback
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import HTML, display
from ramanchada2.protocols.calibration.resolution import (
    MIN_NEON_PEAKS,
    resolution_from_calibration,
)

from utils import (get_config_findkw, get_config_units, init_logging,
                   load_calibration_model, load_config, toc_heading)

# + tags=["parameters"]
product = None
config_templates = None
config_root = None
key = None
upstream = None
neon_tag = None
calcite_tag = None
curve_fit_degree = 2
# -


logger = init_logging(Path(product["nb"]).parent, f"spectrares_{key}.log")


def select_spectrum(op_data, tag, prefer_hdr=False):
    if prefer_hdr:
        matching_row = op_data.loc[(op_data["sample"] == tag) & (op_data["overexposed"] == "HDR_MERGE")]
        if not matching_row.empty:
            logger.info(f"{tag}: using HDR merge")
            return matching_row["spectrum"].iloc[0]
    matching_row = op_data.loc[op_data["sample"] == tag, "spectrum"]
    return None if matching_row.empty else matching_row.iloc[0]


def plot_group(entry_id, x_sped, sped, ne_peaks, pixel_res, spectral_res,
               sped_sres, calcite_peak, sres, uniform_grid=False,
               sres_plausible=None):
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 4))
    fig.suptitle(entry_id)

    ax1.plot(x_sped, sped, color="blue")
    if uniform_grid:
        ax1.text(0.03, 0.95, "resampled export grid,\nnot detector pixels",
                 transform=ax1.transAxes, va="top", fontsize=8, color="#a33327",
                 bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))
    ax1.set_xlabel("Raman shift/cm⁻¹")
    ax1.set_ylabel("Spectral distribution/cm⁻¹ per pixel")
    ax1.set_title("Spectral distribution curve")
    ax1.grid()

    ax2.scatter(ne_peaks["center"], ne_peaks["fwhm"], label="Ne peak FWHM", color="blue")
    if np.isfinite(pixel_res).any():
        ax2.plot(x_sped, pixel_res, color="orange", label="pixel resolution curve")
    if np.isfinite(spectral_res).any():
        ax2.plot(x_sped, spectral_res, color="green", linestyle="--",
                 label="spectral resolution curve")
    if calcite_peak is not None:
        _sres_label = f"SRes (calcite, E2529) {sres:.2f} cm⁻¹"
        if sres_plausible is False:
            _sres_label += " — implausible, not applied"
        ax2.scatter([calcite_peak["center"]], [sres], color="red", marker="x", s=80,
                    label=_sres_label)
    ax2.set_xlabel("Raman shift/cm⁻¹")
    ax2.set_ylabel("FWHM/cm⁻¹")
    ax2.set_title("Pixel & spectral resolution curves")
    ax2.grid()
    ax2.legend()

    if sped_sres is not None:
        ax3.plot(x_sped, sped_sres, color="purple")
    ax3.set_xlabel("Raman shift/cm⁻¹")
    ax3.set_ylabel("SpeD:SRes")
    ax3.set_title("SpeD:SRes curve")
    ax3.grid()
    plt.tight_layout()
    plt.show()
    note = (
        "Narrow dips at a handful of regularly-spaced points in the spectral "
        "distribution curve (left) mark detector segment-stitching seams "
        "already present in the raw spectrum, not a calibration or fitting "
        "defect - the pixel/spectral resolution curves (middle) are fit "
        "through the neon peaks and are not affected by them.")
    if uniform_grid:
        note += (
            " <b>The raw spectrum of this instrument is on a uniform grid</b> "
            "(vendor-resampled export), so the flat spectral distribution "
            "curve shows the resampling grid, not the physical pixel pitch; "
            "the SpeD and SpeD:SRes curves must not be interpreted as CWA "
            "pixel properties.")
    if sres_plausible is False:
        note += (
            " <b>The calcite fit is implausible</b> (its E2529 spectral "
            "resolution falls well below the neon-derived instrument "
            "function), so the laser-effect rescale was not applied and no "
            "spectral resolution curve is drawn.")
    display(HTML(
        '<p style="max-width:900px;color:#52514e;font-size:0.9em;margin-top:-0.5em">'
        + note + "</p>"))


def main(df, calmodel_path, _config):
    all_peaks, all_curves, all_summary = [], [], []
    df_bkg_substracted = df.loc[df["background"] == "BACKGROUND_SUBTRACTED"]
    grouped_df = df_bkg_substracted.groupby(["laser_wl", "optical_path"], dropna=False)
    for (laser_wl, optical_path), op_data in grouped_df:
        entry_id = f"[{key}] {laser_wl}nm {optical_path}"
        toc_heading(entry_id)
        try:
            calmodel = load_calibration_model(laser_wl, optical_path, calmodel_path)
        except Exception:
            traceback.print_exc()
            calmodel = None
        if calmodel is None:
            logger.warning(f"{entry_id}: no calibration model found, skipping")
            continue

        spe_neon = select_spectrum(op_data, neon_tag, prefer_hdr=True)
        if spe_neon is None:
            logger.warning(f"{entry_id}: no {neon_tag} spectrum, skipping")
            continue
        spe_calcite = select_spectrum(op_data, calcite_tag)
        if spe_calcite is None:
            logger.warning(f"{entry_id}: no {calcite_tag} spectrum, "
                           "spectral resolution (section 4) will be skipped")

        # Sections 3 & 4 are computed by the shared ramanchada2 implementation;
        # this task only selects the spectra, tabulates the products and plots.
        try:
            res = resolution_from_calibration(
                calmodel, spe_neon,
                neon_units=get_config_units(_config, key, tag="neon"),
                spe_calcite=spe_calcite,
                calcite_units=get_config_units(_config, key, tag=calcite_tag.lower()),
                find_kw=dict(get_config_findkw(_config, key, "ne")),
                calcite_find_kw=dict(get_config_findkw(_config, key, calcite_tag.lower())),
                curve_fit_degree=curve_fit_degree,
                title=entry_id,
            )
        except Exception:
            logger.error(f"{entry_id}: resolution failed:\n{traceback.format_exc()}")
            continue

        display(res.neon_peaks)
        if res.uniform_grid:
            logger.warning(
                f"{entry_id}: raw x-axis is a uniform grid (step {res.grid_step:.5f}) "
                "- vendor-resampled export; SpeD reflects the grid, not detector pixels")
        if not res.curve_ok:
            logger.warning(f"{entry_id}: only {res.n_neon_peaks} neon peaks fitted "
                           f"(< {MIN_NEON_PEAKS}); no resolution curve, points only")
        if res.sres_plausible is False:
            logger.warning(f"{entry_id}: implausible calcite fit - SRes "
                           f"{res.spectral_resolution:.3f} cm-1; laser-effect rescale "
                           "NOT applied")
        elif res.spectral_resolution is not None:
            logger.info(f"{entry_id}: calcite FWHM {res.calcite_fwhm:.3f} cm-1 "
                        f"({res.calcite_profile}), SRes {res.spectral_resolution:.3f} "
                        f"cm-1, laser effect ratio {res.laser_effect_ratio}")

        calcite_peak = (
            {"center": res.calcite_center} if res.calcite_center is not None else None)
        plot_group(entry_id, res.raman_shift, res.sped, res.neon_peaks,
                   res.pixel_res, res.spectral_res, res.sped_sres,
                   calcite_peak, res.spectral_resolution,
                   uniform_grid=res.uniform_grid, sres_plausible=res.sres_plausible)

        cols = ["center", "fwhm", "fwhm_nm", "height"]
        if "fwhm_stderr" in res.neon_peaks.columns:
            cols.append("fwhm_stderr")
        peaks_records = res.neon_peaks[cols].copy()
        peaks_records.insert(0, "sample", neon_tag)
        if res.calcite_center is not None:
            peaks_records = pd.concat([peaks_records, pd.DataFrame([{
                "sample": calcite_tag,
                "center": res.calcite_center,
                "fwhm": res.calcite_fwhm,
                "fwhm_nm": np.nan,
                "height": np.nan,
            }])], ignore_index=True)
        peaks_records["key"] = key
        peaks_records["laser_wl"] = laser_wl
        peaks_records["optical_path"] = optical_path
        all_peaks.append(peaks_records)

        all_curves.append(pd.DataFrame({
            "key": key, "laser_wl": laser_wl, "optical_path": optical_path,
            "raman_shift": res.raman_shift,
            "sped": res.sped,
            "pixel_res": res.pixel_res,
            "spectral_res": res.spectral_res,
            "sped_sres": res.sped_sres,
        }))

        all_summary.append({
            "key": key, "laser_wl": laser_wl, "optical_path": optical_path,
            "n_neon_peaks": res.n_neon_peaks,
            "curve_ok": res.curve_ok,
            "curve_monotonic": res.curve_monotonic,
            "uniform_grid": res.uniform_grid,
            "grid_step": res.grid_step,
            "sres_plausible": res.sres_plausible,
            "fit_lo": res.fit_lo,
            "fit_hi": res.fit_hi,
            "neon_fwhm_median": res.neon_fwhm_median,
            "pixel_res_coeffs": None,
            "calcite_center": res.calcite_center,
            "calcite_fwhm": res.calcite_fwhm,
            "calcite_profile": res.calcite_profile,
            "spectral_resolution": res.spectral_resolution,
            "laser_effect_ratio": res.laser_effect_ratio,
            "max_neon_fwhm_nm": res.max_neon_fwhm_nm,
            # CWA 18133 Table 1: pixel resolution < 0.8 nm boundary of use
            "within_cwa_boundary": res.within_cwa_boundary,
        })

    return (pd.concat(all_peaks) if all_peaks else pd.DataFrame(),
            pd.concat(all_curves) if all_curves else pd.DataFrame(),
            pd.DataFrame(all_summary))


toc_heading(f"Spectral distribution & resolution curves (CWA 18133 sections 3 & 4) {key}", "h1")

Path(product["nb"]).parent.mkdir(parents=True, exist_ok=True)
try:
    df = pd.read_hdf(upstream["spectraframe_*"][f"spectraframe_{key}"]["h5"], key="templates_read")
    _config = load_config(os.path.join(config_root, config_templates))
    calmodel_path = upstream["spectracal_*"][f"spectracal_{key}"]["calmodels"]
    df_peaks, df_curves, df_summary = main(df, calmodel_path, _config)
    df_peaks.to_csv(product["peaks"], index=False)
    df_curves.to_csv(product["curves"], index=False)
    df_summary.to_csv(product["summary"], index=False)
    toc_heading("Summary", "h2")
    display(df_summary)
except Exception:
    traceback.print_exc()
