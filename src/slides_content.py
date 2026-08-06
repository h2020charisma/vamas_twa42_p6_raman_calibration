"""Statistics and HTML rendering for the presentation deck.

Importable helpers with **no module-level side effects**, so the numbers that
end up on a slide can be unit-tested without building the DAG. `slides.py` is
the thin Ploomber driver over this module.

Every figure quoted in the deck is computed here from the assessment CSVs of
one pipeline run, so a rerun with a different `match_mode` / `interpolator`
produces a correspondingly different deck rather than a stale transcription.

Units differ between the two peak tables and must not be mixed: the neon
anchors (`matched_peaks_Ne.csv`) are matched in **nm** against NIST emission
lines, while the sample peaks (`matched_peaks_samples.csv`) are in **cm-1**
against  reference sample peaks Raman positions.
"""
from __future__ import annotations

import html
import math

import numpy as np
import pandas as pd

# Stage labels as written by calibration_verify / calibration_analysis. The
# numeric prefix makes them sort into pipeline order.
NE_STAGE_BEFORE = "1.original"
NE_STAGE_AFTER = "2.Ne_clbr"
SAMPLE_STAGES = ["1.original", "2.x-clbr", "3.y-clbr"]

# Human-readable material names; keys are the `sample` tags used by the run.
MATERIAL_LABELS = {
    "S0B": "Silicon (S0B)",
    "S0N": "Silicon (S0N)",
    "CAL": "Calcite (CAL)",
    "PST": "Polystyrene (PST)",
    "APAP": "Acetaminophen (APAP)",
}

# Shared with resolution_compare.py so the deck matches the other reports
# rather than introducing a second visual language.
PALETTE = ["#2a78d6", "#1baf7a", "#eda100", "#008300",
           "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"]


# --- small numeric helpers --------------------------------------------------


def _abs_distance(df):
    """|distances| as a float Series, NaNs dropped."""
    return pd.to_numeric(df["distances"], errors="coerce").abs().dropna()


