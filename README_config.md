# VAMAS Project 06 – Raman Calibration Data Analysis Pipeline

This repository contains a [Ploomber](https://ploomber.io/)-based analysis pipeline for [VAMAS TWA 42 Project 6](https://www.vamas.org/twa42/documents/2024_vamas_twa42_p6_raman_calibration.pdf).

[Home](README.md) | [Tasks](README_pipeline.md) | [Input Files](README_input.md) 

## ⚙️ Configuration Files

### env.yaml

Defines global runtime parameters:

- Paths: `config_templates`, `config_root`, `config_output`
- Sample categorization tags: `ne_tag`, `pst_tag`, `ti_tags`, etc.
- Matching: `match_mode` = `cluster` or `argmin2d`
- Interpolation: `interpolator` = `pchip`
- Execution flags: `fit_ne_peaks` = `True ` enables Neon peak detection (slower)

These are injected into `pipeline.yaml` using [Ploomber](https://ploomber.io/)’s Jinja-style templating.

### config_pipeline.json

Maps datasets to: Metadata template file and data directory

- Notes for interpretation (e.g., missing files, unit anomalies)
- Excluded metadata columns (e.g., laser_power_percent, background)
- Preprocessing actions (e.g., axis trimming)
- Optional calibration tweaks (e.g., windowing for peak-finding)

