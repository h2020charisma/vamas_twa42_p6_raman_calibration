# 📘 Overview: Raman Calibration Pipeline for VAMAS Project 06

This document provides a high-level overview of the Raman data analysis pipeline developed for VAMAS TWA 42 Project 6 (CHARISMA interlaboratory comparison). The pipeline standardizes the calibration and verification of Raman spectra using certified reference materials (e.g., Neon, Silicon) and is implemented as a reproducible Ploomber workflow with domain-specific spectral processing handled by [`ramanchada2`](https://github.com/h2020charisma/ramanchada2).

---

## 🎯 Purpose and Scope

The pipeline enables reproducible:
- Loading and harmonization of Raman spectral data and metadata
- Wavenumber (x-axis) calibration using certified standards (Neon, Silicon)
- Relative intensity calibration (y-axis normalization)
- Generation of verification plots and summary notebooks

It ensures consistent preprocessing across datasets from different instruments and operators, aligned with the [VAMAS TWA 42 Project 6](https://www.vamas.org/twa42/documents/2024_vamas_twa42_p6_raman_calibration.pdf) protocol.

---

## 🧱 Components Overview

| Component       | Description                                                                 |
|----------------|-----------------------------------------------------------------------------|
| **Ploomber**    | Python-native workflow engine; executes and tracks pipeline steps          |
| **ramanchada2** | CHARISMA-developed library for Raman spectrum I/O and processing            |
| **This codebase** | Links metadata to spectra, applies calibration, performs verification     |

---

## 🗂 Configuration and Metadata

The workflow is driven by a combination of structured configuration files and metadata templates:

### `env.yaml` (Runtime Settings)

- Defines global parameters:
  - `config_templates`: JSON file linking dataset templates and folders
  - `config_root`: Root input directory
  - `config_output`: Destination for pipeline outputs
  - Material tags: `ne_tag`, `si_tag`, `pst_tag`, `apap_tag`, `ti_tags`, etc.
  - Algorithm choices: `match_mode`, `interpolator`
  - Feature flags: `fit_ne_peaks = True` enables Neon peak fitting

### `config_pipeline.json` (Dataset Mapping)

- Links each participant’s dataset to:
  - A metadata Excel template
  - A folder of spectral files
  - Units (e.g., nm vs. cm⁻¹)
  - Excluded columns and preprocessing rules
  - Notes on known issues or formatting quirks

### Metadata Template (Excel)

- CHARISMA-standard template (e.g., `Template Raman Reporting_CHARISMA_ILC_final.xlsx`)
- Key sheet: **`Files sheet`**
  - Each row describes a measurement
  - **Column A (`Sample`)**: Contains the material name (e.g., `"Neon"`, `"S0B"`)
    - These are matched to calibration types via `*_tag` settings
  - Other fields: OP, acquisition time, laser power, humidity, etc.

### Spectral Files

- Accepted in any format supported by `ramanchada2`: `.txt`, `.csv`, `.spa`, `.jdx`, `.json`, `.xlsx`, etc.
- Each file must match a record in the metadata file and be located in the configured folder path.

---

## 🔄 Workflow and Logic

The `pipeline.yaml` file defines a sequence of Ploomber tasks:

1. **`spectraframe_load.py`**  
   - Loads metadata and corresponding spectra
   - Tags each spectrum by material type using `*_tag` rules

2. **`spectraframe_calibrate.py`**  
   - Performs x-axis calibration using certified references (e.g., Neon, Silicon)
   - Aligns spectra using interpolation

3. **`spectraframe_ycalibrate.py`** *(optional)*  
   - Applies intensity calibration if configured

4. **`calibration_verify.py`**  
   - Generates figures and metrics to evaluate calibration performance

Each task receives dynamic parameters from `env.yaml`, merged with dataset-specific information from `config_pipeline.json`.

---

## 📓 Ploomber Outputs

Running the pipeline via:

```bash
ploomber build
```

produces:

- ✅ Executed Jupyter notebooks (e.g., spectraframe_load.ipynb)
- 📊 Plots and figures in the output directory
- 📁 CSVs and logs summarizing processed spectra
- 📈 Calibration reports for each dataset

This enables transparent, step-by-step inspection of the workflow and easy reproducibility.

## 🔧 Extending or Customizing

You can extend the workflow by:

- Adding a new dataset to config_pipeline.json
- Defining new sample tags in env.yaml
- Adjusting calibration/interpolation parameters
- Editing task logic in spectraframe_*.py scripts

## 👥 Intended Users

Researchers contributing to CHARISMA’s Raman ILC

Analysts developing standardized processing for Raman data

Developers adapting the pipeline to new instrument formats or materials

## 📚 References

- [VAMAS TWA 42 Project 6 Guidance (PDF)](https://www.vamas.org/twa42/documents/2024_vamas_twa42_p6_raman_calibration.pdf)
- [ramanchada2 on GitHub](https://github.com/h2020charisma/ramanchada2)
- [Ploomber documentation](https://docs.ploomber.io/)