
import numpy as np
import pandas as pd
from ramanchada2.misc.utils.matchsets import match_peaks_monotonic_simple
from ramanchada2.misc.utils import find_closest_pairs_idx

def hybrid_match(spe_pos_dict, ref, tolerance=100):
    # Step 1: Coarse Match (Global)
    # Monotonic simple is robust to large uniform shifts
    x_spe_coarse, x_ref_coarse, _, _ = match_peaks_monotonic_simple(
        spe_pos_dict, ref, tolerance=tolerance, relative=False, weight_intensity=0.5
    )
    
    if len(x_spe_coarse) < 2:
        print("  [Hybrid] Warning: Coarse match failed to find enough points. Fallback to argmin2d raw.")
        # Fallback: Just return argmin2d on original data
        x = np.array(list(spe_pos_dict.keys()))
        y = np.array(list(ref.keys()))
        x_idx, y_idx = find_closest_pairs_idx(x, y)
        return x[x_idx], y[y_idx]

    # Calculate global shift guess
    shift_guess = np.median(x_ref_coarse - x_spe_coarse)
    print(f"  [Hybrid] Detected coarse shift: {shift_guess:.4f}")

    # Step 2: Fine Match (Local)
    # Apply guess to spectrum temporary
    spe_keys = np.array(list(spe_pos_dict.keys()))
    spe_keys_shifted = spe_keys + shift_guess
    ref_keys = np.array(list(ref.keys()))

    # Run argmin2d on the ALIGNED data
    x_idx, y_idx = find_closest_pairs_idx(spe_keys_shifted, ref_keys)
    
    # Get the original (unshifted) values using the indices
    x_spe_fine = spe_keys[x_idx]
    x_ref_fine = ref_keys[y_idx]
    
    return x_spe_fine, x_ref_fine

def run_test():
    # Base Reference (Neon)
    ref = {
        585.25: 1.0, 594.48: 0.8, 603.00: 0.5, 609.61: 0.9, 614.31: 0.7,
        626.65: 0.6, 633.44: 1.0, 640.22: 0.8, 650.65: 0.5, 659.89: 0.4
    }

    # Scenarios
    scenarios = {
        "Small Shift (0.5)": 0.5,
        "Medium Shift (5.0)": 5.0,   # This broke argmin2d before
        "Large Shift (50.0)": 50.0,
        "Negative Shift (-20.0)": -20.0
    }

    print("Testing Hybrid Matching Strategy...")
    print("="*60)

    for name, offset in scenarios.items():
        print(f"\nScenario: {name}")
        spe = {k + offset: v for k, v in ref.items()}
        
        # Run Hybrid
        try:
            x_spe, x_ref = hybrid_match(spe, ref)
            
            diffs = x_spe - x_ref
            accuracy = np.sum(np.isclose(diffs, offset, atol=0.1)) / len(ref)
            
            print(f"  -> Accuracy: {accuracy:.1%}")
            if len(diffs) > 0:
                print(f"  -> Mean diff found: {np.mean(diffs):.4f} (Expected: {offset})")
        except Exception as e:
            print(f"  -> Error: {e}")

if __name__ == "__main__":
    run_test()
