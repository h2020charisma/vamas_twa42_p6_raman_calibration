"""CWA 18134:2024 twinning protocol (CHARISMA) — CF + Q_HI per instrument pair.

Twins each configured participant (RI_T) against the configured reference (RI_R):
the TiPS test-sample spectra (>= min_powers distinct laser powers, measured mW
from a calibrated power meter) are x-calibrated with the spectracal calmodels,
paired per laser power and passed through QhiTwinningComponent, which yields the
Correction Factor CF = S_RIR / S_RIT (Formula 3) plus the Q_HI quality factor
(Formula 4, PASS > 0.9) and the CWA section 6.5 verification figures. No
relative-intensity (y) calibration is applied — the CF absorbs the intensity
difference (CWA 18134 section 6.3 processing chain).
"""
import os.path
import traceback
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import display

from twinning_utils import (STATUS_OK, NotEnoughPowers, QhiTwinningComponent,
                            TWINNING_GROUPING_COLS, prepare_key_groups)
from utils import init_logging, load_config, toc_collapsible, toc_heading

# + tags=["parameters"]
product = None
upstream = None
config_templates = None
config_root = None
reference_key = None
twinned_keys = None
tips_sample_tag = "TiPS_Ti"
reference_band_cm1 = 144
boundaries = (50, 2000)
min_powers = 5
power_tolerance = 0.0
validation_powers = None
# -


logger = init_logging(Path(product["nb"]).parent, "twinning.log")
validation_powers = validation_powers or []
boundaries = tuple(boundaries)

_config = load_config(os.path.join(config_root, config_templates))

RESULT_COLUMNS = [
    "reference_key", "twinned_key", "laser_wl", "optical_path_ref", "optical_path_twin",
    "tips_sample_tag", "rrb_cm1", "n_powers_fit", "paired_powers",
    "unpaired_ref_powers", "unpaired_twin_powers",
    "slope_ref", "intercept_ref", "r2_ref", "slope_twin", "intercept_twin", "r2_twin",
    "CF", "Q_HI_mean", "Q_HI_min", "n_powers_validation", "Q_HI_validation_mean",
    "verdict", "reason",
]

qhi_rows, val_rows, harmonized_frames = [], [], []


def key_paths(key):
    """h5 + calmodels paths of one participant from the wildcarded upstream."""
    h5 = upstream["spectraframe_*"][f"spectraframe_{key}"]["h5"]
    calmodels = upstream["spectracal_*"][f"spectracal_{key}"]["calmodels"]
    return h5, calmodels


def groups_for(key):
    h5, calmodels = key_paths(key)
    return prepare_key_groups(key, h5, calmodels, _config, tips_sample_tag,
                              logger=logger, min_powers=min_powers)


def split_validation(frame):
    """(fit_rows, validation_rows) by membership in validation_powers (section 6.5)."""
    if not validation_powers:
        return frame, None
    from ramanchada2.protocols.spectraframe import SpectraFrame
    vpct = {round(float(v), 4) for v in validation_powers}
    mask = frame["laser_power_percent"].map(lambda v: round(float(v), 4) in vpct)
    # loc drops SpectraFrame back to DataFrame — rewrap for the frame methods
    return SpectraFrame(frame.loc[~mask]), SpectraFrame(frame.loc[mask])


def plot_pair(cmp, stem):
    """Save the 2-panel regression/area evaluation and the spectra overlay figure."""
    ax = cmp.plot()
    fig = ax[0].figure
    fig.savefig(os.path.join(product["plots"], f"{stem}_evaluation.png"), dpi=150)
    plt.close(fig)

    # section 6.5(b): twinned spectra x CF coincide with the reference per power
    fig, (ax_pre, ax_post) = plt.subplots(1, 2, figsize=(14, 3), sharex=True)
    ax_pre.set_title("normalized, pre-CF")
    ax_post.set_title(f"harmonized (CF = {cmp.correction_factor:.3f})")
    for _, row in cmp.reference.iterrows():
        row["spe_processed"].plot(ax=ax_pre, color="black")
        row["spe_processed"].plot(ax=ax_post, color="black")
    for _, row in cmp.twinned.iterrows():
        label = f"{row['laser_power_percent']}%"
        row["spe_processed"].plot(ax=ax_pre, linestyle="--", label=label)
        row["spectrum_harmonized"].plot(ax=ax_post, linestyle="--", label=label)
    ax_post.legend(fontsize=7)
    ax_pre.set_xlabel("Raman shift/cm⁻¹")
    ax_post.set_xlabel("Raman shift/cm⁻¹")
    fig.tight_layout()
    fig.savefig(os.path.join(product["plots"], f"{stem}_spectra.png"), dpi=150)
    plt.close(fig)


def run_pair(twin_key, laser_wl, op_ref, frame_ref, op_twin, frame_twin):
    """Twin one (reference, candidate) optical-path pair; returns the summary row."""
    fit_r, val_r = split_validation(frame_ref)
    fit_t, val_t = split_validation(frame_twin)
    cmp = QhiTwinningComponent(
        fit_t, fit_r,
        boundaries=boundaries,
        reference_band_cm1=float(reference_band_cm1),
        grouping_cols=TWINNING_GROUPING_COLS,
        min_powers=min_powers,
        power_tolerance=power_tolerance,
    )
    cmp.derive_model()
    qhi = cmp.compute_qhi()
    row = cmp.summary_fields()

    qhi.insert(0, "twinned_key", twin_key)
    qhi.insert(0, "reference_key", reference_key)
    qhi_rows.append(qhi)
    row["n_powers_validation"] = 0
    row["Q_HI_validation_mean"] = None
    if validation_powers:
        vdf = cmp.validation_qhi(val_r, val_t)
        if not vdf.empty:
            vdf.insert(0, "twinned_key", twin_key)
            vdf.insert(0, "reference_key", reference_key)
            val_rows.append(vdf)
            row["n_powers_validation"] = int(vdf.shape[0])
            row["Q_HI_validation_mean"] = float(vdf["Q_HI"].mean())

    stem = f"{reference_key}__{twin_key}_wl{laser_wl}_{op_ref}_{op_twin}"
    plot_pair(cmp, stem)
    toc_collapsible(
        f"{stem}: CF={cmp.correction_factor:.3f} "
        f"Q_HI_mean={row['Q_HI_mean']:.3f} verdict={row['verdict']}",
        "evaluation: RRB vs laser power regressions (+ CF-corrected overlay); "
        f"see plots/{stem}_evaluation.png and plots/{stem}_spectra.png")
    display(qhi)

    harmonized_frames.append(cmp.twinned.assign(
        reference_key=reference_key, twinned_key=twin_key,
        laser_wl=laser_wl, optical_path_ref=op_ref))
    return row


