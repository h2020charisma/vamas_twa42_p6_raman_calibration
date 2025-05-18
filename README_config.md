# VAMAS Project 06 – Raman Calibration Data Analysis Pipeline

[Home](README.md) | [Tasks](README_pipeline.md) | [Input Files](README_input.md) 

This repository contains a [Ploomber](https://ploomber.io/)-based analysis pipeline for [VAMAS TWA 42 Project 6](https://www.vamas.org/twa42/documents/2024_vamas_twa42_p6_raman_calibration.pdf).

## ⚙️ Configuration File env.yaml

Defines global runtime parameters:

- Paths: `config_templates`, `config_root`, `config_output`
- Sample categorization tags: `ne_tag`, `pst_tag`, `ti_tags`, etc.
- Matching: `match_mode` = `cluster` or `argmin2d`
- Interpolation: `interpolator` = `pchip`
- Execution flags: `fit_ne_peaks` = `True ` enables Neon peak detection (slower)

These are injected into `pipeline.yaml` using [Ploomber](https://ploomber.io/)’s Jinja-style templating.

## ⚙️ Configuration File config_pipeline.json

Maps datasets to: Metadata template file and data directory

```json
{
    "version": "2",
    "templates": {
        "KEY": {
            "template": "folder/Template Raman Reporting_CHARISMA.xlsx",
            "path": "folder/data/",
            "notes": "Neon_5 is overexposed 1000ms. Neon_7 says not overexposed, but it is  (5000ms)",
            "background" : {
                "skip" : ["CAL_2_OP1.csv","APAP_2_OP1.csv","PST_2_OP1.csv"]
            },
            "units" : {
                "neon" : "nm"
            },
            "find_kw" : {
                "si" :  {"wlen": 10, "width": 1} 
            },            
            "preprocess" : {
                "trim_axes" : {
                    "method": "x-axis",
                    "boundaries": [100, 3400]
                  }
            }            
            "exclude_cols" : ["date", "time", "measurement", "source", "file_name", "notes", "laser_power_percent",  "laser_power_mW", "background"]
            
        }
        ...
    }
}
```

- **Metadata template file**: Defines the structure and expected content of metadata for consistent parsing.
- **Data directory**: Where raw and intermediate data files are stored.
- **Notes**: Provides context on data quality, missing or inconsistent files, and special handling instructions.
- **Excluded metadata columns**: Specifies columns to ignore during analysis to avoid irrelevant or noisy data.
- **Preprocessing actions**: Includes optional data cleaning or transformations, such as axis trimming.
- **Calibration tweaks**: Allows fine-tuning of peak detection parameters to accommodate dataset-specific characteristics.

### 🔑 Role of key in the Pipeline

In the [Ploomber pipeline](README_pipeline.md), the key values defined in the grid section of each task correspond directly to dataset identifiers found in the config_pipeline.json file. These keys (e.g., `0101`, `0401`, etc.) are used to parameterize and parallelize the pipeline over multiple datasets. Here's how this works:

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

### 🔁 Role of exclude_cols in Context
In this pipeline, spectra are grouped to identify and link them with the correct background files. This grouping is based on shared metadata attributes, such as sample ID, optical path, or measurement conditions.

However, some metadata fields (e.g., timestamp, filename, laser power, etc.) vary between measurements even when the underlying condition is the same. Including them would unnecessarily fragment the grouping.

To address this, the pipeline constructs the grouping keys as:
```
groupby_cols = [start_col] + [col for col in df.columns if col not in exclude_cols and col != start_col]
```

#### ✅ What exclude_cols does:
- Ensures consistent grouping of related spectra.
- Prevents over-fragmentation of groups caused by inconsequential differences (e.g., timestamp or file name).
- Supports correct association between BACKGROUND_NOT_SUBTRACTED spectra and BACKGROUND_ONLY files.

#### ❌ What exclude_cols does not do:
- It does not exclude columns from analysis, calibration, or plotting.
- It does not drop the fields from the DataFrame — they're still available for later use.

#### 🔧 Example

Suppose you have the following metadata:

| file\_name       | sample\_id | OP  | background                  | date       | laser\_power\_percent |
| ---------------- | ---------- | --- | --------------------------- | ---------- | --------------------- |
| sample1\_OP1.txt | S1         | OP1 | BACKGROUND\_NOT\_SUBTRACTED | 2024-01-01 | 10                    |
| bg1\_OP1.txt     | S1         | OP1 | BACKGROUND\_ONLY            | 2024-01-01 | 10                    |


You define:

```json
"exclude_cols": ["file_name", "date", "laser_power_percent"]
```

Then the grouping is done using just `sample_id` and `OP`, leading to the correct association of the two rows and enabling assignment of the background file.


This structured setup ensures reproducibility and flexibility when processing diverse datasets within the pipeline.