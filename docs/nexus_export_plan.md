# NeXus export from the pipeline — the calibration workflow as a first-class record

Status: planned. Drafted 2026-08-05.

## Context

The pipeline computes complete x- and y-calibrations over the round-robin dataset but persists them as
`.pkl` (Python-only), `.json` (portable), and CWA 18133 §8 `.csv`/`.json` pairs. It writes no NeXus at
all today, although `nexusformat` and `pyambit` are already declared dependencies in `pyproject.toml`.

**A calibration is its own protocol, not metadata bolted onto a spectrum.** It has its own procedure
(fit a mapping from the raw axis to the calibrated axis against reference standards), its own inputs
(the Ne/Si calibrant spectra), and its own outputs (fit coefficients, a calibrated-axis mapping).
NeXus has a purpose-built representation for exactly this: `NXcalibration`, which `extends="NXprocess"`.

One derived calibration is reapplied to many spectra (Ne, Si, PST, APAP, calcite per optical path), so
the calibration must be its own addressable record that the sample spectra *reference*, not a blob
duplicated onto each one.

**Goal:** a new Ploomber task producing, per participant key, a NeXus bundle that carries the
calibration workflow itself — all calibrants, the processing applied, and the final model in
*reconstructable* form (curve points, spline knots, polynomial coefficients, Si zeroing) — plus the
raw / x-calibrated / y-calibrated sample spectra referencing it.

### Why this pipeline is the right place to build it

The calibrant spectra are already on disk in the spectraframe `.h5`, with the HDR-merge selection logic
already written (`spectraframe_calibrate.py:117-131`). An interactive front-end holding calibrants only
in browser-session memory would need a new persistence design just to get them to an exporter; here
there is nothing to invent. `calibration_verify.py:184-223` additionally already builds the
raw → x-calibrated → y-calibrated triple, proven over the real dataset.

### What is already reconstructable

`CalibrationModel.to_dict()` (`calibration_model.py:105-117`) plus `interpolator_to_tagged_dict`
(`interpolators.py:500-507`) already serialize JSON-clean `coef`/`degree`/`x_min`/`x_max` for
polynomials, `x`/`y` knots for PCHIP, `x_original`/`y_original` anchors, and the Si zeroing float —
round-trip tested in `tests/protocols/test_calmodel_serialization.py`. Nothing new has to be invented
to make the model reconstructable; it has to be *mapped* onto NXcalibration fields.

## Layering

Three repositories, with a split that keeps Raman-calibration concepts out of the generic NeXus layer:

- **pyambit — generic NeXus/NXraman structure only.** Gains `NXcalibration`/`NXprocess` in codegen, a
  field-driven writer, and a `process_pa` bug fix. No notion of Neon, Silicon, laser zeroing, or Raman
  shift.
- **ramanchada2 — the Raman-calibration → NXcalibration mapping.** Lives in
  `protocols/calibration/serialization.py`, beside the `export_cwa_x`/`export_cwa_y` this pipeline
  already imports. This is where `520.45`, `laser_wl`, Ne and Si legitimately belong. Shared by any
  downstream consumer, and covered by that repo's real pytest fixtures.
- **this pipeline — orchestration.** Which (key, laser_wl, optical_path, tag) tuples exist, file naming,
  and instrument metadata harvested from the Excel front sheet.

Because pyambit gains generic capability and ramanchada2 gains the domain mapping, calibration details
do not leak into pyambit.

**Dependency step.** Point at the local pyambit checkout in `pyproject.toml`, the same pattern already
used for ramanchada2:

```toml
[tool.uv.sources]
pyambit = { path = "../pyambit-main", editable = true }
```

Two constraints: the installed pyambit is PyPI `0.0.2` and has **no** `NXRamanProtocolApplication` or
`nexus_models/`, so the local checkout is required; and per `AGENTS.md` a local editable path must not
be committed to `main` — keep it on a branch. The local pyambit working tree is currently dirty; commit
or stash it before wiring this pipeline to it.

## Plan

### Phase 1 — the calibration workflow bundle

Self-contained and independently useful: no changes to any existing stage.

#### 1a. pyambit — generic NXcalibration support

