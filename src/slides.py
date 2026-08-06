"""Presentation deck generated from the assessment products.

A talk about the  ILC should not be a hand-maintained HTML file that
drifts from the run it describes. This task reads the assessment CSVs of the
current run, computes every statistic it quotes, and writes a self-contained
deck plus a flat table of the same numbers.

Rerunning with a different `match_mode` / `interpolator` / `fit_ne_peaks`
regenerates the deck with the corresponding numbers, and the per-participant
examples are picked by rule, so they follow the data instead of a story that
was true once.

Products:
  nb    - this notebook, rendered
  deck  - the slide deck (open in a browser, present from it)
  stats - every quoted number as a long table, for checking and for the poster
"""
import json
import pickle
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from IPython.display import HTML, display

from slides_content import (
    gross_mismatches,
    ne_summary,
    overall_summary,
    participation,
    per_configuration_material,
    per_participant,
    pick_examples,
    resolution_stats,
    sample_summary,
    sample_summary_by_laser,
    stats_table,
    ycal_summary,
)
from slides_figures import (
    copy_pipeline_figure,
    error_bars_figure,
    intensity_correction_figure,
    intensity_reference_figure,
    material_stage_figure,
    neon_figure,
    resolution_curves_figure,
    resolution_spread_figure,
    worked_example_figure,
)
from utils import get_config_units, load_calibration_model, load_config
from slides_render import render_deck
from utils import init_logging, toc_heading

# + tags=["parameters"]
upstream = None
product = None
context = ""
meeting = "Raman metrology meeting"
title = "VAMAS TWA42 P6 - Raman calibration ILC"
artifact_cm1 = 20.0
min_example_peaks = 5
ne_outlier_nm = 1.0
# participation accounting: keys the pipeline loaded vs keys it could calibrate
dataset_key = []
calibration_key = []
total_labs = None
max_intensity_curves = 8
# SpectraStream screenshots for the app slide: full paths, as explicit
# parameters rather than derived from this script's own location (a Ploomber
# notebook task has no reliable __file__). Empty string skips the screenshot
# and leaves the placeholder.
spectrastream_screenshot_derive = ""
spectrastream_screenshot_verify = ""
# Configurations walked through step by step. Fixed rather than auto-selected:
# the first has been examined independently by others, and the second is included
# because it shows what the procedure looks like when it does not work.
# Each entry is "key:laser_wl:optical_path:description".
worked_example_specs = [
    "P6_0901:532:OP1:WITec Apyron 300RA",
    "P6_01001:785:OP1:WITec Alpha300_apyron_confocal_Raman",
    "P6_01201:532:OP1:LabRAM HR Evolution",
    "P6_0301:532:SSL1:Cramol532",
    "P6_0701:785:OP4:LabRAM HR evolution",
    "P6_0702:785:OP1:Lightnovo"
]
config_templates = None
config_root = None
neon_tag = "Neon"
si_tag = "S0B"
verify_tags = "CAL,PST,S0N,APAP"
# -


logger = init_logging(Path(product["nb"]).parent, "slides.log")


def read_upstream(task, key):
    """Read one upstream CSV product by name.

    Upstream products are addressed by task and product key rather than by a
    constructed path, so moving an output location cannot silently produce an
    empty deck.
    """
    try:
        path = Path(str(upstream[task][key]))
    except (KeyError, TypeError):
        logger.error(f"upstream {task}[{key}] not declared")
        return pd.DataFrame()
    if not path.is_file():
        logger.error(f"upstream {task}[{key}] missing: {path}")
        return pd.DataFrame()
    df = pd.read_csv(path)
    logger.info(f"{task}[{key}]: {len(df)} rows from {path}")
    return df


