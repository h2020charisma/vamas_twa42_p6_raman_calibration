"""Resolution-aware comparison across instruments (CWA 18133 objective 2).

Aggregates the per-key products of the spectrares_[[key]] tasks (CWA 18133
Figure 2, sections 3 & 4) and compares instruments that share a laser
wavelength: spectral distribution curves, pixel/spectral resolution curves,
SpeD:SRes curves and the ASTM E2529 spectral resolution values.

Also derives, per laser wavelength, the harmonization target: the envelope
(pointwise maximum) of the spectral resolution curves - the resolution a
spectrum adjustment function would need to bring all instruments to, per
CWA 18133 objective 2 ("facilitate correction of each instrument based on
their resolution across the whole range").
"""
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import traceback
import os.path
from IPython.display import display, HTML
from utils import toc_heading, init_logging

# + tags=["parameters"]
product = None
upstream = None
context = ""
# -


logger = init_logging(Path(product["nb"]).parent, "resolution_compare.log")

# fixed categorical palette (8 CVD-safe hues); hues are assigned to
# instruments in stable (sorted) order so an instrument keeps its identity
# across all figures. Beyond 8 instruments sharing one laser wavelength, hues
# repeat and are paired with a distinct linestyle (secondary encoding) so
# instruments stay distinguishable instead of silently colliding.
PALETTE = ["#2a78d6", "#1baf7a", "#eda100", "#008300",
           "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
LINESTYLES = ["-", "--", "-.", ":"]
GRID_KW = {"color": "#e1e0d9", "linewidth": 0.8}
# mirrors MIN_NEON_PEAKS in spectraframe_resolution.py, used only for labels
MIN_NEON_PEAKS = 6


def load_products(product_name):
    frames = []
    for task_name, products in upstream["spectrares_*"].items():
        path = str(products[product_name])
        if os.path.isfile(path):
            frames.append(pd.read_csv(path))
        else:
            logger.warning(f"{task_name}: missing product {path}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def with_entity(df):
    df = df.copy()
    df["entity"] = df["key"] + " " + df["optical_path"].astype(str)
    return df


def entity_styles(entities):
    """color+linestyle per instrument: color cycles every 8 (PALETTE), and a
    second linestyle kicks in once colors wrap, so identity is never lost
    even with >8 instruments sharing one laser wavelength."""
    n = len(entities)
    if n > len(PALETTE):
        logger.info(f"{n} instruments share one laser wavelength; using "
                    f"{len(PALETTE)} colors x linestyle to keep each distinct")
    styles = {}
    for i, ent in enumerate(sorted(entities)):
        color = PALETTE[i % len(PALETTE)]
        linestyle = LINESTYLES[(i // len(PALETTE)) % len(LINESTYLES)]
        styles[ent] = (color, linestyle)
    return styles


def overlay(ax, curves_wl, ycol, styles, ylabel, title, fallback_col=None,
            peaks_wl=None, peak_ycol=None):
    """One line per instrument (color+linestyle identity, see entity_styles).
    Instruments whose curve was gated out (all-NaN ycol) get their raw peak
    points scattered instead, if peaks are supplied, so the data is shown
    without inventing a curve. A fallback curve (e.g. pixel resolution
    standing in for spectral resolution) is drawn dotted to mark it as such."""
    for ent, (color, linestyle) in styles.items():
        sub = curves_wl.loc[curves_wl["entity"] == ent]
        if not sub.empty and sub[ycol].notna().any():
            ax.plot(sub["raman_shift"], sub[ycol], color=color, linewidth=1.8,
                    linestyle=linestyle, label=ent)
        elif not sub.empty and fallback_col is not None and sub[fallback_col].notna().any():
            ax.plot(sub["raman_shift"], sub[fallback_col], color=color, linewidth=1.2,
                    linestyle=":", label=f"{ent} ({fallback_col}, no calcite)")
        elif peaks_wl is not None and peak_ycol is not None:
            pk = peaks_wl.loc[(peaks_wl["entity"] == ent) & (peaks_wl["sample"] == "Neon")]
            if not pk.empty:
                ax.scatter(pk["center"], pk[peak_ycol], color=color, s=14,
                           alpha=0.6, label=f"{ent} (points only, <{MIN_NEON_PEAKS} peaks)")
    ax.set_xlabel("Raman shift/cm⁻¹")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(**GRID_KW)
    ax.legend(fontsize=7, ncol=2 if len(styles) > 8 else 1)


def resolution_envelope(curves_wl, styles, npoints=500):
    """Pointwise maximum of the spectral resolution curves on a common grid."""
    valid = curves_wl.dropna(subset=["spectral_res"])
    if valid.empty:
        return None
    grid = np.linspace(valid["raman_shift"].min(), valid["raman_shift"].max(), npoints)
    stack = []
    for ent in styles:
        sub = valid.loc[valid["entity"] == ent].sort_values("raman_shift")
        if len(sub) < 2:
            continue
        stack.append(np.interp(grid, sub["raman_shift"], sub["spectral_res"],
                               left=np.nan, right=np.nan))
    if not stack:
        return None
    arr = np.vstack(stack)
    n_instruments = np.sum(~np.isnan(arr), axis=0)
    with np.errstate(all="ignore"):
        envelope = np.where(n_instruments > 0, np.nanmax(arr, axis=0), np.nan)
    return pd.DataFrame({"raman_shift": grid,
                         "target_resolution": envelope,
                         "n_instruments": n_instruments})


def caption(text):
    """Figure-legend style explanation, as in a paper, shown under a plot."""
    display(HTML(f'<p style="max-width:900px;color:#52514e;font-size:0.9em;'
                 f'margin-top:-0.5em">{text}</p>'))


def plot_sres_bars(summary):
    """ASTM E2529 spectral resolution per instrument, colored by laser wavelength."""
    valid = summary.dropna(subset=["spectral_resolution"]).sort_values(
        ["laser_wl", "spectral_resolution"])
    missing = summary.loc[summary["spectral_resolution"].isna(), "entity"].tolist()
    if missing:
        toc_heading(f"No spectral resolution value (calcite missing/not fitted): "
                    f"{', '.join(missing)}", "p")
    if valid.empty:
        return
    laser_wls = sorted(valid["laser_wl"].unique())
    wl_color = {wl: PALETTE[i % len(PALETTE)] for i, wl in enumerate(laser_wls)}
    fig, ax = plt.subplots(figsize=(max(6, 0.8 * len(valid)), 4))
    bars = ax.bar(valid["entity"], valid["spectral_resolution"],
                  color=[wl_color[wl] for wl in valid["laser_wl"]], width=0.6)
    ax.bar_label(bars, fmt="%.1f", fontsize=8, color="#52514e")
    handles = [plt.Rectangle((0, 0), 1, 1, color=wl_color[wl]) for wl in laser_wls]
    ax.legend(handles, [f"{wl} nm" for wl in laser_wls], title="laser")
    ax.set_ylabel("Spectral resolution/cm⁻¹ (ASTM E2529)")
    ax.set_title("Spectral resolution per instrument")
    ax.grid(axis="y", **GRID_KW)
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    plt.show()
    caption(
        "<b>Figure 1.</b> Spectral resolution (CWA 18133 §3.1.10) of each "
        "instrument/optical path, derived from the FWHM of the calcite "
        "~1085.91 cm⁻¹ band via the ASTM E2529 formula "
        "(SRes = FWHM / 0.684 &minus; 1.029). Bars are grouped by laser "
        "wavelength (color, see legend) because resolution is not "
        "comparable across different excitation wavelengths. A lower bar "
        "means a sharper (better-resolving) instrument. Instruments without "
        "a calcite spectrum, or where the calcite peak fit failed, are "
        "listed separately above and omitted from the chart rather than "
        "assigned a fabricated value.")


toc_heading(f"Resolution-aware comparison across instruments {context}", "h1")
toc_heading(
    "This report aggregates the per-instrument outputs of the spectrares "
    "tasks, which implement CWA 18133:2024 Figure 2, sections 3 and 4 "
    "(spectral distribution, pixel/spectral resolution and SpeD:SRes "
    "curves - see spectrares_&lt;key&gt; reports for the per-instrument "
    "detail). Instruments are compared only within the same laser "
    "wavelength, since resolution and dispersion depend on the excitation "
    "wavelength and are not directly comparable across lasers. Each "
    "instrument keeps one fixed color (and, once more than 8 instruments "
    "share a laser wavelength, one of 4 linestyles paired with that color) "
    "across every figure below, so a given trace always identifies the "
    "same instrument/optical path.", "p")

try:
    summary = with_entity(load_products("summary"))
    curves = with_entity(load_products("curves"))
    peaks = with_entity(load_products("peaks"))

    toc_heading("Summary of all instruments", "h2")
    display(summary.drop(columns=["pixel_res_coeffs"], errors="ignore"))
    summary.to_csv(product["summary"], index=False)
    caption(
        "<b>Table 1.</b> One row per instrument/optical path/laser "
        "wavelength: number of neon peaks fitted, whether a resolution "
        "curve could be trusted (<code>curve_ok</code>, requires &ge; 6 "
        "neon peaks) and whether it is monotonically non-decreasing "
        "(<code>curve_monotonic</code>), the neon-peak span the curve is "
        "valid over (<code>fit_lo</code>/<code>fit_hi</code>), the calcite "
        "1085.91 cm⁻¹ fit and resulting ASTM E2529 spectral resolution, "
        "the laser-effect scaling ratio applied to the pixel-resolution "
        "curve, and the CWA 18133 Table 1 boundary-of-use check "
        "(pixel resolution &lt; 0.8 nm).")

    plot_sres_bars(summary)

    envelopes = []
    for laser_wl, curves_wl in curves.groupby("laser_wl"):
        toc_heading(f"Laser {laser_wl} nm", "h2")
        styles = entity_styles(curves_wl["entity"].unique())
        peaks_wl = peaks.loc[peaks["laser_wl"] == laser_wl] if not peaks.empty else None

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 4))
        overlay(ax1, curves_wl, "sped", styles,
                "Spectral distribution/cm⁻¹ per pixel", "Spectral distribution curves")
        overlay(ax2, curves_wl, "spectral_res", styles,
                "FWHM/cm⁻¹", "Spectral resolution curves", fallback_col="pixel_res",
                peaks_wl=peaks_wl, peak_ycol="fwhm")

        envelope = resolution_envelope(curves_wl, styles)
        if envelope is not None:
            ax2.plot(envelope["raman_shift"], envelope["target_resolution"],
                     color="#0b0b0b", linewidth=2.4, linestyle=":",
                     label="harmonization target (envelope)")
            ax2.legend(fontsize=7, ncol=2 if len(styles) > 8 else 1)
            envelope.insert(0, "laser_wl", laser_wl)
            envelopes.append(envelope)
        plt.tight_layout()
        plt.show()
        caption(
            f"<b>Figure {laser_wl}.1.</b> Left: spectral distribution curve "
            "(CWA §3.1.9) - the Raman-shift width each detector pixel "
            "covers on the calibrated axis, i.e. sampling density (lower = "
            "finer sampling). Right: spectral resolution curve (CWA "
            "§3.1.11, solid/dashed lines) - the neon-derived pixel "
            "resolution curve rescaled by the calcite/E2529 measurement to "
            "give the true achievable Raman resolution (lower = sharper "
            "optics). A dotted line without the calcite rescale means that "
            "instrument had no usable calcite fit, so only its unscaled "
            "pixel-resolution curve is shown; scattered points mark "
            "instruments with too few neon peaks (&lt;6) to fit any curve. "
            "The black dotted line is the harmonization target: the "
            "point-wise worst (largest FWHM) resolution across all "
            "instruments at that laser wavelength - the resolution every "
            "instrument's spectrum would need to be degraded to for a "
            "resolution-matched, apples-to-apples comparison (CWA "
            "objective 2).")

        fig, ax3 = plt.subplots(figsize=(7.5, 4))
        overlay(ax3, curves_wl, "sped_sres", styles, "SpeD:SRes", "SpeD:SRes curves")
        plt.tight_layout()
        plt.show()
        caption(
            f"<b>Figure {laser_wl}.2.</b> SpeD:SRes = spectral distribution "
            "&divide; spectral resolution, at each point of the calibrated "
            "Raman-shift axis. Values well below 1 mean the instrument "
            "samples far more finely than its optics can actually resolve "
            "(safe, but pixels carry little extra information); values "
            "approaching or exceeding 1 mean the pixel spacing is coarser "
            "than the optical resolution (the instrument is under-sampling "
            "and may alias or blur closely spaced peaks).")

    df_envelope = pd.concat(envelopes, ignore_index=True) if envelopes else pd.DataFrame()
    df_envelope.to_csv(product["envelope"], index=False)
    if not df_envelope.empty:
        toc_heading("Harmonization target", "h2")
        display(df_envelope.groupby("laser_wl")
                .agg(shift_min=("raman_shift", "min"), shift_max=("raman_shift", "max"),
                     target_max=("target_resolution", "max"),
                     n_instruments_max=("n_instruments", "max")))
        caption(
            "<b>Table 2.</b> Per laser wavelength: the Raman-shift span "
            "covered by the harmonization envelope, the worst (largest) "
            "target resolution within it, and the maximum number of "
            "instruments contributing to any single point of the envelope "
            "(fewer instruments near the edges of the shared range, where "
            "not every instrument's neon-peak coverage extends).")
except Exception:
    traceback.print_exc()
