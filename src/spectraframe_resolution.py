"""CWA 18133:2024 Figure 2, Sections 3 & 4.

Section 3: spectral distribution curve (Raman shift width per pixel of the
calibrated x-axis) and pixel resolution curve (Gaussian-fit neon peak FWHM vs
position on the calibrated Raman shift axis).
Section 4: spectral resolution from the calcite ~1085.91 cm-1 peak FWHM
(Voigt fit, ASTM E2529 formula), spectral resolution curve and SpeD:SRes curve.

Uses the x-calibration models (calmodels) produced by spectracal_[[key]] only;
y-calibration is intentionally not applied (CWA sections 3-4 are x-axis only).
"""
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import traceback
import os.path
from IPython.display import display, HTML
import ramanchada2.misc.constants as rc2const
from ramanchada2.misc.types.peak_candidates import ListPeakCandidateMultiModel
from ramanchada2.misc.utils.ramanshift_to_wavelength import (
    shift_cm_1_to_abs_nm, abs_nm_to_shift_cm_1)
from utils import (find_peaks, load_config, load_calibration_model,
                   get_config_units, get_config_findkw, toc_heading, init_logging)

# + tags=["parameters"]
product = None
config_templates = None
config_root = None
key = None
upstream = None
neon_tag = None
calcite_tag = None
e2529_divisor = 0.684
e2529_offset = 1.029
curve_fit_degree = 2
# -


logger = init_logging(Path(product["nb"]).parent, f"spectrares_{key}.log")

# CWA 18133 Table 7 (RR1 calcite study); ASTM E2529 uses the ~1085 cm-1 band
CALCITE_REF_CM1 = 1085.91
CALCITE_WINDOW_CM1 = 100
# CWA 18133 Table 1 boundary of use
PIXEL_RESOLUTION_BOUNDARY_NM = 0.8
# max distance between a fitted peak and a NIST neon line to accept it
NEON_MATCH_TOL_CM1 = 10
# min fitted neon peaks required to trust a resolution curve (below this the
# polynomial is under-determined and the curve is not drawn / not enveloped)
MIN_NEON_PEAKS = 6
# resolution curves are only evaluated within the neon peak span, widened by
# this fraction of the span (small margin, no far extrapolation)
CURVE_MARGIN_FRAC = 0.05
# raw x-axis spacing with relative spread below this is a vendor-resampled
# (uniform) grid: the spectral distribution then shows the export grid, not
# the physical detector pixels (see docs/flat_resolution_curves.md)
UNIFORM_GRID_REL_TOL = 0.01
# the spectral resolution cannot be meaningfully better than the neon-derived
# pixel resolution (neon lines have ~zero intrinsic width, so their FWHM *is*
# the instrument function); a laser-effect ratio below this bound - allowing
# for the ~20% stated accuracy of the ASTM E2529 formula - means the calcite
# fit is defective and the rescale is not applied
SRES_MIN_RATIO = 0.8


def detect_uniform_grid(x, rel_tol=UNIFORM_GRID_REL_TOL):
    """(is_uniform, median_step) of a raw x-axis. A (near-)constant spacing
    means the vendor export was resampled onto a uniform grid."""
    d = np.diff(np.asarray(x, dtype=float))
    med = float(np.median(d))
    if len(d) < 2 or med == 0:
        return False, med
    return bool((d.max() - d.min()) / abs(med) < rel_tol), med


def fwhm_cm1_to_nm(center_cm1, fwhm_cm1, laser_wl):
    """FWHM expressed on the wavelength axis at the given peak position."""
    lo = shift_cm_1_to_abs_nm(center_cm1 - fwhm_cm1 / 2, laser_wl)
    hi = shift_cm_1_to_abs_nm(center_cm1 + fwhm_cm1 / 2, laser_wl)
    return abs(hi - lo)


