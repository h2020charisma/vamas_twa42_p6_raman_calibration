"""Tests for the deck statistics.

These pin the numbers that end up on a slide. They run on small synthetic
frames rather than the real assessment CSVs, so they stay fast and do not
depend on a particular pipeline run existing on disk.
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from slides_content import (  # noqa: E402
    gross_mismatches,
    ne_summary,
    overall_summary,
    pct_change,
    per_participant,
    pick_examples,
    resolution_stats,
    sample_summary,
    stats_table,
    table_html,
)
from slides_render import render_deck  # noqa: E402


def sample_frame(rows):
    """rows: (key, laser, path, sample, stage, distance)"""
    return pd.DataFrame(
        [dict(key=k, laser_wl=w, optical_path=p, sample=s,
              before_after=st, distances=d, inlier_mask=True)
         for k, w, p, s, st, d in rows])


# --- pct_change -------------------------------------------------------------


def test_pct_change_positive_when_error_shrinks():
    assert pct_change(2.0, 1.0) == pytest.approx(50.0)


def test_pct_change_negative_when_error_grows():
    assert pct_change(1.0, 2.0) == pytest.approx(-100.0)


def test_pct_change_is_nan_rather_than_dividing_by_zero():
    assert np.isnan(pct_change(0.0, 1.0))
    assert np.isnan(pct_change(np.nan, 1.0))


# --- neon -------------------------------------------------------------------


def test_ne_summary_uses_only_neon_rows():
    """matched_peaks_Ne.csv carries sample rows too; they must not leak into
    the neon statistics, which are in nm rather than cm-1."""
    df = pd.DataFrame([
        dict(sample="Ne", before_after="1.original", laser_wl=532, distances=0.4),
        dict(sample="Ne", before_after="1.original", laser_wl=532, distances=-0.2),
        dict(sample="Ne", before_after="2.Ne_clbr", laser_wl=532, distances=0.02),
        # a sample row that would wreck the median if counted
        dict(sample="PST", before_after="1.original", laser_wl=532, distances=99.0),
    ])
    out = ne_summary(df)
    before = out.loc[(out["stage"] == "1.original") & (out["laser_wl"] == "all")]
    assert before["n"].item() == 2
    assert before["median"].item() == pytest.approx(0.3)


def test_ne_summary_counts_outliers_above_threshold():
    df = pd.DataFrame([
        dict(sample="Ne", before_after="1.original", laser_wl=532, distances=2.5),
        dict(sample="Ne", before_after="1.original", laser_wl=532, distances=0.1),
        dict(sample="Ne", before_after="2.Ne_clbr", laser_wl=532, distances=0.01),
    ])
    out = ne_summary(df, outlier_nm=1.0)
    before = out.loc[(out["stage"] == "1.original") & (out["laser_wl"] == "all")]
    after = out.loc[(out["stage"] == "2.Ne_clbr") & (out["laser_wl"] == "all")]
    assert before["outliers"].item() == 1
    assert after["outliers"].item() == 0


# --- samples ----------------------------------------------------------------


def test_sample_summary_medians_per_material_and_stage():
    df = sample_frame([
        ("K1", 532, "OP1", "S0B", "1.original", 1.0),
        ("K1", 532, "OP1", "S0B", "1.original", 3.0),
        ("K1", 532, "OP1", "S0B", "2.x-clbr", 0.1),
        ("K1", 532, "OP1", "S0B", "2.x-clbr", 0.3),
    ])
    out = sample_summary(df)
    before = out.loc[(out["sample"] == "S0B") & (out["stage"] == "1.original")]
    after = out.loc[(out["sample"] == "S0B") & (out["stage"] == "2.x-clbr")]
    assert before["median"].item() == pytest.approx(2.0)
    assert after["median"].item() == pytest.approx(0.2)


def test_artifact_filter_excludes_exactly_the_rows_above_threshold():
    """A few peaks matched to the wrong reference line dominate any mean, so
    the robust variant must drop them and only them."""
    df = sample_frame([
        ("K1", 532, "OP1", "CAL", "1.original", 1.0),
        ("K1", 532, "OP1", "CAL", "1.original", 2.0),
        ("K1", 532, "OP1", "CAL", "1.original", 181.0),
    ])
    unrobust = sample_summary(df)
    robust = sample_summary(df, artifact_cm1=20.0)
    assert unrobust.loc[0, "n"] == 3
    assert robust.loc[0, "n"] == 2
    assert robust.loc[0, "mean"] == pytest.approx(1.5)


def test_sample_summary_reports_standard_deviation():
    df = sample_frame([
        ("K1", 532, "OP1", "PST", "1.original", 1.0),
        ("K1", 532, "OP1", "PST", "1.original", 3.0),
    ])
    out = sample_summary(df)
    # sample SD (ddof=1) of {1, 3} is sqrt(2)
    assert out["sd"].item() == pytest.approx(np.sqrt(2.0))


def test_standard_deviation_undefined_for_single_observation():
    """A single peak has no spread; reporting 0 would imply certainty that is
    not there."""
    df = sample_frame([("K1", 532, "OP1", "PST", "1.original", 1.0)])
    assert np.isnan(sample_summary(df)["sd"].item())


def test_do_no_harm_example_excludes_degraded_paths():
    """An already-good path that the calibration still made worse is a
    regression, not evidence that good instruments are left alone."""
    rows = []
    for _ in range(6):
        # smallest starting error, but degrades badly
        rows.append(("SMALL_BUT_WORSE", 532, "OP1", "PST", "1.original", 0.10))
        rows.append(("SMALL_BUT_WORSE", 532, "OP1", "PST", "2.x-clbr", 0.40))
        # slightly larger start, essentially unchanged
        rows.append(("STEADY", 532, "OP2", "PST", "1.original", 0.50))
        rows.append(("STEADY", 532, "OP2", "PST", "2.x-clbr", 0.49))
        # a clear success so the success slot is taken by something else
        rows.append(("BEST", 785, "OP1", "PST", "1.original", 8.0))
        rows.append(("BEST", 785, "OP1", "PST", "2.x-clbr", 0.5))
    picks = pick_examples(sample_frame(rows), min_peaks=5)
    assert picks["do_no_harm"]["key"] == "STEADY"


def test_sample_summary_stage_ordering_is_pipeline_order():
    df = sample_frame([
        ("K1", 532, "OP1", "PST", "3.y-clbr", 1.0),
        ("K1", 532, "OP1", "PST", "1.original", 1.0),
        ("K1", 532, "OP1", "PST", "2.x-clbr", 1.0),
    ])
    out = sample_summary(df)
    assert list(out["stage"]) == ["1.original", "2.x-clbr", "3.y-clbr"]


def test_overall_summary_reports_all_and_per_laser():
    df = sample_frame([
        ("K1", 532, "OP1", "PST", "1.original", 1.0),
        ("K2", 785, "OP1", "PST", "1.original", 3.0),
    ])
    out = overall_summary(df)
    assert set(out["laser_wl"]) == {"all", "532", "785"}
    total = out.loc[out["laser_wl"] == "all"]
    assert total["n"].item() == 2


# --- per participant and examples -------------------------------------------


def test_per_participant_final_falls_back_to_x_when_no_y_stage():
    """Not every optical path has an intensity certificate; the final stage is
    y-calibrated where it exists and x-calibrated otherwise."""
    df = sample_frame([
        ("K1", 532, "OP1", "PST", "1.original", 2.0),
        ("K1", 532, "OP1", "PST", "2.x-clbr", 1.0),
    ])
    out = per_participant(df)
    assert out["final"].iloc[0] == pytest.approx(1.0)
    assert out["improvement_pct"].iloc[0] == pytest.approx(50.0)


def test_pick_examples_selects_success_and_regression_by_rule():
    rows = []
    # a clear improvement
    for i in range(6):
        rows.append(("GOOD", 532, "OP1", "PST", "1.original", 4.0))
        rows.append(("GOOD", 532, "OP1", "PST", "2.x-clbr", 0.4))
    # a clear regression
    for i in range(6):
        rows.append(("BAD", 785, "OP1", "PST", "1.original", 1.0))
        rows.append(("BAD", 785, "OP1", "PST", "2.x-clbr", 5.0))
    # already good, barely changes
    for i in range(6):
        rows.append(("FLAT", 532, "OP2", "PST", "1.original", 0.10))
        rows.append(("FLAT", 532, "OP2", "PST", "2.x-clbr", 0.09))

    picks = pick_examples(sample_frame(rows), min_peaks=5)
    assert picks["success"]["key"] == "GOOD"
    assert picks["regression"]["key"] == "BAD"
    assert picks["do_no_harm"]["key"] == "FLAT"


def test_pick_examples_respects_minimum_peak_count():
    """A path with two matched peaks is not evidence; it must not become the
    headline example."""
    rows = [("TINY", 532, "OP1", "PST", "1.original", 9.0),
            ("TINY", 532, "OP1", "PST", "2.x-clbr", 0.1)]
    for i in range(6):
        rows.append(("SOLID", 532, "OP2", "PST", "1.original", 2.0))
        rows.append(("SOLID", 532, "OP2", "PST", "2.x-clbr", 1.0))
    picks = pick_examples(sample_frame(rows), min_peaks=5)
    assert picks["success"]["key"] == "SOLID"


def test_pick_examples_returns_empty_when_nothing_qualifies():
    df = sample_frame([("K1", 532, "OP1", "PST", "1.original", 1.0)])
    assert pick_examples(df, min_peaks=5) == {}


# --- artifacts and resolution -----------------------------------------------


def test_gross_mismatches_counts_rows_still_flagged_inlier():
    df = sample_frame([
        ("K1", 532, "OP1", "CAL", "1.original", 1.0),
        ("K1", 532, "OP1", "CAL", "1.original", 181.0),
    ])
    out = gross_mismatches(df, artifact_cm1=20.0)
    assert out["n_gross"] == 1
    assert out["n_gross_still_inlier"] == 1
    assert out["max_abs"] == pytest.approx(181.0)


def test_resolution_stats_spread_and_pass_counts():
    df = pd.DataFrame([
        dict(key="K1", laser_wl=532, optical_path="OP1", spectral_resolution=0.4,
             within_cwa_boundary=True, uniform_grid=False, max_neon_fwhm_nm=0.08),
        dict(key="K2", laser_wl=532, optical_path="OP1", spectral_resolution=16.0,
             within_cwa_boundary=False, uniform_grid=False, max_neon_fwhm_nm=0.8),
        dict(key="K3", laser_wl=785, optical_path="OP1",
             spectral_resolution=float("nan"),
             within_cwa_boundary=False, uniform_grid=True, max_neon_fwhm_nm=1.9),
    ])
    out = resolution_stats(df)
    assert out["n_paths"] == 3
    assert out["n_within"] == 1
    assert out["spread_factor"] == pytest.approx(40.0)
    reasons = {f["key"]: f["reason"] for f in out["failures"]}
    assert "no calcite fit" in reasons["K3"]
    assert "vendor-resampled grid" in reasons["K3"]
    assert "resolution" in reasons["K2"]


# --- rendering --------------------------------------------------------------


def test_table_html_escapes_and_handles_empty():
    assert "No rows" in table_html(pd.DataFrame())
    out = table_html(pd.DataFrame([{"k": "<script>"}]))
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def build_full_frames():
    rows = []
    for _ in range(6):
        rows += [
            ("K1", 532, "OP1", "S0B", "1.original", 1.4),
            ("K1", 532, "OP1", "S0B", "2.x-clbr", 0.08),
            ("K1", 532, "OP1", "S0B", "3.y-clbr", 0.07),
            ("K2", 785, "OP1", "PST", "1.original", 1.1),
            ("K2", 785, "OP1", "PST", "2.x-clbr", 1.3),
            ("K2", 785, "OP1", "PST", "3.y-clbr", 1.4),
        ]
    df_samples = sample_frame(rows)
    df_ne = pd.DataFrame([
        dict(sample="Ne", before_after="1.original", laser_wl=532, distances=0.21),
        dict(sample="Ne", before_after="2.Ne_clbr", laser_wl=532, distances=0.017),
        dict(sample="Ne", before_after="1.original", laser_wl=785, distances=0.23),
        dict(sample="Ne", before_after="2.Ne_clbr", laser_wl=785, distances=0.021),
    ])
    df_res = pd.DataFrame([
        dict(key="K1", laser_wl=532, optical_path="OP1", spectral_resolution=0.41,
             within_cwa_boundary=True, uniform_grid=False, max_neon_fwhm_nm=0.08),
        dict(key="K2", laser_wl=785, optical_path="OP1", spectral_resolution=16.4,
             within_cwa_boundary=False, uniform_grid=False, max_neon_fwhm_nm=0.8),
    ])
    return df_samples, df_ne, df_res


def test_render_deck_produces_all_slides_without_placeholder_nans():
    df_samples, df_ne, df_res = build_full_frames()
    ctx = dict(title="T", meeting="M", context="Match mode qargmin2d "
               "Interpolators poly Fit Ne peaks True", generated="2026-08-06",
               n_keys=2, n_paths=2, lasers="532 / 785",
               match_mode="qargmin2d", interpolator="poly", fit_ne_peaks="True")
    html = render_deck(
        ctx=ctx,
        ne=ne_summary(df_ne),
        samples=sample_summary(df_samples),
        overall=overall_summary(df_samples, artifact_cm1=20.0),
        resolution=resolution_stats(df_res),
        gross=gross_mismatches(df_samples, artifact_cm1=20.0),
        worked_examples=[("K1, 532 nm, OP1", None, "worked_K1")],
        per_material={},
    )
    # 14 fixed slides plus one per worked example
    assert html.count('class="slide"') == 15
    assert "<!doctype html>" in html
    # A rendered page must never show raw missing-value markers. Match them as
    # standalone cell/word content rather than as substrings, so ordinary words
    # that happen to contain "nan" (provenance) do not trip the check.
    assert not re.search(r">\s*(nan|None|NaN|inf)\s*<", html)
    assert not re.search(r"\b(nan|NaN)\b", html)


def test_stats_table_covers_every_section():
    df_samples, df_ne, df_res = build_full_frames()
    stats = stats_table(
        ne_summary(df_ne),
        sample_summary(df_samples),
        overall_summary(df_samples, artifact_cm1=20.0),
        resolution_stats(df_res),
        pick_examples(df_samples, min_peaks=5),
    )
    assert set(stats["section"]) >= {"neon", "samples", "overall",
                                     "resolution", "example"}
    assert not stats.empty
