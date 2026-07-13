# Flat resolution curves — findings and fixes

**Date:** 2026-07-13 · **Products analyzed:** `VAMAS_P6_analysis/new/processed_True_qargmin2d_poly/`
(per-key `resolution_curves-*.csv`, `resolution_peaks-*.csv`, `resolution_summary-*.csv`,
`assessment/resolution_compare.html`)

Domain experts reviewing the CWA 18133 sections 3–4 reports flagged a few curves as flat,
which cannot be physical, and asked whether the pipeline plots flat curves where there is
no data.

## Verdict

The plotting is honest: `spectraframe_resolution.py` clips resolution curves to the fitted
neon-peak span (`fit_lo`/`fit_hi` + 5 % margin) and sets NaN elsewhere, and the comparison
overlay only draws non-NaN points. **The flatness is in the data itself**, from two distinct
causes; the experts' physical intuition is correct in both cases.

## Finding 1 — flat *spectral distribution* curves = vendor-resampled input grid

| instrument | laser | raw x-axis step |
|---|---|---|
| P6_0702 OP1 | 785 nm | exactly 1.00000 cm⁻¹, perfectly uniform |
| P6_0601 OP1 | 532 nm | 0.9640 ± 0.0005 cm⁻¹, uniform to 0.1 % |
| P6_0101 OP1 (native, for contrast) | 532 nm | 0.0037–0.0178 nm, genuinely non-uniform |

The vendor software already interpolated the export onto an even cm⁻¹ grid, so the CWA 3.1.9
spectral distribution `np.gradient(x)` faithfully shows a constant — **the resampling grid,
not the physical pixel pitch**. Native detector pixels cannot be equidistant in cm⁻¹.
For these instruments the SpeD curve and the SpeD:SRes curve characterize the export format,
not the instrument, and must not be interpreted as CWA pixel properties.

## Finding 2 — flat *and unphysically low* spectral resolution curve = defective calcite fit

| instrument | calcite 1085 FWHM | neon median FWHM | E2529 SRes | laser-effect ratio |
|---|---|---|---|---|
| P6_0101 OP1 @532 | 1.10 cm⁻¹ (Gaussian fallback, Voigt failed) | 1.55 cm⁻¹ | 0.58 cm⁻¹ | 0.29 |
| P6_0701 OP3 @785 | 3.88 cm⁻¹ | 7.16 cm⁻¹ | 4.65 cm⁻¹ | 0.59 |

A calcite band FWHM **narrower than the same instrument's neon FWHM is physically
impossible**: neon atomic lines have essentially zero intrinsic width, so their fitted FWHM
*is* the instrument function; calcite adds natural broadening on top of it. The ASTM E2529
affine formula (`SRes = FWHM/0.684 − 1.029`, zero at FWHM ≈ 0.70 cm⁻¹) amplifies the error,
and the resulting laser-effect ratio (0.29 for P6_0101) multiplies the entire
pixel-resolution curve down — both flattening it visually and making the instrument look
absurdly good (SRes 0.6 cm⁻¹).

## Non-findings

Most other visually flat traces (e.g. P6_01002 at both lasers) decline gently by ~25–35 %
across the range — exactly what physics predicts for a constant FWHM in nm converted to
cm⁻¹ (the 1/λ² factor). Those are correct.

## Fix plan (implemented in `src/spectraframe_resolution.py` / `src/resolution_compare.py`)

1. **Uniform-grid guard** — detect a (near-)constant raw x-axis spacing
   (relative spread of `np.diff(x)` below 1 %) on the raw neon spectrum:
   - annotate the per-instrument SpeD and SpeD:SRes panels ("resampled export grid, not
     detector pixels");
   - add `uniform_grid` / `grid_step` columns to the summary product;
   - suffix the instrument label with "(resampled grid)" in the cross-instrument SpeD overlay.
2. **Calcite-vs-neon sanity guard** — before applying the laser-effect rescale, require the
   ratio `SRes / pixel_res_curve(calcite center)` to be at least **0.8** (`SRES_MIN_RATIO`),
   and `SRes > 0`. Rationale: the true spectral resolution cannot be meaningfully better
   than the neon-derived pixel resolution (neon lines have ~zero intrinsic width, so their
   FWHM *is* the instrument function); the 0.8 bound allows for the ~20 % stated accuracy
   of the E2529 formula. Checking the ratio rather than the raw calcite-vs-neon FWHM avoids
   false flags where the deg-2 neon curve locally overshoots near 1085 cm⁻¹ (verified
   against the existing products: P6_0101 @532 ratio 0.29 and P6_0701 OP3 @785 ratio 0.59
   are flagged; P6_0701 OP2 @532 ratio 1.01 and P6_0801 ratio 1.16 correctly pass).
   - on violation: log a warning, **do not apply the ratio** (the spectral-resolution curve
     stays empty, so the comparison report falls back to the clearly-marked dotted unscaled
     pixel-resolution curve), mark the calcite point in the per-instrument plot as
     "implausible, not applied";
   - add an `sres_plausible` column to the summary product;
   - exclude implausible SRes values from the per-instrument bar chart (listed separately
     with the reason, same as instruments without calcite).

Both guards only flag/withhold derived quantities; no measured data is altered.
