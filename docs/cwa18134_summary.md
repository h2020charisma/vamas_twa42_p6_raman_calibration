# CWA 18134:2024 — Raman instruments twinning protocol (summary)

*Reference summary for VAMAS TWA42 P6 agents. Source PDF: `cwa18134-1.pdf`
(repo root). CEN Workshop Agreement, September 2024, CHARISMA H2020
(GA 952921). Ideaconsult / Nina Jeliazkova is a listed contributor.*

> **Implementation status:** implemented in **ramanchada2**
> (`ramanchada2.protocols.twinning.TwinningComponent`) **and in the VAMAS P6
> pipeline** as `src/pipeline.twinning.yaml` + `src/twinning.py` /
> `src/twinning_utils.py`. The pipeline applies the **x-calibration
> prerequisite only** — deliberately: the Correction Factor absorbs absolute
> intensity differences, and the spec's own §6.3 pre-processing chain contains
> no y-calibration step. Full CWA 18133 x/y calibration remains the
> instrument-qualification prerequisite, verified outside this data-processing
> task.

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
> the 18133 x-calibration panel. They are **loaded normally** by the P6 loader
> into the `templates_read` HDF5 key (there is no `ignore_samples` filter —
> the earlier claim in this doc was wrong); `spectraframe_tips.py` displays
> them and `src/twinning.py` consumes them as the 18134 test material.

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

## P6 pipeline implementation

Implemented as `src/pipeline.twinning.yaml` (run from `src/`:
`uv run ploomber build -e pipeline.twinning.yaml`; env keys in
`src/env.twinning.example.yaml`):

- The pipeline reuses the standard `spectraframe_load.py` + 
  `spectraframe_calibrate.py` tasks over the `twinning_keys` list, then a
  single `twinning` task (`src/twinning.py`, helpers in
  `src/twinning_utils.py`) wraps ramanchada2's `TwinningComponent` via a
  `QhiTwinningComponent` subclass.
- Per configured reference participant (`twinning_reference_key`) ×
  twinned participant, per laser wavelength / optical path, it: selects the
  background-subtracted TiPS rows (sample tag `tips_sample_tag`), applies the
  x-cal model (`calmodel.apply_calibration_x`), averages replicates, aligns
  the two frames on paired laser powers, then normalizes (power + integration
  time), removes the baseline (snip), fits the TiO₂ RRB
  (`twinning_rrb`, default 144 cm⁻¹), regresses vs power and computes
  **CF** (Formula 3) and **Q_HI** per power pair + mean (Formula 4).
- Outputs under `{{config_output}}/twinning/`: `twinning_results.csv`/`.xlsx`
  (slopes, CF, Q_HI mean/min, PASS/FAIL/not_twinable verdicts + reasons),
  regression & harmonization plots (`plots/`, incl. the §6.5(a) CF-corrected
  overlay), and `twinning_harmonized.h5` (CF-multiplied TiPS spectra).
- Only ≥5 distinct power levels with calibrated-power-meter measured
  `laser_power_mW` (§5/§6.2) can be twinned; everything else is reported as
  `not_twinable`/`skipped` with a reason instead of failing the DAG.
  Optional §6.5 validation at `twinning_validation_powers` (2 extra powers).
- Depends on 18133 **x-calibration** being applied first (prerequisite
  chain); y-calibration is deliberately not applied — CF absorbs the
  intensity scale.