def read_gridded_upstream(pattern, key):
    """Concatenate one product across every task of a gridded upstream.

    `spectrares_*` produces one resolution-curve table per laboratory; the deck
    needs them together.
    """
    frames = []
    try:
        tasks = upstream[pattern]
    except (KeyError, TypeError):
        logger.error(f"upstream {pattern} not declared")
        return pd.DataFrame()
    for task_name, products in tasks.items():
        try:
            path = Path(str(products[key]))
        except (KeyError, TypeError):
            logger.warning(f"{task_name}: no product {key}")
            continue
        if not path.is_file():
            logger.warning(f"{task_name}: missing {path}")
            continue
        frames.append(pd.read_csv(path))
    logger.info(f"{pattern}[{key}]: {len(frames)} tables")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def read_ycal_models(max_curves):
    """Find the relative-intensity models and load a sample of their curves.

    The CWA section 8 export writes one CSV of correction factor against Raman
    shift per model; the filename carries the configuration and the certificate
    used, which is what distinguishes an NIST SRM glass from an LED reference.
    """
    models, curves = [], []
    try:
        tasks = upstream["spectracaly_*"]
    except (KeyError, TypeError):
        logger.warning("spectracaly_* not declared; no intensity models")
        return models, curves

    for task_name, products in sorted(tasks.items()):
        try:
            folder = Path(str(products["ycalmodels"]))
        except (KeyError, TypeError):
            continue
        if not folder.is_dir():
            logger.warning(f"{task_name}: missing {folder}")
            continue
        key = folder.parent.name
        for csv_path in sorted(folder.glob("ycalmodel_*_cwa.csv")):
            # ycalmodel_<laser>_<path>_<certificate>_cwa.csv
            parts = csv_path.stem[len("ycalmodel_"):-len("_cwa")].split("_")
            if len(parts) < 3:
                logger.warning(f"unexpected model filename: {csv_path.name}")
                continue
            laser, optical_path, certificate = parts[0], parts[1], "_".join(parts[2:])
            models.append((key, laser, optical_path, certificate))
            if len(curves) < max_curves:
                try:
                    # the certificate's own validity range, so the curve is not
                    # drawn where no correction is defined
                    cert_range = None
                    json_path = csv_path.with_suffix(".json")
                    if json_path.is_file():
                        meta = json.loads(json_path.read_text(encoding="utf-8"))
                        cert_range = (meta.get("certificate", {}) or {}).get(
                            "raman_shift") or meta.get("spectral_range_cm1")
                    curves.append((f"{key} {laser} {optical_path}",
                                   pd.read_csv(csv_path), cert_range))
                except Exception as exc:  # a malformed export must not stop the deck
                    logger.warning(f"could not read {csv_path}: {exc}")
    logger.info(f"intensity models: {len(models)} over "
                f"{len({m[0] for m in models})} laboratories")
    return models, curves


def read_participant_table():
    """The participant/instrument/optical-path list from overview.py's own
    Summary sheet - already computed once for the whole ILC, so this
    reads it rather than re-deriving instrument metadata from the HDF5 files."""
    try:
        path = Path(str(upstream["overview"]["data"]))
    except (KeyError, TypeError):
        logger.warning("upstream overview[data] not declared")
        return pd.DataFrame()
    if not path.is_file():
        logger.warning(f"upstream overview[data] missing: {path}")
        return pd.DataFrame()
    try:
        df = pd.read_excel(path, sheet_name="Summary")
    except Exception as exc:
        logger.warning(f"could not read {path}: {exc}")
        return pd.DataFrame()
    cols = ["id", "instrument_make", "instrument_model", "optical_path",
           "laser_wl"]
    df = df[[c for c in cols if c in df.columns]].drop_duplicates()
    df["calibrated"] = df["id"].astype(str).isin(
        {str(k) for k in calibration_key})
    logger.info(f"overview[data]: {len(df)} participant rows")
    return df


df_participants = read_participant_table()

df_samples = read_upstream("calibration_verify_xy", "matched_peaks")
df_ne = read_upstream("calibration_analysis", "matched_peaks")
df_res = read_upstream("resolution_compare", "summary")
df_curves = read_gridded_upstream("spectrares_*", "curves")
ycal_models, ycal_curves = read_ycal_models(max_intensity_curves)

