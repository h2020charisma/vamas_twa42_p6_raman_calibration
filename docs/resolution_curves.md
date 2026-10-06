# Resolution curves — definitions and calculation

CWA 18133:2024 Figure 2, sections 3–4. Four related quantities, each a
function of Raman shift over the calibrated x-axis, plus two scalar values
derived along the way. The CWA text is not fully consistent in its own
symbols (see the terminology note below), so this doc fixes one vocabulary
and uses it throughout:

| Symbol | Kind | CWA clause | Meaning |
|---|---|---|---|
| **SpeD** | curve | §3.1.9 | spectral distribution curve — cm⁻¹ per pixel of the calibrated axis |
| **PRC** | curve | §3.1.5 | pixel resolution curve — neon-FWHM-fitted instrument response |
| **PRes** | scalar | §3.1.4 | PRC evaluated at the calcite line, 1085.91 cm⁻¹ |
| **SRes** | scalar | §3.1.10 | spectral resolution at 1085.91 cm⁻¹, from the calcite FWHM via ASTM E2529 |
| **SRC** | curve | §3.1.11 | spectral resolution curve — PRC rescaled by SRes / PRes |
| **SpeD:SRes** | curve | Figure 2, panel 3 | SpeD divided by SRC (curve-to-curve), **not** by the scalar SRes |

**Terminology note.** §3.1.10 and Figure 2 introduce **SRes** as the scalar
calcite-derived value, but the "SpeD:SRes curve" label in Figure 2's third
panel is only correct if read as SpeD divided by the *curve* built from that
value (SRC), not the scalar itself — the CWA does not clearly distinguish the
two uses of "SRes" in its own notation. This note keeps SRes strictly scalar
and SRC strictly curve-valued to avoid that ambiguity; see §4 below for the
exact equation and how it maps onto the code.

Separately, §3.1.9 labels SpeD "spectral distribution", but what it defines
(cm⁻¹ span covered by one detector pixel) is a **dispersion** quantity in the
usual spectroscopy sense, not a distribution — "spectral distribution" more
naturally refers to how Raman-scattered intensity is spread across
wavelength/frequency, an unrelated quantity this pipeline does not compute.
This doc keeps the CWA's own symbol **SpeD** for continuity with the code and
CSV column names, but the more accurate name for §3.1.9 would be *spectral
dispersion* (SDis / SDC for the curve) — worth revisiting if the CWA text
itself is revised.

This note defines each of the four curves and points to the single shared
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
position, in cm⁻¹/pixel. Despite the CWA's name for it, this is a
*dispersion* quantity, not a distribution — see the terminology note above.

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

## 2. Pixel resolution curve (PRC)

**CWA 18133 §3.1.5.** How the instrument's line-spread function (FWHM) varies
with position on the calibrated Raman-shift axis, derived purely from neon
emission lines. **PRes** (§3.1.4) is the scalar value of PRC evaluated at the
calcite line position, 1085.91 cm⁻¹ — used in step 3 of the next section.

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

## 3. Spectral resolution (SRes) and spectral resolution curve (SRC)

**CWA 18133 §3.1.10 (SRes, scalar) / §3.1.11 (SRC, curve) / §4, ASTM E2529.**
SRes is the single calcite-derived resolution value; SRC is the pixel
resolution curve (PRC) rescaled so it agrees with SRes at the calcite
position — the **"laser effect"** correction. Keeping these as two symbols,
one scalar and one curve, matters for §4 below, where the CWA's own notation
does not clearly separate them.

**Why only one point is needed, unlike the neon curve:** CWA §3.1.10 defines
spectral resolution directly as the calcite FWHM (SRes ≡ calcite FWHM), and
§4 uses it to *adjust* the already-fitted pixel resolution curve rather than
to fit a new one — the CWA panel only specifies one calcite band
(~1085.91 cm⁻¹, Table 7) for this purpose, so there is no dense grid of
independent calcite measurements the way there is for neon lines. The
underlying physical reason a single point suffices: neon lines are
intrinsically ~zero width, so their FWHM measures pure instrument response,
whereas the calcite band carries real molecular linewidth on top of that
response, giving access to true spectral resolution that neon cannot
provide at all — but only at the one position calcite is measured. Rather
than fit an independent curve from that single value, the method **reuses
the shape already fitted from neon** and assumes only the *scale* differs
between PRes and SRes (the "laser effect", e.g. contributions such as laser
linewidth that neon is blind to but calcite reveals). One calcite point is
exactly enough to fix that one scale factor — a single-point calibration of
an existing curve, not an independent curve fit. This also means the whole
of SRC stands or falls on that one point, which is why step 4 below guards
it rather than trusting it unconditionally.

