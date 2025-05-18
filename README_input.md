# VAMAS Project 06 – Raman Calibration Data Analysis Pipeline

This repository contains a [Ploomber](https://ploomber.io/)-based analysis pipeline for [VAMAS TWA 42 Project 6](https://www.vamas.org/twa42/documents/2024_vamas_twa42_p6_raman_calibration.pdf).

[Back](../README.md) 

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
