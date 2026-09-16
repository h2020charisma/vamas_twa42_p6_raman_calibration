"""CWA 18134:2024 Raman instruments twinning helpers (CHARISMA).

Adapts P6 template metadata to ramanchada2 SpectraFrames and extends
``ramanchada2.protocols.twinning.TwinningComponent`` (the CWA 18134 §6
reference implementation: normalize by laser power and integration time,
baseline removal, Voigt fit of the TiO2 144 cm-1 reference Raman band,
laser-power regression, CF = S_RIR / S_RIT) with:

- power-aligned reference/twinned pairing that protects the positional zip in
  ``TwinningComponent.normalize_by_laserpower_time``,
- the Formula 4 quality factor Q_HI per power pair and its mean (section 6.5),
- the corrected-points verification overlay (section 6.5(a)).

Prerequisite is x-axis (18133) calibration only: relative-intensity (y)
calibration is intentionally not applied here, the CF absorbs the intensity
difference (verified against the CWA 18134 §6.3 processing chain).
"""

import logging

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from ramanchada2.protocols.spectraframe import SpectraFrame
from ramanchada2.protocols.twinning import TwinningComponent
from sklearn.linear_model import LinearRegression

from utils import load_calibration_model, parse_numeric_value

logger = logging.getLogger(__name__)

# laser_power_mW is deliberately excluded from the grouping columns: replicates
# whose power-meter readings differ by 0.1 mW would split into separate groups
# and unbalance the reference/twinned frames (mW is restored as a group mean,
# see build_twin_spectra_frame and _attach_mw).
TWINNING_GROUPING_COLS = [
    "sample",
    "provider",
    "device",
    "device_id",
    "laser_wl",
    "laser_power_percent",
    "time_ms",
    "optical_path",
]

# prepare_key_groups group statuses
STATUS_OK = "ok"
STATUS_NO_TIPS = "no_tips_rows"
STATUS_ALL_OVEREXPOSED = "all_overexposed"
STATUS_NO_CALMODEL = "no_x_calmodel"
STATUS_MISSING_MW = "missing_power_meter_values"
STATUS_INSUFFICIENT = "insufficient_powers"
STATUS_CALIBRATION_FAILED = "calibration_failed"


class NotEnoughPowers(Exception):
    """A reference/twinned group cannot be twinned (too few usable powers)."""


def _percent_key(value, tolerance=0.0):
    """Power-pairing key for a laser_power_percent value.

    With tolerance > 0 values are snapped to the tolerance grid so that
    near-equal set points (e.g. 80 vs 80.4 %) still pair up.
    """
    if pd.isna(value):
        return None
    value = float(value)
    if tolerance and tolerance > 0:
        return round(round(value / tolerance) * tolerance, 4)
    return round(value, 6)


def _mw_table(frame):
    """laser_power_mW group means keyed by (round(percent, 4), round(time, 4))."""
    table = {}
    for (pct, time), group in frame.groupby(
        ["laser_power_percent", "time_ms" if "time_ms" in frame.columns else "integration_time_ms"]
    ):
        table[(round(float(pct), 4), round(float(time), 4))] = float(
            group["laser_power_mW"].mean()
        )
    return table


def _attach_mw(frame, mw_table):
    """Re-attach laser_power_mW after average() dropped it (it is not a group col)."""
    frame["laser_power_mW"] = [
        mw_table.get(
            (
                round(float(pct), 4),
                round(float(time), 4),
            ),
            np.nan,
        )
        for pct, time in zip(frame["laser_power_percent"], frame["time_ms"])
    ]
    return frame


def select_tips_rows(df, tips_tag):
    """TiPS rows usable for twinning from a templates_read slice.

    Keeps background-subtracted, non-overexposed rows of the given sample tag
    (overexposed "NO" or unset; values include "NO", free text, "HDR_MERGE").

    Returns:
        (kept_df, info): kept rows and a dict with n_tagged / n_dropped_overexposed.
    """
    tagged = df.loc[df["sample"] == tips_tag]
    info = {"n_tagged": int(tagged.shape[0]), "n_dropped_overexposed": 0}
    if tagged.empty:
        return tagged, info
    overexposed = tagged["overexposed"] if "overexposed" in tagged.columns else None
    if overexposed is None:
        kept = tagged
    else:
        ok = overexposed.isna() | (overexposed == "NO")
        info["n_dropped_overexposed"] = int((~ok).sum())
        kept = tagged.loc[ok]
    return kept, info


