"""Integration test: front-sheet instrument metadata (grating, wavelength, make/model)
actually reaches the written NeXus file, through the real chain
nx_meta_from_row -> export_nexus_calibration -> pyambit configure_papp/to_nexus.

Uses the real ramanchada2/pyambit packages (both editable-linked per pyproject.toml), not
mocks, so this catches wiring gaps between VAMAS and the exporter's actual parameter
names -- exactly the class of bug where a value is computed but never passed through.
"""
import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nexus_export import nx_meta_from_row  # noqa: E402


def _entry_path(h5file):
    names = [k for k, v in h5file.items()
            if v.attrs.get("NX_class") in (b"NXentry", "NXentry")]
    assert len(names) == 1, f"expected exactly one NXentry, found {names}"
    return names[0]


@pytest.fixture
def op_data_row():
    """Shaped like utils.read_template's merged FRONT_SHEET_COLUMNS + FILES_SHEET_COLUMNS
    output for one row -- the real column set spectraframe_nexus.py reads op_data.iloc[0]
    from."""
    return pd.Series({
        "sample": "Neon", "optical_path": "OP1", "background": "BACKGROUND_SUBTRACTED",
        "overexposed": "NO", "laser_wl": 785,
        "instrument_make": "TestVendor", "instrument_model": "TestModel-9000",
        "max_laser_power_mW": 100.0, "spectral_range": "100-3500",
        "collection_optics": "50x objective", "slit_size": 100.0,
        "grating": "600 g/mm", "pin_hole_size": float("nan"),
        "collection_fibre_diameter": float("nan"),
    })


def test_grating_reaches_papp_parameters_before_write(op_data_row):
    """Isolates the flattening step (configure_papp + sync_parameters) from the file-
    write step, to pin down whether a lost grating value is a flattening bug or a
    to_nexus writer bug."""
    pytest.importorskip("pyambit")
    from pyambit.nexus_spectra import configure_papp

    meta = nx_meta_from_row(op_data_row)
    assert meta.get("grating") == "600 g/mm"

    papp = None
    from pyambit.nexus_spectra import NXRamanProtocolApplication
    import pyambit.datamodel as mx
    papp = NXRamanProtocolApplication(
        protocol=mx.Protocol(topcategory="P-CHEM",
                             category=mx.EndpointCategory(code="ANALYTICAL_METHODS_SECTION")),
        effects=[])
    configure_papp(
        papp, instrument=("TestVendor", "TestModel-9000"), wavelength=785,
        provider="P6_TEST", sample="calibration", sample_provider="CHARISMA",
        investigation="test", citation=None, prefix="P6_TEST", meta=meta)

    assert "instrument/monochromator/grating/period" in papp.parameters, (
        f"grating not in flattened parameters; keys were: {sorted(papp.parameters)}")

    import nexusformat.nexus.tree as nx
    nx_root = nx.NXroot()
    papp.to_nexus(nx_root)
    entry = next(iter(nx_root.entries.values()))
    assert "monochromator" in entry.get("instrument", {}), (
        f"no monochromator group written; instrument children: "
        f"{list(entry['instrument'].keys()) if 'instrument' in entry else 'no instrument'}")


def test_grating_survives_second_sync_parameters_call(op_data_row):
    """_build_measurement_papp calls papp.sync_parameters() again after configure_papp
    already called it once internally (spe2ambit -> configure_papp -> sync_parameters).
    Isolates whether that REDUNDANT second call is what drops the grating entry."""
    pytest.importorskip("pyambit")
    from pyambit.nexus_spectra import configure_papp, NXRamanProtocolApplication
    import pyambit.datamodel as mx
    import nexusformat.nexus.tree as nx

    meta = nx_meta_from_row(op_data_row)
    papp = NXRamanProtocolApplication(
        protocol=mx.Protocol(topcategory="P-CHEM",
                             category=mx.EndpointCategory(code="ANALYTICAL_METHODS_SECTION")),
        effects=[])
    configure_papp(
        papp, instrument=("TestVendor", "TestModel-9000"), wavelength=785,
        provider="P6_TEST", sample="calibration", sample_provider="CHARISMA",
        investigation="test", citation=None, prefix="P6_TEST", meta=meta)

    before = dict(papp.parameters)
    papp.sync_parameters()  # the extra call _build_measurement_papp makes
    after = dict(papp.parameters)

    assert "instrument/monochromator/grating/period" in before
    assert "instrument/monochromator/grating/period" in after, (
        f"redundant sync_parameters() call dropped it; before had {sorted(before)}, "
        f"after has {sorted(after)}")

    nx_root = nx.NXroot()
    papp.to_nexus(nx_root)
    entry = next(iter(nx_root.entries.values()))
    assert "monochromator" in entry.get("instrument", {})