Calculation (`fit_calcite_1085` + `spectral_resolution_e2529`):

1. Voigt-fit the calcite peak nearest 1085.91 cm⁻¹ (Gaussian fallback if the
   Voigt fit fails) after SNIP baseline subtraction.
2. Convert its FWHM to a spectral resolution value via the ASTM E2529 affine
   formula:

   ```python
   SRes = (FWHM_1085 - E2529_OFFSET) / E2529_SLOPE   # 0.684, 1.0209
   ```

   (cross-checked against ASTM E2529.)
3. Evaluate PRC at the calcite peak's position — that value is **PRes**
   (`neon_fwhm_1085` in the code) — and take the ratio
   `laser_effect_ratio = SRes / PRes`.
4. **Plausibility guard:** since neon FWHM is the noise floor (near-zero
   intrinsic linewidth) and calcite adds real molecular broadening on top of
   it, SRes can never be meaningfully *below* PRes. If the ratio is below
   `SRES_MIN_RATIO` = 0.8 (allowing ~20 % for the E2529 formula's stated
   accuracy) or `SRes <= 0`, the calcite fit is treated as defective: the
   rescale is **not applied**, SRC is not drawn, and `sres_plausible=False`
   is recorded.
5. Otherwise, **SRC** is PRC scaled by that one ratio:

   ```python
   SRC = lambda x: (SRes / PRes) * PRC(x)
   ```

   i.e. same shape as PRC, anchored to match SRes at 1085.91 cm⁻¹. It is
   clipped to the same neon-supported range as PRC. In the code, the array
   holding SRC evaluated on the output grid is named `spectral_res` (see
   `ResolutionResult.spectral_res`) — distinct from `spectral_resolution`,
   the scalar SRes, held in the same result object. The array name reads
   like the scalar and is easy to misread as one; they are not the same
   thing, which matters for the next section.

## 4. SpeD:SRes curve

**CWA Figure 2, third panel.** Despite the panel's label, this is **SpeD
divided by SRC** (curve over curve), evaluated pointwise — *not* SpeD
divided by the scalar SRes. CWA §4 names the panel "SpeD:SRes" using SRes as
shorthand for "the resolution curve derived using SRes", which is what SRC
already is; read literally against §3.1.10's own scalar definition of SRes,
the panel label is ambiguous. This doc's equation removes that ambiguity:

```python
SpeD_SRes = SpeD / SRC        # curve / curve, evaluated at each x
```

which is what the code computes (`sped_sres = sped / spectral_res`, where
`spectral_res` — despite its name — already holds SRC sampled on the grid,
per the note at the end of §3).

Interpretable as "how many calibrated-axis pixels fit inside one resolution
element" — a measure of whether the axis sampling is fine enough relative to
the instrument's actual resolving power. It is NaN wherever SRC
is NaN (i.e., wherever there is no valid pixel resolution curve, or the
calcite rescale was not applied because it failed the plausibility guard).

## Summary of dependencies

```
raw neon spectrum ──calibration──> calibrated neon spectrum
        │                                  │
        │ np.gradient(x)                   │ NIST-line matching + Gaussian fit
        ▼                                  ▼
     SpeD curve                  neon (center, FWHM) points
                                            │ polyfit deg-2 (+ outlier reject)
                                            ▼
                                          PRC
                                       (pixel resolution curve)
                                            │ PRes = PRC(calcite center)
        │                                  ▼         ▲
        │                                 SRC    calcite peak FWHM
        │                          (scaled by SRes/PRes)  (Voigt/Gaussian fit)
        │                                  │              → ASTM E2529 → SRes
        └──────────────divide──────────────┘
                        ▼
                  SpeD:SRes curve
                (= SpeD / SRC, curve-to-curve)
```

## Related docs

- [`docs/cwa18133_summary.md`](cwa18133_summary.md) §6.2 — where sections
  3–4 sit in the full CWA x-axis calibration flow.
- [`ramanchada2/tests/protocols/test_resolution.py`](https://github.com/h2020charisma/ramanchada2/blob/main/tests/protocols/test_resolution.py)
  — unit tests for this module.
