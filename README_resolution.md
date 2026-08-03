# CWA 18133 Figure 2, Sections 3 & 4 — implementation plan (spectrares task)

Implements the **spectral distribution curve** and **pixel resolution curve** (Section 3) and the
**spectral resolution / SpeD:SRes curves** (Section 4) of the CWA 18133:2024 x-axis calibration and
verification protocol (`cwa18133-1.pdf`, Figure 2, p. 17) as a Ploomber task.

## Context

- Sections 1–2 (neon wavelength calibration + Si laser zeroing) are already implemented in
  `spectracal_[[key]]` (`src/spectraframe_calibrate.py`), which pickles one
  `ramanchada2 CalibrationModel` per `(laser_wl, optical_path)` into its `calmodels` product.
- Sections 3–4 existed neither in this repo nor in ramanchada2 (verified 2026-07-06).
- Calibrated spectra are **not** persisted by `spectracal`; the repo pattern (see
  `src/spectraframe_ycalibrate.py`, `src/calibration_verify.py`) is to reload the calmodel and
  re-apply `apply_calibration_x` to raw spectra from the `spectraframe_load.h5` product. The new
  task follows the same pattern.
- Decision: the task depends on `spectracal_*` only (x-calibration). y-calibration
  (`spectracaly_*`) is intentionally not used — CWA sections 3–4 are x-axis only (y-axis is CWA
  section 7).

## Protocol mapping (CWA 18133 → code)

| CWA element | Definition | Implementation |
|---|---|---|
| Spectral distribution curve (3.1.9) | width collected by pixel n = halfway(n,n+1) − halfway(n−1,n) on the calibrated Raman-shift axis | `np.gradient(spe_ne_calibrated.x)`, non-monotonic segments masked |
| Pixel resolution curve (3.1.5) | function fit of neon peak FWHM vs position | Gaussian fits (lmfit Levenberg–Marquardt) via `utils.find_peaks`; `np.polyfit` (degree = `curve_fit_degree`, default 2) |
| Spectral resolution (3.1.10, Fig. 2 §4) | calcite ~1085.91 cm⁻¹ peak FWHM (Voigt) → ASTM E2529 formula | `SRes = FWHM₁₀₈₅ / 0.684 − 1.029` (constants are task params; E2529 calibration, ~20 % accuracy, dispersive systems) |
| Spectral resolution curve (3.1.11) | pixel resolution curve adjusted for laser effect | scale pixel-resolution curve by `SRes / curve(1085.91)` |
| SpeD:SRes curve | spectral distribution ÷ spectral resolution | elementwise ratio on the calibrated neon axis |
| Boundary of use (Table 1) | pixel resolution < 0.8 nm | neon FWHM converted cm⁻¹→nm at each peak position; flag in summary |

Reference values: calcite 1085.91 cm⁻¹ (CWA Table 7, RR1 study); neon NIST lines already in
`ramanchada2.misc.constants.NEON_WL` (used upstream by `spectracal`).

## Files

### `src/pipeline.yaml` — task `spectrares_[[key]]`

- `source: spectraframe_resolution.py`, `upstream: ["spectraframe_*", "spectracal_*"]`,
  `grid: key: {{calibration_key}}` (same keys as `spectracal`, so calmodels always exist).
- Products, co-located with `calmodels` under
  `{{config_output}}/processed_{{fit_ne_peaks}}_{{match_mode}}_{{interpolator}}/[[key]]/`:
  - `nb`: `spectrares.{{report_format}}` — report with per-group three-panel plots
  - `peaks`: `resolution_peaks.csv` — fitted Ne + calcite peaks (center, fwhm, fwhm_nm, height, stderr)
  - `curves`: `resolution_curves.csv` — per pixel: raman_shift, sped, pixel_res, spectral_res, sped_sres
  - `summary`: `resolution_summary.csv` — per group: n peaks, polyfit coefficients, calcite center/FWHM, SRes, laser-effect ratio, CWA boundary flag
- Params: `neon_tag`, `calcite_tag`, `e2529_divisor: 0.684`, `e2529_offset: 1.029`,
  `curve_fit_degree: 2`.
- Note: Ploomber suffixes grid products with the task index (e.g. `resolution_summary-10.csv`).

### `src/spectraframe_resolution.py` — task script

Per `(laser_wl, optical_path)` group of `BACKGROUND_SUBTRACTED` rows:

1. Reload calmodel: `utils.load_calibration_model(...)` from
   `upstream["spectracal_*"][f"spectracal_{key}"]["calmodels"]`; skip group with warning if absent.