def test_instrument_membership_check_after_to_nexus(op_data_row):
    """Isolates export_nexus_calibration's own post-processing: it does
    `if "instrument" not in entry: entry["instrument"] = nx.NXinstrument()` to get a
    handle on the instrument group pyambit's to_nexus already created. If that membership
    check is wrong (e.g. "instrument" not in entry is True even though it exists), this
    REPLACES the real NXinstrument (with monochromator/grating already on it) with a
    fresh empty one, silently discarding grating/monochromator right before this
    function's own calibration_x/calibration_y groups get added to it."""
    pytest.importorskip("pyambit")
    from pyambit.nexus_spectra import configure_papp, NXRamanProtocolApplication
    import pyambit.datamodel as mx
    import nexusformat.nexus.tree as nx

    meta = nx_meta_from_row(op_data_row)
    papp = NXRamanProtocolApplication(
        protocol=mx.Protocol(topcategory="P-CHEM",
                             category=mx.EndpointCategory(code="ANALYTICAL_METHODS_SECTION")),
        effects=[])
    configure_papp(
        papp, instrument=("TestVendor", "TestModel-9000"), wavelength=785,
        provider="P6_TEST", sample="calibration", sample_provider="CHARISMA",
        investigation="test", citation=None, prefix="P6_TEST", meta=meta)

    nx_root = nx.NXroot()
    papp.to_nexus(nx_root)
    entry = next(iter(nx_root.entries.values()))

    assert "monochromator" in entry["instrument"], "sanity: present right after to_nexus"

    membership = "instrument" not in entry
    assert not membership, (
        '"instrument" not in entry incorrectly returned True even though the '
        "instrument group exists -- this is exactly the bug that makes "
        "export_nexus_calibration's guard replace the real NXinstrument (with "
        "monochromator/grating already on it) with an empty one")


def test_free_text_grating_falls_back_to_generic_parameters_bucket(op_data_row):
    """A grating description with no leading number (real front-sheet values are often
    free text, e.g. "holographic 1800 gr/mm" or a vendor name, not "600 g/mm") can't
    become NXGrating.period -- that field is numeric-only per NXDL. pyambit's own
    contract is to fall back to the generic /parameters/{key} bucket rather than drop the
    value; this confirms that fallback actually reaches the written file."""
    pytest.importorskip("pyambit")
    from pyambit.nexus_spectra import configure_papp, NXRamanProtocolApplication
    import pyambit.datamodel as mx
    import nexusformat.nexus.tree as nx

    row = op_data_row.copy()
    row["grating"] = "holographic 1800 gr/mm"
    meta = nx_meta_from_row(row)
    assert meta["grating"] == "holographic 1800 gr/mm"

    papp = NXRamanProtocolApplication(
        protocol=mx.Protocol(topcategory="P-CHEM",
                             category=mx.EndpointCategory(code="ANALYTICAL_METHODS_SECTION")),
        effects=[])
    configure_papp(
        papp, instrument=("TestVendor", "TestModel-9000"), wavelength=785,
        provider="P6_TEST", sample="calibration", sample_provider="CHARISMA",
        investigation="test", citation=None, prefix="P6_TEST", meta=meta)

    assert "/parameters/grating" in papp.parameters, (
        f"free-text grating not in the generic fallback bucket either; "
        f"keys: {sorted(papp.parameters)}")

    nx_root = nx.NXroot()
    papp.to_nexus(nx_root)
    entry = next(iter(nx_root.entries.values()))
    assert "parameters" in entry, "generic /parameters bucket group missing from the file"
    assert "grating" in entry["parameters"], (
        f"grating value dropped somewhere between papp.parameters and the written file; "
        f"parameters group has: {list(entry['parameters'].keys())}")
    assert str(entry["parameters"]["grating"].nxvalue) == "holographic 1800 gr/mm"


def test_build_measurement_papp_multi_effect_preserves_grating(op_data_row):
    """Reproduces _build_measurement_papp's actual loop (multiple spe2ambit calls onto a
    growing papp) directly, isolating it from export_nexus_calibration's post-processing,
    to find whether the multi-call loop itself (vs. a single configure_papp call) is what
    drops the grating value."""
    pytest.importorskip("pyambit")
    from ramanchada2.protocols.calibration.serialization import _build_measurement_papp
    import nexusformat.nexus.tree as nx
    import numpy as np

    meta_dict = dict(nx_meta_from_row(op_data_row))
    assert meta_dict.get("grating") == "600 g/mm"

    spe_list = [
        (np.linspace(100, 200, 10), np.random.rand(10), "RAW_DATA", "reference_neon", "cm-1"),
        (np.linspace(100, 200, 10), np.random.rand(10), "X_CALIBRATION",
         "calibration_curve_x", "cm-1"),
    ]
    papp = _build_measurement_papp(
        spe_list, meta=meta_dict, instrument=("TestVendor", "TestModel-9000"),
        wavelength=785, provider="P6_TEST", investigation="test", sample="calibration")
    assert papp is not None

    assert "instrument/monochromator/grating/period" in papp.parameters, (
        f"grating dropped by the multi-call loop; papp.parameters keys: "
        f"{sorted(papp.parameters)}")

    nx_root = nx.NXroot()
    papp.to_nexus(nx_root)
    entry = next(iter(nx_root.entries.values()))
    assert "monochromator" in entry.get("instrument", {}), (
        f"instrument children after multi-effect to_nexus: "
        f"{list(entry['instrument'].keys()) if 'instrument' in entry else 'NO INSTRUMENT'}")


