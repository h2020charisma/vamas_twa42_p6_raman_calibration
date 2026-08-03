import numpy as np
from scipy.interpolate import PchipInterpolator, RBFInterpolator

def model_fit(x, ref, model_name="rbf", extrapolate=False):
    if model_name == "rbf":
        return RBFInterpolator(x[:, None], np.array(ref), kernel="thin_plate_spline", smoothing=1e-3)
    elif model_name == "pchip":
        return PchipInterpolator(x, ref, extrapolate=extrapolate)

def model_predict(model, x, model_name="rbf", extrapolate=False):
    if model_name == "rbf":
        result =  model(x[:, None])
    elif model_name == "pchip":
        result =  model(x)
    return result


def match_peaks_1to1_skip(measured_pixels, ref_wavelengths,
                          measured_intensities=None, ref_intensities=None,
                          gap_penalty=None, k=0.75, tolerance=0.3,
                          alpha=1.0, beta=1.0):
    """
    One-to-one monotonic alignment with optional skipping.

    Match cost = Euclidean distance in (position, intensity) space:
        sqrt( (Δpos)^2 + (Δint)^2 )

    Intensity normalization is automatically handled.
    Strength parameters:
        alpha : scales match cost
        beta  : inflates skip penalties for strong peaks
    """

    mp = np.array(measured_pixels, dtype=float)
    rw = np.array(ref_wavelengths, dtype=float)

    n, m = len(mp), len(rw)

    # ---- position normalization ----
    mp_norm = (mp - mp.min()) / (mp.max() - mp.min()) if n > 1 else np.zeros_like(mp)
    rw_norm = (rw - rw.min()) / (rw.max() - rw.min()) if m > 1 else np.zeros_like(rw)

    # ---- intensity normalization ----
    mi_norm = None
    ri_norm = None
    if measured_intensities is not None:
        mi_norm = np.array(measured_intensities, dtype=float)
        mi_norm = mi_norm / (mi_norm.max() + 1e-12)
    if ref_intensities is not None:
        ri_norm = np.array(ref_intensities, dtype=float)
        ri_norm = ri_norm / (ri_norm.max() + 1e-12)

    # ---- default gap penalty ----
    if gap_penalty is None:
        gap_penalty = k * np.median(np.abs(np.diff(rw_norm))) if m > 1 else k

    # ---- DP table ----
    DP = np.full((n+1, m+1), np.inf)
    DP[0,0] = 0.0

    # ========================= DP LOOP =========================
    for i in range(n+1):
        for j in range(m+1):

            # ----- skip measured -----
            if i > 0:
                gp = gap_penalty
                if mi_norm is not None:
                    gp *= (1 + beta * mi_norm[i-1])
                DP[i,j] = min(DP[i,j], DP[i-1,j] + gp)

            # ----- skip reference -----
            if j > 0:
                gp = gap_penalty
                if ri_norm is not None:
                    gp *= (1 + beta * ri_norm[j-1])
                DP[i,j] = min(DP[i,j], DP[i,j-1] + gp)

            # ----- match (i,j) -----
            if i > 0 and j > 0:

                # Δ position
                dp = mp_norm[i-1] - rw_norm[j-1]

                # Δ intensity if available
                if mi_norm is not None and ri_norm is not None:
                    di = mi_norm[i-1] - ri_norm[j-1]
                else:
                    # fallback to position-only metric
                    di = 0.0

                # Euclidean cost
                cost = np.sqrt(dp*dp + di*di)

                # hard tolerance on position mismatches
                if abs(dp) > tolerance:
                    cost = 1.0

                # scale match cost
                cost *= 1.0 / (1 + alpha)

                DP[i,j] = min(DP[i,j], DP[i-1,j-1] + cost)

    # ========================= BACKTRACK =========================
    i, j = n, m
    pairs = []
    path = []

    while i > 0 or j > 0:

        # attempt match
        if i > 0 and j > 0:
            dp = mp_norm[i-1] - rw_norm[j-1]

            if mi_norm is not None and ri_norm is not None:
                di = mi_norm[i-1] - ri_norm[j-1]
            else:
                di = 0.0

            cost = np.sqrt(dp*dp + di*di)
            if abs(dp) > tolerance:
                cost = 1.0
            cost *= 1.0 / (1 + alpha)

            if DP[i,j] == DP[i-1,j-1] + cost:
                pairs.append((mp[i-1], rw[j-1]))
                path.append((i,j))
                i -= 1
                j -= 1
                continue

        # skip measured
        if i > 0:
            gp = gap_penalty
            if mi_norm is not None:
                gp *= (1 + beta * mi_norm[i-1])
            if DP[i,j] == DP[i-1,j] + gp:
                i -= 1
                continue

        # skip reference
        if j > 0:
            gp = gap_penalty
            if ri_norm is not None:
                gp *= (1 + beta * ri_norm[j-1])
            if DP[i,j] == DP[i,j-1] + gp:
                j -= 1
                continue

    path.append((0,0))
    path = path[::-1]
    pairs.reverse()

    mp_out, rw_out = zip(*pairs) if pairs else ([], [])

    return np.array(mp_out), np.array(rw_out), pairs, DP, path


