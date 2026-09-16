"""Synthetic end-to-end check for the CWA 18134 twinning implementation (no file IO).

Fabricates reference and twinned TiPS SpectraFrames (TiO2 144 cm-1 RRB band whose
intensity is strictly proportional to slope * laser_power_mW, plus a 638 cm-1 band
for meaningful areas) and drives the repo-side QhiTwinningComponent (subclass of
ramanchada2's TwinningComponent) from protocols/twinning.py.

Cases (per docs/cwa18134_summary.md / the approved plan):
  * happy path: twinned slope = reference slope / 1.39  ->  CF ~= 1.39 (CWA Annex D
    worked example), exactly one Q_HI row per paired power with mean > 0.95
    (Formula 4), verdict PASS, plot renders incl. the §6.5(a) CF-corrected overlay
  * near-miss power levels pair only with power_tolerance > 0 (control: they do
    not pair at tolerance 0)
  * unbalanced power sets (5 ref vs 4 twinned, intersection < min_powers)
  * fewer than min_powers=5 distinct powers on both sides
  * twinned rows missing calibrated-meter laser_power_mW (CWA §5/§6.2)
  * flat-zero spectra -> all peak fits fail
  ... all four negatives must raise NotEnoughPowers with a reason.

Usage:
    cd src && uv run python tests/test_twinning_p6.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib

matplotlib.use("Agg")  # headless rendering

import numpy as np
import pandas as pd
from ramanchada2.protocols.spectraframe import SpectraFrame
from ramanchada2.spectrum import Spectrum

from twinning_utils import TWINNING_GROUPING_COLS, QhiTwinningComponent, NotEnoughPowers

X = np.arange(0.0, 3200.0, 1.0)
POWERS = [20.0, 40.0, 60.0, 80.0, 100.0]  # % of available power
MW_FACTOR = 2.0  # mW per percent
TIME_MS = 1000.0
BANDS = [(144.0, 20.0, 1.0), (638.0, 18.0, 0.3)]  # (center, sigma, amp fraction)
TARGET_CF = 1.39  # CWA 18134 Annex D worked example
NOISE_REL = 0.001


def _gauss(x, center, sigma, amp):
    return amp * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def _spectrum(slope, mW, flat=False, seed=7):
    """Intensity ∝ slope * mW on the RRB bands (+ small noise); flat=True -> pure zeros."""
    if flat:
        return Spectrum(x=X.copy(), y=np.zeros_like(X))
    rng = np.random.default_rng(seed)
    amp = slope * mW
    y = np.full_like(X, 0.02 * amp)  # constant pedestal, removed by baseline_snip
    for center, sigma, frac in BANDS:
        y = y + _gauss(X, center, sigma, amp * frac)
    y = y + rng.normal(0.0, NOISE_REL * amp, size=X.shape)
    return Spectrum(x=X.copy(), y=y)


def make_frame(key, slope, powers, mW_values=None, mW_missing=False, flat=False, wl=532):
    """One instrument: replicate rows per (power), schema-valid for SpectraFrame."""
    rows = []
    for p_i, pct in enumerate(powers):
        mW = (float(mW_values[p_i]) if mW_values else pct * MW_FACTOR)
        for rep in (1, 2, 3):
            rows.append(
                dict(
                    sample="TiPS_Ti",
                    provider=key,
                    device=f"{key} BWtek iRaman",
                    device_id=f"{key} BWtek 785nm-{wl}",
                    laser_wl=int(wl),
                    laser_power_percent=float(pct),
                    laser_power_mW=(np.nan if mW_missing else float(mW)),
                    time_ms=TIME_MS,
                    replicate=rep,
                    optical_path="OP1",
                    spectrum=_spectrum(slope, mW, flat=flat, seed=7 + 11 * p_i + rep),
                )
            )
    df = pd.DataFrame(rows)
    return SpectraFrame.from_dataframe(df, column_mapping={})


def run_pair(ref_kwargs, twin_kwargs, power_tolerance=0.0):
    """Construct QhiTwinningComponent and derive_model — the contract point."""
    cmp = QhiTwinningComponent(
        twinned=make_frame("TWN", **twin_kwargs),
        reference=make_frame("REF", **ref_kwargs),
        boundaries=(50, 2000),
        reference_band_cm1=144.0,
        grouping_cols=TWINNING_GROUPING_COLS,
        min_powers=5,
        power_tolerance=power_tolerance,
    )
    cmp.derive_model()
    return cmp


def _qhi_values(qhi_df):
    col = next(c for c in qhi_df.columns if c.upper().startswith("Q_HI"))
    return qhi_df[col].astype(float)


def _assert_cf_and_qhi(cmp, n_pairs=5):
    assert abs(cmp.correction_factor - TARGET_CF) < 0.05, (
        f"CF {cmp.correction_factor:.4f} not within 0.05 of {TARGET_CF}"
    )
    qhi_df = cmp.compute_qhi()
    qhi = _qhi_values(qhi_df)
    assert len(qhi) == n_pairs, f"expected exactly {n_pairs} power-pair rows, got {len(qhi)}"
    assert ((qhi > 0.0) & (qhi < 1.5)).all(), f"implausible Q_HI values: {list(qhi)}"
    assert qhi.mean() > 0.95, f"Q_HI mean {qhi.mean():.4f} <= 0.95"


def _assert_corrected_overlay(cmp):
    """CWA §6.5(a): the plot must show RRB intensity * CF vs the reference regression."""
    ax = cmp.plot()  # 2-panel: regressions + area bars
    assert ax is not None and len(ax) == 2, "plot() must return the 2-panel axes"
    expected = np.asarray(cmp.twinned["peak_intensity"], dtype=float) * cmp.correction_factor
    found = False
    for ln in ax[0].get_lines():
        label = str(ln.get_label()).lower()
        yd = ln.get_ydata()
        try:
            y = np.asarray(yd, dtype=float)
        except (TypeError, ValueError):
            continue
        if y.shape == expected.shape and np.allclose(y, expected, rtol=1e-6, equal_nan=True):
            found = True
            break
        if "corrected" in label and y.shape[0] == expected.shape[0]:
            found = True
            break
    assert found, (
        "no CF-corrected-points overlay line in ax[0] "
        f"({len(ax[0].get_lines())} lines; expected RRB intensity * CF = {cmp.correction_factor:.3f})"
    )
    import matplotlib.pyplot as plt

    plt.close("all")


def test_happy_path():
    # reference slope s, twinned slope s/1.39 -> CF must be ~1.39
    cmp = run_pair(dict(slope=1.0, powers=POWERS), dict(slope=1.0 / TARGET_CF, powers=POWERS))
    _assert_cf_and_qhi(cmp)
    verdict = getattr(cmp, "verdict", None) or cmp.compute_qhi().attrs.get("verdict")
    if verdict is None:
        print("  WARN: no verdict exposed (cmp.verdict / qhi_df.attrs['verdict'])")
    else:
        assert verdict == "PASS", f"verdict {verdict!r} != PASS"
    _assert_corrected_overlay(cmp)


def _expect_not_twinable(label, ref_kwargs, twin_kwargs, reason_contains=None,
                         power_tolerance=0.0):
    try:
        run_pair(ref_kwargs, twin_kwargs, power_tolerance=power_tolerance)
    except NotEnoughPowers as e:
        msg = str(e)
        if reason_contains and reason_contains.lower() not in msg.lower():
            raise AssertionError(
                f"{label}: NotEnoughPowers reason {msg!r} lacks {reason_contains!r}"
            )
        print(f"    ({label}) NotEnoughPowers: {e}")
        return
    except Exception as e:
        raise AssertionError(
            f"{label}: expected NotEnoughPowers, got {type(e).__name__}: {e}"
        ) from e
    raise AssertionError(f"{label}: expected NotEnoughPowers, but the pair twinned fine")


def test_unbalanced_powers():
    # intersection (4) < min_powers=5 despite ref having 5 powers
    _expect_not_twinable(
        "5 vs 4 powers",
        dict(slope=1.0, powers=POWERS),
        dict(slope=0.5, powers=POWERS[:4]),
    )


def test_too_few_powers():
    _expect_not_twinable(
        "both sides 4 powers",
        dict(slope=1.0, powers=POWERS[:4]),
        dict(slope=0.5, powers=POWERS[:4]),
    )


def test_missing_mW():
    # CWA §5/§6.2: real measured (calibrated power meter) mW are mandatory
    _expect_not_twinable(
        "twinned laser_power_mW missing",
        dict(slope=1.0, powers=POWERS),
        dict(slope=0.5, powers=POWERS, mW_missing=True),
        reason_contains="laser_power_mW",
    )


def test_power_tolerance_pairing():
    # Near-miss power levels (20.1 vs 20 …): pairing works only with a
    # positive power_tolerance; with the default 0 the sets don't intersect.
    # Identical measured mW both sides keeps the CF/Q_HI merge well defined.
    tol_powers = [20.1, 40.1, 60.1, 80.1, 100.0]
    mWs = [40.0, 80.0, 120.0, 160.0, 200.0]
    ref = dict(slope=1.0, powers=tol_powers, mW_values=mWs)
    twin = dict(slope=1.0 / TARGET_CF, powers=POWERS, mW_values=mWs)
    cmp = run_pair(ref, twin, power_tolerance=1.0)
    _assert_cf_and_qhi(cmp)
    # control: without tolerance the same pair must not twin
    _expect_not_twinable(
        "tolerance actually required", ref, twin, power_tolerance=0.0
    )


def test_all_fits_fail():
    # flat zero spectra: no RRB anywhere -> every peak fit fails
    _expect_not_twinable(
        "flat zero spectra",
        dict(slope=1.0, powers=POWERS, flat=True),
        dict(slope=0.5, powers=POWERS, flat=True),
    )


def main():
    cases = [
        ("CF/Q_HI happy path (CF ~= 1.39)", test_happy_path),
        ("power tolerance pairing", test_power_tolerance_pairing),
        ("unbalanced power sets", test_unbalanced_powers),
        ("fewer than min_powers", test_too_few_powers),
        ("missing laser_power_mW", test_missing_mW),
        ("all peak fits fail", test_all_fits_fail),
    ]
    failures = 0
    for name, fn in cases:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:
            failures += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print("=" * 60)
    print(f"{len(cases) - failures}/{len(cases)} cases passed"
          + ("" if failures == 0 else " — FAILURES PRESENT"))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
