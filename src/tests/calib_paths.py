"""Resolve pipeline paths from src/env.yaml so test/validation scripts stay portable.

No absolute paths are hardcoded in the test scripts; everything is read from the same
``env.yaml`` the Ploomber pipeline uses (``config_root``, ``config_output``, and the
``fit_ne_peaks`` / ``match_mode`` / ``interpolator`` triplet that names the processed folder).
"""
import os

import yaml

_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../src


def load_env(env_path=None):
    with open(env_path or os.path.join(_SRC, "env.yaml")) as f:
        return yaml.safe_load(f)


def config_root(env=None):
    return (env or load_env())["config_root"]


def config_output(env=None):
    return (env or load_env())["config_output"]


def config_templates(env=None):
    return (env or load_env()).get("config_templates", "config_pipeline.json")


def processed_dir(env=None):
    env = env or load_env()
    name = f"processed_{env['fit_ne_peaks']}_{env['match_mode']}_{env['interpolator']}"
    return os.path.join(env["config_output"], name)
