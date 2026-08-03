# CWA 18133:2024 — Raman calibration & verification protocol (summary)

*Reference summary for VAMAS TWA42 P6 agents. Source PDF: `cwa18133-1.pdf`
(repo root). CEN Workshop Agreement, September 2024, from the CHARISMA H2020
project (GA 952921). Ideaconsult / Nina Jeliazkova is a listed contributor.*

## What it is

A **post-acquisition** data-harmonization protocol for Raman instruments,
covering three axes:

1. **x-axis position** (Raman shift accuracy),
2. **x-axis resolution** (how FWHM varies across the detector),
3. **y-axis relative intensity** correction.

Developed and validated on **532 nm and 785 nm dispersive backscatter**
systems; primary use is fixed-grating dispersive spectrometers. Other lasers
(514.5, 633 nm) are "unconfirmed". It calibrates *data*, not the instrument
firmware ("virtual calibration"). Applies **per optical path + laser**; x-cal
can be shared between similar optical paths *with verification*, y-cal must be
per optical path.

## Method character

CWA 18133's x-calibration is the classical **detect → peak-fit → spline**
pipeline (Annex A §6.1: peak finding + Gaussian / Voigt / **Pearson IV**
fitting + **polyharmonic spline** interpolation/extrapolation). Reference
implementations: ramanchada2 (`xcalibration.py`), and the Altaxo / Oranchada
tools described in Annex C.

## Reference materials and their roles (§6.1, Annex A)

Four prerequisite spectra, acquired in the **same session**:

| Material | Role in the protocol | Reference table |
|---|---|---|
| **Neon** | Emission lines → **wavelength x-axis** (matched to NIST absolute nm). Neon FWHM → **pixel resolution**. Laser-independent. | Table 5 — 74 NIST lines, 533–966 nm |
| **Silicon** | 520.45 cm⁻¹ band → **laser zero** (Raman-shift origin) | Table 6 — 520.45 (Itoh CRM); dopant/orientation variants 520.27–520.66 |
| **Calcite (CAL)** | **Verifies** calibration; **final Raman-shift adjustment** (with PST); **defines spectral resolution** (SRes ≡ calcite FWHM, §3.1.10) | Table 7 — 155.21 / 281.26 / 711.95 / 1085.91 / 1435.22 / 1748.91 |
| **Polystyrene (PST)** | Verifies; final Raman-shift adjustment (with calcite) | Table 8 — ASTM E1840, 11 peaks 620.9–3054.3 (+ rel. intensities) |

Plus a **laser wavelength integer** (nominal, e.g. 532/785). y-axis correction
(§7) uses a NIST SRM fluorescent glass, a traceable LED (ELODIZ), or a white
light source, per ASTM E2911.

> **APAP (acetaminophen) is not part of this protocol** — the four x-axis
> prerequisite samples are Neon, Silicon, Calcite, Polystyrene. In the P6
> exercise APAP is carried as an additional, non-CWA analyte (useful precisely
> *because* it is outside the standard panel). **TiPS belongs to the separate
> CWA 18134 twinning protocol** (see `cwa18134_summary.md`).

## x-axis flow (§6.2, five sections)

1. **Wavelength x-axis** — match neon peaks to NIST assignments; fit the axis.
2. **Laser-zeroed Raman-shift x-axis** — apply the wavelength axis to silicon;
   the Si peak sets the laser zero, converting wavelength → Raman shift.
3. **Spectral distribution + pixel resolution curves** — from neon FWHM on the
   laser-zeroed axis.
4. **Spectral resolution + SpeD:SRes curve** — calcite FWHM gives Raman
   spectral resolution, adjusting the pixel-resolution curve.
5. **Calibrated Raman-shift x-axis** — final adjustment from calcite + PST peak
   positions.

## Data-quality requirements (§5.3 — useful as truth constraints)

- **SNR ≥ 8** (ideally > 100), computed (S−B)/N.
- No **saturation**; **spikes** removed; no **pedestalling** (y-offset → 0).
- **Background/dark subtracted** — same acquisition params, **laser off**.
- **Raw data** only: no smoothing/baseline pre-processing (binding/stitching OK).
- Calcite fluorescence < 20 % of the 1085 cm⁻¹ peak.
- Pixel resolution < 0.8 nm (neon FWHM); one optical path + laser per cal.

## Calibration file (§8)

- Metadata (§5.3.3: make/model/serial, optical path, laser wavelength, grating,
  slit, acquisition params) + date.
- **x-cal curve** = (uncalibrated shift → calibrated shift) points feeding a
  **spline**; first/last points = spectral-range ends; + Si peak position +
  (optional) calibrated laser wavelength.
- **y-cal curve** = (calibrated shift → intensity factor) points → spline.

## Algorithms required (§6.1)

Peak base/baseline; peak finding/candidate generation; peak fitting
(**Gaussian / Voigt / Pearson IV**, chosen by fit error); **polyharmonic
spline** for interpolation/extrapolation of the axis. Software: ramanchada2
(Python), Altaxo (C#), Oranchada (Orange add-on).

## Normative references

ASTM E1840 (Raman shift standards), ASTM E2911 (relative intensity correction).
Related standards: ASTM E2529 (resolution testing), CWA 17815:2021 (metadata).
