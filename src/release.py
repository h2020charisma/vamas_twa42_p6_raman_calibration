import os
import shutil
from datetime import datetime
from IPython.display import HTML, display
import pandas as pd


# + tags=["parameters"]
product = None
results_folder = None
release_folder = None
dataset_key = None
# -


def make_release(
    input_folder,
    output_folder,
    only_if_updated=False,
    dataset_key=None,
    exclude_folders=None
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

    allowed_ext = {'.html', '.ipynb', '.pkl', '.xls', '.xlsx', '.xlsm'}
    records = []

    for root, dirs, files in os.walk(input_folder):
        rel_root = os.path.relpath(root, input_folder)

        # Skip excluded folders
        if any(part in exclude_folders for part in rel_root.split(os.sep)):
            continue
        dirs[:] = [d for d in dirs if d not in exclude_folders]

        for file in files:
            _, ext = os.path.splitext(file)
            if ext.lower() not in allowed_ext:
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
                    shutil.copy2(src_path, dest_path)
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


make_release(results_folder, release_folder, only_if_updated=True, dataset_key=dataset_key, exclude_folders=["processed_False_cluster_pchip"])
