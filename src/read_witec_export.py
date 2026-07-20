from pathlib import Path
import os
import numpy as np
from ramanchada2.spectrum import Spectrum
from utils import (
    load_config
)

# + tags=["parameters"]
product = None
config_templates = None
config_root = None
key = None
plot = False
# -


from pathlib import Path
import re
import numpy as np
import ramanchada2 as rc2


def parse_witec_metadata(info_file):
    """
    Parse WITec Information.txt file into a dictionary.
    """

    metadata = {}

    text = Path(info_file).read_text(
        encoding="utf-8",
        errors="ignore"
    )

    for line in text.splitlines():

        if ":" in line:
            key, value = line.split(":", 1)

            key = key.strip()
            value = value.strip()

            # try numeric conversion
            try:
                value_num = float(value)
                metadata[key] = value_num
            except ValueError:
                metadata[key] = value

    return metadata, text


def get_spectral_center(metadata, text):
    """
    Get Raman shift center offset.
    """

    # already provided
    for key in metadata:
        if "Spectral Center" in key:
            return float(metadata[key])

    # fallback: calculate from wavelengths
    laser = None
    center = None

    for key, value in metadata.items():

        if "Excitation Wavelength" in key:
            laser = float(value)

        if "Center Wavelength" in key:
            center = float(value)

    if laser and center:

        return (
            1 / laser -
            1 / center
        ) * 1e7

    raise ValueError(
        "No Raman calibration information found"
    )


def find_info_file(data_file):
    """
    Match:
    ZZZ--Spectrum--YYY--Spec.Data 2.txt
    ->
    ZZZ--Spectrum--YYY--Information.txt
    """

    data_file = Path(data_file)

    info_file = data_file.parent / data_file.name.replace(
        "--Spec.Data 2.txt",
        "--Information.txt"
    )

    if not info_file.exists():
        raise FileNotFoundError(
            f"Missing information file:\n{info_file}"
        )

    return info_file


def read_witec_spectrum(data_file):
    """
    Read WITec ASCII spectrum export.
    """

    lines = Path(data_file).read_text(
        encoding="utf-8",
        errors="ignore"
    ).splitlines()

    start = None

    for i, line in enumerate(lines):
        if line.strip() == "[Data]":
            start = i + 3
            break

    if start is None:
        raise ValueError(
            f"No [Data] section in {data_file}"
        )

    x = []
    y = []

    for line in lines[start:]:

        parts = line.split()

        if len(parts) >= 2:

            try:
                x.append(float(parts[0]))
                y.append(float(parts[1]))

            except ValueError:
                pass

    return np.asarray(x), np.asarray(y)


def convert_witec_to_cha(data_file):

    data_file = Path(data_file)

    # matching metadata file
    info_file = find_info_file(data_file)

    # read spectrum
    x_relative, y = read_witec_spectrum(data_file)
    print(x_relative.min(), x_relative.max())
    # read all metadata
    metadata, raw_metadata = parse_witec_metadata(info_file)

    # WITec exports "rel. 1/cm" already as calibrated Raman shift
    # (instrument software applied the grating calibration before export),
    # so the exported axis is used directly. "Spectral Center" is the Raman
    # shift at the CCD center pixel - informational only, not an offset.
    try:
        spectral_center = get_spectral_center(metadata, raw_metadata)
    except ValueError:
        spectral_center = None

    x = x_relative

    # create ramanchada2 Spectrum
    spectrum = Spectrum(
        x=x,
        y=y,
        metadata={
            "Source file":
                str(data_file),

            "Information file":
                str(info_file),

            "Original axis":
                "rel. 1/cm (calibrated Raman shift)",

            "Converted axis":
                "Raman shift 1/cm",

            "Spectral Center cm-1":
                spectral_center,
            }
    )
    if plot:
        spectrum.plot(label=data_file)
    # write cha
    output = str(data_file.with_suffix(".cha"))
    print(type(output), output)
    Path(data_file.with_suffix(".cha")).unlink(missing_ok=True)
    spectrum.write_cha(output, dataset="/raw")

    return output, spectrum


def convert_witec_folder(root_folder):
    """
    Recursively convert all WITec:
    
    ZZZ--Spectrum--YYY--Spec.Data 2.txt
    
    files into ramanchada2 .cha files.
    
    The matching:
    
    ZZZ--Spectrum--YYY--Information.txt
    
    file is used for metadata and Raman calibration.
    """

    root_folder = Path(root_folder)

    converted = []
    failed = []

    for data_file in root_folder.rglob(
        "*--Spec.Data 2.txt"
    ):

        try:
            cha_file, spectrum = convert_witec_to_cha(
                data_file
            )

            converted.append(cha_file)

            print(
                f"OK: {data_file} -> {cha_file}"
            )

        except Exception as e:

            failed.append(
                (data_file, str(e))
            )

            print(
                f"FAILED: {data_file}\n  {e}"
            )

    print("\nSummary")
    print("Converted:", len(converted))
    print("Failed:", len(failed))

    return converted, failed


_config = load_config(os.path.join(config_root, config_templates))
print(key, _config["templates"].keys())

path = os.path.join(config_root, _config["templates"][key]["path"])
print(path)
convert_witec_folder(path)