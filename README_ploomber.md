# How Ploomber manages the pipeline execution

[Home](README.md) | [Tasks](README_pipeline.md) | [Input Files](README_input.md) | [Configuration Files](README_config.md) 

This project uses [Ploomber](https://ploomber.io/), a Python-based pipeline tool, to organize and automate the steps for  [VAMAS TWA 42 Project 6](https://www.vamas.org/twa42/documents/2024_vamas_twa42_p6_raman_calibration.pdf) data analysis. The pipeline is made up of multiple tasks, each corresponding to a specific Python script that performs a step in the workflow (e.g., loading data, calibration, verification).

## pipeline.yaml

In [Ploomber](https://ploomber.io/), the [pipeline.yaml](src/pipeline.yaml) file is the central configuration file that defines the entire data pipeline. It describes what tasks make up the pipeline, how they are connected, what inputs they take, what outputs they produce, and any parameters or settings each task requires.

What pipeline.yaml contains:
- `Metadata` : This section can include general pipeline-level options, such as whether to automatically extract upstream dependencies from the code.
- `Tasks`: The core of the file is the list of tasks. 

For each task, pipeline.yaml specifies:

- `source`: The script or notebook that contains the code to run the task.
- `name`: A unique name for the task; often parameterized to run multiple instances (e.g., "spectraframe_[[key]]").
- `upstream`: Which other tasks this task depends on, establishing the order of execution.
- `product`: The outputs the task creates, often files or notebooks that act as both results and cache markers.
- `params`: Parameters passed to the task for configuration or customization.
- `grid`: A list of parameter sets for batch execution, letting you run the task multiple times with different inputs or keys.

Why pipeline.yaml is important

- It serves as a single source of truth for the entire pipeline setup.
- It makes the pipeline modular and reproducible—you can easily track, modify, and extend steps.
- It enables Ploomber to handle incremental execution by checking if outputs exist and if dependencies have changed.
- It supports parameterization and batching via grids, so you can scale your analyses efficiently.

In short, [pipeline.yaml](src/pipeline.yaml) is like the blueprint or workflow recipe that tells Ploomber what to run, when, with what inputs, and what to produce.

### 🔄 Pipeline grid parameters

#### 🔑 Role of key in the Pipeline

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

#### 🧪 How It Works in the Pipeline

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

### 🔁 Summary

| Key Usage       | Description                                                 |
| --------------- | ----------------------------------------------------------- |
| `grid.key`      | Defines which datasets (by key) to run the task on          |
| `[[key]]`       | Used in task `name` and `product` to generate unique names  |
| Config lookup   | Scripts access dataset-specific settings via `key`          |
| Param injection | Enables running the same script with dataset-specific logic |
| DAG formation   | Ensures correct dependency chaining and reusability         |


### Execution order and dependency graph

By specifying upstream dependencies, the YAML file effectively defines a Directed Acyclic Graph (DAG) of tasks. Ploomber uses this to know which tasks to run first and which depend on the outputs of others.

## Tasks and Products

Each task in [pipeline.yaml](src/pipeline.yaml) is defined by its source script (e.g., [spectraframe_load.py](src/spectraframe_load.py)) and a list of `products`. Products are the output files or artifacts that the task produces, such as Jupyter notebooks (.ipynb), data files (.h5), or Excel spreadsheets (.xlsx). 

These products serve two purposes:

- They store the results of the task.
- They act as cache indicators. If the products already exist and are up to date, Ploomber can skip re-running that task, saving time.

```yaml
tasks:

  - source: spectraframe_load.py
    name: "spectraframe_[[key]]"
    upstream: []
    product: 
      nb: "{{config_output}}/[[key]]/spectraframe_load.ipynb"
      h5: "{{config_output}}/[[key]]/spectraframe_load.h5"
      xlsx: "{{config_output}}/[[key]]/spectraframe_load.xlsx"
    params:
      config_templates: "{{config_templates}}"
      config_root: "{{config_root}}"
    grid:
      key: ["0101","0401","0402","0601","0701","0702","0801","01001","01201","01202"]
```

## Parameters (params)

Tasks can accept parameters that customize their behavior or control inputs. 

For example, calibration tasks use parameters like `fit_neon_peaks` or `match_mode` to adjust how the calibration is done. 

Parameters are often passed from configuration files [env.yaml](src/env_example.yaml) or templates, making the pipeline flexible and easy to adapt without changing code.

```yaml
    params:
      config_templates: "{{config_templates}}"
      config_root: "{{config_root}}"
      fit_neon_peaks: "{{fit_ne_peaks}}"
      match_mode: "{{match_mode}}"
      interpolator: "{{interpolator}}"  
```

## Grid

The grid is a way to run the same task multiple times with different parameter sets or on different data subsets. Here, the key in the grid is a list of dataset identifiers (e.g., "0101", "0701"). For each key, Ploomber will create a separate task instance and corresponding products. This allows batch processing of multiple spectra sets in parallel or sequence.

```yaml
    grid:
      key: ["0101","0401","0402","0601","0701","0702","0801","01001","01201","01202"]
```

## Upstream dependencies

Tasks declare dependencies on other tasks via the upstream field. This forms a directed graph of execution order. For example:

- The spectraframe_calibrate.py tasks depend on the results of all spectraframe_load.py tasks.
- The spectraframe_ycalibrate.py depends on both spectraframe_load.py and spectraframe_calibrate.py.
- The verification step depends on calibration and loading tasks.

Ploomber uses this `dependency graph` to decide what to run, ensuring tasks run in the correct order and only rerun if inputs or upstream results have changed.

```yaml
  - source: spectraframe_calibrate.py
    name: "spectracal_[[key]]"    
    upstream: "spectraframe_*"    
```

## How task execution and caching works in practice

When you run the pipeline, Ploomber checks for the existence and timestamps of each task’s products.

- If the output files exist and none of the upstream tasks have changed since the product was created, Ploomber skips executing that task (cache hit).
- If the products are missing or outdated (due to code changes, parameter changes, or upstream output changes), Ploomber executes the task to update the outputs.

This incremental execution optimizes computation, so only tasks affected by changes are rerun.

In summary, 
- Ploomber uses task definitions with input scripts, output products, parameters, and dependencies to build a graph of steps.
- It then intelligently executes tasks based on this graph and whether their results are up to date, enabling efficient, reproducible pipeline runs. 
- The grid feature allows you to batch process multiple datasets or parameter sets cleanly within the same pipeline definition.

