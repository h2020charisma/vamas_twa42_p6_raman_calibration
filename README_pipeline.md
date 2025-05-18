# VAMAS Project 06 – Raman Calibration Data Analysis Pipeline

This repository contains a [Ploomber](https://ploomber.io/)-based analysis pipeline for [VAMAS TWA 42 Project 6](https://www.vamas.org/twa42/documents/2024_vamas_twa42_p6_raman_calibration.pdf).

[Home](README.md) | [Input Files](README_input.md) | [Configuration Files](README_config.md) 

## 🔄 Pipeline Overview

This Ploomber pipeline has four main steps:

### load (spectraframe_load.py)

- Parses metadata, loads all spectra using ramanchada2, and tags them based on configuration.

### calibrate (spectraframe_calibrate.py)

- Applies spectral calibration (using Neon and Silicon peaks) and interpolates to a standard axis.

### ycalibrate (spectraframe_ycalibrate.py)

- Performs intensity calibration or correction (e.g., laser power normalization).

### verify (calibration_verify.py)

- Generates QC plots and summary statistics to validate calibration results.