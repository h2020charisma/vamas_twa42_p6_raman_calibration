import pandas as pd
from matched_peaks_analysis import (
    analyze_peak_matching_quality,
    compare_before_after_calibration,
    analyze_systematic_vs_random_errors,
    plot_calibration_analysis
)
from IPython.display import display
import matplotlib.pyplot as plt
from utils import (
    toc, toc_anchor, toc_entry, toc_link, toc_heading, toc_collapsible,
    get_config_units, init_logging
    )
import traceback
from pathlib import Path


# + tags=["parameters"]
product = None
upstream = None
exclude = "P6_0301"
context = ""
# -

logger = init_logging(Path(product["nb"]).parent , f"calibration_analysis.log")


toc_heading(f"Calibration analysis","h1")

toc_collapsible("Details", context)

matched_peaks = None
for key in upstream["spectracal_*"].keys():
    matched_peaks_file = upstream["spectracal_*"][key]["matched_peaks"]
    _matched_peaks = pd.read_csv(matched_peaks_file)
    if matched_peaks is None:
        matched_peaks = _matched_peaks
    else:
        matched_peaks = pd.concat([matched_peaks, _matched_peaks])

matched_peaks_file = upstream["calibration_verify_x"]["matched_peaks"]
_matched_peaks = pd.read_csv(matched_peaks_file)
matched_peaks = _matched_peaks if matched_peaks is None else pd.concat([matched_peaks, _matched_peaks])


try:
    # Run matched peak analyses
    mp_filtered = matched_peaks.loc[matched_peaks["key"] != exclude]
    samples = matched_peaks["sample"].unique()
    for sample in samples:
        mp = mp_filtered.loc[mp_filtered["sample"] == sample]
        toc_heading(f"{sample} peak calibration analysis","h2")        
        toc_heading(f"Analyze {sample} peak matching quality","h3")
        summary = analyze_peak_matching_quality(mp)
        toc_collapsible("Table", summary._repr_html_())
        toc_heading(f"Compare {sample} peaks before/after calibration","h3")
        comparison = compare_before_after_calibration(mp)
        toc_collapsible("Table", comparison._repr_html_())
        toc_heading(f"Analyze {sample} peaks systematic vs random errors","h3")
        systematic_analysis = analyze_systematic_vs_random_errors(mp)
        toc_collapsible("Table", systematic_analysis._repr_html_())
        # Visualize
        toc_heading(f"Visualisaiton","h3")
        fig = plot_calibration_analysis(
            mp, product["analysis"])
        plt.show()    
    matched_peaks.to_csv(product["matched_peaks"], index=False)
except Exception as err:
    traceback.print_exc()