import numpy as np
import pandas as pd
from ramanchada2.misc.utils.matchsets import match_peaks_ransac

def test_nonlinear_matching():
    # Mock reference peaks (Neon)
    ref = {
        585.25: 1.0, 594.48: 0.8, 603.00: 0.5, 609.61: 0.9, 614.31: 0.7,
        626.65: 0.6, 633.44: 1.0, 640.22: 0.8, 650.65: 0.5, 659.89: 0.4
    }
    
    # Simulate Quadratic Calibration: spe = ref + A*ref^2 + B*ref + C
    # Let's make it a noticeable curve
    # spe = ref + 0.0005*(ref-600)^2 + 20
    
    spe_pos_dict = {}
    for r, inten in ref.items():
        # Vertex at 600, shift up 20 units
        s = r + 0.002 * (r - 600)**2 + 20.0
        spe_pos_dict[s] = inten
        
    # Add some noise/outliers
    spe_pos_dict[600.0] = 0.2 # Outlier 1
    spe_pos_dict[700.0] = 0.2 # Outlier 2

    print(f"Testing with Quadratic Distortion")
    print("-" * 60)
    
    try:
        x_spe, x_ref, distances, _, df = match_peaks_ransac(spe_pos_dict, ref)
        
        if len(x_spe) == 0:
            print("FAILED: No matches found")
            return

        # Check accuracy
        # The matches should be close to the generated equation
        # expected_spe = ref + 0.002*(ref-600)^2 + 20
        expected_spe = x_ref + 0.002 * (x_ref - 600)**2 + 20.0
        residuals = np.abs(x_spe - expected_spe)
        
        correct = np.sum(residuals < 1.0)
        accuracy = correct / len(ref)
        
        print(f"Accuracy: {accuracy:.1%} ({correct}/{len(ref)})")
        print(f"Residuals mean: {np.mean(residuals):.4f}")
        print(df)
        
        if accuracy >= 0.9:
            print("PASS")
        else:
            print("FAIL")

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_nonlinear_matching()
