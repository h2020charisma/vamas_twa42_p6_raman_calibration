"""Figures for the deck.

Two kinds of picture end up in the slides:

- **plots generated here** from the run's own CSVs (resolution curves, error
  bars with standard deviation), written as PNG next to the deck;
- **figures the pipeline already produced** per participant, copied next to the
  deck and referenced, so the deck shows the same pictures as the reports
  rather than a redrawn approximation.

Everything writes into one `figures/` directory beside the deck, so the deck
plus that directory is the whole portable artifact.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from matched_peaks_analysis import plot_calibration_analysis  # noqa: E402

# Shared with resolution_compare.py so the deck matches the other reports.
PALETTE = ["#2a78d6", "#1baf7a", "#eda100", "#008300",
           "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]
LINESTYLES = ["-", "--", "-.", ":"]
GRID_KW = {"color": "#e1e0d9", "linewidth": 0.8}
FIG_KW = dict(dpi=150, bbox_inches="tight", facecolor="white")

# Fixed colours for the verification materials: the palette's blue and green sit
# too close to be told apart under a dashed overlay.
MATERIAL_COLORS = {
    "CAL": "#2a78d6",   # calcite, blue
    "PST": "#eb6834",   # polystyrene, orange
    "S0B": "#4a3aa7",
    "S0N": "#008300",
    "APAP": "#e87ba4",
}

#  reference sample peaks positions verification is scored against (cm-1), the
# same lookup as get_reference_peaks() in calibration_verify.py, reused here
# rather than duplicated by value so a future change to the reference table
# only needs to happen in one place. Kept as a lazy import to avoid a hard
# dependency for callers that only need the other figures.
def _reference_positions(tag):
    from calibration_verify import get_reference_peaks
    refs = get_reference_peaks(tag)
    return sorted(refs.keys()) if refs else []


def _style(ax, xlabel, ylabel, title=None):
    ax.grid(True, **GRID_KW)
    ax.set_axisbelow(True)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    if title:
        ax.set_title(title, fontsize=10, fontweight="bold")
    ax.tick_params(labelsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)


def resolution_curves_figure(df_curves, out_dir, filename="resolution_curves.png"):
    """CWA 18133 sections 3-4 curves, as the pipeline itself computes them.

    Two rows, one column per laser wavelength, matching the quantities in
    `resolution_curves.csv`:

    - top: the **spectral resolution curve** (FWHM in cm-1 against Raman
      shift) with the neon-derived pixel resolution curve shown dashed where it
      differs, since the spectral curve is that curve rescaled by the calcite
      measurement;
    - bottom: the **SpeD:SRes ratio**, i.e. how many calibrated-axis points fall
      within one resolution element, which says whether the sampling is fine
      enough for the resolution actually achieved.

    A configuration whose calcite fit was rejected has no spectral resolution
    curve by construction; it is counted in the caption rather than drawn, so an
    absent line is never mistaken for a flat one.
    """
    if df_curves is None or df_curves.empty:
        return None, "no resolution curves available"

    df = df_curves.copy()
    for col in ("raman_shift", "sped", "pixel_res", "spectral_res", "sped_sres"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["entity"] = df["key"].astype(str) + " " + df["optical_path"].astype(str)

    lasers = sorted(df["laser_wl"].dropna().unique())
    if not lasers:
        return None, "no laser wavelengths in resolution curves"

    fig, axes = plt.subplots(2, len(lasers), figsize=(5.6 * len(lasers), 6.2),
                             squeeze=False)
    drawn = skipped = 0
    for col, laser in enumerate(lasers):
        sub = df.loc[df["laser_wl"] == laser]
        entities = sorted(sub["entity"].unique())
        ax_res, ax_ratio = axes[0][col], axes[1][col]
        title = f"{laser:g} nm" if isinstance(laser, (int, float)) else str(laser)

        for i, ent in enumerate(entities):
            e = sub.loc[sub["entity"] == ent].sort_values("raman_shift")
            color = PALETTE[i % len(PALETTE)]
            ls = LINESTYLES[(i // len(PALETTE)) % len(LINESTYLES)]
            sres = e.get("spectral_res")
            if sres is not None and sres.notna().any():
                ax_res.plot(e["raman_shift"], sres, color=color, linestyle=ls,
                            linewidth=1.6, label=ent)
                drawn += 1
            else:
                # no valid calcite scaling: show the neon-derived curve instead,
                # dashed and unlabelled as spectral resolution
                pres = e.get("pixel_res")
                if pres is not None and pres.notna().any():
                    ax_res.plot(e["raman_shift"], pres, color=color,
                                linestyle=":", linewidth=1.1, alpha=0.75,
                                label=f"{ent} (pixel res.)")
                skipped += 1
            ratio = e.get("sped_sres")
            if ratio is not None and ratio.notna().any():
                ax_ratio.plot(e["raman_shift"], ratio, color=color, linestyle=ls,
                              linewidth=1.6, label=ent)

        _style(ax_res, "", "FWHM / cm$^{-1}$",
               f"{title} — spectral resolution")
        _style(ax_ratio, "Raman shift / cm$^{-1}$", "SpeD : SRes",
               f"{title} — sampling per resolution element")
        if entities:
            ax_res.legend(fontsize=6, frameon=False, ncol=2)

    fig.tight_layout()
    path = Path(out_dir) / filename
    fig.savefig(path, **FIG_KW)
    plt.close(fig)
    caption = ("Top: spectral resolution (FWHM) against Raman shift, "
               f"{drawn} optical configurations. Bottom: ratio of spectral "
               "distribution to spectral resolution"
               + (f". {skipped} configurations without a valid calcite fit are "
                  "shown dotted as neon-derived pixel resolution"
                  if skipped else ""))
    return path.name, caption


def error_bars_figure(df_samples, out_dir, filename="sample_errors.png",
                      stages=("1.original", "2.x-clbr", "3.y-clbr")):
    """Deviation from reference sample peak positions, as boxplots.

    One panel per material, one box per stage, built from one mean |error|
    per optical path (an optical path contributes several matched peaks, so
    it is collapsed to its mean first — the box then shows how paths differ
    from each other, not how peaks differ within a path). Points are the
    individual optical paths, jittered, matching the neon boxplot's style so
    the two "before/after" results in the deck read as the same kind of
    picture.
    """
    if df_samples is None or df_samples.empty:
        return None, "no sample statistics available"

    df = df_samples.copy()
    df["abs_d"] = pd.to_numeric(df["distances"], errors="coerce").abs()
    per_path = (df.groupby(["sample", "before_after", "key", "laser_wl",
                             "optical_path"])["abs_d"]
                  .mean().reset_index())

    materials = sorted(per_path["sample"].unique())
    if not materials:
        return None, "no materials in sample statistics"

    fig, axes = plt.subplots(1, len(materials),
                             figsize=(2.9 * len(materials), 3.6),
                             squeeze=False, sharey=False)
    rng = np.random.default_rng(0)
    for col, material in enumerate(materials):
        ax = axes[0][col]
        sub = per_path.loc[per_path["sample"] == material]
        data = [sub.loc[sub["before_after"] == s, "abs_d"].to_numpy(dtype=float)
                for s in stages]
        data = [d[np.isfinite(d)] for d in data]
        bp = ax.boxplot(data, showfliers=False, widths=0.5, patch_artist=True)
        for i, (patch, vals) in enumerate(zip(bp["boxes"], data)):
            patch.set_facecolor(PALETTE[i % len(PALETTE)])
            patch.set_alpha(0.35)
            patch.set_edgecolor(PALETTE[i % len(PALETTE)])
            if vals.size:
                jitter = rng.uniform(-0.12, 0.12, size=vals.size)
                ax.scatter(np.full(vals.size, i + 1) + jitter, vals, s=8,
                           color=PALETTE[i % len(PALETTE)], alpha=0.6,
                           linewidths=0, zorder=3)
        for line in bp["medians"]:
            line.set_color("#2a2a2a")
            line.set_linewidth(1.4)
        ax.set_xticks(range(1, len(stages) + 1))
        ax.set_xticklabels([s.split(".", 1)[-1] for s in stages],
                           rotation=30, ha="right", fontsize=7)
        _style(ax, "", "|error| / cm$^{-1}$", material)

    fig.tight_layout()
    path = Path(out_dir) / filename
    fig.savefig(path, **FIG_KW)
    plt.close(fig)
    return path.name, ("Each point is one optical path's mean |error| "
                       "against reference sample peak positions; box shows "
                       "median and IQR across optical paths")


def neon_figure(df_ne, out_dir, filename="neon_residuals.png"):
    """Neon anchor residual before and after calibration, as boxplots.

    One box per (laser, stage) over every matched neon line from every
    optical path: median, IQR and whiskers, with individual lines are shown
    as a jittered scatter so outliers are still visible as points rather than
    hidden in a whisker. A mean+-SD bar chart understates the before/after
    story here because the "before" distribution is exactly the
    heavy-tailed one the calibration is meant to fix.
    """
    if df_ne is None or df_ne.empty:
        return None, "no neon data available"

    df = df_ne.copy()
    if "sample" in df.columns:
        df = df.loc[df["sample"].astype(str).str.strip() == "Ne"]
    df["abs_d"] = pd.to_numeric(df["distances"], errors="coerce").abs()
    df = df.loc[df["abs_d"].notna()]
    stages = ["1.original", "2.Ne_clbr"]
    df = df.loc[df["before_after"].isin(stages)]

    lasers = sorted(df["laser_wl"].dropna().unique())
    if not lasers:
        return None, "no per-laser neon data"

    fig, axes = plt.subplots(1, len(lasers), figsize=(3.4 * len(lasers), 3.6),
                             squeeze=False, sharey=True)
    rng = np.random.default_rng(0)
    for col, laser in enumerate(lasers):
        ax = axes[0][col]
        sub = df.loc[df["laser_wl"] == laser]
        data = [sub.loc[sub["before_after"] == s, "abs_d"].to_numpy(dtype=float)
                for s in stages]
        data = [d[np.isfinite(d)] for d in data]
        bp = ax.boxplot(data, showfliers=False, widths=0.5, patch_artist=True)
        for i, (patch, vals) in enumerate(zip(bp["boxes"], data)):
            patch.set_facecolor(PALETTE[i % len(PALETTE)])
            patch.set_alpha(0.35)
            patch.set_edgecolor(PALETTE[i % len(PALETTE)])
            if vals.size:
                jitter = rng.uniform(-0.12, 0.12, size=vals.size)
                ax.scatter(np.full(vals.size, i + 1) + jitter, vals, s=8,
                           color=PALETTE[i % len(PALETTE)], alpha=0.6,
                           linewidths=0, zorder=3)
        for line_key in ("medians",):
            for line in bp[line_key]:
                line.set_color("#2a2a2a")
                line.set_linewidth(1.4)
        ax.set_xticks([1, 2])
        ax.set_xticklabels([s.split(".", 1)[-1] for s in stages])
        title = f"{laser:g} nm" if isinstance(laser, (int, float)) else str(laser)
        _style(ax, "", "|residual| / nm" if col == 0 else "", title)

    fig.tight_layout()
    path = Path(out_dir) / filename
    fig.savefig(path, **FIG_KW)
    plt.close(fig)
    return path.name, ("Neon peak positions against matched NIST lines, "
                       "before and after calibration; each point is one "
                       "matched line, box shows median and IQR")


def resolution_spread_figure(df_res, out_dir, filename="resolution_spread.png"):
    """ASTM E2529 spectral resolution per optical path, sorted, CWA pass/fail
    encoded by colour."""
    if df_res is None or df_res.empty:
        return None, "no resolution summary available"

    df = df_res.copy()
    df["sres"] = pd.to_numeric(df["spectral_resolution"], errors="coerce")
    df = df.loc[df["sres"].notna()].copy()
    if df.empty:
        return None, "no valid spectral resolution values"
    df["label"] = df["key"].astype(str) + " " + df["optical_path"].astype(str)
    ok = df.get("within_cwa_boundary")
    df["ok"] = (ok.astype(str).str.lower().isin(["true", "1"])
                if ok is not None else True)
    df = df.sort_values("sres")

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    colors = ["#1baf7a" if v else "#e34948" for v in df["ok"]]
    ax.bar(np.arange(len(df)), df["sres"], color=colors, width=0.72)
    ax.set_xticks(np.arange(len(df)))
    ax.set_xticklabels(df["label"], rotation=45, ha="right", fontsize=6.5)
    _style(ax, "", "Spectral resolution / cm$^{-1}$")
    handles = [plt.Rectangle((0, 0), 1, 1, color="#1baf7a"),
               plt.Rectangle((0, 0), 1, 1, color="#e34948")]
    ax.legend(handles, ["within CWA boundary", "outside"],
              fontsize=8, frameon=False)
    fig.tight_layout()
    path = Path(out_dir) / filename
    fig.savefig(path, **FIG_KW)
    plt.close(fig)
    return path.name, ("ASTM E2529 spectral resolution per optical path, "
                       "sorted; colour marks the CWA 18133 boundary check")


def intensity_correction_figure(curves, out_dir,
                                filename="intensity_correction.png"):
    """Relative-intensity correction factor against Raman shift.

    `curves` is a sequence of (label, DataFrame with calibrated_cm1 and
    intensity_factor). One line per optical configuration shows how strongly the
    instrument response deviates from the reference (NIST SRM or traceable LED),
    which is the quantity y-calibration removes.
    """
    if not curves:
        return None, "no relative-intensity models available"

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    drawn = 0
    for i, entry in enumerate(curves):
        # (label, dataframe) or (label, dataframe, (lo, hi)) reference range
        label, df = entry[0], entry[1]
        cert_range = entry[2] if len(entry) > 2 else None
        if df is None or df.empty:
            continue
        x = pd.to_numeric(df.get("calibrated_cm1"), errors="coerce")
        y = pd.to_numeric(df.get("intensity_factor"), errors="coerce")
        ok = x.notna() & y.notna()
        # Outside the reference's validity range no correction is defined, so
        # anything plotted there would not be a real intensity factor.
        if cert_range:
            lo, hi = float(cert_range[0]), float(cert_range[1])
            ok &= (x >= lo) & (x <= hi)
        if not ok.any():
            continue
        ax.plot(x[ok], y[ok], linewidth=1.5,
                color=PALETTE[i % len(PALETTE)],
                linestyle=LINESTYLES[(i // len(PALETTE)) % len(LINESTYLES)],
                label=label)
        drawn += 1
    if not drawn:
        plt.close(fig)
        return None, "relative-intensity models contained no usable curve"

    ax.axhline(1.0, color="#4a4a4a", linewidth=0.9, linestyle=":")
    # The factors differ by orders of magnitude between instruments, so on a
    # linear axis all but the largest collapse onto the baseline.
    ax.set_yscale("log")
    _style(ax, "Raman shift / cm$^{-1}$",
           "Intensity correction factor (log scale)")
    ax.legend(fontsize=6.5, frameon=False, ncol=2)
    fig.tight_layout()
    path = Path(out_dir) / filename
    fig.savefig(path, **FIG_KW)
    plt.close(fig)
    return path.name, ("Multiplicative correction derived from the reference "
                       "response, logarithmic scale; unity (dotted) would mean "
                       "no correction needed")


def intensity_reference_figure(label, spe_measured, certificate, cert_range,
                               out_dir, filename="intensity_reference.png"):
    """The measured intensity reference against its known reference response.

    This is the comparison the correction is derived from: the reference curve
    is what the instrument should have recorded, the measured curve is what it
    did, and their ratio is the correction. Both are normalised, since only the
    shape carries the instrument response. The reference may be a certified
    NIST SRM or a traceable (not certified) LED; the caller's `label` names
    which one this particular curve is.
    """
    if spe_measured is None or certificate is None:
        return None, "no measured intensity reference available"

    x = np.asarray(spe_measured.x, float)
    y = np.asarray(spe_measured.y, float)
    if cert_range:
        lo, hi = float(cert_range[0]), float(cert_range[1])
        keep = (x >= lo) & (x <= hi)
        if keep.any():
            x, y = x[keep], y[keep]
    if x.size == 0:
        return None, "measured reference outside its validity range"

    try:
        reference = np.asarray(certificate.Y(x), float)
    except Exception as exc:
        return None, f"could not evaluate the reference response: {exc}"

    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    ax.plot(x, y / (np.nanmax(y) or 1.0), color=PALETTE[0], linewidth=1.4,
            label=f"measured ({label})")
    ax.plot(x, reference / (np.nanmax(reference) or 1.0), color=PALETTE[5],
            linewidth=1.6, linestyle="--", label="reference response")
    _style(ax, "Raman shift / cm$^{-1}$", "normalised intensity")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    path = Path(out_dir) / filename
    fig.savefig(path, **FIG_KW)
    plt.close(fig)
    return path.name, ("Measured broadband reference and its known reference "
                       "response, both normalised; their ratio is the "
                       "correction applied to every spectrum")


def material_stage_figure(df_samples, out_dir, material, units="cm-1"):
    """Per-material calibration analysis, using the pipeline's own plotting.

    Calls `plot_calibration_analysis` on the peaks of a single material, so the
    deck shows the same panels as the assessment report — systematic error per
    laboratory and original against calibrated — rather than a separate summary
    of them. A combined chart would hide that the materials behave differently,
    which is the substantive finding.
    """
    sub = df_samples.loc[df_samples["sample"] == material].copy()
    if sub.empty:
        return None, f"no peaks for {material}"

    path = Path(out_dir) / f"material_{material}.png"
    try:
        plot_calibration_analysis(sub, units=units, output_path=str(path))
    except Exception as exc:
        return None, f"could not plot {material}: {exc}"
    finally:
        plt.close("all")
    if not path.is_file():
        return None, f"no figure written for {material}"
    return path.name, (f"{material}: error distribution, systematic error per "
                       "laboratory and configuration, and original against "
                       "calibrated, at each processing stage")


def worked_example_figure(spe_neon, spe_neon_cal, calmodel, spe_sil,
                          spe_sil_cal, samples, out_dir,
                          filename="worked_example.png", title="",
                          sample_lo_cm1=100.0, error_table=None):
    """The calibration of one optical configuration, step by step.

    Four panels showing what was actually fitted rather than a summary of it:
    the neon spectrum with the reference lines it was matched to, the fitted
    calibration curve, the silicon band that fixes the wavenumber origin, and
    the sample spectra before and after correction.

    `error_table`, if given, is the output of
    `per_configuration_material_all_stages` for this exact configuration - the
    mean/median |error| per material at each stage - printed as a small table
    in panel 4. The spectrum plot alone can look fine while a matched-peak
    statistic elsewhere is large (a mismatched reference line, not a bad
    calibration), so the numbers that go with the plot are shown next to it
    rather than left implicit.

    Every argument may be None; the corresponding panel is then annotated as
    unavailable instead of the figure failing, because the deck must still build
    when one spectrum is missing for a laboratory.
    """
    fig, axes = plt.subplots(2, 2, figsize=(11.0, 6.4))
    (ax_ne, ax_curve), (ax_si, ax_spe) = axes

    # 1. neon, measured against the reference lines it is matched to
    if spe_neon is not None:
        ax_ne.plot(spe_neon.x, spe_neon.y, color=PALETTE[0], linewidth=0.9,
                   label="measured")
        _style(ax_ne, "wavelength / nm" if spe_neon_cal is None else
               "x (uncalibrated)", "intensity", "1. Neon reference spectrum")
        ax_ne.legend(fontsize=7.5, frameon=False)
    else:
        _style(ax_ne, "", "", "1. Neon reference spectrum")
        ax_ne.text(0.5, 0.5, "not available", ha="center", va="center",
                   transform=ax_ne.transAxes, color="#8a8a8a", fontsize=9)

    # 2. the fitted calibration curve, with the neon lines it was fitted through
    drew_curve = False
    if calmodel is not None:
        try:
            component = calmodel.components[0]
            model = component.model
            grid = np.linspace(float(np.min(model.x)), float(np.max(model.x)),
                               1000)
            ax_curve.plot(grid, model(grid), color=PALETTE[0], linewidth=1.6,
                          label="fitted curve")
            matched = component.matched_peaks
            if matched is not None and len(matched):
                # only the assignments this model was actually derived from
                first = matched.loc[matched["before_after"] == "1.original"] \
                    if "before_after" in matched.columns else matched
                ax_curve.scatter(first["spe"], first["reference"], s=16,
                                 color=PALETTE[5], zorder=3,
                                 label=f"matched neon lines (n={len(first)})")
            drew_curve = True
        except Exception:
            drew_curve = False
    _style(ax_curve, "measured wavelength / nm", "reference wavelength / nm",
           "2. Fitted wavelength calibration")
    if drew_curve:
        ax_curve.legend(fontsize=7.5, frameon=False)
    else:
        ax_curve.text(0.5, 0.5, "not available", ha="center", va="center",
                      transform=ax_curve.transAxes, color="#8a8a8a", fontsize=9)

    # 3. silicon, which fixes the wavenumber origin at 520.45 cm-1
    if spe_sil_cal is not None or spe_sil is not None:
        if spe_sil is not None:
            ax_si.plot(spe_sil.x, spe_sil.y, color="#9aa1a8", linewidth=1.0,
                       label="before")
        if spe_sil_cal is not None:
            ax_si.plot(spe_sil_cal.x, spe_sil_cal.y, color=PALETTE[1],
                       linewidth=1.3, label="after")
            ax_si.axvline(520.45, color=PALETTE[5], linestyle="--",
                          linewidth=1.0, label="520.45 cm$^{-1}$")
            ax_si.set_xlim(480, 560)
        _style(ax_si, "Raman shift / cm$^{-1}$", "intensity",
               "3. Silicon band and wavenumber origin")
        ax_si.legend(fontsize=7.5, frameon=False)
    else:
        _style(ax_si, "", "", "3. Silicon band and wavenumber origin")
        ax_si.text(0.5, 0.5, "not available", ha="center", va="center",
                   transform=ax_si.transAxes, color="#8a8a8a", fontsize=9)

    # 4. a verification sample before and after the full correction, so the
    #    shift the calibration applies is visible rather than merely asserted
    def trimmed(spe):
        """Drop the region below `sample_lo_cm1`.

        Near the laser line the signal is dominated by the Rayleigh wing and the
        edge filter rather than by Raman bands; leaving it in also swamps the
        normalisation, so the bands of interest become invisible.
        """
        x = np.asarray(spe.x, float)
        y = np.asarray(spe.y, float)
        keep = x >= sample_lo_cm1
        return (x[keep], y[keep]) if keep.any() else (x, y)

    drew_sample = False
    for i, entry in enumerate(samples or []):
        # (label, original, x-calibrated, y-calibrated) - the middle stage is
        # optional so a two-stage caller (no y-calibration model) still works.
        if len(entry) == 4:
            label, spe_before, spe_x, spe_after = entry
        else:
            label, spe_before, spe_after = entry
            spe_x = None
        color = MATERIAL_COLORS.get(label, PALETTE[i % len(PALETTE)])
        # Original solid in the material's own colour, x-calibrated dotted,
        # y-calibrated (final) dashed in near-black: three line styles so each
        # stage's effect is separately readable rather than only the endpoints.
        if spe_before is not None:
            x, y = trimmed(spe_before)
            ax_spe.plot(x, y / (np.nanmax(y) or 1.0),
                        linewidth=1.3, color=color, linestyle="-",
                        alpha=0.9, label=f"{label} original")
            drew_sample = True
        if spe_x is not None:
            x, y = trimmed(spe_x)
            ax_spe.plot(x, y / (np.nanmax(y) or 1.0),
                        linewidth=1.2, color=color, linestyle=":",
                        alpha=0.9, label=f"{label} x-calibrated")
            drew_sample = True
        if spe_after is not None:
            x, y = trimmed(spe_after)
            ax_spe.plot(x, y / (np.nanmax(y) or 1.0),
                        linewidth=1.3, color="#1c2024", linestyle="--",
                        alpha=0.85, label=f"{label} y-calibrated")
            drew_sample = True

        # reference positions this material is actually scored against, so a
        # visible offset from the calibrated peak is legible rather than only
        # implied by a separate table
        try:
            for pos in _reference_positions(label):
                if pos >= sample_lo_cm1:
                    ax_spe.axvline(pos, color=color, linestyle="-",
                                  linewidth=0.6, alpha=0.35, zorder=0)
        except Exception:
            pass
    _style(ax_spe, "Raman shift / cm$^{-1}$", "normalised intensity",
           "4. Verification sample: original, x- and y-calibrated")
    if drew_sample:
        ax_spe.legend(fontsize=7.5, frameon=False)
    else:
        ax_spe.text(0.5, 0.5, "not available", ha="center", va="center",
                    transform=ax_spe.transAxes, color="#8a8a8a", fontsize=9)

    # error_table: mean |error| per material at each stage, matching the
    # matched-peak statistics elsewhere in the deck exactly, so a viewer of
    # this plot is not left guessing whether the spectrum shown corresponds to
    # a good or a poor number.
    if error_table is not None and len(error_table):
        stage_labels = {"1.original": "orig", "2.x-clbr": "x-cal",
                        "3.y-clbr": "y-cal"}
        lines = ["material   " + "  ".join(
            f"{stage_labels.get(s, s):>6}" for s in
            ["1.original", "2.x-clbr", "3.y-clbr"])]
        for material in error_table["sample"].unique():
            sub = error_table.loc[error_table["sample"] == material] \
                .set_index("stage")
            cells = []
            for stage in ["1.original", "2.x-clbr", "3.y-clbr"]:
                cells.append(f"{sub.loc[stage, 'mean']:6.1f}"
                             if stage in sub.index else f"{'--':>6}")
            lines.append(f"{material:<10} " + "  ".join(cells))
        ax_spe.text(0.02, 0.98, "\n".join(lines), transform=ax_spe.transAxes,
                    fontsize=6.5, family="monospace", va="top", ha="left",
                    bbox=dict(boxstyle="round", facecolor="white",
                             edgecolor="#c9c2b2", alpha=0.9))

    if title:
        fig.suptitle(title, fontsize=11, fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, 0.96))
    else:
        fig.tight_layout()
    path = Path(out_dir) / filename
    fig.savefig(path, **FIG_KW)
    plt.close(fig)
    return path.name, ("Calibration of a single optical configuration: neon "
                       "reference, fitted wavelength curve, silicon band fixing "
                       "the wavenumber origin, and a verification sample at each "
                       "stage against its  reference sample peaks positions "
                       "(thin vertical lines)")


def copy_pipeline_figure(source, out_dir, filename):
    """Copy a figure the pipeline already produced next to the deck.

    Reusing the existing PNG keeps the deck showing the same picture as the
    per-participant report instead of a redrawn approximation that could drift
    from it.
    """
    src = Path(str(source))
    if not src.is_file():
        return None
    dest = Path(out_dir) / filename
    shutil.copyfile(src, dest)
    return dest.name