# A deck with no sample peaks would render as a page of dashes and look like a
# successful build. Fail loudly instead.
if df_samples.empty:
    raise RuntimeError(
        "no sample peaks available from calibration_verify_xy; "
        "cannot generate the deck")

# --- statistics -------------------------------------------------------------

ne = ne_summary(df_ne, outlier_nm=ne_outlier_nm) if not df_ne.empty else pd.DataFrame()
samples = sample_summary(df_samples, artifact_cm1=None)
samples_robust = sample_summary(df_samples, artifact_cm1=artifact_cm1)
samples_by_laser = sample_summary_by_laser(df_samples, artifact_cm1=None)
overall = overall_summary(df_samples, artifact_cm1=artifact_cm1)
participants = per_participant(df_samples)
examples = pick_examples(df_samples, min_peaks=min_example_peaks)
gross = gross_mismatches(df_samples, artifact_cm1=artifact_cm1)
resolution = resolution_stats(df_res) if not df_res.empty else dict(
    n_paths=0, n_within=0, n_outside=0, sres_min=float("nan"),
    sres_max=float("nan"), sres_median=float("nan"),
    spread_factor=float("nan"), failures=[])
ycal = ycal_summary(ycal_models)
parts = participation(dataset_key, calibration_key, total_labs=total_labs)
logger.info(f"participation: {parts['n_calibrated']} calibrated of "
            f"{parts['n_loaded']} loaded; excluded {parts['excluded']}")

for role, row in examples.items():
    logger.info(f"example {role}: {row['key']} {row['laser_wl']} "
                f"{row['optical_path']} -> {row['improvement_pct']:.1f}%")
if not examples:
    logger.warning("no participant examples qualified; that slide will be empty")

# --- context ----------------------------------------------------------------


def parse_context(text):
    """Pull the run options out of the `context` string the other report tasks
    already receive, so the deck states the configuration it describes."""
    out = {"match_mode": "?", "interpolator": "?", "fit_ne_peaks": "?"}
    lowered = str(text)
    for label, key in (("Match mode", "match_mode"),
                       ("Interpolators", "interpolator"),
                       ("Fit Ne peaks", "fit_ne_peaks")):
        if label in lowered:
            tail = lowered.split(label, 1)[1].strip()
            out[key] = tail.split()[0] if tail.split() else "?"
    return out


opts = parse_context(context)
lasers = sorted(str(w) for w in df_samples["laser_wl"].dropna().unique())
n_paths = len(df_res) if not df_res.empty else int(
    df_samples.groupby(["key", "laser_wl", "optical_path"]).ngroups)

ctx = dict(
    title=title,
    meeting=meeting,
    context=context or "unspecified run",
    generated=date.today().isoformat(),
    n_keys=int(df_samples["key"].nunique()),
    n_paths=n_paths,
    lasers=" / ".join(lasers),
    participation=parts,
    **opts,
)

# --- figures ----------------------------------------------------------------

deck_path = Path(str(product["deck"]))
deck_path.parent.mkdir(parents=True, exist_ok=True)
fig_dir = deck_path.parent / "figures"
fig_dir.mkdir(parents=True, exist_ok=True)

figures = {}


def add_figure(slot, result):
    """Record a (filename, caption) pair, logging what could not be drawn."""
    name, caption = result
    if name:
        figures[slot] = (name, caption)
        logger.info(f"figure {slot}: {name}")
    else:
        logger.warning(f"figure {slot} not produced: {caption}")


add_figure("neon", neon_figure(df_ne, fig_dir))
add_figure("samples", error_bars_figure(df_samples, fig_dir))
add_figure("resolution_spread", resolution_spread_figure(df_res, fig_dir))
add_figure("resolution_curves", resolution_curves_figure(df_curves, fig_dir))
add_figure("intensity_correction",
           intensity_correction_figure(ycal_curves, fig_dir))

for slot, src_path, caption in (
        ("spectrastream_derive", spectrastream_screenshot_derive,
         "SpectraStream — Derive calibration"),
        ("spectrastream_verify", spectrastream_screenshot_verify,
         "SpectraStream — Verify: resolution curves")):
    if not src_path:
        continue
    name = copy_pipeline_figure(src_path, fig_dir, f"{slot}.png")
    if name:
        figures[slot] = (name, caption)
        logger.info(f"figure {slot}: copied from {src_path}")
    else:
        logger.warning(f"figure {slot} not found at {src_path}")