def match_peaks_position_intensity(measured_pixels, ref_wavelengths,
                                   measured_intensities=None,
                                   k=1.0, alpha=1.0, tolerance=None):
    """
    Match measured peaks to reference peaks:
    - Match cost based on position, slightly favoring strong measured peaks
    - Skip cost depends only on measured intensity
    """
    mp = np.array(measured_pixels, dtype=float)
    rw = np.array(ref_wavelengths, dtype=float)
    n, m = len(mp), len(rw)

    # normalize measured intensity
    if measured_intensities is not None:
        mp_i = np.array(measured_intensities, dtype=float)
        mp_i = mp_i / (mp_i.max() + 1e-12)
    else:
        mp_i = np.ones(n)

    DP = np.full((n+1, m+1), np.inf)
    DP[0,0] = 0.0

    # Fill DP table
    for i in range(n+1):
        for j in range(m+1):
            # Skip measured
            if i > 0:
                DP[i,j] = min(DP[i,j], DP[i-1,j] + k * mp_i[i-1])
            # Skip reference
            if j > 0:
                DP[i,j] = min(DP[i,j], DP[i,j-1])
            # Match
            if i > 0 and j > 0:
                pos_diff = abs(mp[i-1] - rw[j-1])
                if tolerance is None or pos_diff <= tolerance:
                    cost = pos_diff / (1 + alpha * mp_i[i-1])
                else:
                    cost = np.inf
                DP[i,j] = min(DP[i,j], DP[i-1,j-1] + cost)

    # Backtrack
    i, j = n, m
    pairs = []
    path = [(i,j)]
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            pos_diff = abs(mp[i-1] - rw[j-1])
            if tolerance is None or pos_diff <= tolerance:
                cost = pos_diff / (1 + alpha * mp_i[i-1])
            else:
                cost = np.inf
            if DP[i,j] == DP[i-1,j-1] + cost:
                pairs.append((mp[i-1], rw[j-1]))
                i -= 1
                j -= 1
                path.append((i,j))
                continue
        if i > 0 and DP[i,j] == DP[i-1,j] + k * mp_i[i-1]:
            i -= 1
            path.append((i,j))
            continue
        if j > 0 and DP[i,j] == DP[i,j-1]:
            j -= 1
            path.append((i,j))
            continue

    pairs.reverse()
    path = path[::-1]
    mp_out, rw_out = zip(*pairs) if pairs else ([], [])
    return np.array(mp_out), np.array(rw_out), pairs, DP, path


