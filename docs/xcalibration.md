# X-calibration — definitions and calculation

CWA 18133:2024 §6.2, steps 1–2 (of five; steps 3–5 are the resolution curves
and the final calcite/PST adjustment, covered separately). X-calibration
turns the raw, uncalibrated x-axis (pixel, nm, or an approximate cm⁻¹ grid)
into a **wavelength-accurate, laser-zeroed Raman-shift axis**, using neon
emission lines and the silicon 520.45 cm⁻¹ band.

## Where the code lives

- [`ramanchada2/protocols/calibration/xcalibration.py`](https://github.com/h2020charisma/ramanchada2/blob/main/src/ramanchada2/protocols/calibration/xcalibration.py)
  — `XCalibrationComponent` (neon → wavelength axis) and
  `LazerZeroingComponent` (silicon → laser-zeroed Raman shift), plus the
  shared `match_peaks` / `fit_peaks` helpers.
- [`ramanchada2/protocols/calibration/calibration_model.py`](https://github.com/h2020charisma/ramanchada2/blob/main/src/ramanchada2/protocols/calibration/calibration_model.py)
  — `CalibrationModel.derive_model_x(...)` (or the older
  `calibration_model_factory`) chains the two components into one model;
  `apply_calibration_x(spe)` applies both in sequence to any spectrum.
- [`ramanchada2/protocols/calibration/interpolators.py`](https://github.com/h2020charisma/ramanchada2/blob/main/src/ramanchada2/protocols/calibration/interpolators.py)
  — the interpolator/extrapolator families the neon curve can be built from
  (`poly`, `pchip`, `polyinverse`, `pchipinverse`, `rbfinverse`, ...).
  `CustomPChipInterpolator.__call__` documents the unit-slope
  constant-correction extrapolation used beyond the neon-line span.
- [`ramanchada2/protocols/calibration/serialization.py`](https://github.com/h2020charisma/ramanchada2/blob/main/src/ramanchada2/protocols/calibration/serialization.py)
  — `export_cwa_x(calmodel, ...)` writes the CWA §8 portable calibration
  file: `uncalibrated_cm1,calibrated_cm1` curve CSV + JSON metadata.

This repo only selects spectra and drives the shared implementation — it
does not reimplement the matching/fitting math:

- [`src/spectraframe_calibrate.py`](../src/spectraframe_calibrate.py) —
  per-key, per-(laser, optical path) task: builds the neon calibration
  curve, applies it to silicon, derives the laser-zeroing model, saves
  `calmodel_<laser>_<path>.pkl` / `.json` (+ CWA CSV/JSON via
  `export_cwa_x`), and plots diagnostics (matched-peak overlays, calibration
  curve monotonicity, Si peak fit).
- [`src/matched_peaks_analysis.py`](../src/matched_peaks_analysis.py) —
  peak-matching quality / systematic-vs-random error analysis consumed at
  the end of `spectraframe_calibrate.py`.

## Step 1 — wavelength x-axis from neon (`XCalibrationComponent`)

**CWA §6.2 step 1.** Neon emission lines have precisely known NIST
wavelengths (`rc2const.NEON_WL[laser_wl]`, laser-independent since neon is
an atomic emission reference, not a Raman-shifted band). Matching the
instrument's neon peaks to those NIST positions gives the mapping
"uncalibrated x → true wavelength (nm)".

1. **Find & fit neon peaks** (`fit_peaks`): peak-find on the raw neon
   spectrum (`find_peak_multipeak`, prominence set from
   `spe.y_noise_MAD() * prominence_coeff`), then Gaussian-fit each candidate
   group (`fit_peak_multimodel`). `should_fit=False` skips the fit and uses
   raw candidate positions instead (VAMAS default, `fit_neon_peaks` config
   flag) — faster, and avoids fit divergence on noisy neon spectra when only
   the peak position (not FWHM) is needed for this step.
2. **Match to NIST lines** (`match_peaks`, `xcalibration.py`): pairs each
   found peak with a reference neon line. Several `match_method` strategies
   are available (`qargmin2d` closest-pair default, `argmin2d`, `cluster`,
   `assignment` = Hungarian algorithm, `monotonic` = order-preserving DP);
   VAMAS configures this per key (`match_mode` parameter). All non-trivial
   methods finish with `qmatch.robust_poly_residual_filter` — a 3σ
   MAD-based outlier rejection against a low-order polynomial fit of
   matched pairs, so a mismatched peak does not distort the curve.
3. **Fit the calibration curve**: an interpolator (`interpolator_method`,
   e.g. `poly`/`pchip`) through the matched `(uncalibrated_x, nist_nm)`
   pairs — this *is* the x-calibration model, mapping any future
   uncalibrated x-value to a calibrated wavelength. With extrapolation
   enabled (`extrapolate=True`), points outside the neon-line span are
   extended by continuing the edge correction at constant (unit) slope,
   not by letting the interpolant run away (`CustomPChipInterpolator`
   docstring) — important because neon lines don't reach as far as, e.g.,
   the CH-stretch region (~2900 cm⁻¹) or sometimes the Si peak itself.

## Step 2 — laser-zeroed Raman shift from silicon (`LazerZeroingComponent`)

**CWA §6.2 step 2.** The neon step gives an accurate wavelength axis, but
wavelength alone doesn't fix the Raman-shift **origin** — that depends on
the exact laser wavelength, which drifts from its nominal value
(532/785/...). The silicon 520.45 cm⁻¹ band is a certified reference
(Itoh CRM, CWA Table 6) used purely to anchor this zero point.

1. Apply the neon wavelength model to the raw silicon spectrum
   (`model_neon.process(spe_sil, ...)`) → silicon on a wavelength axis.
2. Fit the Si band (default profile `Pearson4`, `fit_peak_multimodel`) and
   take the highest-amplitude peak's position, `zero_peak_nm`.
3. Convert wavelength → Raman shift using that measured Si peak position
   *as the effective laser wavelength*, referenced against the certified
   520.45 cm⁻¹ value:

   ```python
   def zero_nm_to_shift_cm_1(self, wl, zero_pos_nm, zero_ref_cm_1=520.45):
       return 1e7 * (1 / zero_pos_nm - 1 / wl) + zero_ref_cm_1
   ```

   i.e. `shift = 1e7·(1/λ_measured − 1/λ_Si_peak) + 520.45`. Applying this
   with `wl = old_spe.x` (the neon-calibrated wavelength axis) to *any*
   spectrum converts it from wavelength to a laser-zeroed Raman-shift axis
   in one step (`LazerZeroingComponent.process`). See
   [ELODIZ's calibration write-up](https://www.elodiz.com/calibration-and-validation-of-raman-instruments/),
   cited directly in the source, for the rationale.
4. The model doesn't *shift* the spectrum by a fitted offset; it re-derives
   Raman shift directly from the measured Si peak position each time,
   which is why only `zero_peak_nm` (a single float) needs to be persisted.

## Combined model (`CalibrationModel`)

`CalibrationModel.derive_model_x(spe_neon, ..., spe_sil, ...)` runs both
steps back-to-back and stores them as an ordered list of components
(`self.components`). `apply_calibration_x(spe)` then threads any spectrum
through each enabled component in turn (`model.process(...)`), converting
uncalibrated x → wavelength (nm) → laser-zeroed Raman shift (cm⁻¹). This is
the axis that [`docs/resolution_curves.md`](resolution_curves.md) and the
final calcite/PST adjustment (CWA §6.2 steps 3–5) are then built on.

`nonmonotonic` (`"error"` / `"nan"` / `"drop"`) controls what happens if the
fitted interpolator ever produces a non-increasing x-value (can happen near
the extrapolated edges of a poorly-conditioned curve) — VAMAS uses `"drop"`.

## Persistence

- `calmodel.save(path)` — `.json` → the portable CWA §8 representation
  (`to_dict()`: laser wavelength, components incl. matched-peak anchors,
  interpolator model); anything else → legacy pickle.
- `export_cwa_x(calmodel, base_path, spectral_range)` — writes the
  human-readable CWA calibration file pair: `<base>.csv`
  (`uncalibrated_cm1,calibrated_cm1`, sampled at `spectral_range` bounds)
  and `<base>.json` (metadata + full model).

## Related docs

- [`docs/cwa18133_summary.md`](cwa18133_summary.md) §6.2 — where
  x-calibration (steps 1–2) sits relative to the resolution curves
  (steps 3–4) and the final calcite/PST adjustment (step 5).
- [`docs/resolution_curves.md`](resolution_curves.md) — the CWA §3–4 curves
  built on top of this calibrated axis.