def select_spectrum(op_data, tag, prefer_hdr=False):
    if prefer_hdr:
        matching_row = op_data.loc[(op_data["sample"] == tag) & (op_data["overexposed"] == "HDR_MERGE")]
        if not matching_row.empty:
            logger.info(f"{tag}: using HDR merge")
            return matching_row["spectrum"].iloc[0]
    matching_row = op_data.loc[op_data["sample"] == tag, "spectrum"]
    return None if matching_row.empty else matching_row.iloc[0]


def spectral_distribution(spe_calibrated):
    """CWA 18133 3.1.9: width collected by pixel n, taken as
    halfway(n, n+1) - halfway(n-1, n) == np.gradient.

    A few narrow dips are expected at regular pixel intervals: they mark
    detector segment-stitching seams already present in the raw
    (pre-calibration) spectrum (CWA 18133 3.1.6 lists "stitching data
    segments" as a primary-data treatment) - a brief local compression of
    the native pixel pitch where two acquisition segments were joined.
    The calibration curve is smooth and faithfully carries the seam
    through, so this is real instrument characterization, not a defect;
    it is smoothed out by the polynomial pixel-resolution curve fit."""
    x = spe_calibrated.x
    sped = np.gradient(x)
    return x, sped


def neon_reference_cm1(laser_wl):
    """NIST neon lines (nm) converted to Raman shift for this laser."""
    lines_nm = np.array(sorted(rc2const.NEON_WL[laser_wl].keys()))
    return np.sort(abs_nm_to_shift_cm_1(lines_nm, laser_wl))


def fit_neon_peaks(spe_ne_cal, _config, laser_wl):
    """Pixel resolution points: Gaussian fit (lmfit default = Levenberg-
    Marquardt) of the neon peaks on the calibrated Raman shift axis.
    Only candidate groups near a NIST neon line are fitted, and each
    reference line keeps its single best (highest) fitted peak - otherwise
    noise bumps distort the resolution curve."""
    ref_cm1 = neon_reference_cm1(laser_wl)
    find_kw = dict(get_config_findkw(_config, key, "ne"))
    find_kw["prominence"] = spe_ne_cal.y_noise_MAD() * 3
    cand = spe_ne_cal.find_peak_multipeak(**find_kw)
    groups = [g for g in cand
              if np.min(np.abs(np.asarray(g.positions)[:, None] - ref_cm1[None, :]))
              < NEON_MATCH_TOL_CM1]
    logger.info(f"neon candidate groups: {len(cand)} found, "
                f"{len(groups)} near NIST reference lines")
    if not groups:
        return pd.DataFrame(columns=["center", "fwhm", "fwhm_stderr", "height"])
    fitres = spe_ne_cal.fit_peak_multimodel(
        profile="Gaussian", candidates=ListPeakCandidateMultiModel(root=groups),
        no_fit=False, bound_centers_to_group=True, vary_baseline=False)
    df_peaks = fitres.to_dataframe_peaks()
    df_peaks = df_peaks.loc[
        np.isfinite(df_peaks["fwhm"]) & (df_peaks["fwhm"] > 0)
        & np.isfinite(df_peaks["center"])
        & (df_peaks["center"] >= min(spe_ne_cal.x))
        & (df_peaks["center"] <= max(spe_ne_cal.x))]
    if "fwhm_stderr" in df_peaks.columns:
        df_peaks = df_peaks.loc[
            df_peaks["fwhm_stderr"].isna() | (df_peaks["fwhm_stderr"] < df_peaks["fwhm"])]
    if df_peaks.empty:
        return df_peaks
    # one fitted peak per NIST line: nearest line within tolerance, best height wins
    idx = np.argmin(np.abs(df_peaks["center"].values[:, None] - ref_cm1[None, :]), axis=1)
    df_peaks = df_peaks.assign(ref_line=ref_cm1[idx])
    df_peaks = df_peaks.loc[(df_peaks["center"] - df_peaks["ref_line"]).abs() < NEON_MATCH_TOL_CM1]
    df_peaks = (df_peaks.sort_values("height", ascending=False)
                .groupby("ref_line", as_index=False).first())
    return df_peaks.sort_values(by="center")


