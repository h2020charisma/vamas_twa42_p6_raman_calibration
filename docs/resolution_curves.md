# Resolution curves — definitions and calculation

CWA 18133:2024 Figure 2, sections 3–4. Four related quantities, each a
function of Raman shift over the calibrated x-axis: the **spectral
distribution curve** (SpeD), the **pixel resolution curve**, the
**spectral resolution curve** (SRes, from calcite), and the **SpeD:SRes
curve**. This note defines each and points to the single shared
implementation.

## Where the code lives

All four curves are computed by one function, shared between this repo, the
CHARISMA SpectraStream app, and any other consumer:

- [`ramanchada2/protocols/calibration/resolution.py`](https://github.com/h2020charisma/ramanchada2/blob/main/src/ramanchada2/protocols/calibration/resolution.py)
  — `resolution_from_calibration(calmodel, spe_neon, spe_calcite=...)`
  returns a `ResolutionResult` dataclass holding all four curves plus the
  neon/calcite fit diagnostics.

This repo's Ploomber task is a thin wrapper: it selects the neon/calcite
spectra per optical path + laser, calls the shared function, tabulates the
results to CSV, and plots them — it does not reimplement any of the math.

- [`src/spectraframe_resolution.py`](../src/spectraframe_resolution.py) —
  per-key task that calls `resolution_from_calibration` and writes
  `resolution_peaks-*.csv`, `resolution_curves-*.csv`, `resolution_summary-*.csv`.
- [`src/resolution_compare.py`](../src/resolution_compare.py) — cross-instrument
  overlay/comparison report built from those CSVs.

Only the **x-calibration** model is used (`calmodel.apply_calibration_x`);
y-calibration is intentionally not applied, since CWA sections 3–4 are
x-axis-only quantities.

## Prerequisite: the calibrated Raman-shift axis

All curves are evaluated on `raman_shift`, the calibrated x-axis obtained by
applying the fitted x-calibration model to the raw neon spectrum:

```python
spe_ne_cal = calmodel.apply_calibration_x(spe_neon, spe_units=neon_units)
```

This axis is the output of the earlier CWA steps (wavelength calibration from
NIST neon lines, laser-zeroing from the silicon 520.45 cm⁻¹ band) — see
`cwa18133_summary.md` §6.2 steps 1–2. Sections 3–4 (this doc) are steps 3–4.

## 1. Spectral distribution curve (SpeD)

**CWA 18133 §3.1.9.** The Raman-shift width represented by each pixel of the
calibrated axis — i.e. how coarse or fine the calibrated grid is at a given
position, in cm⁻¹/pixel.

```python
def spectral_distribution(spe_calibrated):
    x = spe_calibrated.x
    return x, np.gradient(x)
```

`np.gradient(x)` is the discrete equivalent of "halfway(n, n+1) −
halfway(n−1, n)": the local spacing of the calibrated x-axis at each pixel.
It says nothing about peak widths — only about how densely the calibrated
axis samples Raman shift at that position.

**Caveat:** if the *raw* x-axis before calibration was already
vendor-resampled onto a uniform grid (common export practice for some
instruments), SpeD comes out flat/constant. That
flatness reflects the export grid, not the physical detector pixel pitch, and
must not be read as a CWA pixel property. `resolution.py` detects this via
`detect_uniform_grid()` (relative spread of `np.diff(raw_x)` below 1 %) and
annotates the plot / sets `uniform_grid=True` in the summary rather than
silently mislabeling the curve.

## 2. Pixel resolution curve

**CWA 18133 §3.1.5.** How the instrument's line-spread function (FWHM) varies
with position on the calibrated Raman-shift axis, derived purely from neon
emission lines.

Calculation (`fit_neon_peaks` + `fit_pixel_resolution_curve`):

1. Match candidate peaks in the calibrated neon spectrum to NIST reference
   neon lines (within `NEON_MATCH_TOL_CM1` = 10 cm⁻¹), keeping the single
   best (highest) fitted peak per reference line.
2. Gaussian-fit each matched peak → `(center, fwhm)` pairs. Neon lines have
   essentially zero intrinsic linewidth, so a neon peak's fitted FWHM *is*
   the instrument response function at that position.
3. Fit a degree-2 polynomial of FWHM vs. center through these points
   (`np.polyfit`), with one round of MAD-based outlier rejection.
4. Require at least `MIN_NEON_PEAKS` = 6 points, or the curve is not drawn
   (points only) — below that the polynomial is under-determined.
5. The curve is only evaluated within the fitted neon peak span
   (`fit_lo`/`fit_hi`), widened by a 5 % margin (`CURVE_MARGIN_FRAC`); NaN
   elsewhere, since extrapolating a low-order polynomial far outside the
   line-covered range is not trustworthy.

## 3. Spectral resolution curve (SRes)

**CWA 18133 §3.1.10 / §4, ASTM E2529.** The pixel resolution curve rescaled
so it agrees with a single independent resolution measurement from the
calcite ~1085.91 cm⁻¹ band — the **"laser effect"** correction.

Calculation (`fit_calcite_1085` + `spectral_resolution_e2529`):

1. Voigt-fit the calcite peak nearest 1085.91 cm⁻¹ (Gaussian fallback if the
   Voigt fit fails) after SNIP baseline subtraction.
2. Convert its FWHM to a spectral resolution value via the ASTM E2529 affine
   formula:

   ```python
   SRes = (FWHM_1085 - E2529_OFFSET) / E2529_SLOPE   # 0.684, 1.0209
   ```

   (cross-checked against ASTM E2529.)
3. Evaluate the neon pixel-resolution curve at the calcite peak's position,
   and take the ratio `laser_effect_ratio = SRes / pixel_res_curve(calcite_center)`.
4. **Plausibility guard:** since neon FWHM is the noise floor (near-zero
   intrinsic linewidth) and calcite adds real molecular broadening on top of
   it, SRes can never be meaningfully *below* the neon-derived pixel
   resolution. If the ratio is below `SRES_MIN_RATIO` = 0.8 (allowing ~20 %
   for the E2529 formula's stated accuracy) or `SRes <= 0`, the calcite fit
   is treated as defective: the rescale is **not applied**, no spectral
   resolution curve is drawn, and `sres_plausible=False` is recorded.
5. Otherwise, the spectral resolution curve is the pixel resolution curve
   scaled by that one ratio:

   ```python
   spectral_res_curve = lambda x: laser_effect_ratio * pixel_res_curve(x)
   ```

   i.e. same shape as the pixel resolution curve, anchored to match the
   calcite-measured value at 1085.91 cm⁻¹. It is clipped to the same
   neon-supported range as the pixel resolution curve.

## 4. SpeD:SRes curve

**CWA Figure 2, third panel.** The ratio of spectral distribution to
spectral resolution at each point of the calibrated axis:

```python
sped_sres = sped / spectral_res
```

Interpretable as "how many calibrated-axis pixels fit inside one resolution
element" — a measure of whether the axis sampling is fine enough relative to
the instrument's actual resolving power. It is NaN wherever `spectral_res`
is NaN (i.e., wherever there is no valid pixel resolution curve, or the
calcite rescale was not applied because it failed the plausibility guard).

## Summary of dependencies

```
raw neon spectrum ──calibration──> calibrated neon spectrum
        │                                  │
        │ np.gradient(x)                   │ NIST-line matching + Gaussian fit
        ▼                                  ▼
   SpeD curve                    neon (center, FWHM) points
                                            │ polyfit deg-2 (+ outlier reject)
                                            ▼
                                  pixel resolution curve
                                            │ x scale by SRes/pixel_res(calcite center)
        │                                  ▼         ▲
        │                        spectral resolution curve   calcite peak FWHM
        │                                  │              (Voigt/Gaussian fit)
        └──────────────divide──────────────┘              → ASTM E2529 formula
                        ▼
                SpeD:SRes curve
```

## Related docs

- [`docs/cwa18133_summary.md`](cwa18133_summary.md) §6.2 — where sections
  3–4 sit in the full CWA x-axis calibration flow.
- [`ramanchada2/tests/protocols/test_resolution.py`](https://github.com/h2020charisma/ramanchada2/blob/main/tests/protocols/test_resolution.py)
  — unit tests for this module.
