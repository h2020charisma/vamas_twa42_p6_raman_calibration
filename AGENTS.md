# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this project is

A [Ploomber](https://ploomber.io/)-based data-analysis pipeline for **VAMAS TWA 42 Project 6**,
implementing the [CWA18133](https://static1.squarespace.com/static/5fabfc06f012f739139f5df2/t/66ebcf55aa76f94840f51f97/1726730081110/cwa18133-1.pdf)
Raman instrument calibration and verification protocols. It ingests raw Raman spectra + Excel
metadata from ~25 participants, performs wavenumber (x) and relative-intensity (y) calibration,
verifies and compares results across providers, and produces HTML/Excel reports.

Core Raman processing lives in the external [ramanchada2](https://github.com/h2020charisma/ramanchada2)
library (see `[tool.uv.sources]` in `pyproject.toml` — it is used as an **editable local dependency**
at `../ramanchada2`).

## Environment & commands

This project uses [`uv`](https://github.com/astral-sh/uv) for dependency and venv management. **Never
activate the venv or call `python`/`pip` directly — always go through `uv run`.**

```sh
uv sync                                  # install/refresh the environment
cd src && uv run ploomber build          # run the full pipeline (from src/)
cd src && uv run ploomber build -e pipeline.demo.yaml   # quick demo run
cd src && uv run ploomber status         # show task status without executing
cd src && uv run ploomber build --dry-run
cd src && uv run ploomber task spectraframe_P6_0101     # run one task
```

- Ploomber commands must be run **from the `src/` directory** (that's where `pipeline.yaml` and
  `env.yaml` live).
- Testing/linting is aspirational: `CONTRIBUTING.md` documents `pytest`, `black`, `flake8`,
  `pre-commit`, but they are marked **WiP / not implemented**. Do not assume a test suite or hooks
  exist. `src/tests/` holds standalone reproduction/stress scripts, **not** a pytest suite.

## Repository layout

- `src/pipeline.yaml` — the Ploomber DAG (source of truth for task wiring, products, params).
  `src/pipeline.demo.yaml` is the reduced demo variant.
- `src/env.yaml` / `src/env_example.yaml` — pipeline config: participant keys, tags, paths, options.
  `env.yaml` is machine-specific; **do not commit real local paths** — `env_example.yaml` shows the
  template with `CHANGEIT` placeholders.
- `src/*.py` pipeline stages (each is a **Ploomber notebook-script**, see below):
  - `overview.py` → participant/data overview report
  - `spectraframe_load.py` → parse metadata + spectra, subtract background, store to `.h5`/`.xlsx`
  - `spectraframe_calibrate.py` → wavenumber (x) calibration
  - `spectraframe_ycalibrate.py` → relative-intensity (y) calibration
  - `calibration_verify.py` → cross-provider comparison, QA reports (grid: `x`, `xy`)
  - `calibration_analysis.py`, `matched_peaks_analysis.py` → post-hoc analysis
  - `spectraframe_tips.py`, `qmatch.py`, `release.py` → twinning, matching QC, release copy
- `src/utils.py` — shared helpers (template/config loading, plotting, TOC/HTML report helpers).
- `src/matchpeaks.py`, `src/qmatch.py`, `src/deepcal.py` — peak-matching / interpolation algorithms.
- `src/config_pipeline_example.json` — the `config_templates` JSON (per-participant template paths,
  units, peak-find/fit kwargs, skip lists). Real one is referenced via `config_templates` in env.
- `README_*.md` — deep-dive docs (`README_pipeline.md`, `README_config.md`, `README_input.md`,
  `README_ploomber.md`, `README_overview.md`, `README_template.md`).

## Working with the pipeline scripts

The `src/*.py` stages are **not plain scripts** — Ploomber executes them as parameterized notebooks
(papermill/ploomber-engine). Key conventions to respect when editing them:

- Each has a parameters cell marked with `# + tags=["parameters"]`, declaring injected globals
  (`product`, `config_root`, `config_templates`, `key`, tag params, …) initialized to `None`.
  Ploomber overwrites these at run time from `pipeline.yaml` `params` + `grid`. Do not remove them.
- They rely on module-level globals and `IPython.display` (`display`, `HTML`, `Markdown`) for report
  output — top-level code with side effects is expected, not a `main()` guard.
- `product` is a dict whose keys match the `product:` block for that task in `pipeline.yaml`
  (e.g. `product["h5"]`, `product["nb"]`). Adding/renaming an output means editing both.
- Grid tasks fan out over participant keys (`{{dataset_key}}` / `{{calibration_key}}`) and modes;
  task names use `[[key]]` / `[[mode]]` placeholders (e.g. `spectracal_[[key]]`).
- Imports like `from utils import ...` work because Ploomber runs with `src/` as the working dir —
  keep that in mind; these are not a package.

## Conventions & gotchas

- Wavenumbers/units in reports use unicode superscripts (see `unicode_unit`, `superscripts` in
  `utils.py`); reference Si peak is `520.45 cm⁻¹`.
- The `processed_{fit_ne_peaks}_{match_mode}_{interpolator}` output-folder pattern encodes the run
  configuration; several products live under it and are keyed off env values.
- Match modes: `match_mode` (e.g. `cluster`); interpolators: `pchip`, `rbf` (see `matchpeaks.py`).
- `pipeline.yaml` currently contains at least one **hardcoded absolute Windows path** in
  `calibration_analysis` (`sample_peaks: C:\\Users\\jelia\\...`). Treat such paths as machine-specific;
  don't propagate them.

## Contribution etiquette (from CONTRIBUTING.md)

- **Never commit to `main` directly.** Use feature branches + pull requests.
- Prefer rebase over merge commits: `git config pull.rebase true`.
- When testing against a local `ramanchada2`, **do not commit** the resulting `pyproject.toml` /
  `uv.lock` changes — `git restore -- pyproject.toml uv.lock` before committing.
- Commit only when asked; when you do, branch off `main` first if on it.