def match_peaks_auto_k(measured_pixels, ref_wavelengths,
                                  measured_intensities=None,
                                  alpha=1.0, tolerance=None):
    """
    Monotonic one-to-one peak alignment with:
    - Match cost based on normalized position, slightly favoring strong measured peaks
    - Skip cost depends only on measured intensity
    - Automatic skip weight k
    - Proper tolerance handling
    """
    mp = np.array(measured_pixels, dtype=float)
    rw = np.array(ref_wavelengths, dtype=float)
    n, m = len(mp), len(rw)

    # Normalize positions to [0,1]
    mp_p = (mp - mp.min()) / (mp.max() - mp.min()) if n > 1 else np.zeros_like(mp)
    rw_p = (rw - rw.min()) / (rw.max() - rw.min()) if m > 1 else np.zeros_like(rw)

    # Normalize measured intensity
    if measured_intensities is not None:
        mp_i = np.array(measured_intensities, dtype=float)
        mp_i = mp_i / (mp_i.max() + 1e-12)
    else:
        mp_i = np.ones(n)

    # Automatic skip weight based on typical normalized step
    if m > 1:
        delta_pos = np.median(np.diff(np.sort(rw_p)))
    else:
        delta_pos = 1.0
    k = delta_pos / 0.5

    # Large cost for out-of-tolerance matches
    large_penalty = 10 * delta_pos

    # DP table
    DP = np.full((n+1, m+1), np.inf)
    DP[0,0] = 0.0

    # Fill DP table
    for i in range(n+1):
        for j in range(m+1):
            # Skip measured
            if i > 0:
                DP[i,j] = min(DP[i,j], DP[i-1,j] + k * mp_i[i-1])
            # Skip reference (free)
            if j > 0:
                DP[i,j] = min(DP[i,j], DP[i,j-1])
            # Match
            if i > 0 and j > 0:
                pos_diff = abs(mp_p[i-1] - rw_p[j-1])
                if tolerance is None or pos_diff <= tolerance:
                    cost = pos_diff / (1 + alpha * mp_i[i-1])
                else:
                    cost = large_penalty
                DP[i,j] = min(DP[i,j], DP[i-1,j-1] + cost)

    # Backtrack
    i, j = n, m
    pairs = []
    path = [(i,j)]
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            pos_diff = abs(mp_p[i-1] - rw_p[j-1])
            if tolerance is None or pos_diff <= tolerance:
                cost = pos_diff / (1 + alpha * mp_i[i-1])
            else:
                cost = large_penalty
            if DP[i,j] == DP[i-1,j-1] + cost:
                pairs.append((mp[i-1], rw[j-1]))
                i -= 1
                j -= 1
                path.append((i,j))
                continue
        if i > 0 and DP[i,j] == DP[i-1,j] + k * mp_i[i-1]:
            i -= 1
            path.append((i,j))
            continue
        if j > 0 and DP[i,j] == DP[i,j-1]:
            j -= 1
            path.append((i,j))
            continue

    pairs.reverse()
    path = path[::-1]
    mp_out, rw_out = zip(*pairs) if pairs else ([], [])
    return np.array(mp_out), np.array(rw_out), pairs, DP, path, k


