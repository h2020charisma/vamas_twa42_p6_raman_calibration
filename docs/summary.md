# VAMAS TWA42 P6 x-calibration pipeline vs CWA 18133:2024 — implementation summary

*Status: 2026-07-06, branch `troubleshoot/xcal` (pipeline) + `issue233` (ramanchada2).
Dataset: VAMAS P6 round robin, 11 calibration keys, 532/785 nm, Ne + Si + calcite (CAL) +
polystyrene (PST) + APAP; assessment against certified PST/CAL peak positions.*

## 1. What the implementation covers, mapped to the CWA

| CWA 18133:2024 clause | Implementation | Status |
|---|---|---|
| §6.1 Prerequisites A–E (Ne, Si, calcite, PS spectra, laser wavelength integer) | `spectraframe_load` → `spectraframe_calibrate`; NIST Ne lines and Si 520.45 cm⁻¹ from `ramanchada2.misc.constants` | ✅ |
| §6.2.1 Section 1 — Ne → wavelength x-axis, matched to NIST assignments | `CalibrationModel.derive_model_curve`: peak find/fit (Gaussian/Pearson IV per §6.1c), peak↔NIST matching (`qargmin2d` + robust filter), interpolator through matched anchors | ✅ (with additions the CWA does not specify — see §3) |
| §6.2.2 Section 2 — Si → laser zero → Raman-shift x-axis | `derive_model_zero`, Pearson IV fit of Si, laser wavelength solved from the Ne-calibrated Si position | ✅ |
| §6.2.3–6.2.4 Sections 3–4 — pixel/spectral resolution curves (Ne FWHM, calcite) | `overview.py` computes per-instrument resolution estimates; no SpeD:SRes curve product | ⚠️ partial |
| §6.2.5 Section 5 — **final adjustment** of the laser-zeroed axis using calcite + PS peak positions | **Not implemented as a calibration step.** PST/CAL are used only for *verification* (assessment CSVs, `calibration_verify`) | ❌ deliberate deviation, see §4.1 |
| §7 y-axis relative intensity correction (SRM glass / LED) | `spectraframe_ycalibrate` (NIST SRM2242a / ELODIZ LED tags), applied after x-calibration as required | ✅ |
| §8 Calibration files (portable point list + spline, Si position, calibrated laser wl) | Models persisted as Python **pickles** (`calmodel_*.pkl`) | ⚠️ deviation, see §4.4 |
| §5.3 Data quality (SNR>8, spike removal, no pedestal, background subtraction) | Pedestal removal (`y − min`), SNIP baseline, HDR merge; **no automated SNR gate or spike removal step** | ⚠️ partial |
| §6.1d Polyharmonic spline for interpolation/extrapolation | `rbfinverse` implements the CWA recipe (thin-plate spline evaluated forward on a dense grid + monotone PCHIP inverse); `poly`, `pchip(inverse)`, `(pchip)polyinverse` provided as alternatives and compared empirically | ✅ + extensions |

## 2. Issues found in production runs and their solutions

The headline problem: **x-calibration made certified-sample residuals worse than no
calibration** on a handful of optical paths (all 532 nm), across every interpolator variant.
Root cause was never the interpolator: it was defective **anchor sets**, whose local error at
the Si wavelength (547.15 nm @532) is converted by laser zeroing (§6.2.2) into a whole-axis
tilt that grows with Raman shift (e.g. 0 at Si → +14 cm⁻¹ at 2904 cm⁻¹).