`NXCalibration` currently generates as a near-empty stub (only `device_path`, `calibration_status`) and
`NXProcess` generates as literally `pass`, because neither is in
`DEFAULT_BASE_CLASS_MERGE_TARGETS` (`dev-tools/gen_nexus_models.py:180-189`) and `NXcalibration`'s own
NXDL fields are all optional.

There is a CLI escape hatch (`--merge-base-class`, `gen_nexus_models.py:473-486`), so **verify before
changing any code**:

```
poetry run python dev-tools/gen_nexus_models.py --appdef NXraman \
    --merge-base-class NXcalibration --merge-base-class NXprocess
```

`NXcalibration extends="NXprocess"`, so both are likely needed — confirm empirically rather than
assuming, then promote to the default allowlist. Expect the regenerated model to gain `original_axis`,
`calibrated_axis`, `calibration_parameters` (an `NXparameters` **group**), `calibration_object` (an
`NXnote` **group**), `fit_formula_description`, `identifier_calibration_reference`, `applied`,
`description`, `physical_quantity`, plus inherited `program`/`version`/`date`.

Also fix `process_pa`'s `_default` bug (`nexus_writer.py:673`): `_default` is initialized to `None` and
never reassigned, so `entry.attrs["default"]` is overwritten by every effect and ends up pointing at
the *last* group rather than the primary one.

Note the NXDL is **not vendored** — it comes from the virtualenv, and `pynxtools` and `nexusformat` each
ship a copy. Record which one codegen read; it can shift under you on upgrade.

#### 1b. ramanchada2 — `protocols/calibration/serialization.py`

The existing `export_nexus` (`serialization.py:124-152`) is **unreachable dead code**, imported nowhere
in either repository, so its signature is free to change. Replace it with:

```python
def calibration_to_nxcalibration(calmodel, spectral_range=(100, 3500), npoints=200): ...
    # pure mapping, no I/O -> unit-testable on its own

def export_nexus_calibration(calmodel, filename, spectral_range=(100, 3500), npoints=200,
                             metadata=None, instrument=None, ycal_component=None,
                             spe_neon=None, spe_neon_units="cm-1",
                             spe_silicon=None, spe_silicon_units="cm-1", title=None): ...
```

Keep `export_nexus` as an alias for one release. Reuse `_calibration_curve()` (`:22`) and
`_laser_zero_info()` (`:31`) unchanged — they already do the right thing.

Field mapping — **this is the reconstructable-model requirement**:

| NXcalibration target | Source |
|---|---|
| `original_axis[ncal]` / `calibrated_axis[ncal]` | `_calibration_curve()`; equal length, satisfying the NXDL `ncal` symbol constraint |
| `calibration_parameters/` (NXparameters) | poly: `coef`, `degree`, `x_min`, `x_max`, `fit_error`; pchip: knots `x`, `y`; Si zeroing: `si_peak_nm`, `si_reference_cm1`, `calibrated_laser_wl_nm` from `_laser_zero_info` |
| `calibration_object/` (NXnote) | `json.dumps(calmodel.to_dict())` — the full portable model |
| `fit_formula_description` | interpolator type, degree, normalization, **and the extrapolation rule** |
| `anchors/` (its own NXdata) | `x_original`/`y_original` plus the inlier mask from `XCalibrationComponent.to_dict()["anchors"]` |

Two traps:

- **Anchors are not the axis.** The matched Ne anchors have a different length than `ncal` and are not
  what `original_axis`/`calibrated_axis` mean. They get their own group.
- **Extrapolation must be documented.** Both interpolators continue with *constant correction* (unit
  slope) beyond the anchor span (`interpolators.py:67-89`, `:259-272`). A reader that reimplements naive
  polynomial extrapolation will diverge by tens of nm in the CH-stretch region.

Do **not** build on `Spectrum.write_nexus` / `io/HSDS.py`. It is broken:
`require_group('raman_shift', data=x)` (`HSDS.py:50`) takes no `data=` kwarg, so the x axis is silently
lost; metadata is printed rather than written (`:30-31`); and every block is wrapped in a bare
`except: pass`. Fixing it is an independent chore (phase 3), not a dependency here.

#### 1c. this pipeline — new stage and task

Two new files, deliberately split:

- `src/nexus_export.py` — importable helpers with **no module-level side effects**. This is what makes
  them testable; every existing stage is untestable precisely because it lacks this split.
- `src/spectraframe_nexus.py` — a thin Ploomber notebook-script driver over those helpers.