def match_peaks_ready(measured_pixels, ref_wavelengths,
                      measured_intensities=None,
                      alpha=1.0, gamma=2.0,
                      skip_baseline=0.02, tolerance=None,
                      normalize=False):
    """
    Monotonic one-to-one peak alignment using dynamic programming.

    Aligns measured peaks to reference peaks, allowing skips. 
    Match cost is based on position differences and favors stronger measured peaks nonlinearly.
    Skip cost depends on measured peak intensity plus an optional baseline. Positions can be optionally normalized.

    Parameters
    ----------
    measured_pixels : array_like
        Array of measured peak positions (e.g., pixel indices, wavelengths).
    ref_wavelengths : array_like
        Array of reference peak positions to align to.
    measured_intensities : array_like, optional
        Array of measured peak intensities. Stronger peaks are preferred in matching.
        Defaults to None, in which case all peaks are treated equally.
    alpha : float, optional
        Linear weighting factor for measured peak intensity in match cost. Default is 1.0.
        Set alpha=0 to ignore intensity.
    gamma : float, optional
        Exponent to nonlinearly amplify strong peaks in match cost. Default is 2.0.
    skip_baseline : float, optional
        Small constant added to skip cost for all measured peaks to prevent medium peaks
        from being skipped too cheaply. Default is 0.02.
    tolerance : float, optional
        Maximum allowed normalized position difference for a match. Peaks beyond this
        are penalized. If None, a default based on median reference spacing is used.
    normalize : bool, optional
        If True, positions are normalized to [0,1] for scale-independent computation. 
        Default is False.

    Returns
    -------
    mp_out : ndarray
        Array of measured peaks that were matched to reference peaks.
    rw_out : ndarray
        Array of corresponding matched reference peaks.
    pairs : list of tuples
        List of matched pairs as (measured_peak, reference_peak).
    DP : ndarray
        Dynamic programming table of cumulative costs.
    path : list of tuples
        Backtracked path through the DP table showing the sequence of matches and skips.
    k : float
        Automatically computed skip weight based on reference spacing.

    Notes
    -----
    - The algorithm is monotonic: peaks are matched in order and one-to-one.
    - Match cost favors strong measured peaks via alpha and gamma.
    - Skip cost depends only on measured intensity plus optional baseline.
    - Using normalized positions makes the method scale-independent; set `normalize=True`.
    - Strong measured peaks are more likely to be matched, while weak/noisy peaks can be skipped.
    """
    mp = np.array(measured_pixels, dtype=float)
    rw = np.array(ref_wavelengths, dtype=float)
    n, m = len(mp), len(rw)

    # Normalize positions to [0,1]
    if normalize:
        mp_p = (mp - mp.min()) / (mp.max() - mp.min()) if n > 1 else np.zeros_like(mp)
        rw_p = (rw - rw.min()) / (rw.max() - rw.min()) if m > 1 else np.zeros_like(rw)
    else:
        mp_p = mp
        rw_p = rw
    # Normalize measured intensity
    if measured_intensities is not None:
        mp_i = np.array(measured_intensities, dtype=float)
        mp_i = mp_i / (mp_i.max() + 1e-12)
    else:
        mp_i = np.ones(n)

    # Automatic skip weight based on reference median step
    if m > 1:
        delta_pos = np.median(np.diff(np.sort(rw_p)))
    else:
        delta_pos = 1.0
    k = delta_pos / 0.5

    # Set default tolerance if not provided
    if tolerance is None and m > 1:
        tolerance = delta_pos

    # Large penalty for out-of-tolerance matches
    large_penalty = 10 * delta_pos

    # DP table
    DP = np.full((n+1, m+1), np.inf)
    DP[0,0] = 0.0

    # Fill DP table
    for i in range(n+1):
        for j in range(m+1):
            # Skip measured
            if i > 0:
                DP[i,j] = min(DP[i,j], DP[i-1,j] + k * mp_i[i-1] + skip_baseline)
            # Skip reference (free)
            if j > 0:
                DP[i,j] = min(DP[i,j], DP[i,j-1])
            # Match
            if i > 0 and j > 0:
                pos_diff = abs(mp_p[i-1] - rw_p[j-1])
                if tolerance is None or pos_diff <= tolerance:
                    cost = pos_diff / (1 + alpha * mp_i[i-1])**gamma
                else:
                    cost = large_penalty
                DP[i,j] = min(DP[i,j], DP[i-1,j-1] + cost)

    # Backtrack to get matched pairs
    i, j = n, m
    pairs = []
    path = [(i,j)]
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            pos_diff = abs(mp_p[i-1] - rw_p[j-1])
            if tolerance is None or pos_diff <= tolerance:
                cost = pos_diff / (1 + alpha * mp_i[i-1])**gamma
            else:
                cost = large_penalty
            if DP[i,j] == DP[i-1,j-1] + cost:
                pairs.append((mp[i-1], rw[j-1]))
                i -= 1
                j -= 1
                path.append((i,j))
                continue
        if i > 0 and DP[i,j] == DP[i-1,j] + k * mp_i[i-1] + skip_baseline:
            i -= 1
            path.append((i,j))
            continue
        if j > 0 and DP[i,j] == DP[i,j-1]:
            j -= 1
            path.append((i,j))
            continue

    pairs.reverse()
    path = path[::-1]
    mp_out, rw_out = zip(*pairs) if pairs else ([], [])
    return np.array(mp_out), np.array(rw_out), pairs, DP, path, k