# config_templates is a filename relative to config_root, as in the other stages
_config = None
if config_templates and config_root:
    try:
        _config = load_config(Path(config_root) / config_templates)
    except Exception as exc:
        logger.warning(f"could not load {config_templates}: {exc}; "
                       "assuming cm-1 reference units")


def build_worked_example(key, laser_wl, optical_path, slot):
    """Load the spectra and model of one configuration and plot its calibration.

    Uses the same selection rule as the calibration stage (HDR-merged neon where
    present), so the figure shows the data the model was actually derived from.
    """
    try:
        h5 = upstream["spectraframe_*"][f"spectraframe_{key}"]["h5"]
    except (KeyError, TypeError):
        logger.warning(f"no spectraframe product for {key}")
        return None, "worked example unavailable"

    df = pd.read_hdf(str(h5), key="templates_read")
    op = df.loc[(df["background"] == "BACKGROUND_SUBTRACTED")
                & (df["optical_path"] == optical_path)
                & (df["laser_wl"].astype(int) == int(laser_wl))]
    if op.empty:
        logger.warning(f"no rows for {key} {laser_wl} {optical_path}")
        return None, "worked example configuration not found"

    def pick(tag):
        rows = op.loc[op["sample"] == tag]
        if rows.empty:
            return None
        hdr = rows.loc[rows["overexposed"] == "HDR_MERGE"]
        return (hdr if not hdr.empty else rows)["spectrum"].iloc[0]

    spe_neon = pick(neon_tag)
    spe_sil = pick(si_tag)

    calmodel = None
    try:
        calmodels = Path(str(
            upstream["spectracal_*"][f"spectracal_{key}"]["calmodels"]))
        calmodel = load_calibration_model(int(laser_wl), optical_path,
                                          str(calmodels))
    except Exception as exc:
        logger.warning(f"could not load calibration model for {key}: {exc}")

    def apply(spe, tag):
        if spe is None or calmodel is None:
            return None
        try:
            units = (get_config_units(_config, key, tag=tag)
                     if _config else "cm-1")
            return calmodel.apply_calibration_x(spe, spe_units=units)
        except Exception as exc:
            logger.warning(f"could not calibrate {tag} for {key}: {exc}")
            return None

    spe_neon_cal = apply(spe_neon, "neon")
    spe_sil_cal = apply(spe_sil, "si")

    # First available y-calibration model for this configuration, matching
    # calibration_verify.py's own choice of ycalmodels[0].
    ycalmodel = None
    try:
        ydir = Path(str(
            upstream["spectracaly_*"][f"spectracaly_{key}"]["ycalmodels"]))
        for pkl_path in sorted(ydir.glob(
                f"ycalmodel_{int(laser_wl)}_{optical_path}_*.pkl")):
            if pkl_path.name.endswith("_cwa.pkl"):
                continue
            with open(pkl_path, "rb") as fh:
                ycalmodel = pickle.load(fh)
            break
    except Exception as exc:
        logger.warning(f"no relative-intensity model for {key}: {exc}")

    def trim_to_certificate(raw_spe, x_cal_spe):
        """Trim raw and x-calibrated spectra to the y-certificate's validity
        range, using the calibrated axis to decide which points are in range.

        apply_calibration_x only relabels the x-axis - it does not resample -
        so raw and x-calibrated spectra share the same sample positions and a
        mask built from the calibrated axis applies unchanged to the raw one.
        All three stages must be trimmed identically or the normalisation
        (each divided by its own max) is computed over different windows and
        the traces are not actually comparable.
        """
        if ycalmodel is None or x_cal_spe is None:
            return raw_spe, x_cal_spe
        try:
            lo, hi = ycalmodel.ref.raman_shift
            x = np.asarray(x_cal_spe.x, float)
            mask = (x >= lo) & (x <= hi)
            x_cal_trimmed = x_cal_spe.trim_axes(
                method="x-axis", boundaries=ycalmodel.ref.raman_shift)
            raw_trimmed = None
            if raw_spe is not None:
                raw_x = np.asarray(raw_spe.x, float)[mask]
                raw_y = np.asarray(raw_spe.y, float)[mask]
                raw_trimmed = raw_spe.set_new_xaxis(raw_x)
                raw_trimmed.y = raw_y
            return raw_trimmed, x_cal_trimmed
        except Exception as exc:
            logger.warning(f"could not trim to certificate range for "
                           f"{key}: {exc}")
            return raw_spe, x_cal_spe

    def apply_y(spe_x_trimmed):
        """x-calibrated (already trimmed) -> y-calibrated."""
        if spe_x_trimmed is None or ycalmodel is None:
            return None
        try:
            return ycalmodel.process(spe_x_trimmed)
        except Exception as exc:
            logger.warning(f"could not y-calibrate for {key}: {exc}")
            return None

    verification = []
    for tag in [t.strip() for t in str(verify_tags).split(",") if t.strip()]:
        raw = pick(tag)
        x_cal = apply(raw, "si")
        raw, x_cal = trim_to_certificate(raw, x_cal)
        y_cal = apply_y(x_cal)
        if raw is not None or x_cal is not None or y_cal is not None:
            verification.append((tag, raw, x_cal, y_cal))

    return worked_example_figure(
        spe_neon=spe_neon, spe_neon_cal=spe_neon_cal, calmodel=calmodel,
        spe_sil=spe_sil, spe_sil_cal=spe_sil_cal, samples=verification,
        out_dir=fig_dir, filename=f"{slot}.png",
        title=f"{key} · {laser_wl} nm · {optical_path}")