2. Select neon spectrum by `sample == neon_tag`, preferring `overexposed == "HDR_MERGE"`;
   calibrate with `calmodel.apply_calibration_x(spe, spe_units=...)` (units from
   `utils.get_config_units`).
3. Section 3: spectral distribution (`np.gradient`), neon Gaussian peak fits
   (`utils.find_peaks`, `find_kw` from config), filter bad fits (non-finite / stderr ≥ fwhm),
   polynomial pixel-resolution curve.
4. Section 4: calibrate calcite spectrum, trim to 1085.91 ± 100 cm⁻¹, pedestal + SNIP baseline
   (`subtract_baseline_rc1_snip(niter=40)`), Voigt fit, take peak nearest 1085.91 (reject if
   > 20 cm⁻¹ away), apply E2529, scale curve, compute SpeD:SRes. Degrades gracefully (Section 3
   outputs still written) when calcite is missing or the resolution curve could not be fit.
5. Write the three CSVs and plot per group: (a) spectral distribution, (b) Ne FWHM scatter +
   pixel/spectral resolution curves + calcite SRes point, (c) SpeD:SRes curve.

Reused existing code: `utils.find_peaks`, `utils.load_calibration_model`, `utils.load_config`,
`utils.get_config_units/get_config_findkw`, `CalibrationModel.apply_calibration_x`,
`FitPeaksResult.to_dataframe_peaks()`, `shift_cm_1_to_abs_nm`.

Robustness measures (added after first full run):

- Neon peaks are matched against the NIST reference lines (`rc2const.NEON_WL[laser_wl]`
  converted to cm⁻¹): only candidate groups within `NEON_MATCH_TOL_CM1` (10 cm⁻¹) of a
  reference line are fitted, and each line keeps its single best fitted peak. Without this,
  noise bumps produced >150 "peaks" per spectrum and distorted the resolution curve.
- The calcite Voigt fit occasionally aborts in lmfit ("model function generated NaN values");
  the task falls back to a Gaussian profile (E2529 permits mixed Gaussian/Lorentzian) and
  records the profile used in the summary (`calcite_profile`).

### `src/resolution_compare.py` — task `resolution_compare`

Resolution-aware comparison across instruments (CWA 18133 objective 2), separate task,
`upstream: ["spectrares_*"]`, no grid. Aggregates the per-key CSVs and produces, under
`processed_.../assessment/`:

- `nb`: `resolution_compare.{{report_format}}` — per laser wavelength: overlaid spectral
  distribution curves, spectral resolution curves (dashed pixel-resolution fallback when an
  instrument has no calcite value) and SpeD:SRes curves, one fixed color per instrument
  across all figures; bar chart of the ASTM E2529 spectral resolution per instrument.
- `summary`: `resolution_summary_all.csv` — concatenated per-instrument summaries.
- `envelope`: `resolution_envelope.csv` — per laser wavelength, the **harmonization
  target**: pointwise maximum of the spectral resolution curves on a common grid (the
  resolution to which spectra could be degraded for resolution-matched comparison), with
  the number of contributing instruments per point.

## Verification (done 2026-07-06)

```
cd src
uv run ploomber status                            # DAG renders; 11 spectrares_* tasks
uv run ploomber task spectrares_P6_0301 --force   # end-to-end run
```

P6_0301 (532 nm, SSL1) results are physically sensible: 28 Ne peaks, FWHM ~15→9 cm⁻¹ across the
range but ~0.38 nm roughly constant in wavelength (grating behaviour), within the 0.8 nm CWA
boundary; calcite at 1084.3 cm⁻¹, FWHM 12.8 cm⁻¹ → SRes 17.7 cm⁻¹, laser-effect ratio 1.28;
SpeD ≈ 5.2 cm⁻¹/pixel; SpeD:SRes ≈ 0.25. Report HTML renders without Python tracebacks.

## Out of scope / follow-ups

- CWA Section 5 (final PST/calcite axis adjustment) and Section 7 (y-axis) untouched.
- The E2529 constants are calibrated for 785 nm dispersive systems; they are exposed as task
  params so wavelength-specific values can be substituted.
- Applying the harmonization envelope (actually degrading spectra to the common resolution
  before comparison) is a possible follow-up to `resolution_compare`.

## Tips

- To run against a specific processed variant without editing `env.yaml`
  (e.g. while another interpolator build is running):
  `uv run ploomber task spectrares_P6_0301 --force --env--interpolator poly`
