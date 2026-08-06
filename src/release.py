import os
import shutil
from datetime import datetime
from IPython.display import HTML, display
import pandas as pd


# + tags=["parameters"]
product = None
results_folder = None
release_folder = None
processed_folder = None
dataset_key = None
enable = None
# -


def make_release(
    input_folder,
    output_folder,
    only_if_updated=False,
    dataset_key=None,
    processed_folder=None,
    exclude_folders=None,
    dryrun=True
):
    """
    Recursively copies .html, .ipynb, .pkl, and Excel files from input_folder
    to output_folder, preserving directory structure.

    Groups files based on dataset_key being present anywhere in the relative path.
    Adds a Description column based on filename patterns.
    Skips folders listed in exclude_folders.
    """
    if dataset_key is None:
        dataset_key = []
    if exclude_folders is None:
        exclude_folders = []

    allowed_ext = {'.html', '.ipynb', '.pkl', '.xls', '.xlsx', '.xlsm', '.nxs'}
    # CWA 18133 §8 portable calibration files (calmodel_*_cwa.csv/.json,
    # ycalmodel_*_cwa.csv/.json) and the NeXus export manifest are the
    # language-independent deliverables computed by the pipeline; everything else in
    # .csv/.json (matched_peaks*, resolution_*, config JSON, ...) is diagnostic output,
    # not release material, so the filter is by suffix rather than opening the allowlist
    # to every .csv/.json in the tree.
    # .png is scoped the same way: only the slides deck's own figures/ folder,
    # not the per-participant diagnostic PNGs elsewhere in the tree, which stay
    # release material only via their embedding HTML report.
    released_suffix_ext = {'.csv', '.json', '.png'}
    released_suffixes = ('_cwa.csv', '_cwa.json', 'nexus_manifest.csv',
                        'slides_stats.csv')
    released_path_markers = (f"{os.sep}figures{os.sep}",)
    records = []

    for root, dirs, files in os.walk(input_folder):
        rel_root = os.path.relpath(root, input_folder)
        if rel_root.startswith("processed") and not rel_root.startswith(processed_folder):
            continue
        # Skip excluded folders
        if any(part in exclude_folders for part in rel_root.split(os.sep)):
            continue
        dirs[:] = [d for d in dirs if d not in exclude_folders]

        for file in files:
            _, ext = os.path.splitext(file)
            ext = ext.lower()
            if ext not in allowed_ext:
                by_suffix = ext in released_suffix_ext and file.endswith(released_suffixes)
                by_path = ext == '.png' and any(
                    marker in (root + os.sep) for marker in released_path_markers)
                if not (by_suffix or by_path):
                    continue

            src_path = os.path.join(root, file)
            dest_dir = os.path.join(output_folder, rel_root)
            dest_path = os.path.join(dest_dir, file)
            os.makedirs(dest_dir, exist_ok=True)

            # Copy logic
            copy_status = "Copied"
            if only_if_updated and os.path.exists(dest_path):
                if os.path.getmtime(src_path) <= os.path.getmtime(dest_path):
                    copy_status = "Unchanged"
                else:
                    if dryrun:
                        print(f"Copy {src_path} to {dest_path}")
                    else:
                        shutil.copy2(src_path, dest_path)
            else:
                if dryrun:
                    print(f"Copy {src_path} to {dest_path}")
                else:
                    shutil.copy2(src_path, dest_path)

            # Match dataset key anywhere in relative path
            rel_file_path = os.path.normpath(os.path.join(rel_root, file)).replace("\\", "/")
            matched_key = next((k for k in dataset_key if k in rel_file_path), "Summary")

            # Determine description based on filename prefix
            description = ""
            if file.startswith("spectraframe_"):
                description = "metadata" if file.endswith("xlsx") else "dataset load"
            elif file.startswith("spectracal-"):
                description = "x calibration"
            elif file.startswith("spectracaly-"):
                description = "relative intensity calibration"
            elif file.startswith("calmodel"):
                description = "calibration model"
            elif file.startswith("ycalmodel"):
                description = "relative intensity calibration model"
            elif file.endswith("_calibration.nxs"):
                description = "NeXus calibration bundle (calibrants + reconstructable model)"
            elif file.endswith(".nxs"):
                description = "NeXus spectra"
            elif file == "nexus_manifest.csv":
                description = "NeXus export manifest"
            elif "_cwa" in file:
                description = "CWA 18133 §8 portable calibration"
            elif file == "slides_deck.html":
                description = "presentation deck"
            elif file == "slides_stats.csv":
                description = "presentation deck — quoted statistics"
            elif f"{os.sep}figures{os.sep}" in (root + os.sep):
                description = "presentation deck — figure"
            link = f"<a href='{rel_file_path}' target='_blank'>{file}</a>"

            records.append({
                "Dataset Key": matched_key,
                "Relative Path": rel_root if rel_root != "." else "./",
                "File": link,
                "Status": "✅ Copied" if copy_status == "Copied" else "— Unchanged",
                "Description": description
            })

    # Build DataFrame
    if not records:
        display(HTML("<p><b>No files copied or found matching the allowed extensions.</b></p>"))
        return

    df = pd.DataFrame(records)

    # Sort dataset_key according to input list, "Other" last
    def key_order(k):
        return dataset_key.index(k) if k in dataset_key else len(dataset_key)
    
    df["Dataset Key Order"] = df["Dataset Key"].apply(key_order)
    df = df.sort_values(by=["Dataset Key Order", "Relative Path", "File"])
    df.drop(columns=["Dataset Key Order"], inplace=True)

    # Display timestamp and paths
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = f"""
    <h3>📦 Release Summary</h3>
    <p><b>🕒 Executed:</b> {timestamp}<br>
    """

    grouped_html = ""
    for key, group in df.groupby("Dataset Key"):
        grouped_html += f"<h4>📁 {key}</h4>"
        grouped_html += group[["Relative Path", "File", "Status", "Description"]].to_html(
            escape=False, index=False, border=0, justify="left"
        )

    footer = "<p>✅ Release build complete!</p>"
    display(HTML(header + grouped_html + footer))


make_release(results_folder, release_folder, only_if_updated=True, 
             dataset_key=dataset_key, 
             processed_folder=processed_folder,
             exclude_folders=["processed_False_cluster_pchip"],
             dryrun=not enable)

if enable:
    shutil.copy2(product["nb"], os.path.join(release_folder, "index.html"))