worked_examples = []
per_material_tables = {}
for spec in worked_example_specs:
    parts_spec = str(spec).split(":")
    if len(parts_spec) < 3:
        logger.warning(f"malformed worked example specification: {spec}")
        continue
    wkey, wlaser, wpath = parts_spec[0], parts_spec[1], parts_spec[2]
    description = parts_spec[3] if len(parts_spec) > 3 else ""
    slot = f"worked_{wkey}_{wlaser}_{wpath}"
    try:
        add_figure(slot, build_worked_example(wkey, wlaser, wpath, slot))
    except Exception as exc:
        logger.warning(f"worked example {wkey} failed: {exc}")

    row = participants.loc[
        (participants["key"] == wkey)
        & (participants["laser_wl"].astype(str) == str(wlaser))
        & (participants["optical_path"] == wpath)]
    label = f"{wkey}, {wlaser} nm, configuration {wpath}"
    if description:
        label = f"{label} — {description}"
    worked_examples.append(
        (label, row.iloc[0] if len(row) else None, slot))
    per_material_tables[slot] = per_configuration_material(
        df_samples, wkey, wlaser, wpath)


def build_intensity_reference():
    """Measured broadband reference against its certificate, for one example.

    Taken from the first worked example that has an intensity model, so the
    figure belongs to a configuration already shown step by step.
    """
    from ramanchada2.protocols.calibration.ycalibration import CertificatesDict

    certs = CertificatesDict()
    for spec in worked_example_specs:
        bits = str(spec).split(":")
        if len(bits) < 3:
            continue
        wkey, wlaser, wpath = bits[0], bits[1], bits[2]
        match = [m for m in ycal_models
                 if m[0] == wkey and str(m[1]) == str(wlaser) and m[2] == wpath]
        if not match:
            continue
        certificate_id = match[0][3]
        try:
            h5 = upstream["spectraframe_*"][f"spectraframe_{wkey}"]["h5"]
            df = pd.read_hdf(str(h5), key="templates_read")
            op = df.loc[(df["background"] == "BACKGROUND_SUBTRACTED")
                        & (df["optical_path"] == wpath)
                        & (df["laser_wl"].astype(int) == int(wlaser))]
            # the reference measurement is tagged with the certificate it used
            rows = op.loc[op["sample"].astype(str).str.contains(
                certificate_id.split("_")[0], case=False, na=False)]
            if rows.empty:
                continue
            spe = rows["spectrum"].iloc[0]
            calmodels = Path(str(
                upstream["spectracal_*"][f"spectracal_{wkey}"]["calmodels"]))
            calmodel = load_calibration_model(int(wlaser), wpath, str(calmodels))
            if calmodel is not None:
                spe = calmodel.apply_calibration_x(spe, spe_units="cm-1")
            cert = certs.get(int(wlaser), certificate_id)
            return intensity_reference_figure(
                f"{wkey} {wlaser} nm {wpath}", spe, cert,
                getattr(cert, "raman_shift", None), fig_dir)
        except Exception as exc:
            logger.warning(f"intensity reference for {wkey} failed: {exc}")
    return None, "no measured intensity reference matched a worked example"