def fit_pixel_resolution_curve(centers, fwhms, degree):
    """CWA 18133 3.1.5: a function fit of FWHM vs neon peak position.

    Requires at least MIN_NEON_PEAKS points, and does one round of MAD-based
    outlier rejection so a single mis-fit neon peak does not distort the curve.
    Returns (poly, fit_lo, fit_hi) or (None, None, None)."""
    centers = np.asarray(centers, dtype=float)
    fwhms = np.asarray(fwhms, dtype=float)
    if len(centers) < MIN_NEON_PEAKS:
        return None, None, None
    deg = min(degree, len(centers) - 1)
    if deg < 1:
        return None, None, None
    poly = np.poly1d(np.polyfit(centers, fwhms, deg))
    resid = fwhms - poly(centers)
    mad = np.median(np.abs(resid - np.median(resid)))
    if mad > 0:
        keep = np.abs(resid - np.median(resid)) <= 3 * 1.4826 * mad
        if keep.sum() >= MIN_NEON_PEAKS and keep.sum() < len(centers):
            centers, fwhms = centers[keep], fwhms[keep]
            deg = min(degree, len(centers) - 1)
            poly = np.poly1d(np.polyfit(centers, fwhms, deg))
    return poly, float(centers.min()), float(centers.max())


def clip_to_range(x, lo, hi):
    """Boolean mask of x within [lo, hi] widened by CURVE_MARGIN_FRAC."""
    margin = (hi - lo) * CURVE_MARGIN_FRAC
    return (x >= lo - margin) & (x <= hi + margin)


def fit_calcite_1085(spe_cal_calibrated, _config):
    """Voigt fit of the calcite ~1085.91 cm-1 peak (CWA Figure 2, Section 4).
    Falls back to Gaussian when the Voigt fit aborts (lmfit occasionally
    generates NaN model values); E2529 accepts mixed Gaussian/Lorentzian."""
    spe = spe_cal_calibrated.dropna().trim_axes(
        method='x-axis',
        boundaries=(CALCITE_REF_CM1 - CALCITE_WINDOW_CM1, CALCITE_REF_CM1 + CALCITE_WINDOW_CM1))
    spe.y = spe.y - np.min(spe.y)
    spe = spe.subtract_baseline_rc1_snip(niter=40)
    fitres = None
    for profile in ("Voigt", "Gaussian"):
        try:
            fitres, cand = find_peaks(spe, profile=profile,
                                      find_kw=get_config_findkw(_config, key, calcite_tag.lower()),
                                      vary_baseline=False)
            break
        except Exception as err:
            logger.warning(f"calcite {profile} fit failed: {err}")
    if fitres is None:
        return None, spe
    df_peaks = fitres.to_dataframe_peaks()
    df_peaks = df_peaks.assign(profile=profile)
    df_peaks = df_peaks.loc[np.isfinite(df_peaks["fwhm"]) & (df_peaks["fwhm"] > 0)]
    if df_peaks.empty:
        return None, spe
    df_peaks = df_peaks.iloc[(df_peaks["center"] - CALCITE_REF_CM1).abs().argsort()]
    peak = df_peaks.iloc[0]
    if abs(peak["center"] - CALCITE_REF_CM1) > 20:
        logger.warning(f"Nearest calcite peak at {peak['center']:.2f} cm-1 is too far from {CALCITE_REF_CM1}")
        return None, spe
    return peak, spe


