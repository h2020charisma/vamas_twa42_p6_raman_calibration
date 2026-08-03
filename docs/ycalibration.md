# Y-calibration — definitions and calculation

CWA 18133:2024 §7 — relative intensity (y-axis) correction. Unlike
x-calibration (wavelength/Raman-shift accuracy), y-calibration corrects the
spectrum's **intensity response**: every instrument has a wavelength- and
optical-path-dependent sensitivity curve, and y-calibration removes it by
comparing a measured spectrum of a certified broadband emitter against its
known true spectral response.

## Where the code lives

- [`ramanchada2/protocols/calibration/ycalibration.py`](https://github.com/h2020charisma/ramanchada2/blob/main/src/ramanchada2/protocols/calibration/ycalibration.py)
  — `YCalibrationCertificate` (a certified reference response function),
  `CertificatesDict` (loads all certificates from `config_certs.json`), and
  `YCalibrationComponent` (fits + applies the correction).
- [`ramanchada2/protocols/calibration/serialization.py`](https://github.com/h2020charisma/ramanchada2/blob/main/src/ramanchada2/protocols/calibration/serialization.py)
  — `export_cwa_y(ycal_component, ...)` writes the CWA §8 portable
  intensity-factor curve (CSV + JSON).

As with x-calibration and the resolution curves, this repo only selects
spectra and drives the shared implementation:

- [`src/spectraframe_ycalibrate.py`](../src/spectraframe_ycalibrate.py) —
  per-key, per-(laser, optical path), per-certificate task: builds
  `YCalibrationComponent` from the measured SRM/reference spectrum, saves
  `ycalmodel_<laser>_<path>_<cert>.pkl` (+ CWA CSV/JSON via `export_cwa_y`),
  and demonstrates applying the correction to PST/APAP spectra.

## Reference materials (CWA §7, ASTM E2911)

y-calibration uses a **certified broadband intensity reference**, not the
neon/silicon/calcite/PST panel used for x-calibration. Typical references: a NIST SRM
fluorescent glass (e.g. `NIST785_SRM2241`, `NIST532_SRM2242a`), a traceable
LED (ELODIZ), or a white-light source, each per ASTM E2911. Certificates are
looked up per laser wavelength via `CertificatesDict`, from
[`ramanchada2/protocols/calibration/config_certs.json`](https://github.com/h2020charisma/ramanchada2/blob/main/src/ramanchada2/protocols/calibration/config_certs.json).

### `YCalibrationCertificate`

Each certificate stores the reference's **true relative intensity response**
as an analytic function of Raman shift, defined by a formula string plus
named parameter values, e.g.:

```python
YCalibrationCertificate(
    id="NIST785_SRM2241",
    wavelength=785,
    params="A0 = 9.71937e-02, A1 = 2.28325e-04, ...",
    equation="A0 + A1 * x + A2 * x**2 + ...",
    raman_shift=(200, 3500),   # certified validity range
)
```

`cert.Y(x)` evaluates this equation at any Raman shift `x` — the ground
truth the measured reference spectrum is compared against. `raman_shift` is
the certificate's validity window; outside it there is no certified
response.

## Calculation (`YCalibrationComponent`)

Given the certificate and a measured spectrum of that same reference
material (already x-calibrated — see [`docs/xcalibration.md`](xcalibration.md)):

1. **Trim** the measured reference spectrum to the certificate's
   `raman_shift` range (`_trimmed_reference`) — no correction is defined
   outside it.
2. **Denoise the measured reference** (`_build_model` /
   `_fit_reference`): rather than interpolating the raw (noisy) measured
   points directly, `YCalibrationComponent` fits the measured spectrum with
   the **certificate's own functional form** — a polynomial of the
   certificate's order (linear least squares, `np.polyfit`) if the
   certificate is polynomial, or a nonlinear fit of the certificate's exact
   equation (`scipy.optimize.curve_fit`, seeded by the certificate's own
   parameter values) otherwise. This is an analytic denoise: it assumes the
   *measured* reference should have the same functional shape as the
   *certified* one, just with different (instrument-specific) coefficients.
   `fit_order` can force a specific polynomial order; `normalize=True`
   (default) scales the measured y to unit max before fitting for numerical
   stability. If the fit fails or produces non-finite values, it falls back
   to `CustomPChipInterpolator` — a raw interpolation of the measured
   points (the older, unfitted behavior). See
   [`docs/flat_resolution_curves.md`](flat_resolution_curves.md)-adjacent
   history: an earlier version pre-smoothed with Savitzky–Golay before this
   analytic fit existed, which distorted amplitude and was dropped (see
   git history of `spectraframe_ycalibrate.py`, "drop the savgol
   pre-smoothing of the SRM").
3. **Compute the per-wavelength intensity factor** (`safe_factor`): the
   ratio of the certificate's true response to the (denoised) measured
   response,

   ```python
   factor(x) = certificate.Y(x) / measured_reference_model(x)
   ```

   masked (`safe_mask`) to exclude points where the measured reference is
   at or below its noise floor (`y_noise_MAD()`) or outside the certificate's
   `raman_shift` range — outside that range the underlying PCHIP model
   would otherwise fall back to a unit-slope extrapolation meant for
   x-calibration curves, not a real intensity factor, so those points are
   excluded rather than trusted.
4. **Apply** (`process`): any spectrum to correct is multiplied by this
   factor, resampled onto its own x-axis:

   ```python
   spe_ycalibrated.y = spe_to_correct.y * factor(spe_to_correct.x)
   ```

## Combined with x-calibration

y-calibration is x-axis-position-dependent (the intensity factor is a
function of Raman shift), so the reference spectrum must already be on a
calibrated Raman-shift axis before fitting the y-model — VAMAS applies the
saved x-`CalibrationModel` (`calmodel.apply_calibration_x(...)`, see
[`docs/xcalibration.md`](xcalibration.md)) to the measured SRM/reference
spectrum first (`spectraframe_ycalibrate.py`'s `create_ycal`), *then* builds
`YCalibrationComponent` from the result. x- and y-calibration are otherwise
independent: x fixes Raman-shift accuracy, y fixes relative intensity — CWA
requires y-calibration **per optical path** (not shareable across optical
paths the way x-calibration sometimes is).

## Persistence

- `pickle.dump(ycal, f)` — legacy full-object persistence (as used by
  `spectraframe_ycalibrate.py`).
- `export_cwa_y(ycal_component, base_path, spectral_range=None)` — writes
  the CWA §8 portable pair: `<base>.csv`
  (`calibrated_cm1,intensity_factor`, dense-evaluated over
  `spectral_range` or the certificate's own `raman_shift`) and
  `<base>.json` (metadata + certificate + model, optionally cross-referencing
  the x-calibration file via `x_calibration_ref`).

## Related docs

- [`docs/cwa18133_summary.md`](cwa18133_summary.md) — full CWA flow; §7 is
  y-axis-only, separate from the §6.2 x-axis steps.
- [`docs/xcalibration.md`](xcalibration.md) — the calibrated Raman-shift
  axis y-calibration is applied on top of.
- [`docs/resolution_curves.md`](resolution_curves.md) — CWA §3–4 curves,
  also x-axis-only (y-calibration is intentionally *not* applied there).