def _stats(values):
    """median / mean / sd / p90 / max / rmse / n for one group.

    `sd` is the sample standard deviation (ddof=1) of |error|, undefined for a
    single observation — reported as NaN there rather than as a spurious 0.
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return dict(n=0, median=math.nan, mean=math.nan, sd=math.nan,
                    p90=math.nan, max=math.nan, rmse=math.nan)
    return dict(
        n=int(v.size),
        median=float(np.median(v)),
        mean=float(np.mean(v)),
        sd=float(np.std(v, ddof=1)) if v.size > 1 else math.nan,
        p90=float(np.percentile(v, 90)),
        max=float(np.max(v)),
        rmse=float(np.sqrt(np.mean(v ** 2))),
    )


def pct_change(before, after):
    """Improvement in percent; positive means the error got smaller.

    Returns NaN rather than dividing by zero when there is nothing to improve
    on, so a degenerate group is visibly absent instead of silently 0 or inf.
    """
    if not np.isfinite(before) or not np.isfinite(after) or before == 0:
        return math.nan
    return 100.0 * (before - after) / before


def fmt(value, digits=3, dash="—"):
    """Format a float for a slide, with an explicit dash for missing values."""
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return dash
    return f"{value:.{digits}f}"


def fmt_pct(value, dash="—"):
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return dash
    return f"{value:+.1f}%"


# --- neon anchors -----------------------------------------------------------


def ne_summary(df_ne, outlier_nm=1.0):
    """Neon anchor residuals (nm) before and after calibration.

    `matched_peaks_Ne.csv` is a superset: it carries the neon rows plus the
    sample rows re-included. Only `sample == "Ne"` rows are anchors, and
    filtering on the neon stage labels is what separates them.
    """
    df = df_ne.copy()
    if "sample" in df.columns:
        df = df.loc[df["sample"].astype(str).str.strip() == "Ne"]
    df = df.loc[df["before_after"].isin([NE_STAGE_BEFORE, NE_STAGE_AFTER])]

    rows = []
    for stage in [NE_STAGE_BEFORE, NE_STAGE_AFTER]:
        sub = df.loc[df["before_after"] == stage]
        st = _stats(_abs_distance(sub))
        st["stage"] = stage
        st["laser_wl"] = "all"
        st["outliers"] = int((_abs_distance(sub) > outlier_nm).sum())
        rows.append(st)
        for laser, grp in sub.groupby("laser_wl"):
            g = _stats(_abs_distance(grp))
            g["stage"] = stage
            g["laser_wl"] = str(laser)
            g["outliers"] = int((_abs_distance(grp) > outlier_nm).sum())
            rows.append(g)

    out = pd.DataFrame(rows)
    return out[["stage", "laser_wl", "n", "median", "mean", "sd",
                "p90", "max", "rmse", "outliers"]]


def ne_anchor_counts(df_ne):
    """Anchors per (key, laser, optical_path) at the original stage, with the
    median residual before and after — the per-path view behind the headline."""
    df = df_ne.copy()
    if "sample" in df.columns:
        df = df.loc[df["sample"].astype(str).str.strip() == "Ne"]
    df["abs_d"] = pd.to_numeric(df["distances"], errors="coerce").abs()

    grouped = (df.groupby(["key", "laser_wl", "optical_path", "before_after"])
                 .agg(n=("abs_d", "size"), median=("abs_d", "median"))
                 .reset_index())
    wide = grouped.pivot_table(
        index=["key", "laser_wl", "optical_path"],
        columns="before_after", values=["n", "median"]).reset_index()
    wide.columns = ["_".join(str(p) for p in c if p != "").strip("_")
                    for c in wide.columns]
    return wide


# --- sample peaks -----------------------------------------------------------


def sample_summary(df_samples, artifact_cm1=None):
    """Per (material, stage) accuracy against reference positions, cm-1.

    `artifact_cm1` drops gross mis-assignments before aggregating. This is not
    cosmetic: a handful of peaks matched to the wrong reference line sit tens
    of cm-1 away and dominate any mean or RMSE, so the robust variant is the
    only honest way to quote those two statistics.
    """
    df = df_samples.copy()
    df["abs_d"] = pd.to_numeric(df["distances"], errors="coerce").abs()
    if artifact_cm1 is not None:
        df = df.loc[df["abs_d"] <= artifact_cm1]

    rows = []
    for (sample, stage), grp in df.groupby(["sample", "before_after"]):
        st = _stats(grp["abs_d"])
        st["sample"] = sample
        st["stage"] = stage
        rows.append(st)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["stage_order"] = out["stage"].apply(
        lambda s: SAMPLE_STAGES.index(s) if s in SAMPLE_STAGES else 99)
    out = out.sort_values(["sample", "stage_order"]).drop(columns="stage_order")
    return out[["sample", "stage", "n", "median", "mean", "sd",
                "p90", "max", "rmse"]]


def overall_summary(df_samples, artifact_cm1=None):
    """All materials pooled, per stage and per laser wavelength."""
    df = df_samples.copy()
    df["abs_d"] = pd.to_numeric(df["distances"], errors="coerce").abs()
    if artifact_cm1 is not None:
        df = df.loc[df["abs_d"] <= artifact_cm1]

    rows = []
    for stage, grp in df.groupby("before_after"):
        st = _stats(grp["abs_d"])
        st["stage"] = stage
        st["laser_wl"] = "all"
        rows.append(st)
        for laser, sub in grp.groupby("laser_wl"):
            g = _stats(sub["abs_d"])
            g["stage"] = stage
            g["laser_wl"] = str(laser)
            rows.append(g)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["stage_order"] = out["stage"].apply(
        lambda s: SAMPLE_STAGES.index(s) if s in SAMPLE_STAGES else 99)
    out = out.sort_values(["laser_wl", "stage_order"]).drop(columns="stage_order")
    return out[["stage", "laser_wl", "n", "median", "mean", "sd", "rmse"]]


def sample_summary_by_laser(df_samples, artifact_cm1=None):
    """Per (material, laser wavelength, stage) accuracy, cm-1.

    The two excitation wavelengths have different neon coverage and different
    reference materials in range, so pooling them can hide a real difference in
    how well the procedure works at each.
    """
    df = df_samples.copy()
    df["abs_d"] = pd.to_numeric(df["distances"], errors="coerce").abs()
    if artifact_cm1 is not None:
        df = df.loc[df["abs_d"] <= artifact_cm1]

    rows = []
    for (sample, laser, stage), grp in df.groupby(
            ["sample", "laser_wl", "before_after"]):
        st = _stats(grp["abs_d"])
        st["sample"] = sample
        st["laser_wl"] = str(laser)
        st["stage"] = stage
        rows.append(st)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["stage_order"] = out["stage"].apply(
        lambda s: SAMPLE_STAGES.index(s) if s in SAMPLE_STAGES else 99)
    out = (out.sort_values(["sample", "laser_wl", "stage_order"])
              .drop(columns="stage_order"))
    return out[["sample", "laser_wl", "stage", "n", "median", "mean", "sd",
                "rmse"]]


def per_participant(df_samples):
    """Median |error| per (key, laser, optical path) at each stage, plus the
    percent change from original to the last stage that path actually has."""
    df = df_samples.copy()
    df["abs_d"] = pd.to_numeric(df["distances"], errors="coerce").abs()

    grouped = (df.groupby(["key", "laser_wl", "optical_path", "before_after"])
                 .agg(median=("abs_d", "median"), n=("abs_d", "size"))
                 .reset_index())
    wide = grouped.pivot_table(index=["key", "laser_wl", "optical_path"],
                               columns="before_after",
                               values=["median", "n"]).reset_index()
    wide.columns = ["_".join(str(p) for p in c if p != "").strip("_")
                    for c in wide.columns]

    before = f"median_{SAMPLE_STAGES[0]}"
    x_stage = f"median_{SAMPLE_STAGES[1]}"
    y_stage = f"median_{SAMPLE_STAGES[2]}"
    for col in (before, x_stage, y_stage):
        if col not in wide.columns:
            wide[col] = math.nan

    # the final stage is y-calibrated where it exists, x-calibrated otherwise:
    # not every optical path has a usable intensity certificate.
    wide["final"] = wide[y_stage].where(wide[y_stage].notna(), wide[x_stage])
    wide["improvement_pct"] = [
        pct_change(b, f) for b, f in zip(wide[before], wide["final"])
    ]
    n_col = f"n_{SAMPLE_STAGES[0]}"
    wide["n_peaks"] = wide[n_col] if n_col in wide.columns else math.nan
    return wide.sort_values("improvement_pct", ascending=False)


def pick_examples(df_samples, min_peaks=5, do_no_harm_pct=-5.0):
    """Choose the success / do-no-harm / regression trio **by rule**.

    Hardcoding participant keys would silently lie once the run options change,
    so the examples follow the data:

    - success:     largest improvement, among paths with enough matched peaks
    - do no harm:  smallest starting error among paths the calibration did NOT
                   make meaningfully worse. Requiring the improvement to stay
                   above `do_no_harm_pct` matters: an already-good path that
                   still degraded is a regression, not a demonstration that the
                   method leaves good instruments alone.
    - regression:  worst degradation

    Returns a dict with whichever roles could be filled; a small or uniform
    dataset legitimately yields fewer than three.
    """
    table = per_participant(df_samples)
    before = f"median_{SAMPLE_STAGES[0]}"

    eligible = table.loc[
        (table["n_peaks"].fillna(0) >= min_peaks)
        & table[before].notna()
        & table["final"].notna()
        & table["improvement_pct"].notna()
    ]
    if eligible.empty:
        return {}

    picks = {}
    best = eligible.sort_values("improvement_pct", ascending=False).iloc[0]
    if best["improvement_pct"] > 0:
        picks["success"] = best

    worst = eligible.sort_values("improvement_pct", ascending=True).iloc[0]
    if worst["improvement_pct"] < 0 and worst.name != best.name:
        picks["regression"] = worst

    used = {p.name for p in picks.values()}
    steady = eligible.loc[
        ~eligible.index.isin(used)
        & (eligible["improvement_pct"] >= do_no_harm_pct)
    ]
    if not steady.empty:
        picks["do_no_harm"] = steady.sort_values(before).iloc[0]

    return picks


def per_configuration_material(df_samples, key, laser_wl, optical_path):
    """Median |error| per material for one optical configuration.

    Pooling the materials hides that they behave differently on the same
    instrument, which is exactly what the individual cases are meant to show.
    """
    df = df_samples.copy()
    df["abs_d"] = pd.to_numeric(df["distances"], errors="coerce").abs()
    sub = df.loc[(df["key"].astype(str) == str(key))
                 & (df["laser_wl"].astype(str) == str(laser_wl))
                 & (df["optical_path"].astype(str) == str(optical_path))]
    if sub.empty:
        return pd.DataFrame(columns=["sample", "n", "before", "final",
                                     "improvement_pct"])

    rows = []
    for material, grp in sub.groupby("sample"):
        stages = grp.groupby("before_after")["abs_d"].median()
        before = stages.get(SAMPLE_STAGES[0], math.nan)
        final = math.nan
        for stage in reversed(SAMPLE_STAGES):
            if stage in stages.index and np.isfinite(stages[stage]):
                final = stages[stage]
                break
        n = int((grp["before_after"] == SAMPLE_STAGES[0]).sum())
        rows.append(dict(sample=material, n=n, before=before, final=final,
                         improvement_pct=pct_change(before, final)))
    order = {m: i for i, m in enumerate(["CAL", "PST", "S0B", "S0N", "APAP"])}
    out = pd.DataFrame(rows)
    out["_order"] = out["sample"].map(lambda s: order.get(s, 99))
    return out.sort_values("_order").drop(columns="_order")


def per_configuration_material_all_stages(df_samples, key, laser_wl,
                                          optical_path):
    """Mean and median |error| per material, at each of the three stages
    separately, for one optical configuration.

    `per_configuration_material` collapses x-calibrated and y-calibrated into
    one "final" column, which hides exactly the kind of stage-to-stage jump
    seen on some configurations (e.g. a mismatched peak present at the
    original/x-calibrated stages but excluded by the y-calibration
    certificate's validity window at the y-calibrated stage). This keeps all
    three stages so that is visible rather than hidden.
    """
    df = df_samples.copy()
    df["abs_d"] = pd.to_numeric(df["distances"], errors="coerce").abs()
    sub = df.loc[(df["key"].astype(str) == str(key))
                 & (df["laser_wl"].astype(str) == str(laser_wl))
                 & (df["optical_path"].astype(str) == str(optical_path))]
    if sub.empty:
        return pd.DataFrame(columns=["sample", "stage", "n", "mean", "median"])

    rows = []
    for (material, stage), grp in sub.groupby(["sample", "before_after"]):
        rows.append(dict(sample=material, stage=stage, n=int(len(grp)),
                         mean=float(grp["abs_d"].mean()),
                         median=float(grp["abs_d"].median())))
    order = {m: i for i, m in enumerate(["CAL", "PST", "S0B", "S0N", "APAP"])}
    out = pd.DataFrame(rows)
    out["_m_order"] = out["sample"].map(lambda s: order.get(s, 99))
    out["_s_order"] = out["stage"].apply(
        lambda s: SAMPLE_STAGES.index(s) if s in SAMPLE_STAGES else 99)
    return (out.sort_values(["_m_order", "_s_order"])
              .drop(columns=["_m_order", "_s_order"])
              .reset_index(drop=True))


def gross_mismatches(df_samples, artifact_cm1=20.0):
    """Rows the matcher kept as inliers despite a physically implausible
    distance. These are matcher artifacts, not calibration error, and quoting
    an unrobustified mean without acknowledging them is misleading."""
    df = df_samples.copy()
    df["abs_d"] = pd.to_numeric(df["distances"], errors="coerce").abs()
    gross = df.loc[df["abs_d"] > artifact_cm1].copy()
    flagged_inlier = 0
    if "inlier_mask" in gross.columns:
        mask = gross["inlier_mask"].astype(str).str.lower().isin(["true", "1"])
        flagged_inlier = int(mask.sum())
    return dict(
        n_rows=int(len(df)),
        n_gross=int(len(gross)),
        n_gross_still_inlier=flagged_inlier,
        max_abs=float(gross["abs_d"].max()) if not gross.empty else math.nan,
        worst=gross.sort_values("abs_d", ascending=False).head(5),
    )


# --- resolution -------------------------------------------------------------


def resolution_stats(df_res):
    """Cohort spread of ASTM E2529 spectral resolution and CWA pass/fail."""
    df = df_res.copy()
    sres = pd.to_numeric(df.get("spectral_resolution"), errors="coerce")
    valid = sres.dropna()

    ok_col = df.get("within_cwa_boundary")
    if ok_col is not None:
        ok_mask = ok_col.astype(str).str.lower().isin(["true", "1"])
    else:
        ok_mask = pd.Series(dtype=bool)

    failures = df.loc[~ok_mask].copy() if len(ok_mask) else df.iloc[0:0].copy()
    reasons = []
    for _, row in failures.iterrows():
        why = []
        if not np.isfinite(pd.to_numeric(row.get("spectral_resolution"),
                                         errors="coerce")):
            why.append("no calcite fit")
        if str(row.get("uniform_grid")).lower() in ("true", "1"):
            why.append("vendor-resampled grid")
        max_fwhm = pd.to_numeric(row.get("max_neon_fwhm_nm"), errors="coerce")
        if np.isfinite(max_fwhm) and max_fwhm > 1.0:
            why.append(f"max Ne FWHM {max_fwhm:.2f} nm")
        sr = pd.to_numeric(row.get("spectral_resolution"), errors="coerce")
        if np.isfinite(sr) and sr > 10:
            why.append(f"resolution {sr:.1f} cm-1")
        reasons.append(dict(
            key=row.get("key"),
            laser_wl=row.get("laser_wl"),
            optical_path=row.get("optical_path"),
            reason=", ".join(why) if why else "outside CWA boundary",
        ))

    return dict(
        n_paths=int(len(df)),
        n_within=int(ok_mask.sum()) if len(ok_mask) else 0,
        n_outside=int((~ok_mask).sum()) if len(ok_mask) else 0,
        sres_min=float(valid.min()) if not valid.empty else math.nan,
        sres_max=float(valid.max()) if not valid.empty else math.nan,
        sres_median=float(valid.median()) if not valid.empty else math.nan,
        spread_factor=(float(valid.max() / valid.min())
                       if not valid.empty and valid.min() > 0 else math.nan),
        failures=reasons,
    )


def participation(dataset_keys, calibration_keys, total_labs=None):
    """Account for who is in the analysis and who is not.

    The study has more participants than the analysis has results, and the
    difference is not a detail to gloss over: a laboratory drops out when a
    required reference measurement (typically neon) is absent or unusable, and
    saying so is part of reporting the outcome honestly.
    """
    loaded = [str(k) for k in (dataset_keys or [])]
    calibrated = [str(k) for k in (calibration_keys or [])]
    excluded = [k for k in loaded if k not in set(calibrated)]
    return dict(
        total_labs=total_labs,
        n_loaded=len(loaded),
        n_calibrated=len(calibrated),
        n_excluded=len(excluded),
        excluded=excluded,
    )


def ycal_summary(models):
    """Relative-intensity models available, grouped by reference certificate.

    `models` is a sequence of (key, laser_wl, optical_path, certificate).
    """
    rows = [dict(key=k, laser_wl=w, optical_path=p, certificate=c)
            for k, w, p, c in models]
    if not rows:
        return pd.DataFrame(columns=["certificate", "n_models", "n_labs"])
    df = pd.DataFrame(rows)
    out = (df.groupby("certificate")
             .agg(n_models=("key", "size"), n_labs=("key", "nunique"))
             .reset_index()
             .sort_values("n_models", ascending=False))
    return out


def envelope_stats(df_env):
    """Cohort resolution envelope range per laser wavelength."""
    if df_env is None or df_env.empty:
        return []
    out = []
    for laser, grp in df_env.groupby("laser_wl"):
        target = pd.to_numeric(grp["target_resolution"], errors="coerce").dropna()
        if target.empty:
            continue
        shift = pd.to_numeric(grp["raman_shift"], errors="coerce")
        n_inst = pd.to_numeric(grp.get("n_instruments"), errors="coerce")
        out.append(dict(
            laser_wl=str(laser),
            target_min=float(target.min()),
            target_max=float(target.max()),
            target_median=float(target.median()),
            shift_min=float(shift.min()) if shift.notna().any() else math.nan,
            shift_max=float(shift.max()) if shift.notna().any() else math.nan,
            max_instruments=int(n_inst.max()) if n_inst.notna().any() else 0,
        ))
    return out


# --- flat stats product -----------------------------------------------------


def stats_table(ne, samples, overall, resolution, examples):
    """One long, machine-checkable table of every number the deck quotes.

    A rendered HTML page can look complete after a partial failure; this is
    what a test asserts on.
    """
    rows = []
    for _, r in ne.iterrows():
        subject = f"{r['stage']} / {r['laser_wl']}"
        for metric, col in (("median_nm", "median"), ("mean_nm", "mean"),
                            ("sd_nm", "sd"), ("outliers", "outliers")):
            rows.append(dict(section="neon", subject=subject,
                             metric=metric, value=r[col], n=r["n"]))
    for _, r in samples.iterrows():
        subject = f"{r['sample']} / {r['stage']}"
        for metric, col in (("median_cm1", "median"), ("mean_cm1", "mean"),
                            ("sd_cm1", "sd")):
            rows.append(dict(section="samples", subject=subject,
                             metric=metric, value=r[col], n=r["n"]))
    for _, r in overall.iterrows():
        subject = f"{r['stage']} / {r['laser_wl']}"
        for metric, col in (("median_cm1", "median"), ("mean_cm1", "mean"),
                            ("sd_cm1", "sd")):
            rows.append(dict(section="overall", subject=subject,
                             metric=metric, value=r[col], n=r["n"]))
    for k, v in resolution.items():
        if k == "failures":
            continue
        rows.append(dict(section="resolution", subject="cohort",
                         metric=k, value=v, n=resolution["n_paths"]))
    for role, row in examples.items():
        rows.append(dict(
            section="example", metric=role,
            subject=f"{row['key']} {row['laser_wl']} {row['optical_path']}",
            value=row["improvement_pct"], n=row.get("n_peaks")))
    return pd.DataFrame(rows, columns=["section", "subject", "metric", "value", "n"])


# --- rendering --------------------------------------------------------------


def _esc(text):
    return html.escape(str(text), quote=True)


def svg_before_after(labels, before, after, title, unit,
                     width=430, height=210, lower_is_better=True):
    """Grouped before/after bars as inline SVG.

    Inline rather than a PNG so the deck stays a single self-contained file
    and the type matches the surrounding page.
    """
    values = [v for v in list(before) + list(after) if np.isfinite(v)]
    if not values:
        return f'<p class="muted">No data for {_esc(title)}.</p>'
    vmax = max(values) * 1.18
    pad_l, pad_b, pad_t = 46, 30, 12
    plot_w = width - pad_l - 8
    plot_h = height - pad_b - pad_t
    group_w = plot_w / max(len(labels), 1)
    bar_w = min(group_w * 0.32, 26)

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="{_esc(title)}">']
    for frac in (0, 0.5, 1.0):
        y = pad_t + plot_h * (1 - frac)
        parts.append(f'<line class="grid-line" x1="{pad_l}" y1="{y:.1f}" '
                     f'x2="{width - 8}" y2="{y:.1f}"/>')
        parts.append(f'<text class="axis-label" x="{pad_l - 6}" y="{y + 3:.1f}" '
                     f'text-anchor="end">{vmax * frac:.2f}</text>')

    for i, label in enumerate(labels):
        cx = pad_l + group_w * (i + 0.5)
        for value, offset, cls in ((before[i], -bar_w * 0.55, "bar-before"),
                                   (after[i], bar_w * 0.55, "bar-after")):
            if not np.isfinite(value):
                continue
            h = plot_h * (value / vmax) if vmax else 0
            x = cx + offset - bar_w / 2
            y = pad_t + plot_h - h
            parts.append(f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" '
                         f'width="{bar_w:.1f}" height="{max(h, 0.6):.1f}"/>')
        parts.append(f'<text class="axis-label" x="{cx:.1f}" '
                     f'y="{height - 10}" text-anchor="middle">{_esc(label)}</text>')

    parts.append(f'<text class="axis-label" x="{pad_l - 40}" y="{pad_t - 2}">'
                 f'{_esc(unit)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_spread(values, title, unit, width=430, height=210):
    """Sorted dot plot of one value per optical path — shows the cohort spread
    directly instead of collapsing it to a mean."""
    vals = sorted(v for v in values if np.isfinite(v))
    if not vals:
        return f'<p class="muted">No data for {_esc(title)}.</p>'
    pad_l, pad_b, pad_t = 46, 28, 12
    plot_w = width - pad_l - 10
    plot_h = height - pad_b - pad_t
    vmax = max(vals) * 1.1
    step = plot_w / max(len(vals) - 1, 1)

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="{_esc(title)}">']
    for frac in (0, 0.5, 1.0):
        y = pad_t + plot_h * (1 - frac)
        parts.append(f'<line class="grid-line" x1="{pad_l}" y1="{y:.1f}" '
                     f'x2="{width - 10}" y2="{y:.1f}"/>')
        parts.append(f'<text class="axis-label" x="{pad_l - 6}" y="{y + 3:.1f}" '
                     f'text-anchor="end">{vmax * frac:.1f}</text>')
    for i, v in enumerate(vals):
        x = pad_l + step * i
        y = pad_t + plot_h * (1 - v / vmax)
        parts.append(f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="4"/>')
    parts.append(f'<text class="axis-label" x="{pad_l}" y="{height - 8}">'
                 f'best</text>')
    parts.append(f'<text class="axis-label" x="{width - 10}" y="{height - 8}" '
                 f'text-anchor="end">worst</text>')
    parts.append(f'<text class="axis-label" x="{pad_l - 40}" y="{pad_t - 2}">'
                 f'{_esc(unit)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def table_html(df, columns=None, digits=3, classes="data"):
    """Render a dataframe as a slide table, formatting floats consistently."""
    if df is None or len(df) == 0:
        return '<p class="muted">No rows.</p>'
    cols = columns or list(df.columns)
    head = "".join(f"<th>{_esc(c)}</th>" for c in cols)
    body = []
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row.get(c)
            if isinstance(v, (int, np.integer)):
                cells.append(f"<td>{v}</td>")
            elif isinstance(v, float):
                cells.append(f"<td>{fmt(v, digits)}</td>")
            else:
                cells.append(f"<td>{_esc(v)}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return (f'<div class="table-wrap"><table class="{classes}">'
            f"<thead><tr>{head}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>")
