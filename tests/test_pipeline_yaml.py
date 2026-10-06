"""Wiring regression tests for src/pipeline.yaml and src/pipeline.demo.yaml — no data, milliseconds. See
docs/nexus_export_plan.md."""
from pathlib import Path

import re
import yaml

PIPELINE_YAML = Path(__file__).resolve().parents[1] / "src" / "pipeline.yaml"
PIPELINE_DEMO_YAML = Path(__file__).resolve().parents[1] / "src" / "pipeline.demo.yaml"


def _load_tasks(path=PIPELINE_YAML):
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return doc["tasks"]


def _find(tasks, name):
    for task in tasks:
        if task.get("name") == name:
            return task
    return None


def test_spectranexus_task_exists_with_expected_upstream():
    tasks = _load_tasks()
    task = _find(tasks, "spectranexus_[[key]]")
    assert task is not None, "spectranexus_[[key]] task missing from pipeline.yaml"
    assert task["source"] == "spectraframe_nexus.py"
    assert set(task["upstream"]) == {"spectraframe_*", "spectracal_*", "spectracaly_*"}
    assert task["grid"]["key"] == "{{calibration_key}}"
    assert "nexus" in task["product"]
    assert "manifest" in task["product"]


def test_release_runs_after_spectranexus():
    tasks = _load_tasks()
    release = next((t for t in tasks if t.get("source") == "release.py"), None)
    assert release is not None, "release.py task missing from pipeline.yaml"
    assert "spectranexus_*" in release["upstream"]


def test_release_runs_after_slides():
    """The deck must exist before release copies it, or the release folder
    silently ships without a presentation."""
    tasks = _load_tasks()
    release = next((t for t in tasks if t.get("source") == "release.py"), None)
    assert release is not None
    assert "slides" in release["upstream"]


def test_pipeline_yaml_is_valid_yaml():
    tasks = _load_tasks()
    assert isinstance(tasks, list)
    assert len(tasks) > 0


def test_slides_task_exists_with_expected_upstream():
    tasks = _load_tasks()
    task = _find(tasks, "slides")
    assert task is not None, "slides task missing from pipeline.yaml"
    assert task["source"] == "slides.py"
    assert set(task["upstream"]) == {
        "calibration_verify_xy", "calibration_analysis",
        "resolution_compare", "spectrares_*", "spectracaly_*",
        "spectraframe_*", "spectracal_*", "overview"}


def test_slides_declares_deck_and_stats_products():
    """The stats CSV is the machine-checkable product: an HTML page can look
    complete after a partial failure, a stats table cannot."""
    task = _find(_load_tasks(), "slides")
    assert set(task["product"]) == {"nb", "deck", "poster", "stats"}
    assert str(task["product"]["deck"]).endswith(".html")
    assert str(task["product"]["poster"]).endswith(".html")
    assert str(task["product"]["stats"]).endswith(".csv")


def test_slides_products_are_run_scoped():
    """Outputs land under processed_<options>/ so alternative run
    configurations produce separate decks instead of overwriting."""
    task = _find(_load_tasks(), "slides")
    stem = "processed_{{fit_ne_peaks}}_{{match_mode}}_{{interpolator}}"
    for key in ("nb", "deck", "poster", "stats"):
        assert stem in str(task["product"][key])


def test_slides_passes_the_run_configuration_into_the_deck():
    task = _find(_load_tasks(), "slides")
    context = task["params"]["context"]
    for placeholder in ("{{match_mode}}", "{{interpolator}}", "{{fit_ne_peaks}}"):
        assert placeholder in context


def test_demo_pipeline_includes_the_resolution_task():
    """The demo is what most people run, so the CWA 18133 sections 3 & 4 curves
    have to be in it. Dropping the task stays invisible: the other tasks still
    pass and the demo report simply has no resolution section."""
    task = _find(_load_tasks(PIPELINE_DEMO_YAML), "spectrares_[[key]]")
    assert task is not None, "spectrares_[[key]] task missing from pipeline.demo.yaml"
    assert task["source"] == "spectraframe_resolution.py"
    # calmodels come from spectracal_*; the raw spectra from spectraframe_*
    assert set(task["upstream"]) == {"spectraframe_*", "spectracal_*"}
    assert task["grid"]["key"] == "{{dataset_key}}"
    assert set(task["product"]) == {"nb", "peaks", "curves", "summary"}


def test_demo_resolution_task_passes_neon_and_calcite_tags():
    """select_spectrum matches on the sample name, so a missing calcite tag
    silently degrades the run to neon-only curves instead of failing."""
    params = _find(_load_tasks(PIPELINE_DEMO_YAML),
                   "spectrares_[[key]]")["params"]
    assert params["neon_tag"] == "{{ne_tag}}"
    assert params["calcite_tag"] == "{{calcite_tag}}"


def test_demo_pipeline_includes_overview():
    """The overview page is the entry point of the report; without it the demo
    drops the reader straight into per-participant products."""
    task = _find(_load_tasks(PIPELINE_DEMO_YAML), "overview")
    assert task is not None, "overview task missing from pipeline.demo.yaml"
    assert task["source"] == "overview.py"
    assert task["upstream"] == []
    assert set(task["product"]) == {"nb", "data"}


def test_demo_pipeline_includes_calibration_analysis():
    task = _find(_load_tasks(PIPELINE_DEMO_YAML), "calibration_analysis")
    assert task is not None, "calibration_analysis missing from pipeline.demo.yaml"
    assert task["source"] == "calibration_analysis.py"
    assert set(task["upstream"]) == {"spectracal_*", "calibration_verify_xy"}
    assert set(task["product"]) == {"nb", "matched_peaks", "analysis"}


def test_demo_spectracal_declares_the_matched_peaks_product():
    """calibration_analysis reads upstream["spectracal_*"][key]["matched_peaks"].
    If the product is not declared upstream, that lookup raises a KeyError with
    nothing pointing at the real cause."""
    task = _find(_load_tasks(PIPELINE_DEMO_YAML), "spectracal_[[key]]")
    assert "matched_peaks" in task["product"]


def test_demo_pipeline_includes_resolution_compare():
    task = _find(_load_tasks(PIPELINE_DEMO_YAML), "resolution_compare")
    assert task is not None, "resolution_compare missing from pipeline.demo.yaml"
    assert task["source"] == "resolution_compare.py"
    assert set(task["upstream"]) == {"spectrares_*"}
    assert set(task["product"]) == {"nb", "summary", "envelope"}


def test_no_task_param_is_an_absolute_machine_path():
    """A param pointing into a developer's own folder pins the run to one
    machine. The calibration_analysis sample_peaks param used to be exactly
    that, and the script never even read it."""
    offenders = []
    for path in (PIPELINE_YAML, PIPELINE_DEMO_YAML):
        for task in _load_tasks(path):
            for name, value in (task.get("params") or {}).items():
                if re.search(r"[A-Za-z]:[\\/]", str(value)):
                    offenders.append(f"{path.name}:{task.get('name')}.{name}")
    assert offenders == []