Insert into `pipeline.yaml` after `calibration_verify_[[mode]]`, before `calibration_analysis`:

```yaml
  # CWA 18133 §8 / NXcalibration: the calibration workflow as a self-describing
  # NeXus record — calibrants, processing, and the reconstructable model.
  - source: spectraframe_nexus.py
    name: "spectranexus_[[key]]"
    upstream: ["spectraframe_*", "spectracal_*", "spectracaly_*"]
    product:
      nb: "{{config_output}}/processed_{{fit_ne_peaks}}_{{match_mode}}_{{interpolator}}/[[key]]/spectranexus.{{report_format}}"
      nexus: "{{config_output}}/processed_{{fit_ne_peaks}}_{{match_mode}}_{{interpolator}}/[[key]]/nexus"
      manifest: "{{config_output}}/processed_{{fit_ne_peaks}}_{{match_mode}}_{{interpolator}}/[[key]]/nexus_manifest.csv"
    params:
      config_templates: "{{config_templates}}"
      config_root: "{{config_root}}"
      neon_tag: "{{ne_tag}}"
      si_tag: "{{si_tag}}"
      pst_tag: "{{pst_tag}}"
      apap_tag: "{{apap_tag}}"
      calcite_tag: "{{calcite_tag}}"
      test_tags: "S0N"
      match_mode: "{{match_mode}}"
      interpolator: "{{interpolator}}"
    nbconvert_export_kwargs:
        exclude_input: True
    grid:
      key: "{{calibration_key}}"
```

- Grid on `{{calibration_key}}`, **not** `{{dataset_key}}` — only calibration keys have calmodels, and
  `spectracaly_*` would not resolve otherwise.
- `nexus` is a **directory product**, mirroring `calmodels` (`pipeline.yaml:41`) and `ycalmodels`
  (`:95`); create it at module level with `mkdir(parents=True, exist_ok=True)` exactly as
  `spectraframe_calibrate.py:378` does.
- `nexus_manifest.csv` (`key, laser_wl, optical_path, tag, kind, filename, n_entries, stages, status,
  error`) is the machine-checkable product. A directory product can look complete after a partial
  failure; the manifest is what a test and the HTML report can assert on.

File layout:

```
<...>/<KEY>/nexus/
    <KEY>_<laser_wl>_<optical_path>_calibration.nxs
    <KEY>_<laser_wl>_<optical_path>_<TAG>.nxs        # phase 2
<...>/<KEY>/nexus_manifest.csv
```

Naming mirrors the existing `calmodel_{laser_wl}_{optical_path}.pkl` convention so files line up across
the sibling `calmodels/`, `ycalmodels/` and `nexus/` directories.

Calibration file structure:

```
entry/                              NXentry, default="calibration_curve"
  title, start_time, program_name (+ version)
  instrument/                       NXinstrument   (front-sheet metadata)
    calibration_x/                  NXcalibration
      description, physical_quantity="wavenumber", applied
      fit_formula_description
      original_axis[ncal], calibrated_axis[ncal]
      calibration_parameters/       NXparameters   (coef/degree/knots/Si zeroing)
      calibration_object/           NXnote         (full to_dict() JSON)
      anchors/                      NXdata         (measured, reference, inlier)
    calibration_y/                  NXcalibration  (when a y-model exists)
  reference_neon/                   NXdata         (as-loaded, + HDR flag)
  reference_silicon/                NXdata         (as-loaded)
  calibration_curve/                NXdata         (the default target; plots directly)
```

**Getting the calibrants.** Replicate `spectraframe_calibrate.py:117-131` *exactly*, so the Ne written
is the one the model was actually derived from:

```python
df = pd.read_hdf(upstream["spectraframe_*"][f"spectraframe_{key}"]["h5"], key="templates_read")
op_data = df.loc[(df["background"] == "BACKGROUND_SUBTRACTED")
                 & (df["optical_path"] == optical_path)]
hdr = op_data.loc[(op_data["sample"] == neon_tag) & (op_data["overexposed"] == "HDR_MERGE")]
spe_neon = (hdr["spectrum"].iloc[0] if not hdr.empty
            else op_data.loc[op_data["sample"] == neon_tag]["spectrum"].iloc[0])
```

