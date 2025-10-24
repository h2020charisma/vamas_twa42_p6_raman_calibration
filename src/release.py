import os
import shutil

# + tags=["parameters"]
product = None
results_folder = None
release_folder = None
# -


def make_release(input_folder, output_folder):
    """
    Recursively copies .html, .ipynb, .pkl, and Excel files 
    from input_folder to output_folder, preserving directory structure.
    """
    # Define allowed extensions
    allowed_ext = {'.html', '.ipynb', '.pkl', '.xls', '.xlsx', '.xlsm'}

    # Walk through all files and folders
    for root, _, files in os.walk(input_folder):
        for file in files:
            _, ext = os.path.splitext(file)
            if ext.lower() in allowed_ext:
                # Full path to the source file
                src_path = os.path.join(root, file)

                # Compute relative path to preserve folder structure
                rel_path = os.path.relpath(root, input_folder)
                dest_dir = os.path.join(output_folder, rel_path)

                # Create destination directories if needed
                os.makedirs(dest_dir, exist_ok=True)

                # Destination path
                dest_path = os.path.join(dest_dir, file)

                # Copy the file
                shutil.copy2(src_path, dest_path)
                print(f"Copied: {src_path} -> {dest_path}")

    print("\n✅ Release build complete!")


make_release(results_folder, release_folder)
