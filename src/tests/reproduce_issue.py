
import numpy as np
import pandas as pd
from ramanchada2.misc.utils.matchsets import (
    match_peaks_cluster,
    match_peaks_optimized,
    match_peaks_monotonic_simple,
    match_peaks_ready_wrapper,
    match_peaks_hybrid,
    match_peaks_ransac
)
from ramanchada2.misc.utils import find_closest_pairs_idx

def test_matching_methods():
    # Mock reference peaks (Neon)
    ref = {
        585.25: 1.0, 594.48: 0.8, 603.00: 0.5, 609.61: 0.9, 614.31: 0.7,
        626.65: 0.6, 633.44: 1.0, 640.22: 0.8, 650.65: 0.5, 659.89: 0.4
    }
    
    # Simulate Linear Regression: x_spe = scale * x_ref + offset
    scale = 1.02
    offset = 10.0
    spe_pos_dict = {k * scale + offset: v for k, v in ref.items()}
    
    # Add a false peak to make it harder
    spe_pos_dict[600.0] = 0.5 
    
    print(f"Testing with scale={scale}, offset={offset}")
    
    methods = [
        "cluster",
        "argmin2d",
        "assignment",
        "monotonic",
        "dynamicp",
        "hybrid",
        "ransac"
    ]
    
    results = {}
    
    print(f"Testing with offset: {offset}")
    print("-" * 60)
    
    for method in methods:
        print(f"\nTesting method: {method}")
        try:
            x_spe, x_ref = [], []
            
            if method == "cluster":
                x_spe, x_ref, _, _ = match_peaks_cluster(spe_pos_dict, ref)
            
            elif method == "dynamicp":
                 x_spe, x_ref, _, _ = match_peaks_ready_wrapper(
                    spe_pos_dict, ref, 
                    #normalize=False # Dynamicp wraps ready_wrapper which has normalize=True default
                    # We should check if disabling normalization helps or hurts
                )

            elif method == "argmin2d":
                x = np.array(list(spe_pos_dict.keys()))
                y = np.array(list(ref.keys()))
                x_idx, y_idx = find_closest_pairs_idx(x, y)
                x_spe = x[x_idx]
                x_ref = y[y_idx]
                
            elif method == "assignment": # optimized
                # match_peaks_optimized(spe_pos_dict, ref, tolerance=100, relative=False, weight_intensity=0.9)
                x_spe, x_ref, _, _, _ = match_peaks_optimized(
                    spe_pos_dict, ref, tolerance=100, relative=False, weight_intensity=0.9
                )
                
            elif method == "monotonic": # monotonic_simple
                 x_spe, x_ref, _, _ = match_peaks_monotonic_simple(
                    spe_pos_dict, ref, tolerance=100, relative=False, weight_intensity=0.5
                )

            elif method == "hybrid":
                 x_spe, x_ref, _, _, _ = match_peaks_hybrid(spe_pos_dict, ref)

            elif method == "ransac":
                 x_spe, x_ref, _, _, _ = match_peaks_ransac(spe_pos_dict, ref)

            # Evaluate matches
            if len(x_spe) == 0:
                 print("  -> No matches found.")
                 results[method] = 0.0
                 continue

            # Evaluate matches based on the known ground truth model
            # s_expected = r * scale + offset
            # We check if matched 'spe' is close to 'ref' transformed
            
            diffs = x_spe - x_ref

            # Reconstruct expected spe for the matched refs
            expected_spe = x_ref * scale + offset
            residuals = np.abs(x_spe - expected_spe)
            
            correct_matches = np.sum(residuals < 1.0) # 1.0 pixel/unit tolerance
            accuracy = correct_matches / len(ref)
            mean_diff = np.mean(diffs)
            
            print(f"  -> Accuracy: {accuracy:.1%} ({correct_matches}/{len(ref)})")
            print(f"  -> Mean diff: {mean_diff:.4f}")
            print(f"  -> Matches:\n{pd.DataFrame({'spe': x_spe, 'ref': x_ref, 'diff': diffs})}")
            
            results[method] = accuracy
            
        except Exception as e:
            print(f"  -> Error: {e}")
            results[method] = -1.0

    print("\n" + "="*30)
    print("Summary Results (Accuracy):")
    for m, acc in results.items():
        status = "PASS" if acc > 0.9 else "FAIL"
        print(f"{m:<15}: {acc:.1%} [{status}]")

if __name__ == "__main__":
    test_matching_methods()