try:
    add_figure("intensity_reference", build_intensity_reference())
except Exception as exc:
    logger.warning(f"intensity reference figure failed: {exc}")

materials = sorted(samples["sample"].unique())
for material in materials:
    add_figure(f"material_{material}",
               material_stage_figure(df_samples, fig_dir, material,
                                     units="cm-1"))

# --- render -----------------------------------------------------------------

html = render_deck(
    ctx=ctx,
    ne=ne,
    samples=samples,
    overall=overall,
    resolution=resolution,
    gross=gross,
    artifact_cm1=artifact_cm1,
    figures=figures,
    ycal=ycal,
    materials=materials,
    worked_examples=worked_examples,
    per_material=per_material_tables,
    samples_by_laser=samples_by_laser,
    participants_table=df_participants,
)

deck_path.write_text(html, encoding="utf-8")
logger.info(f"deck written: {deck_path} ({len(html)} bytes)")

stats = stats_table(ne, samples, overall, resolution, examples)
stats_path = Path(str(product["stats"]))
stats.to_csv(stats_path, index=False)
logger.info(f"stats written: {stats_path} ({len(stats)} rows)")

# --- notebook report --------------------------------------------------------

display(HTML(toc_heading("Deck")))
display(HTML(
    f'<p>Slide deck: <a href="{deck_path.name}" target="_blank">'
    f"{deck_path.name}</a> &middot; run: <code>{context}</code></p>"))

display(HTML(toc_heading("Neon anchors (nm)")))
display(ne)

display(HTML(toc_heading("Sample peaks by material (cm-1)")))
display(samples)

display(HTML(toc_heading("Sample peaks, artifacts excluded (cm-1)")))
display(samples_robust)

display(HTML(toc_heading("Pooled by stage and laser (cm-1)")))
display(overall)

display(HTML(toc_heading("Per optical path")))
display(participants)

display(HTML(toc_heading("Examples picked from this run")))
if examples:
    display(pd.DataFrame([
        dict(role=role, key=row["key"], laser_wl=row["laser_wl"],
             optical_path=row["optical_path"],
             median_before=row[f"median_{'1.original'}"],
             median_after=row["final"],
             improvement_pct=row["improvement_pct"],
             n_peaks=row["n_peaks"])
        for role, row in examples.items()]))
else:
    display(HTML("<p>None qualified.</p>"))

display(HTML(toc_heading("Matcher artifacts")))
display(HTML(
    f"<p>{gross['n_gross']} of {gross['n_rows']} scored peaks exceed "
    f"{artifact_cm1:g} cm-1 (max {gross['max_abs']:.1f}); "
    f"{gross['n_gross_still_inlier']} of those are still flagged as inliers.</p>"))
display(gross["worst"])

display(HTML(toc_heading("Resolution")))
display(pd.DataFrame([{k: v for k, v in resolution.items() if k != "failures"}]))
if resolution["failures"]:
    display(pd.DataFrame(resolution["failures"]))

display(HTML(toc_heading("Figures")))
display(pd.DataFrame([dict(slot=slot, file=name, caption=caption)
                      for slot, (name, caption) in figures.items()]))
