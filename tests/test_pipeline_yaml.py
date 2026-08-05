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


def test_pipeline_yaml_is_valid_yaml():
    tasks = _load_tasks()
    assert isinstance(tasks, list)
    assert len(tasks) > 0
