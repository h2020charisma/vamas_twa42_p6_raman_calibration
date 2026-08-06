"""Wiring regression tests for src/pipeline.yaml — no data, milliseconds. See
docs/nexus_export_plan.md."""
from pathlib import Path

import yaml

PIPELINE_YAML = Path(__file__).resolve().parents[1] / "src" / "pipeline.yaml"


def _load_tasks():
    with open(PIPELINE_YAML, encoding="utf-8") as f:
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
        "spectraframe_*", "spectracal_*"}


def test_slides_declares_deck_and_stats_products():
    """The stats CSV is the machine-checkable product: an HTML page can look
    complete after a partial failure, a stats table cannot."""
    task = _find(_load_tasks(), "slides")
    assert set(task["product"]) == {"nb", "deck", "stats"}
    assert str(task["product"]["deck"]).endswith(".html")
    assert str(task["product"]["stats"]).endswith(".csv")


def test_slides_products_are_run_scoped():
    """Outputs land under processed_<options>/ so alternative run
    configurations produce separate decks instead of overwriting."""
    task = _find(_load_tasks(), "slides")
    stem = "processed_{{fit_ne_peaks}}_{{match_mode}}_{{interpolator}}"
    for key in ("nb", "deck", "stats"):
        assert stem in str(task["product"][key])


def test_slides_passes_the_run_configuration_into_the_deck():
    task = _find(_load_tasks(), "slides")
    context = task["params"]["context"]
    for placeholder in ("{{match_mode}}", "{{interpolator}}", "{{fit_ne_peaks}}"):
        assert placeholder in context
