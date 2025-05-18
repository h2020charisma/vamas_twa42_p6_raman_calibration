# VAMAS Project 06 – Raman Calibration Data Analysis Pipeline

This repository contains a [Ploomber](https://ploomber.io/)-based analysis pipeline for [VAMAS TWA 42 Project 6](https://www.vamas.org/twa42/documents/2024_vamas_twa42_p6_raman_calibration.pdf).
It implements [CWA18133 Raman instruments calibration and verification protocols](https://static1.squarespace.com/static/5fabfc06f012f739139f5df2/t/66ebcf55aa76f94840f51f97/1726730081110/cwa18133-1.pdf) using open source [ramanchada2](https://pypi.org/project/ramanchada2/) library [doi:10.1002/jrs.6789](https://doi.org/10.1002/jrs.6789).

---

## 📁 Repository Structure

```
src/
└── rc2_rdv/
└── data_analysis/
├── pipeline.yaml # Defines the Ploomber workflow
├── spectraframe_load.py # Loads raw spectra into memory
├── spectraframe_calibrate.py # Applies spectral axis calibration
├── spectraframe_ycalibrate.py # (Optional) intensity calibration
├── calibration_verify.py # Generates verification outputs
```


---

## 📦 Installation

This project uses [Poetry](https://python-poetry.org/) to manage dependencies. To install:

```bash
git clone https://github.com/h2020charisma/rama-rdv.git
cd rama-rdv
poetry install
```

## 🚀 Usage

### Step 1: Set up configuration

Create or modify env.yaml with:

```
config_templates: "config_pipeline.json"
config_root: "path/to/your/data"
config_output: "path/to/output"

fit_ne_peaks: True

ne_tag: "Neon"
si_tag: "S0B"
pst_tag: "PST"
test_tags: "S0N,CAL"
apap_tag: "APAP"
ti_tags: "TiPS_PS,TiPS_Ti"

match_mode: "cluster"
interpolator: "pchip"
```

⚠️ Use paths relevant to your local or server environment. Do not use example paths as-is.

### Step 2: Run pipeline

```
poetry run ploomber build
```

To run a specific task:

```
poetry run ploomber task spectraframe_calibrate
```

Outputs will be saved under the directory specified in `config_output`.

## 📥 Input Files

### Metadata Template

Each dataset is accompanied by an Excel metadata template. The expected format [Template Wizard](https://enanomapper.adma.ai/projects/enanomapper/datatemplates/pchem/index.html?template=CHARISMA_RR)  with a key sheet:

#### `Files sheet`: Lists all spectrum files with metadata.

- Column A: Sample (used for material identification via *_tag)
- Other fields: Acquisition metadata (e.g., OP, power, humidity)

### Spectral Files
Accepted formats: Any format supported by [ramanchada2](https://h2020charisma.github.io/ramanchada2/ramanchada2/spectrum/creators/from_local_file.html#from_local_file), including spc, sp, spa, 0, 1, 2, wdf, ngs, jdx, dx, txt, txtr, tsv, csv, dpt, prn, rruf, spe

Spectra should be listed in the metadata file with matching file names

Units (e.g., nm, cm⁻¹, or pixels) are inferred per dataset from the config_pipeline.json file. Default is cm⁻¹.

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

## 🔄 Pipeline Overview

This Ploomber pipeline has four main steps:

### load (spectraframe_load.py)

- Parses metadata, loads all spectra using ramanchada2, and tags them based on configuration.

### calibrate (spectraframe_calibrate.py)

- Applies spectral calibration (using Neon and Silicon peaks) and interpolates to a standard axis.

### ycalibrate (spectraframe_ycalibrate.py) (optional)

- Performs intensity calibration or correction (e.g., laser power normalization).

### verify (calibration_verify.py)

- Generates QC plots and summary statistics to validate calibration results.

## 🤝 Contributing

- Fork the repo, create a feature branch, and submit a pull request.


## 🔗 References

- [VAMAS TWA 42 Project 6](https://www.vamas.org/twa42/documents/2024_vamas_twa42_p6_raman_calibration.pdf) Project 06
Protocols for Raman instrument calibration and harmonisation of Raman data
- [CWA18133](https://static1.squarespace.com/static/5fabfc06f012f739139f5df2/t/66ebcf55aa76f94840f51f97/1726730081110/cwa18133-1.pdf)  Raman instruments calibration and verification protocols 
- [ramanchada2](https://github.com/h2020charisma/ramanchada2): Raman spectrum I/O and processing tools
- Georgiev, G., Coca-Lopez, N., Lellinger, D., Iliev, L., Marinov, E., Tsoneva, S., Kochev, N., Bañares, M. A., Portela, R. and Jeliazkova, N. (2025), Open Source for Raman Spectroscopy Data Harmonization. J Raman Spectrosc. https://doi.org/10.1002/jrs.6789
- [Ploomber](https://ploomber.io/): Python-native workflow orchestrator

## Acknowledgements

 This project has received funding from the European Union’s Horizon 2020 research and innovation program under grant agreement No. 952921.
 
This work is part of the CHARISMA project and aligned with the VAMAS international metrology initiative.

