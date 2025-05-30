## 📘 Metadata Template – Sheet-by-Sheet Explanation

The CHARISMA Raman ILC metadata template is an Excel workbook that provides structured annotations for interlaboratory Raman measurements. It connects metadata to physical spectral files, defines Optical Paths (OPs), enforces consistent terminology, and supports reproducible analysis.

The pipeline parses `Front sheet` and the `Files` sheet.

---

### 🧭 Front Sheet: Optical Path Configuration ✅ *(required and parsed)*

This sheet defines instruments and **Optical Paths (OPs)** used in measurements

This sheet typically includes the following columns: 

| Column                | Description                                                                 |
|------------------------|-----------------------------------------------------------------------------|
| `OP`                  | The Optical Path identifier (e.g., `OP1`, `OP2`) used in the `Files` sheet  |
| `Objective`, `Filter`, `Grating`, etc. | Descriptive parameters defining the OP configuration         |
| Notes (optional)       | Free-text remarks, such as calibration comments, anomalies, or mapping to instruments |

- Each row corresponds to an OP identifier (e.g., `OP1`, `OP2`, `OP3`). Calibration is done for each optical path
- The pipeline **parses this sheet** to understand the measurement conditions associated with each `OP`.
steps.


---

### 🗂 Sheet: `Files sheet` ✅ *(required and parsed)*

This is the **core metadata sheet**, listing one row per spectrum. It provides:

| Column             | Description                                                                 |
|--------------------|-----------------------------------------------------------------------------|
| `Sample`           | Material identifier (e.g., `Neon`, `S0B`, `PST`, `APAP`, `TiPS`, etc.). Used to categorize spectra via `*_tag` parameters in `env.yaml`. |
| `File name`        | Name of the physical spectrum file (must exist in the corresponding directory). |
| `OP`               | Optical Path label — must match a defined and enabled OP from the front sheet. |
| Other metadata     | Laser power, integration time, humidity, etc.  |

**Usage in pipeline:**
- File names are matched to actual spectrum files using directory paths from `config_pipeline.json`.
- Sample names are tagged using *_tags defined in `env.yaml`.


---

### Samples

Explain

---


## 🧩 Summary of Sheet Roles

| Sheet       | Required | Parsed by Pipeline | Purpose                                             |
|-------------|----------|--------------------|-----------------------------------------------------|
| `Front Sheet` | ✅ Yes | ✅ Yes           | Defines  Optical Paths (`OP1`, `OP2`, etc.) |
| `Files sheet`     | ✅ Yes   | ✅ Yes             | Connects spectra to metadata; drives pipeline processing |


---