def skipped_row(twin_key, laser_wl, reason):
    row = {col: None for col in RESULT_COLUMNS}
    row.update({
        "reference_key": reference_key, "twinned_key": twin_key,
        "laser_wl": laser_wl, "tips_sample_tag": tips_sample_tag,
        "rrb_cm1": reference_band_cm1, "verdict": "skipped", "reason": reason,
    })
    return row


toc_heading(
    f"Raman instruments twinning (CWA 18134) — RI_R: {reference_key}, "
    f"tag: {tips_sample_tag}, RRB: {reference_band_cm1} cm-1", "h1")

for path in (product["plots"], product["results"], product["results_xlsx"], product["h5"]):
    Path(path).parent.mkdir(parents=True, exist_ok=True)

summary_rows = []
try:
    ref_groups = groups_for(reference_key)
except Exception:
    traceback.print_exc()
    logger.error(f"reference {reference_key}: TiPS preparation failed")
    ref_groups = {}

for twin_key in [k for k in twinned_keys if k != reference_key]:
    toc_heading(f"RI_T: {twin_key} vs RI_R: {reference_key}", "h2")
    try:
        twin_groups = groups_for(twin_key)
    except Exception:
        traceback.print_exc()
        summary_rows.append(skipped_row(twin_key, None, "participant load failed"))
        continue

    wavelengths = sorted(
        {wl for wl, _ in ref_groups} | {wl for wl, _ in twin_groups}, key=str)
    if not wavelengths:
        summary_rows.append(skipped_row(
            twin_key, None, f"no usable {tips_sample_tag} rows for either instrument"))
        continue

    for laser_wl in wavelengths:
        ref_ops = {op: g for (wl, op), g in ref_groups.items() if str(wl) == str(laser_wl)}
        twin_ops = {op: g for (wl, op), g in twin_groups.items() if str(wl) == str(laser_wl)}
        if not ref_ops:
            summary_rows.append(skipped_row(
                twin_key, laser_wl, f"reference: no {tips_sample_tag} group at {laser_wl} nm"))
            continue
        if not twin_ops:
            summary_rows.append(skipped_row(
                twin_key, laser_wl, f"twinned: no {tips_sample_tag} group at {laser_wl} nm"))
            continue

        for op_ref, (frame_ref, status_ref, reason_ref) in ref_ops.items():
            for op_twin, (frame_twin, status_twin, reason_twin) in twin_ops.items():
                base = {
                    "reference_key": reference_key, "twinned_key": twin_key,
                    "laser_wl": laser_wl, "optical_path_ref": op_ref,
                    "optical_path_twin": op_twin, "tips_sample_tag": tips_sample_tag,
                    "rrb_cm1": reference_band_cm1,
                }
                if status_ref != STATUS_OK:
                    base.update({"verdict": "skipped", "reason": f"reference: {status_ref} ({reason_ref})"})
                    summary_rows.append(base)
                    continue
                if status_twin != STATUS_OK:
                    base.update({"verdict": "skipped", "reason": f"twinned: {status_twin} ({reason_twin})"})
                    summary_rows.append(base)
                    continue
                try:
                    row = run_pair(twin_key, laser_wl, op_ref, frame_ref, op_twin, frame_twin)
                    base.update(row)
                    base.setdefault("reason", "")
                except NotEnoughPowers as err:
                    base.update({"verdict": "not_twinable", "reason": str(err)})
                except Exception as err:
                    traceback.print_exc()
                    base.update({"verdict": "not_twinable", "reason": f"error: {err}"})
                summary_rows.append(base)

df_summary = pd.DataFrame(summary_rows, columns=RESULT_COLUMNS)
df_summary.to_csv(product["results"], index=False)
with pd.ExcelWriter(product["results_xlsx"]) as writer:
    df_summary.to_excel(writer, sheet_name="summary", index=False)
    (pd.concat(qhi_rows) if qhi_rows else pd.DataFrame(columns=["reference_key", "twinned_key"])) \
        .to_excel(writer, sheet_name="qhi_by_power", index=False)
    (pd.concat(val_rows) if val_rows else pd.DataFrame(columns=["reference_key", "twinned_key"])) \
        .to_excel(writer, sheet_name="qhi_validation", index=False)
if harmonized_frames:
    try:
        pd.concat(harmonized_frames).to_hdf(product["h5"], key="twinned_harmonized", mode="w")
    except Exception:
        logger.warning("could not persist harmonized TiPS spectra:\n" + traceback.format_exc())

toc_heading("Summary", "h2")
display(df_summary[["reference_key", "twinned_key", "laser_wl", "optical_path_ref",
                    "optical_path_twin", "n_powers_fit", "CF", "Q_HI_mean",
                    "verdict", "reason"]])
