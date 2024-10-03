# + tags=["parameters"]
upstream = []
product = None
config_root = None
config_root_output = None
data_folders = None
# -


import os
import glob
from pathlib import Path
import pandas as pd 


def list_files_recursively_except(directory, exclude_extension=[".xlsx",".zip",".json",".cha",".pkl",".h5",".metadata",""]):
    """
    List files recursively in a directory, excluding files with a specific extension.

    Args:
        directory (str): The directory to search.
        exclude_extension (str): The extension to exclude.

    Returns:
        list: A list of file paths.
    """
    files = []
    basename = []
    extension = []
    print(directory)
    pattern = os.path.join(directory, '**', '*.*')
    for file_path in glob.iglob(pattern, recursive=True):
        if os.path.isfile(file_path):
            _base = os.path.basename(file_path)
            _name, _extension = os.path.splitext(_base)
            if _extension in exclude_extension:
                continue            
            files.append(os.path.dirname(file_path))
            basename.append(_name)
            extension.append(_extension)


    return pd.DataFrame({
    'folder': files,
    'basename': basename,
    'extension': extension
    })

Path(product["data"]).mkdir(parents=True, exist_ok=True)

for data_folder in data_folders.split(","):
    print(data_folder)
    df = list_files_recursively_except(os.path.join(config_root,data_folder), [".xlsx",".zip",".json",".cha",".pkl",".h5",".metadata","",".index",".axoprj",".7z"] )
    df.to_excel(os.path.join(product["data"],"Template_{}.xlsx".format(data_folder)),index=False)