Units come from `get_config_units(_config, key, tag="neon"|"si")` — **do not assume cm-1**. Participants
supply nm and pixel; that is exactly why `_ne_units` exists at `spectraframe_calibrate.py:383`. Write
the real unit into the `@units` attribute and name the axis dataset accordingly (`raman_shift`,
`wavelength`, or `pixel`), and record it in the manifest.

Write the calibrants **as loaded**, with the preprocessing recorded in an `NXprocess`/`NXnote`. The
trimmed and baseline-subtracted version is derivable from the raw one; the reverse is not.

Instrument metadata is already merged into every row by `utils.read_template` (`instrument_make`,
`instrument_model`, `grating`, `slit_size`, `collection_optics`, ...); take it from `op_data.iloc[0]`.
Blank Excel cells arrive as `float('nan')` and h5py will happily write those as float datasets where a
string was intended, so coerce and drop them in a helper.

**Failure policy.** Catch per (laser_wl, optical_path) and record the failure in the manifest, but
**re-raise if zero files were written**. Every existing stage wraps its main loop in
`try/except: traceback.print_exc()` (`spectraframe_calibrate.py:386`, `calibration_verify.py:269`);
copying that pattern here would yield an empty directory and a green build.

#### 1d. release.py

`allowed_ext` (`release.py:40`) currently omits `.json` and `.csv`, which means the CWA 18133 §8 portable
files written since `spectraframe_calibrate.py:301-310` have **never been released** — the pipeline
computes the language-independent deliverable and then drops it in favour of the Python-only `.pkl`.
Add `.nxs`, `.json` and `.csv` together. If `.csv` proves too broad, filter on the `_cwa` suffix.
Extend the description map at `:84-93` for `.nxs`, and add `spectranexus_*` to the task's `upstream`.

### Phase 2 — the sample spectra triple

**2a. Extract the shared helper.** Move the preprocessing and stage-building from
`calibration_verify.py:184-205` into `src/utils.py`:

```python
def prepare_sample_spectrum(op_data, tag, boundaries=(300, 3*1024+300), niter=40): ...
def calibration_stages(spe, calmodel, ycalmodel=None): ...   # -> (spectra, stage_labels)
```

Both `calibration_verify.py` and the new stage then call them, which guarantees the spectra written to
NeXus are the *exact* ones the verification report scores rather than a lookalike that silently drifts.

Do this as a **separate, behaviour-preserving commit** and verify `matched_peaks_samples.csv` is
byte-identical before and after — it feeds `calibration_analysis` (`pipeline.yaml:131`).

**2b. Emit the triple.** One file per (laser_wl, optical_path, tag), one `NXentry` per stage
(`stage_1_original`, `stage_2_x_calibrated`, `stage_3_y_calibrated`) rather than one entry with three
`NXdata`, because the stages have different x lengths — y-calibration trims to
`ycalmodel.ref.raman_shift` (`calibration_verify.py:204`).

Each stage's `NXprocess` carries an `h5py.ExternalLink` to the calibration file's `NXcalibration` group.
That is the payoff of writing the calibration as its own record: five sample files per optical path
reference one calibration instead of duplicating it five times.

The root `default` must point at `stage_3_y_calibrated` when it exists and `stage_2_x_calibrated`
otherwise; hardcoding stage 3 leaves a dangling `default` for optical paths with no certificate.

Route the spectra through pyambit's existing `spe2ambit`/`spe2effect` with distinct `endpointtype`
values — `"RAW_DATA"` for stage 1, the family `process_pa` special-cases to a plain `NXgroup`, and
`"X_CALIBRATED"`/`"Y_CALIBRATED"` for the rest — so the existing fan-out does the work unchanged.

### Phase 3 — conformance and propagation

- Validate against the NXraman application definition (`pynxtools dataconverter` / `nxvalidate`).
  **Until that passes, omit the `definition = "NXraman"` field**: claiming conformance that has not been
  verified is worse than omitting it, because a downstream reader will trust it.
- Add the resolution products (`spectrares_*` → `resolution_curves.csv`) to the bundle; the CWA 18133
  Figure 2 §3–4 outputs belong with the calibration. Requires adding `spectrares_*` to the upstream.
- Fix or deprecate `ramanchada2/io/HSDS.py:write_nexus`, and retire `.cha` in favour of NeXus.
- A cross-key aggregate task producing one multi-entry file for the whole round robin.

## Tests

