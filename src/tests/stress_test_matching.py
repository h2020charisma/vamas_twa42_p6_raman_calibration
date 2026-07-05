
import numpy as np
import pandas as pd
from ramanchada2.misc.utils.matchsets import (
    match_peaks_cluster,
    match_peaks_optimized,
    match_peaks_monotonic_simple,
    match_peaks_ready_wrapper
)

def run_stress_test():
    # Base reference peaks (Neon roughly)
    ref = {
        585.25: 1.0, 594.48: 0.8, 603.00: 0.5, 609.61: 0.9, 614.31: 0.7,
        626.65: 0.6, 633.44: 1.0, 640.22: 0.8, 650.65: 0.5, 659.89: 0.4
    }
    
    scenarios = [
        ("Base Case (Offset=5)", lambda r: {k + 5: v for k, v in r.items()}),
        ("Missing Peaks (Drop 3)", lambda r: {k + 5: v for i, (k, v) in enumerate(r.items()) if i not in [2, 5, 8]}),
        ("Extra Noise Peaks (Add 3)", lambda r: {**{k + 5: v for k, v in r.items()}, **{600.0: 0.2, 620.0: 0.3, 645.0: 0.1}}),
        ("Intensity Distortion (Invert)", lambda r: {k + 5: (1.0 - v + 0.1) for k, v in r.items()}),
        ("Non-linear Distortion (Stretch 1%)", lambda r: {k * 1.01 + 5: v for k, v in r.items()}),
        ("Large Offset (Offset=50)", lambda r: {k + 50: v for k, v in r.items()}),
        ("Peak Swap (Violation)", lambda r: {**{k + 5: v for k, v in r.items() if k not in [603.00, 609.61]}, **{608.0: 0.5, 604.6: 0.9}}), # Swapped order of 603 and 609 approx
    ]

    methods = ["assignment", "monotonic", "dynamicp"]
    
    print(f"{'Scenario':<35} | {'Method':<12} | {'Acc':<6} | {'Status':<6} | {'Details'}")
    print("-" * 100)
    
    for scen_name, scen_func in scenarios:
        spe_pos_dict = scen_func(ref)
        # Sort for consistency
        spe_pos_dict = dict(sorted(spe_pos_dict.items()))
        
        for method in methods:
            try:
                x_spe, x_ref = [], []
                if method == "dynamicp":
                    x_spe, x_ref, _, _ = match_peaks_ready_wrapper(spe_pos_dict, ref)
                elif method == "assignment":
                    x_spe, x_ref, _, _, _ = match_peaks_optimized(spe_pos_dict, ref, tolerance=100, relative=False, weight_intensity=0.9)
                elif method == "monotonic":
                    x_spe, x_ref, _, _ = match_peaks_monotonic_simple(spe_pos_dict, ref, tolerance=100, relative=False, weight_intensity=0.5)

                if len(x_spe) == 0:
                     print(f"{scen_name:<35} | {method:<12} | 0.0%   | FAIL   | No matches")
                     continue

                # Calculate True Positive Accuracy
                # We need to know what the 'true' shift was for each point to judge correctness
                # Warning: this simple 'diff' check assumes roughly constant shift matching the scenario average, 
                # which might fail for non-linear distortion.
                
                diffs = x_spe - x_ref
                median_diff = np.median(diffs)
                
                # Loose check: Majority of matches should have similar shifts
                # For non-linear, diffs drift, so we check smoothness?
                # or just rough accuracy relative to expected keys
                
                # Let's count how many measured peaks were mapped to their GENERATING reference peak
                # This requires knowing the ground truth mapping.
                # For generated dictionary keys, we can try to recover the source.
                
                correct_count = 0
                total_expected = len(spe_pos_dict) 
                # (Note: total_expected is tricky with noise, we just want to see if valid Ref peaks are matched)
                
                # Heuristic: 
                # For Base/Missing/Intensity/LargeOffset: x_spe = x_ref + offset roughly
                # For Non-linear: x_spe = x_ref * 1.01 + 5
                
                is_correct = False
                if "Non-linear" in scen_name:
                     pred_spe = x_ref * 1.01 + 5
                     residuals = np.abs(x_spe - pred_spe)
                     matches = np.sum(residuals < 1.0)
                     acc = matches / len(ref)
                elif "Extra Noise" in scen_name:
                     # We expect 10 matches (original refs), noise ignored
                     # x_spe should be approx x_ref + 5
                     residuals = np.abs((x_spe - x_ref) - 5.0)
                     matches = np.sum(residuals < 0.5)
                     acc = matches / len(ref)
                elif "Large Offset" in scen_name:
                     residuals = np.abs((x_spe - x_ref) - 50.0)
                     matches = np.sum(residuals < 0.5)
                     acc = matches / len(ref)
                else: 
                     # Base, Missing, Intensity
                     residuals = np.abs((x_spe - x_ref) - 5.0)
                     matches = np.sum(residuals < 0.5)
                     # For missing scenario, len(spe) is 7. Acc against 10 refs is max 0.7
                     acc = matches / len(ref)

                status = "PASS" if acc > 0.6 else "FAIL" # Threshold 
                
                print(f"{scen_name:<35} | {method:<12} | {acc:.0%}   | {status:<6} | N={len(x_spe)}, Median Diff={median_diff:.2f}")

            except Exception as e:
                print(f"{scen_name:<35} | {method:<12} | ERR    | ERROR  | {e}")

if __name__ == "__main__":
    run_stress_test()