def build_twin_spectra_frame(rows, key, cfg=None):
    """Build one SpectraFrame of TiPS replicates for a (key, laser_wl, optical_path).

    Coerces the template numerics (ranges like "45-50" via parse_numeric_value),
    sets laser_power_mW to its (percent, time) group mean, synthesizes an integer
    replicate index, maps integration_time_ms to the SpectraFrame schema column
    time_ms and resamples mixed x-grids to a common one when point counts differ.

    Returns:
        (SpectraFrame | None, reason): reason is "" on success, otherwise one of
        "no_rows" / "missing_power_meter_values".
    """
    df = rows.copy()
    if df.empty:
        return None, "no_rows"
    for col in ["laser_power_percent", "laser_power_mW", "integration_time_ms"]:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = df[col].map(parse_numeric_value)
    # CWA 18134 §5 requires calibrated-power-meter measured mW for every used
    # spectrum — no fallback to percent x max_laser_power_mW.
    bad = df[["laser_power_percent", "laser_power_mW", "integration_time_ms"]].isna().any(axis=1)
    if bad.any():
        return None, "missing_power_meter_values"

    # hazard 3: one representative mW per (percent, time) group so averaging
    # and the power normalization stay consistent
    df["laser_power_mW"] = df.groupby(
        ["laser_power_percent", "integration_time_ms"]
    )["laser_power_mW"].transform("mean")

    df["provider"] = key
    instrument = str(df["instrument_make"].iloc[0]) if "instrument_make" in df else ""
    model = str(df["instrument_model"].iloc[0]) if "instrument_model" in df else ""
    df["device"] = f"{instrument} {model}".strip()
    laser_wl = int(float(df["laser_wl"].iloc[0]))
    df["laser_wl"] = laser_wl
    df["device_id"] = f"{key} {instrument} {laser_wl}nm".strip()
    # hazard 5: pydantic wants an int replicate, not the template measurement
    df["replicate"] = (
        df.groupby(["laser_power_percent", "integration_time_ms"]).cumcount() + 1
    )

    # equal x-grid within one instrument, else Spectrum arithmetic is undefined
    point_counts = df["spectrum"].map(lambda spe: len(spe.x)).unique()
    if len(point_counts) > 1:
        min_x = min(min(spe.x) for spe in df["spectrum"])
        max_x = max(max(spe.x) for spe in df["spectrum"])
        bins = int(max(point_counts))
        logger.info(
            f"{key} wl{laser_wl}: resampling {len(point_counts)} export grids to "
            f"common x-range ({min_x:.1f}, {max_x:.1f}) x {bins} points"
        )
        df["spectrum"] = df["spectrum"].map(
            lambda spe: spe.resample_spline_filter(
                x_range=(min_x, max_x), xnew_bins=bins, spline="akima"
            )
        )

    return SpectraFrame.from_dataframe(df, {"integration_time_ms": "time_ms"}), ""


