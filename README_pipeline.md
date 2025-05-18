# VAMAS Project 06 – Raman Calibration Data Analysis Pipeline

[Home](README.md) | [Input Files](README_input.md) | [Configuration Files](README_config.md) 

This repository contains a [Ploomber](https://ploomber.io/)-based analysis pipeline for [VAMAS TWA 42 Project 6](https://www.vamas.org/twa42/documents/2024_vamas_twa42_p6_raman_calibration.pdf).



## 🔄 Pipeline Overview

In [Ploomber](https://ploomber.io/), the [pipeline.yaml](src/pipeline.yaml) file is the central configuration file that defines the entire data pipeline. It describes what tasks make up the pipeline, how they are connected, what inputs they take, what outputs they produce, and any parameters or settings each task requires. 

> Background on [pipeline.yaml](README_ploomber.md##-pipeline.yaml).

This [pipeline.yaml](src/pipeline.yaml) has four main steps:

### load (spectraframe_load.py)

- Parses metadata, loads all spectra using ramanchada2, and tags them based on configuration.

### calibrate (spectraframe_calibrate.py)

- Applies spectral calibration (using Neon peaks) and laser zeroing using Si peak

### ycalibrate (spectraframe_ycalibrate.py)

- Performs relative intensity calibration.

### verify (calibration_verify.py)



## 🔄 Pipeline grid parameters

### 🔑 Role of key in the Pipeline

In the [pipeline.yaml](src/pipeline.yaml), the key values defined in the *grid* section of each task correspond directly to dataset identifiers found in the [config_pipeline.json](README_config.md) file. These keys (e.g., `0101`, `0401`, etc.) are used to parameterize and parallelize the pipeline over multiple datasets. Here's how this works:

Each key represents a unique dataset entry defined in the JSON configuration (config_pipeline.json). These entries include:

- A metadata template (Excel file),
- A path to raw data (e.g., .txt, .csv, .spa files),
- Optional notes, unit conventions, columns to exclude, and preprocessing settings.

```json
"0601": {
    "template": "...",
    "path": "...",
    "notes": "Spectra in .spa are in pixels...",
    "exclude_cols": [...],
    "preprocess": {
        "trim_axes": {
            "method": "x-axis",
            "boundaries": [100, 3400]
        }
    }
}
```

### 🧪 How It Works in the Pipeline

In each task with a grid definition, Ploomber dynamically generates parameterized tasks — one per key. These tasks run independently but are linked by dependencies defined via upstream.

Example:

```yaml
  - source: spectraframe_load.py
    name: "spectraframe_[[key]]"
....
    grid:
      key: ["0101", "0601", "0701"]
```

Ploomber expands this into: `spectraframe_0101`, `spectraframe_0601`, `spectraframe_0701`

These tasks then access their respective dataset info from the [configuration json](README_config.md), using the key as a lookup.

```json
{
    "version": "2",
    "templates": {
        "0101": {
            "template": ...,
....
        },
        "0601": {
            "template": ...,
....
        },
        "0701": {
            "template": ...,
....
        },   
    }
}             
```

### 📦 Product Paths

Each task's product (e.g., notebook output, HDF5, Excel) uses the [[key]] placeholder to generate dataset-specific file paths. For example:

```yaml
product: 
  nb: "{{config_output}}/[[key]]/spectraframe_load.ipynb"
```

If key = "0601", the output becomes: ```<config_output>/0601/spectraframe_load.ipynb```

## 🔁 Summary

| Key Usage       | Description                                                 |
| --------------- | ----------------------------------------------------------- |
| `grid.key`      | Defines which datasets (by key) to run the task on          |
| `[[key]]`       | Used in task `name` and `product` to generate unique names  |
| Config lookup   | Scripts access dataset-specific settings via `key`          |
| Param injection | Enables running the same script with dataset-specific logic |
| DAG formation   | Ensures correct dependency chaining and reusability         |
