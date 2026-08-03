# CWA 18134:2024 — Raman instruments twinning protocol (summary)

*Reference summary for VAMAS TWA42 P6 agents. Source PDF: `cwa18134-1.pdf`
(repo root). CEN Workshop Agreement, September 2024, CHARISMA H2020
(GA 952921). Ideaconsult / Nina Jeliazkova is a listed contributor.*

> **Implementation status:** implemented in **ramanchada2**, **not yet in the
> VAMAS P6 pipeline** — this summary is groundwork for a future pipeline
> implementation.

## What it is (and how it differs from CWA 18133)

CWA 18134 is a **y-axis intensity harmonization** ("twinning") protocol, a
*separate* standard from CWA 18133. Where **18133 calibrates one instrument's
axes** (position + resolution + relative-intensity shape), **18134 twins two
already-18133-calibrated instruments so their spectra match in absolute Raman
intensity.** It is a **prerequisite chain**: 18134 requires that both
instruments have already had full x- and y-axis calibration (18133 is the
tested-against calibration).

The core idea: reduce *all* the intensity differences between two instruments
(spot size, power density, optical path, spectrometer, detector QE, …) to a
**single scalar Correction Factor (CF)**, obtained from how each instrument's
band intensity scales with laser power.

Boundaries (Table 1, adapted from 18133): 532 & 785 nm; no polarisation/
resonance; 180° backscatter only; Stokes only.

## The test sample (Annex A) — this is "TiPS"

A **composite of epoxy + 0.5 wt% anatase TiO₂ particles**, developed to meet
§5's requirements: high homogeneity (Raman response deviation < 3 %; the
example achieves ≤ 2.8 % over 50 points), strong scattering, temporal/thermal/
chemical stability, low-roughness polished surface (Sa ≈ 0.75 µm).

- **Reference Raman Band (RRB)** = the **TiO₂ 144 cm⁻¹** band (most intense);
  the **638 cm⁻¹** band works equivalently for instruments cutting off the low
  end. → This is why the **TiO₂ 144 cm⁻¹ band is usable for verification** in
  the P6 context.
- The test sample is covered by patent **EP23382469.7** (CSIC 50% / ELODIZ 50%,
  filed 2023-05-19) — relevant if the sample or its use is redistributed.

> In the P6 data, TiPS samples (`TiPS_Ti`, `TiPS_PS`) belong here, **not** to
> the 18133 x-calibration panel — the P6 loader currently drops them
> (`ignore_samples`). They are the 18134 test material, out of scope for the
> x-calibration work but the natural input when 18134 is implemented.

## Procedure (§6)

1. **Measure the test sample** in both instruments — the **reference** (RI_R)
   and the **instrument to be twinned** (RI_T) — at **≥ 5 laser powers**
   spanning ~5–100 % (e.g. 20/40/60/80/100 %), with a **calibrated power meter**
   (same meter ideally; < 5 % error). Single-point: ≥ 5 points averaged per
   power; mapping: ≥ 3 maps per power, matched area/resolution to the other
   instrument's illumination spot. **Background-corrected** (laser-off, same
   conditions). Fixed integration time per instrument across its 5 powers.
2. **Pre-process** (§6.3): **normalize** RI_T intensities to RI_R's laser power
   and integration time — `I_N = I_R · (LP_R/LP_T)` (Formula 1) then
   `I_N = I_R · (t_R/t_T)` (Formula 2) — then **remove baseline** with one
   consistent method across all spectra.
3. **Laser-power regression** (§6.4): quantify the RRB intensity (peak-fit with
   Lorentzian / Gaussian / Voigt / Pearson IV) vs laser power for each
   instrument → two linear regression lines. **CF = S_RIR / S_RIT** (ratio of
   slopes, Formula 3).
4. **Verify** (§6.5), three ways: (a) RRB_RIT × CF overlaps the RRB_RIR
   regression line across all powers; (b) full RI_T spectra × CF coincide with
   RI_R; (c) **quality factor** `Q_HI = 1 − |A_R − A_T| / A_R` (Formula 4,
   area-based) — **Q_HI = 1** ideal, **> 0.9** very good — averaged over power
   pairs. Recommended **validation** at 2 *additional* laser powers not used in
   fitting.

## Application (§7)

Harmonize any real (18133-calibrated) sample from RI_T by **multiplying its
spectrum by CF**, provided its laser power / integration time match (or are
normalized to) those used to derive CF. Output units: **a.u.c.** (arbitrary
units corrected). Worked example (Annex D): CF = 1.39 between two instruments.

## Key symbols

CF (correction factor) · RRB (reference Raman band, TiO₂ 144 cm⁻¹) ·
RI_R / RI_T (reference / to-be-twinned instrument) · S_RIR / S_RIT (regression
slopes) · Q_HI (quality of harmonization) · LP (laser power) · a.u.c.

## For a future P6 pipeline implementation

- Inputs already exist in P6: TiPS test-sample spectra at multiple laser
  powers (see `track1_power/` power-linearity work) — 18134 is essentially the
  formalization of that intensity-vs-power regression into a transferable CF.
- ramanchada2 has the reference implementation; a pipeline task would: load
  TiPS spectra per (instrument, power), normalize (power + integration time),
  baseline-remove, fit the 144 cm⁻¹ RRB, regress vs power, compute CF against a
  chosen reference instrument, then emit CF + Q_HI per twinned pair.
- Depends on 18133 x/y calibration being applied first (prerequisite chain).