**ramanchada2 — `tests/protocols/test_nexus_export.py`** (the substantive coverage; reuse the existing
`_load`/`calmodel`/`ycal` fixtures from `test_calmodel_serialization.py`, which build genuine models
from bundled data):

- `test_calibration_object_json_roundtrips` — reload the NXnote JSON, `CalibrationModel.from_dict`,
  re-apply, assert the calibrated axis matches to 1e-9. **This is the assertion that proves
  "reconstructable"**, and it mirrors the existing `test_json_roundtrip_x`.
- `test_calibration_parameters_written` — polynomial models expose `coef`/`degree`/`x_min`/`x_max`;
  PCHIP models expose knots; both as numeric datasets, not stringified JSON.
- `test_original_and_calibrated_axis_same_length` — the NXDL `ncal` constraint.
- `test_reference_spectra_written` — `assert_allclose` on **both x and y** of Ne and Si. This is the
  regression guard against exactly the `HSDS.py` failure mode where an axis is silently dropped.
- `test_anchors_not_in_calibrated_axis` — anchors stay in their own group.
- `test_nexusformat_can_open` — `nxload()` structural sanity.

**pyambit** — regenerated `NXCalibration` has the expected fields; a `process_pa` round-trip; and a
regression test that `entry.attrs["default"]` points at the *first* group.

**this pipeline — bootstrap a suite.** There is none today (`AGENTS.md` records testing as aspirational;
`src/TODO.md` asks for it). Put pytest tests in a **new top-level `tests/`**, not `src/tests/` — that
directory holds standalone reproduction scripts including `test_hybrid_matching.py`, which pytest would
collect and execute on import. Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

- `tests/test_nexus_stage.py` — pure helpers against synthetic data, no DAG and no real spectra:
  filename construction; NaN front-sheet values dropped rather than written as floats; manifest schema.
- `tests/test_pipeline_yaml.py` — `yaml.safe_load(pipeline.yaml)`, assert the `spectranexus_[[key]]`
  task exists with the expected upstream trio and that `release.py` runs after it. Milliseconds, no data.

## Verification

1. pyambit: `poetry run pytest tests/pyambit` after regeneration.
2. ramanchada2: `pytest tests/protocols/test_nexus_export.py`.
3. This repo: `uv sync` (picks up the local pyambit), then `uv run pytest` from the repo root.
4. `cd src && uv run ploomber build --partially spectranexus_P6_0301` — one key, the fastest real check.
5. Confirm reconstructability end to end from the file alone:

   ```python
   import h5py, json
   from nexusformat.nexus import nxload
   from ramanchada2.protocols.calibration.calibration_model import CalibrationModel

   nxload("..._calibration.nxs")                      # structural sanity
   with h5py.File("..._calibration.nxs") as f:
       doc = json.loads(f["/entry/instrument/calibration_x/calibration_object/data"][()])
   model = CalibrationModel.from_dict(doc["model"])   # reconstructed from the file alone
   ```

   Then assert `model.apply_calibration_x(...)` reproduces the pipeline's calibrated axis, and that
   `reference_neon`/`reference_silicon` hold non-empty x **and** y.
6. Full `uv run ploomber build`; confirm `matched_peaks_samples.csv` is unchanged (the phase-2
   refactor guard).

## Critical files

- `src/pipeline.yaml` — new task after the `calibration_verify_[[mode]]` block; `release.py` upstream
- `src/spectraframe_calibrate.py:117-131, 295-312` — calibrant selection and the export pattern to mirror
- `src/calibration_verify.py:184-223` — the raw/x-cal/y-cal triple; source of the phase-2 shared helpers
- `src/utils.py` — destination for the shared helpers; already holds `get_config_units`
- `src/release.py:40, 84-93` — extension allowlist and description map
- `ramanchada2 protocols/calibration/serialization.py:124` — replaces the dead `export_nexus`
- `ramanchada2 protocols/calibration/interpolators.py:106-117, 301-314` — the `to_dict` payloads
- `pyambit dev-tools/gen_nexus_models.py:180-189, 473-486` — merge targets and the CLI escape hatch
- `pyambit src/pyambit/nexus_writer.py:668-729` — `process_pa` and the `_default` bug at `:673`
- `pyambit src/pyambit/nexus_spectra.py` — `spe2ambit`/`configure_papp`, reused unchanged