def spectral_resolution_e2529(fwhm_1085):
    """ASTM E2529-06 calibration formula (dispersive systems, ~20% accuracy)."""
    return fwhm_1085 / e2529_divisor - e2529_offset


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

        try:
            # Section 3 - calibrated Raman shift axis applied to the neon spectrum
            _ne_units = get_config_units(_config, key, tag="neon")
            uniform_grid, grid_step = detect_uniform_grid(spe_neon.x)
            if uniform_grid:
                logger.warning(
                    f"{entry_id}: raw x-axis is a uniform grid "
                    f"(step {grid_step:.5f} {_ne_units}) - vendor-resampled export; "
                    "SpeD reflects the grid, not detector pixels")
            spe_ne_cal = calmodel.apply_calibration_x(spe_neon, spe_units=_ne_units).dropna()

            x_sped, sped = spectral_distribution(spe_ne_cal)

            ne_peaks = fit_neon_peaks(spe_ne_cal, _config, laser_wl)
            display(ne_peaks)
            pixel_res_curve, fit_lo, fit_hi = fit_pixel_resolution_curve(
                ne_peaks["center"].values, ne_peaks["fwhm"].values, curve_fit_degree)
            if pixel_res_curve is None:
                logger.warning(f"{entry_id}: only {len(ne_peaks)} neon peaks fitted "
                               f"(< {MIN_NEON_PEAKS}); no resolution curve, points only")
            # mask of x_sped where the curve is supported by neon peaks
            in_range = (clip_to_range(x_sped, fit_lo, fit_hi)
                        if pixel_res_curve is not None else np.zeros(len(x_sped), bool))
        except Exception:
            logger.error(f"{entry_id}: section 3 failed:\n{traceback.format_exc()}")
            continue

        ne_peaks = ne_peaks.assign(
            sample=neon_tag,
            fwhm_nm=[fwhm_cm1_to_nm(c, f, laser_wl)
                     for c, f in zip(ne_peaks["center"], ne_peaks["fwhm"])])

        # Section 4 - calcite spectral resolution (ASTM E2529)
        calcite_peak, sres, ratio, sres_plausible = None, None, None, None
        spe_calcite = select_spectrum(op_data, calcite_tag)
        if spe_calcite is None:
            logger.warning(f"{entry_id}: no {calcite_tag} spectrum, "
                           "skipping spectral resolution (section 4)")
        elif pixel_res_curve is not None:
            try:
                _cal_units = get_config_units(_config, key, tag=calcite_tag.lower())
                spe_cal_calibrated = calmodel.apply_calibration_x(spe_calcite, spe_units=_cal_units)
                calcite_peak, spe_1085 = fit_calcite_1085(spe_cal_calibrated, _config)
                if calcite_peak is not None:
                    sres = spectral_resolution_e2529(calcite_peak["fwhm"])
                    neon_fwhm_1085 = float(pixel_res_curve(calcite_peak["center"]))
                    # laser effect adjustment: scale the pixel resolution curve
                    # so it passes through the calcite spectral resolution value
                    _ratio = sres / neon_fwhm_1085
                    # sanity: a rescale that pushes the resolution curve well
                    # below the neon-derived instrument function is physically
                    # impossible - the calcite fit is defective (see
                    # docs/flat_resolution_curves.md) and would corrupt the
                    # spectral resolution curve
                    if _ratio < SRES_MIN_RATIO or sres <= 0:
                        sres_plausible = False
                        logger.warning(
                            f"{entry_id}: implausible calcite fit - SRes "
                            f"{sres:.3f} cm-1 is {_ratio:.2f}x the neon-derived "
                            f"{neon_fwhm_1085:.3f} cm-1 at {calcite_peak['center']:.1f} "
                            f"(calcite FWHM {calcite_peak['fwhm']:.3f}); "
                            "laser-effect rescale NOT applied")
                    else:
                        sres_plausible = True
                        ratio = _ratio
                        logger.info(f"{entry_id}: calcite FWHM {calcite_peak['fwhm']:.3f} cm-1 "
                                    f"({calcite_peak.get('profile')}), SRes {sres:.3f} cm-1, "
                                    f"laser effect ratio {ratio:.3f}")
            except Exception:
                logger.error(f"{entry_id}: calcite section failed:\n{traceback.format_exc()}")

        spectral_res_curve = None if ratio is None else (lambda x, r=ratio, c=pixel_res_curve: r * c(x))

        # evaluate curves only within the neon-supported range (NaN elsewhere)
        def eval_clipped(curve):
            if curve is None:
                return np.full(len(x_sped), np.nan)
            y = np.asarray(curve(x_sped), dtype=float)
            y[~in_range] = np.nan
            return y

        pixel_res = eval_clipped(pixel_res_curve)
        spectral_res = eval_clipped(spectral_res_curve)
        with np.errstate(divide="ignore", invalid="ignore"):
            sped_sres = sped / spectral_res
        sped_sres = np.where(np.isfinite(spectral_res), sped_sres, np.nan)

        plot_group(entry_id, x_sped, sped, ne_peaks, pixel_res, spectral_res,
                   sped_sres, calcite_peak, sres, uniform_grid=uniform_grid,
                   sres_plausible=sres_plausible)

        peaks_records = ne_peaks[["sample", "center", "fwhm", "fwhm_nm", "height"]
                                 + (["fwhm_stderr"] if "fwhm_stderr" in ne_peaks.columns else [])].copy()
        if calcite_peak is not None:
            peaks_records = pd.concat([peaks_records, pd.DataFrame([{
                "sample": calcite_tag,
                "center": calcite_peak["center"],
                "fwhm": calcite_peak["fwhm"],
                "fwhm_nm": fwhm_cm1_to_nm(calcite_peak["center"], calcite_peak["fwhm"], laser_wl),
                "height": calcite_peak.get("height", np.nan),
                "fwhm_stderr": calcite_peak.get("fwhm_stderr", np.nan),
            }])], ignore_index=True)
        peaks_records["key"] = key
        peaks_records["laser_wl"] = laser_wl
        peaks_records["optical_path"] = optical_path
        all_peaks.append(peaks_records)

        all_curves.append(pd.DataFrame({
            "key": key, "laser_wl": laser_wl, "optical_path": optical_path,
            "raman_shift": x_sped,
            "sped": sped,
            "pixel_res": pixel_res,
            "spectral_res": spectral_res,
            "sped_sres": sped_sres,
        }))

        curve_ok = pixel_res_curve is not None
        # is the fitted FWHM non-decreasing across the supported range?
        curve_monotonic = None
        if curve_ok:
            xr = np.linspace(fit_lo, fit_hi, 50)
            curve_monotonic = bool(np.all(np.diff(pixel_res_curve(xr)) >= -1e-9))
        max_fwhm_nm = ne_peaks["fwhm_nm"].max() if not ne_peaks.empty else np.nan
        all_summary.append({
            "key": key, "laser_wl": laser_wl, "optical_path": optical_path,
            "n_neon_peaks": len(ne_peaks),
            "curve_ok": curve_ok,
            "curve_monotonic": curve_monotonic,
            "uniform_grid": uniform_grid,
            "grid_step": grid_step,
            "sres_plausible": sres_plausible,
            "fit_lo": fit_lo,
            "fit_hi": fit_hi,
            "neon_fwhm_median": float(ne_peaks["fwhm"].median()) if not ne_peaks.empty else None,
            "pixel_res_coeffs": None if not curve_ok else list(pixel_res_curve.coefficients),
            "calcite_center": None if calcite_peak is None else calcite_peak["center"],
            "calcite_fwhm": None if calcite_peak is None else calcite_peak["fwhm"],
            "calcite_profile": None if calcite_peak is None else calcite_peak.get("profile"),
            "spectral_resolution": sres,
            "laser_effect_ratio": ratio,
            "max_neon_fwhm_nm": max_fwhm_nm,
            # CWA 18133 Table 1: pixel resolution < 0.8 nm boundary of use
            "within_cwa_boundary": bool(max_fwhm_nm < PIXEL_RESOLUTION_BOUNDARY_NM)
            if np.isfinite(max_fwhm_nm) else None,
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