def prepare_key_groups(key, h5_path, calmodels_dir, cfg, tips_tag, logger=None, min_powers=5):
    """Per (laser_wl, optical_path) x-calibrated TiPS SpectraFrames for one participant.

    Args:
        key: participant key (used as SpectraFrame provider).
        h5_path: spectraframe_load h5 with the 'templates_read' key.
        calmodels_dir: spectracal calmodels folder for this key.
        cfg: loaded config_pipeline json (for per-sample units).
        tips_tag: TiPS sample tag ("TiPS_Ti" or "Tips_PS" style sample names).
        min_powers: minimum distinct laser power levels for an ok group.

    Returns:
        dict[(laser_wl, optical_path)] -> (SpectraFrame | None, status, reason)
        with un-averaged replicate frames; status one of STATUS_* constants.
    """
    log = logger if logger is not None else globals()["logger"]
    groups = {}
    df = pd.read_hdf(h5_path, key="templates_read")
    tips = df.loc[df["sample"] == tips_tag]
    if tips.empty:
        return groups

    units = cfg.get("templates", {}).get(key, {}).get("units", {})
    spe_units = units.get(str(tips_tag).lower(), units.get("ti", "cm-1"))

    for (laser_wl, optical_path), rows in tips.groupby(
        ["laser_wl", "optical_path"], dropna=False
    ):
        entry_id = f"[{key}] {laser_wl}nm {optical_path}"
        kept, info = select_tips_rows(rows, tips_tag)
        if kept.empty:
            status = STATUS_ALL_OVEREXPOSED if info["n_dropped_overexposed"] else STATUS_NO_TIPS
            groups[(laser_wl, optical_path)] = (None, status, f"{info} at {entry_id}")
            continue

        try:
            calmodel = load_calibration_model(int(float(laser_wl)), optical_path, calmodels_dir)
        except Exception:
            calmodel = None
        if calmodel is None:
            groups[(laser_wl, optical_path)] = (
                None, STATUS_NO_CALMODEL, f"no x-cal model for {entry_id}")
            continue

        failed = 0
        calibrated = []
        for spe in kept["spectrum"]:
            try:
                calibrated.append(calmodel.apply_calibration_x(spe, spe_units=spe_units))
            except Exception:
                calibrated.append(None)
                failed += 1
        if failed == len(calibrated):
            groups[(laser_wl, optical_path)] = (
                None, STATUS_CALIBRATION_FAILED, f"x-cal failed for all {failed} spectra")
            continue
        if failed:
            log.warning(f"{entry_id}: x-cal failed for {failed} TiPS spectra, dropping them")
            kept = kept.loc[[spe is not None for spe in calibrated]]
            kept = kept.assign(spectrum=[spe for spe in calibrated if spe is not None])

        frame, reason = build_twin_spectra_frame(kept, key, cfg)
        if frame is None:
            groups[(laser_wl, optical_path)] = (None, reason, reason)
            continue
        n_powers = frame["laser_power_percent"].nunique()
        if n_powers < min_powers:
            groups[(laser_wl, optical_path)] = (
                None, STATUS_INSUFFICIENT,
                f"insufficient laser powers (n={n_powers} < min_powers={min_powers})")
            continue
        groups[(laser_wl, optical_path)] = (frame, STATUS_OK, "")
    return groups


