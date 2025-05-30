# VAMAS Project 06 – Raman Calibration Data Analysis Pipeline

[Home](README.md) | [Input Files](README_input.md) | [Configuration Files](README_config.md) 

This repository contains a [Ploomber](https://ploomber.io/)-based analysis pipeline for [VAMAS TWA 42 Project 6](https://www.vamas.org/twa42/documents/2024_vamas_twa42_p6_raman_calibration.pdf).



## 🔄 Pipeline Overview

In [Ploomber](https://ploomber.io/), the [pipeline.yaml](src/pipeline.yaml) file is the central configuration file that defines the entire data pipeline. It describes what tasks make up the pipeline, how they are connected, what inputs they take, what outputs they produce, and any parameters or settings each task requires. 

> Background on [pipeline.yaml](README_ploomber.md#pipelineyaml).

This [pipeline.yaml](src/pipeline.yaml) has four main steps:

### ⚙️ spectraframe_* (spectraframe_load.py)


Parses metadata, loads all spectra using ramanchada2, and tags them based on configuration.

- Input: Raw spectral files (e.g. .txt, .spa, etc.) and a metadata template per dataset.
- Configuration: Controlled by the "templates" entries in the config_pipeline.json, indexed by key (e.g., "0101").
- Output (product):
    - .ipynb: Processing notebook.
    - .xlsx: Structured metadata + derived information.
    - .h5: Similar to .xlsx, but the spectrum column is a ramanchada2 Spectrum object
- Grid: Runs this task separately for each dataset key (see [configuration file](README_config.md)).


### ⚙️ spectracal_* (spectraframe_calibrate.py)

Applies wavenumber calibration (using Neon peaks) and laser zeroing using Si peak as in [CWA18133](https://static1.squarespace.com/static/5fabfc06f012f739139f5df2/t/66ebcf55aa76f94840f51f97/1726730081110/cwa18133-1.pdf).

- Input: Results from spectraframe_[[key]].
- Upstream: Depends on all `spectraframe_*` tasks.
- Parameters: Includes peak fitting modes (fit_ne_peaks), matching strategies, and interpolation method.
- Output:
    - .ipynb: Notebook showing calibration results.
    - calmodels: Folder with fitted calibration models.
- Grid: Runs this task separately for each dataset key (see [configuration file](README_config.md)).


### ⚙️ spectracaly_* (spectraframe_ycalibrate.py)

⚠️ **Under development**: Not yet used by `calibration_verify`

Performs relative intensity calibration as in [CWA18133](https://static1.squarespace.com/static/5fabfc06f012f739139f5df2/t/66ebcf55aa76f94840f51f97/1726730081110/cwa18133-1.pdf).

- Input: Needs both raw load (spectraframe_[[key]]) and wavelength-calibrated (spectracal_[[key]]) data.
- Output: Notebook showing normalized spectra.
- Grid: Same subset of dataset keys as calibration step.

### ⚙️ calibration_verify (calibration_verify.py)

Purpose: Final QC and validation of calibration steps.

- Input: All spectraframe_* and spectracal_* results.
- Output: One .ipynb with summary statistics, plots, and pass/fail diagnostics.

⏎ Aggregates results to visually and quantitatively check calibration performance across labs.