| # | Failure mode | Path (worst) | Solution (ramanchada2 `672f5ff6`) | Result (sample RMSE, cm⁻¹) |
|---|---|---|---|---|
| 1 | Anchor filter band floored at 0.25×Ne-line-spacing (≈0.84 nm) **admitted near-miss mismatches** (spurious peaks matched to the nearest NIST line, +0.5…+1 nm off trend) which tilt the fit; the earlier linear filter had the opposite failure (dropped on-trend near-laser anchors → Si extrapolated) | P6_0901 OP1 | Two-stage band in `robust_poly_residual_filter`: RANSAC search with the wide band, then re-selection within n_σ·MAD of the *consensus* residuals (floor 0.05×spacing); plus a bimodal majority-mode split | 10.45 → **1.88** (orig 2.35) |
| 2 | **Noise-chasing polynomial degree**: degree chosen by pure max-residual minimisation always rewards extra degrees; with noisy anchors (±0.5–1 nm centres from blended Ne lines on low-resolution paths) the deg-3/4 fit tilts at the edges | P6_01002 OP1, P6_0901 OP3 | Parsimonious selection: a higher degree must reduce max residual by >20 % | 6.30 → **3.90** (orig 1.94) |
| 3 | **Unconstrained extrapolation tails** beyond the last Ne anchor: Ne lines end ≈660 nm (532) / ≈967 nm (785), CH-stretch ≈629 nm @532 lies beyond some instruments' anchor spans; polynomial tails ran to −11 nm, PCHIP edge cubics to −62 nm | P6_0901 OP3 (assessment mean **71.5**) | Constant-correction (unit-slope) extrapolation beyond the anchor span in both poly and PCHIP interpolators | 71.5 → **1.57** after full fix set |
| 4 | **Anchor gap spanning Si**: P6_0301 SSL1 has no usable Ne lines between 540–575 nm; the lone 540 anchor is out-voted by 21 anchors ≥575 nm; Si (547) and the 560s-nm fingerprint both interpolated over the hole | P6_0301 SSL1 | Mitigated by #1–#3 (CH-stretch error +8.4 → +2.7); residual ≈ −2 cm⁻¹ fingerprint sag is a **data limitation** | 1.21 → 1.58 (was → 3.8) |
| 5 | **Silent loss of optical paths from the assessment**: when no fitted peak passed the centre-stderr threshold, `center_amplitude` returned an unpackable empty array and the per-tag try/except swallowed the crash — P6_0701 532/OP2 was simply missing from before/after statistics | P6_0701 OP2 | Well-formed empty result + fallback to peak candidates with a warning | path restored (n 343→357) |
| 6 | **Assessment statistics polluted by matching artifacts** (|distance| 35–180 cm⁻¹ pairs present before *and* after calibration, e.g. CAL@785) — plain means overstated or masked regressions | CAL 785 paths | Robust summary in `calibration_verify`: median + artifact-excluded mean (|d| ≤ 20) per stage + explicit "worsened >1 cm⁻¹" table | — |

**End-to-end outcome** (full pipeline rerun, `poly`/`qargmin2d`):

| | robust mean | median |
|---|---|---|
| old code | 1.53 → 2.09 (worse) | 1.04 → 1.19 |
| fixed code | 1.58 → **1.33** (better) | 1.12 → **0.84** |

A matcher × interpolator sweep (`tests/compare_interpolators.py --matchers`) confirmed no
match method dominates; `qargmin2d` retained (Hungarian `assignment` is catastrophic on the
SSL1 anchor gap: RMSE 187).

## 3. What we had to fight with (beyond the CWA's text)

- **Peak↔NIST matching is the hard problem and the CWA is silent on it.** §6.2.1 says
  "match the neon peaks to their NIST assignments" as if it were trivial. In practice, when the
  uncalibrated axis error approaches the local Ne line spacing, every matcher mis-assigns some
  peaks; spurious peaks (non-Ne emission, unresolved blends) grab the nearest NIST line.
  Most of the engineering effort of this pipeline (six match methods, RANSAC outlier filter,
  consensus band, bimodality handling) exists to solve a step the protocol devotes one sentence to.
- **Reference-line sparsity near the laser.** At 532 nm only a handful of usable Ne lines exist
  below the Si wavelength; one instrument (P6_0301 SSL1) measured none between 540–575 nm.
  The protocol assumes anchor coverage it does not require.
- **Blended Ne lines on low-resolution instruments** produce anchor centre errors of ±0.5–1 nm
  (P6_0901 OP3, P6_01002 OP1) — an accuracy floor no interpolator can beat, discoverable only
  from the anchor residual scatter.
- **The Si-zeroing lever arm.** Laser zeroing pins a single point; *any* model error at that one
  wavelength tilts the entire cm⁻¹ axis. This amplification is inherent to the §6.2.2 design and
  is why small anchor defects became tens of cm⁻¹ at CH-stretch.