def test_nx_meta_from_row_carries_real_front_sheet_shape(op_data_row):
    """Sanity check on the fixture/helper pairing before testing the full chain."""
    meta = nx_meta_from_row(op_data_row)
    assert meta["instrument_make"] == "TestVendor"
    assert meta["instrument_model"] == "TestModel-9000"
    assert meta["grating"] == "600 g/mm"
    assert meta["laser_wl"] == 785
    assert "pin_hole_size" not in meta  # NaN dropped


def test_wavelength_and_device_reach_the_written_file(op_data_row, tmp_path):
    """The exact chain spectraframe_nexus.py runs: build instrument_meta via
    nx_meta_from_row, then call export_nexus_calibration with wavelength=laser_wl
    (spectraframe_nexus.py's export_one_calibration). Regression guard for the bug where
    wavelength was computed (laser_wl) but never passed to export_nexus_calibration, so
    beam_incident/wavelength was silently absent from every real pipeline output."""
    pytest.importorskip("pyambit")
    from ramanchada2.protocols.calibration.calibration_model import CalibrationModel
    from ramanchada2.protocols.calibration.serialization import export_nexus_calibration
    from ramanchada2.spectrum import from_test_spe
    import ramanchada2.misc.constants as rc2const

    laser_wl = int(op_data_row["laser_wl"])
    kw = dict(provider=["ICV"], device=["BWtek"], OP=["100"], laser_wl=[str(laser_wl)])
    spe_neon = from_test_spe(sample=["Neon"], **kw).trim_axes(
        method="x-axis", boundaries=(100, 3500))
    spe_sil = from_test_spe(sample=["S0B"], **kw).trim_axes(
        method="x-axis", boundaries=(520.45 - 50, 520.45 + 50))
    calmodel = CalibrationModel.calibration_model_factory(
        laser_wl, spe_neon.subtract_baseline_rc1_snip(niter=40),
        spe_sil.subtract_baseline_rc1_snip(niter=40),
        neon_wl=rc2const.NEON_WL[laser_wl], find_kw={"wlen": 200, "width": 1},
        fit_peaks_kw={}, should_fit=False, interpolator_method="poly")

    instrument_meta = nx_meta_from_row(op_data_row)
    out_path = str(tmp_path / "meta_flow.nxs")

    # mirrors spectraframe_nexus.py's export_one_calibration call, including the
    # wavelength=laser_wl argument this test guards
    export_nexus_calibration(
        calmodel, out_path, spectral_range=(100.0, 3500.0), npoints=101,
        metadata={"key": "P6_TEST", "optical_path": "OP1", "laser_wl": laser_wl},
        instrument=instrument_meta,
        wavelength=laser_wl, provider="P6_TEST",
        investigation="VAMAS TWA42 P6 round robin",
        title="P6_TEST 785nm OP1 x/y calibration",
    )

    with h5py.File(out_path, "r") as f:
        entry = _entry_path(f)
        device = f[f"{entry}/instrument/device_information"]
        assert device["vendor"][()].decode() == "TestVendor"
        assert device["model"][()].decode() == "TestModel-9000"

        beam = f[f"{entry}/instrument/beam_incident"]
        assert "wavelength" in beam, (
            "beam_incident/wavelength missing -- wavelength was not threaded through "
            "to export_nexus_calibration (check the wavelength=laser_wl argument in "
            "spectraframe_nexus.py's export_one_calibration)")
        np.testing.assert_allclose(float(beam["wavelength"][()]), float(laser_wl))
        assert beam["wavelength"].attrs.get("unit") in (b"nm", "nm")

        # grating ("600 g/mm") should route through configure_papp's backward-compat
        # table into a typed NXgrating.period Value(loValue=600.0, unit="g/mm"), not
        # silently vanish
        grating_path = f"{entry}/instrument/monochromator/grating/period"
        assert grating_path in f, (
            f"grating value not found at {grating_path} -- check configure_papp's "
            "_BACKWARD_COMPAT_KEYS routing and that 'grating' survives nx_meta_from_row")
        np.testing.assert_allclose(float(f[grating_path][()]), 600.0)