class QhiTwinningComponent(TwinningComponent):
    """TwinningComponent with CWA 18134 §6.5 quality-of-harmonization checks.

    On top of the parent's derive_model/process (CF = slope_R / slope_T):
    - _align() intersects the reference and twinned laser-power sets (with an
      optional percent tolerance) and keeps only common powers on both sides,
      so the parent's positional zip in normalize_by_laserpower_time never sees
      unbalanced frames; fewer than min_powers common powers raises
      NotEnoughPowers at construction time,
    - failed 144 cm-1 peak fits are dropped before the regressions,
    - compute_qhi() applies Formula 4 per power pair against the reference area,
    - _plot() adds the corrected-points overlay of section 6.5(a) that the
      parent left commented out (twinning.py:235-240).
    """

    def __init__(
        self,
        twinned,
        reference,
        boundaries=(50, 2000),
        reference_band_cm1=144.0,
        grouping_cols=TWINNING_GROUPING_COLS,
        min_powers=5,
        power_tolerance=0.0,
    ):
        self.min_powers = min_powers
        self.power_tolerance = power_tolerance
        # capture mW means from the replicate frames before average() drops them
        mw_reference = _mw_table(reference)
        mw_twinned = _mw_table(twinned)
        super().__init__(
            twinned,
            reference,
            boundaries=boundaries,
            reference_band_nm=reference_band_cm1,
            grouping_cols=list(grouping_cols),
        )
        _attach_mw(self.reference, mw_reference)
        _attach_mw(self.twinned, mw_twinned)
        self.paired_powers = []
        self.unpaired_ref_powers = []
        self.unpaired_twin_powers = []
        self.qhi_mean = None
        self.qhi_min = None
        self._align()

    def _align(self):
        """Intersect the power sets and re-sort both frames by laser power.

        Kills the positional-zip and discarded-sort hazards: after this both
        frames have identical, ascending, one-row-per-power sets.
        """
        ref, dropped_ref = self._power_keyed(self.reference)
        twin, dropped_twin = self._power_keyed(self.twinned)
        common = sorted(set(ref["_pkey"]) & set(twin["_pkey"]))
        ref = ref.loc[ref["_pkey"].isin(common)].reset_index(drop=True)
        twin = twin.loc[twin["_pkey"].isin(common)].reset_index(drop=True)
        assert len(ref) == len(twin) == len(common), (
            "power alignment failed: "
            f"{len(ref)} ref vs {len(twin)} twinned rows for {len(common)} powers"
        )
        self.paired_powers = common
        self.unpaired_ref_powers = dropped_ref
        self.unpaired_twin_powers = dropped_twin
        if len(common) < self.min_powers:
            raise NotEnoughPowers(
                f"unbalanced power sets: common powers n={len(common)} "
                f"< min_powers={self.min_powers}"
            )
        # CWA §5/§6.2: the regression abscissa must be the *measured* (calibrated
        # power meter) laser power — never percent x max-power. Fail with this
        # reason before the fit stage can misreport it as "peak fits failed".
        for side, frame in (("reference", ref), ("twinned", twin)):
            mw = pd.to_numeric(frame["laser_power_mW"], errors="coerce")
            if not (mw.notna() & (mw > 0)).all():
                raise NotEnoughPowers(
                    f"missing measured laser_power_mW (CWA §5, calibrated power "
                    f"meter) on the {side} instrument at "
                    f"{int((~(mw.notna() & (mw > 0))).sum())} paired power(s)"
                )
        self.reference = SpectraFrame.from_dataframe(ref.drop(columns="_pkey"), {})
        self.twinned = SpectraFrame.from_dataframe(twin.drop(columns="_pkey"), {})

    def _power_keyed(self, frame):
        frame = frame.sort_values(
            ["laser_power_percent", "laser_power_mW"]
        ).reset_index(drop=True)
        frame = frame.assign(
            _pkey=[_percent_key(v, self.power_tolerance) for v in frame["laser_power_percent"]]
        )
        # one row per power: where a participant alternated integration times at
        # the same set point, keep the longest exposure and report the dropouts
        keep = frame.groupby("_pkey")["time_ms"].idxmax()
        dropped = sorted(set(frame["_pkey"]) - set(frame.loc[keep, "_pkey"]))
        return frame.loc[keep].reset_index(drop=True), dropped

    def laser_power_regression(self, df, boundaries=None, no_fit=False, source="spectrum"):
        """Parent loop with failed peak fits dropped before the regression.

        calc_peak_intensity returns (None, None, None) on any exception and
        LinearRegression.fit then throws on the Nones; rows whose 144 cm-1 fit
        failed are excluded and, if too few remain, NotEnoughPowers is raised.
        """
        if boundaries is None:
            boundaries = (self.reference_band_nm - 50, self.reference_band_nm + 50)
        for index, row in df.iterrows():
            peak_intensity, peak_position, _ = self.calc_peak_intensity(
                row[source], boundaries=boundaries, no_fit=no_fit
            )
            df.at[index, "peak_intensity"] = peak_intensity
            df.at[index, "peak_position"] = peak_position
        fit_df = df.dropna(subset=["peak_intensity"])
        if len(fit_df) < self.min_powers:
            raise NotEnoughPowers(
                f"peak fits failed (n={len(fit_df)} < min_powers={self.min_powers})"
            )
        return LinearRegression().fit(
            fit_df[["laser_power_mW"]].values, fit_df["peak_intensity"].values
        )

    def derive_model(self):
        """Parent CF derivation, then harmonize the twinned spectra (section 6.5(b))."""
        super().derive_model()
        self.process(self.twinned, source="spe_processed", target="spectrum_harmonized")

    def _r2(self, frame):
        usable = frame.dropna(subset=["peak_intensity", "laser_power_mW"])
        if len(usable) < 2:
            return None
        corr = np.corrcoef(
            usable["laser_power_mW"].astype(float), usable["peak_intensity"].astype(float)
        )[0, 1]
        return float(corr**2)

    def compute_qhi(self):
        """Formula 4 per power pair: Q_HI = 1 - |A_R - A_T| / A_R.

        A_T is taken on the CF-harmonized spectrum (area_harmonized from
        process()), A_R on the identically pre-processed reference (area).
        Both frames are aligned one-row-per-power by _align(), so positional
        pairing is safe.

        Returns:
            tidy DataFrame per power pair; self.qhi_mean / self.qhi_min updated.
        """
        ref, twin = self.reference, self.twinned
        df = pd.DataFrame(
            {
                "laser_power_percent": ref["laser_power_percent"].values,
                "laser_power_mW_ref": ref["laser_power_mW"].values,
                "laser_power_mW_twinned": twin["laser_power_mW"].values,
                "A_ref": ref["area"].values,
                "A_twinned_harmonized": twin["area_harmonized"].values,
            }
        )
        df["Q_HI"] = 1.0 - (df["A_ref"] - df["A_twinned_harmonized"]).abs() / df["A_ref"]
        self.qhi_mean = float(df["Q_HI"].mean())
        self.qhi_min = float(df["Q_HI"].min())
        return df

    def summary_fields(self):
        """Regression/CF/Q_HI scalars for the twinning results table."""
        return {
            "n_powers_fit": len(self.paired_powers),
            "paired_powers": ";".join(str(p) for p in self.paired_powers),
            "unpaired_ref_powers": ";".join(str(p) for p in self.unpaired_ref_powers),
            "unpaired_twin_powers": ";".join(str(p) for p in self.unpaired_twin_powers),
            "intercept_ref": self.linreg_reference[0],
            "slope_ref": self.linreg_reference[1],
            "intercept_twin": self.linreg_twinned[0],
            "slope_twin": self.linreg_twinned[1],
            "r2_ref": self._r2(self.reference),
            "r2_twin": self._r2(self.twinned),
            "CF": self.correction_factor,
            "Q_HI_mean": self.qhi_mean,
            "Q_HI_min": self.qhi_min,
            "verdict": "PASS" if self.qhi_mean is not None and self.qhi_mean > 0.9 else "FAIL",
        }

    def validation_qhi(self, ref_extra, twin_extra, source="spectrum"):
        """Section 6.5 validation at additional laser powers excluded from the fit.

        Multiplies the validation twinned spectra by CF * LP_R/LP_T * t_R/t_T
        (Formulas 1-2) and compares the areas to the reference, as compute_qhi
        does for the fitting powers. Returns an empty frame when either side has
        no validation rows (silent skip, never fails the run).
        """
        columns = ["laser_power_percent", "A_ref", "A_twinned_harmonized", "Q_HI"]
        if ref_extra is None or twin_extra is None:
            return pd.DataFrame(columns=columns)
        if len(ref_extra) == 0 or len(twin_extra) == 0:
            return pd.DataFrame(columns=columns)
        ref = _average_keep_mw(ref_extra, self.grouping_cols)
        twin = _average_keep_mw(twin_extra, self.grouping_cols)
        keys_ref = [_percent_key(v, self.power_tolerance) for v in ref["laser_power_percent"]]
        keys_twin = [_percent_key(v, self.power_tolerance) for v in twin["laser_power_percent"]]
        common = sorted(set(keys_ref) & set(keys_twin))
        if not common:
            return pd.DataFrame(columns=columns)
        # loc/reset_index drop SpectraFrame back to DataFrame (pandas subclass
        # metadata is not propagated) — rewrap so trim/baseline_snip stay available
        ref = SpectraFrame(ref.loc[[k in common for k in keys_ref]].reset_index(drop=True))
        twin = SpectraFrame(twin.loc[[k in common for k in keys_twin]].reset_index(drop=True))

        ref = ref.trim(boundaries=self.boundaries, source=source, target="spe_processed")
        twin = twin.trim(boundaries=self.boundaries, source=source, target="spe_processed")
        # CWA §6.3 order: Formula 1 (power) and Formula 2 (time), then baseline
        for (_, row_reference), (index_twinned, row_twinned) in zip(
            ref.iterrows(), twin.iterrows()
        ):
            twin.at[index_twinned, "spe_processed"] = (
                row_twinned["spe_processed"]
                * (row_reference["laser_power_mW"] / row_twinned["laser_power_mW"])
                * (row_reference["time_ms"] / row_twinned["time_ms"])
            )
        ref.baseline_snip(source="spe_processed", target="spe_processed")
        twin.baseline_snip(source="spe_processed", target="spe_processed")
        ref.spe_area(boundaries=self.boundaries, source="spe_processed", target="area")
        self.process(twin, source="spe_processed", target="spectrum_harmonized")

        df = pd.DataFrame(
            {
                "laser_power_percent": ref["laser_power_percent"].values,
                "A_ref": ref["area"].values,
                "A_twinned_harmonized": twin["area_harmonized"].values,
            }
        )
        df["Q_HI"] = 1.0 - (df["A_ref"] - df["A_twinned_harmonized"]).abs() / df["A_ref"]
        return df

    def _plot(self, ax, **kwargs):
        """Parent 2-panel evaluation figure plus the section 6.5(a) overlay.

        Same as TwinningComponent._plot (twinning.py:213-281) with the
        corrected-points series un-commented: RRB intensity of the twinned
        instrument times CF must lie on the reference regression line.
        """
        A = self.reference
        B = self.twinned
        regression_A = self.linreg_reference
        regression_B = self.linreg_twinned
        ax[0].plot(
            A["laser_power_mW"], A["peak_intensity"], "o", label=A["device_id"].unique()
        )

        A_pred = A["laser_power_mW"] * regression_A[1] + regression_A[0]
        ax[0].plot(
            A["laser_power_mW"],
            A_pred,
            "-",
            label="{:.2e} * LP + {:.2e}".format(regression_A[1], regression_A[0]),
        )

        ax[0].plot(
            B["laser_power_mW"], B["peak_intensity"], "+", label=B["device_id"].unique()
        )

        # section 6.5(a): RRB_RIT x CF vs the RI_R regression line
        ax[0].plot(
            B["laser_power_mW"],
            B["peak_intensity"] * self.correction_factor,
            "+",
            label="{} corrected".format(B["device_id"].unique()),
        )

        B_pred = B["laser_power_mW"] * regression_B[1] + regression_B[0]
        ax[0].plot(
            B["laser_power_mW"],
            B_pred,
            "-",
            label="{:.2e} * LP + {:.2e}".format(regression_B[1], regression_B[0]),
        )

        ax[0].set_ylabel("Peak intensity of the (fitted) peak @ 144cm-1")
        ax[0].set_xlabel("laser power, %")
        ax[0].legend()
        bar_width = 0.2  # Adjust this value to control the width of the groups
        bar_positions = np.arange(len(A["laser_power_percent"].values))
        ax[1].bar(
            bar_positions - bar_width,
            A["area"],
            width=bar_width,
            label=str(A["device_id"].unique()),
        )
        bar_positions = np.arange(len(B["laser_power_percent"].values))
        ax[1].bar(
            bar_positions,
            B["area"],
            width=bar_width,
            label=str(B["device_id"].unique()),
        )
        ax[1].bar(
            bar_positions + bar_width,
            B["area_harmonized"],
            width=bar_width,
            label="{} harmonized CF={:.2e}".format(
                B["device_id"].unique(), self.correction_factor
            ),
        )
        ax[1].set_ylabel("spectrum area")
        ax[1].set_xlabel("laser power, %")
        # Set the x-axis positions and labels
        plt.xticks(bar_positions, B["laser_power_percent"])
        ax[1].legend()
        plt.tight_layout()


def _average_keep_mw(frame, grouping_cols=TWINNING_GROUPING_COLS):
    """Average replicates and restore the laser_power_mW column (dropped by
    SpectraFrame.average when mW is not a grouping column)."""
    mw_table = _mw_table(frame)
    averaged = frame.average(grouping_cols=list(grouping_cols))
    return _attach_mw(averaged, mw_table)