- **Truth conflicts.** Two flagged paths remain where the Ne+Si truth disagrees with the
  certified PST/CAL truth by 1.6–3.6 cm⁻¹ (P6_0701 OP2: near-perfect factory axis "corrected"
  away; P6_0702 OP1@785: smooth +0.4 nm Ne residual trend at the CCD edge, assignments
  verified unambiguous — likely centroid bias of weak edge lines). This is precisely the gap the
  CWA's §6.2.5 final adjustment is designed to close (see §4.1).
- **Tooling/QA traps**: models persisted as pickles are coupled to code versions (a rebuilt model
  can differ from the pickled one for the same data — validation must rebuild, not load);
  notebook per-tag `try/except` swallowed crashes and silently changed the assessed population;
  an editable-install dependency means uncommitted library edits silently change pipeline behaviour.

## 4. Suggestions for the protocol (CWA revision input)

1. **Make Section 5 (calcite+PS final adjustment) normative and bounded.** Our deliberate
   deviation — using PST/CAL only for verification — exposed that Ne+Si alone leaves 1.5–3.5 cm⁻¹
   conflicts with certified samples on some instruments. Conversely an *unbounded* final
   adjustment would hide real Ne/Si failures. Recommend: apply the §6.2.5 adjustment, but require
   reporting the adjustment magnitude, and flag instruments where it exceeds a tolerance.
2. **Specify the matching step.** Require a robust (outlier-tolerant) assignment procedure, a
   documented rejection criterion, and a minimum surviving-anchor count; require reporting of
   anchor residual statistics (scatter, span, largest gap) as calibration quality indicators.
3. **Require anchor coverage around the Si wavelength**, or define the fallback when Si falls in
   an anchor gap / outside the span (our answer: never extrapolate a spline tail; extend the edge
   *correction* at unit slope, and warn).
4. **Define extrapolation behaviour explicitly.** §6.1d permits the spline to "extrapolate the
   rest of the x-axis"; unconstrained polyharmonic/polynomial tails corrupted the 2800–3100 cm⁻¹
   region by tens of cm⁻¹. The protocol should mandate constant-correction (or clearly bounded)
   extrapolation and require flagging spectral regions outside anchor support.
5. **Require monotonicity of the calibration map.** A raw forward spline can fold the axis; the
   protocol should state the map must be strictly monotonic (our `rbfinverse` guarantees it via a
   monotone PCHIP through dense forward-evaluated points).
6. **Add acceptance metrics for verification.** The CWA prescribes verification samples but no
   statistic or threshold. Recommend: median and artifact-excluded mean |Δν̃| per stage, a
   per-optical-path regression table, and a pass criterion (e.g. calibrated median ≤ 1 cm⁻¹ and
   no path worsened by more than 1 cm⁻¹).
7. **Resolution-aware Ne line lists.** Provide curated NIST subsets per spectral-resolution class
   so unresolved doublets are excluded before matching instead of poisoning the anchor set.
8. **Portable calibration file (§8) over language-specific serialisation.** Our pickles violate
   the spirit of §8. Export the point list (uncalibrated → calibrated shift), Si position, and
   solved laser wavelength in an open format (e.g. NeXus/HDF5 or plain CSV+JSON metadata) so any
   implementation can regenerate the spline.

## 5. Residual known limitations

- P6_0301 SSL1: ~−2 cm⁻¹ fingerprint sag — unfixable without Ne lines in 540–575 nm (data).
- P6_01002 OP1 / P6_0901 OP3: ±0.5–1 nm Ne anchor noise floor (blended lines) limits accuracy
  to ~2–4 cm⁻¹ regardless of algorithm.
- P6_0701 OP2 (532), P6_0702 OP1 (785): Ne+Si truth vs certified-sample truth conflicts of
  1.6/3.6 cm⁻¹ — the case for adopting §6.2.5 (see §4.1).
- CH-stretch (~2900 cm⁻¹) is beyond Ne anchor support on several instruments at both lasers;
  values there carry the edge-correction assumption and should be flagged in released data.
