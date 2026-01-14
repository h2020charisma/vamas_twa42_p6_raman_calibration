import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def analyze_peak_matching_quality(df):
    """
    Analyze quality of peak matching across labs and optical paths.
    
    Args:
        df: DataFrame with columns:
            - spe: detected peak position (nm)
            - reference: matched NIST reference (nm)
            - distances: matching distance (nm)
            - inlier_mask: whether peak was kept as inlier
            - optical_path: instrument configuration
            - laser_wl: laser wavelength
            - key: lab identifier
            - match_mode: matching algorithm used
            - before_after: calibration stage (e.g., 'before', 'after', 'intermediate')
    
    Returns:
        Summary DataFrame
    """
    
    # Calculate errors
    df = df.copy()
    df['error_nm'] = df['spe'] - df['reference']
    df['abs_error_nm'] = np.abs(df['error_nm'])
    
    # Group by lab, optical path, and before/after
    summary_list = []
    
    for (key, optical_path, before_after), group in df.groupby(['key', 'optical_path', 'before_after']):
        # Overall statistics
        inliers = group[group['inlier_mask'] == True]
        
        summary_list.append({
            'lab': key,
            'optical_path': optical_path,
            'before_after': before_after,
            'laser_wl': group['laser_wl'].iloc[0] if 'laser_wl' in group.columns else np.nan,
            'n_peaks_total': len(group),
            'n_peaks_inliers': len(inliers),
            'inlier_ratio': len(inliers) / len(group) if len(group) > 0 else 0,
            
            # Error statistics (all peaks)
            'error_mean': group['error_nm'].mean(),
            'error_std': group['error_nm'].std(),
            'error_abs_mean': group['abs_error_nm'].mean(),
            'error_abs_median': group['abs_error_nm'].median(),
            'error_max': group['abs_error_nm'].max(),
            
            # Error statistics (inliers only)
            'error_mean_inliers': inliers['error_nm'].mean() if len(inliers) > 0 else np.nan,
            'error_std_inliers': inliers['error_nm'].std() if len(inliers) > 0 else np.nan,
            'error_abs_mean_inliers': inliers['abs_error_nm'].mean() if len(inliers) > 0 else np.nan,
        })
    
    summary_df = pd.DataFrame(summary_list)
    
    print("\n" + "="*100)
    print("PEAK MATCHING QUALITY SUMMARY")
    print("="*100)
    
    return summary_df


def compare_before_after_calibration(df):
    """
    Compare peak positions across calibration stages.
    Works with any number of before_after values.
    """
    
    df = df.copy()
    if 'error_nm' not in df.columns:
        df['error_nm'] = df['spe'] - df['reference']
    if 'abs_error_nm' not in df.columns:
        df['abs_error_nm'] = np.abs(df['error_nm'])
    
    print("\n" + "="*100)
    print("CALIBRATION STAGE COMPARISON")
    print("="*100)
    
    # Get all unique stages
    stages = sorted(df['before_after'].unique())
    print(f"Calibration stages found: {stages}")
    
    comparison_list = []
    
    for (key, optical_path), group in df.groupby(['key', 'optical_path']):
        row_data = {
            'lab': key,
            'optical_path': optical_path,
        }
        
        # For each stage, add statistics
        for stage in stages:
            stage_data = group[group['before_after'] == stage]
            stage_inliers = stage_data[stage_data['inlier_mask'] == True]
            
            row_data[f'n_peaks_{stage}'] = len(stage_inliers)
            row_data[f'error_mean_{stage}'] = stage_inliers['error_nm'].mean() if len(stage_inliers) > 0 else np.nan
            row_data[f'error_std_{stage}'] = stage_inliers['error_nm'].std() if len(stage_inliers) > 0 else np.nan
            row_data[f'abs_error_{stage}'] = stage_inliers['abs_error_nm'].mean() if len(stage_inliers) > 0 else np.nan
        
        # Calculate improvements between consecutive stages if there are exactly 2
        if len(stages) == 2:
            stage1, stage2 = stages[0], stages[1]
            abs_err_1 = row_data.get(f'abs_error_{stage1}', np.nan)
            abs_err_2 = row_data.get(f'abs_error_{stage2}', np.nan)
            
            if not np.isnan(abs_err_1) and not np.isnan(abs_err_2) and abs_err_1 > 0:
                row_data['error_improvement'] = abs_err_1 - abs_err_2
                row_data['error_ratio'] = abs_err_2 / abs_err_1
            else:
                row_data['error_improvement'] = np.nan
                row_data['error_ratio'] = np.nan
        
        comparison_list.append(row_data)
    
    comparison_df = pd.DataFrame(comparison_list)
    
    # Overall statistics
    if len(stages) == 2:
        print("\n" + "="*100)
        print("OVERALL CALIBRATION EFFECT")
        print("="*100)
        
        if 'error_improvement' in comparison_df.columns:
            print(f"Average absolute error improvement: {comparison_df['error_improvement'].mean():.4f} nm")
            print(f"Average error ratio (stage2/stage1): {comparison_df['error_ratio'].mean():.3f}")
            
            if comparison_df['error_ratio'].mean() < 1.0:
                print(f"✓ Calibration IMPROVED accuracy on average")
            else:
                print(f"✗ Calibration WORSENED accuracy on average")
    
    return comparison_df


def analyze_systematic_vs_random_errors(df):
    """
    Determine if errors are systematic (consistent across labs) or random.
    Works with any number of before_after values.
    """
    
    df = df.copy()
    if 'error_nm' not in df.columns:
        df['error_nm'] = df['spe'] - df['reference']
    
    print("\n" + "="*100)
    print("SYSTEMATIC vs RANDOM ERROR ANALYSIS")
    print("="*100)
    
    # Calculate mean error per lab/optical_path
    grouped = df[df['inlier_mask'] == True].groupby(['key', 'optical_path', 'before_after'])['error_nm'].agg(['mean', 'std', 'count'])
    
    # Get all unique stages
    stages = df['before_after'].unique()
    
    for stage in sorted(stages):
        if stage not in grouped.index.get_level_values('before_after'):
            continue
            
        subset = grouped.xs(stage, level='before_after')
        
        print(f"\nStage '{stage}':")
        print(f"  Mean error across all labs: {subset['mean'].mean():.4f} nm")
        print(f"  Std dev of mean errors: {subset['mean'].std():.4f} nm")
        print(f"  Within-lab std dev (avg): {subset['std'].mean():.4f} nm")
        
        # Systematic vs random
        between_lab_std = subset['mean'].std()
        within_lab_std = subset['std'].mean()
        
        if between_lab_std < 0.1:
            print(f"  → SYSTEMATIC: All labs have similar mean error (~{subset['mean'].mean():.3f} nm)")
        elif between_lab_std < within_lab_std:
            print(f"  → MOSTLY SYSTEMATIC: Between-lab variation < within-lab variation")
        else:
            print(f"  → RANDOM: Each lab/path has different systematic error")
    
    return grouped


def plot_calibration_analysis(df, output_path='calibration_analysis_comprehensive.png'):
    """
    Comprehensive visualization of calibration quality.
    Works with any number of before_after values.
    """
    
    df = df.copy()
    if 'error_nm' not in df.columns:
        df['error_nm'] = df['spe'] - df['reference']
    if 'abs_error_nm' not in df.columns:
        df['abs_error_nm'] = np.abs(df['error_nm'])
    
    # Only use inliers for cleaner plots
    df_inliers = df[df['inlier_mask'] == True].copy()
    df_inliers['lab_path'] = df_inliers['key'] + '_' + df_inliers['optical_path']
    
    # Get all unique stages
    stages = sorted(df_inliers['before_after'].unique())
    n_stages = len(stages)
    
    # Color palette for stages
    stage_colors = plt.cm.tab10(np.linspace(0, 1, n_stages))
    stage_color_map = {stage: stage_colors[i] for i, stage in enumerate(stages)}
    
    fig = plt.figure(figsize=(18, 18))
    gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
    
    # Plot 1: Error distribution for all stages
    ax1 = fig.add_subplot(gs[0, 0])
    for stage in stages:
        subset = df_inliers[df_inliers['before_after'] == stage]
        if len(subset) > 0:
            ax1.hist(subset['error_nm'], bins=50, alpha=0.5, 
                    label=stage, color=stage_color_map[stage])
    ax1.axvline(0, color='black', linestyle='--', alpha=0.5)
    ax1.set_xlabel('Error (nm)')
    ax1.set_ylabel('Count')
    ax1.set_title('Error Distribution by Stage')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Absolute error by lab and stage
    ax2 = fig.add_subplot(gs[0, 1])
    
    lab_paths = sorted(df_inliers['lab_path'].unique())
    x = np.arange(len(lab_paths))
    width = 0.8 / n_stages  # Divide bar width by number of stages
    
    for i, stage in enumerate(stages):
        stage_data = []
        for lab_path in lab_paths:
            subset = df_inliers[(df_inliers['lab_path'] == lab_path) & 
                               (df_inliers['before_after'] == stage)]
            if len(subset) > 0:
                stage_data.append(subset['abs_error_nm'].mean())
            else:
                stage_data.append(0)
        
        offset = (i - n_stages/2 + 0.5) * width
        ax2.bar(x + offset, stage_data, width, label=stage, 
               alpha=0.8, color=stage_color_map[stage])
    
    ax2.set_xlabel('Lab_OpticalPath')
    ax2.set_ylabel('Mean Absolute Error (nm)')
    ax2.set_title('Calibration Error by Lab/Path')
    ax2.set_xticks(x)
    ax2.set_xticklabels(lab_paths, rotation=45, ha='right')
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis='y')
    
    # Plot 3: Error vs reference wavelength
    ax3 = fig.add_subplot(gs[0, 2])
    markers = ['o', 's', '^', 'D', 'v', '<', '>', 'p', '*', 'h']
    for i, stage in enumerate(stages):
        subset = df_inliers[df_inliers['before_after'] == stage]
        if len(subset) > 0:
            ax3.scatter(subset['reference'], subset['error_nm'], 
                       alpha=0.3, s=20, marker=markers[i % len(markers)], 
                       label=stage, color=stage_color_map[stage])
    ax3.axhline(0, color='black', linestyle='--', alpha=0.5)
    ax3.set_xlabel('Reference Wavelength (nm)')
    ax3.set_ylabel('Error (nm)')
    ax3.set_title('Error vs Wavelength')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Mean error per lab (systematic offset)
    ax4 = fig.add_subplot(gs[1, :])
    
    all_labels_plot = []
    for i, stage in enumerate(stages):
        means = []
        stds = []
        labels_plot = []
        
        for lab_path in sorted(df_inliers['lab_path'].unique()):
            subset = df_inliers[(df_inliers['lab_path'] == lab_path) & 
                               (df_inliers['before_after'] == stage)]
            if len(subset) > 0:
                means.append(subset['error_nm'].mean())
                stds.append(subset['error_nm'].std())
                if i == 0:  # Only collect labels once
                    labels_plot.append(lab_path)
        
        if len(means) > 0:
            x = np.arange(len(means))
            offset = (i - n_stages/2 + 0.5) * 0.15
            
            ax4.errorbar(x + offset, means, yerr=stds, fmt='o', 
                        capsize=5, label=stage, color=stage_color_map[stage], alpha=0.7)
            
            if i == 0:
                all_labels_plot = labels_plot
    
    if len(all_labels_plot) > 0:
        ax4.axhline(0, color='black', linestyle='--', alpha=0.5)
        ax4.set_xlabel('Lab_OpticalPath')
        ax4.set_ylabel('Mean Error ± Std Dev (nm)')
        ax4.set_title('Systematic Error per Lab/Path')
        ax4.set_xticks(np.arange(len(all_labels_plot)))
        ax4.set_xticklabels(all_labels_plot, rotation=45, ha='right')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
    
    # Plot 5: Improvement factor (only if exactly 2 stages)
    ax5 = fig.add_subplot(gs[2, 0])
    if n_stages == 2:
        improvements = []
        labels_imp = []
        
        stage1, stage2 = stages[0], stages[1]
        
        for lab_path in sorted(df_inliers['lab_path'].unique()):
            subset = df_inliers[df_inliers['lab_path'] == lab_path]
            data1 = subset[subset['before_after'] == stage1]['abs_error_nm']
            data2 = subset[subset['before_after'] == stage2]['abs_error_nm']
            
            if len(data1) > 0 and len(data2) > 0:
                improvement = (data1.mean() - data2.mean()) / data1.mean() * 100
                improvements.append(improvement)
                labels_imp.append(lab_path)
        
        if len(improvements) > 0:
            colors_bar = ['green' if x > 0 else 'red' for x in improvements]
            ax5.barh(range(len(improvements)), improvements, color=colors_bar, alpha=0.7)
            ax5.axvline(0, color='black', linestyle='--', alpha=0.5)
            ax5.set_yticks(range(len(labels_imp)))
            ax5.set_yticklabels(labels_imp)
            ax5.set_xlabel('Improvement (%)')
            ax5.set_title(f'Improvement: {stage1} → {stage2}')
            ax5.grid(True, alpha=0.3, axis='x')
    else:
        ax5.text(0.5, 0.5, 'Improvement plot\nonly for 2 stages', 
                ha='center', va='center', transform=ax5.transAxes)
    
    # Plot 6: Peak count comparison
    ax6 = fig.add_subplot(gs[2, 1])
    
    lab_paths = sorted(df_inliers['lab_path'].unique())
    x = np.arange(len(lab_paths))
    width = 0.8 / n_stages
    
    for i, stage in enumerate(stages):
        counts = []
        for lab_path in lab_paths:
            count = len(df_inliers[(df_inliers['lab_path'] == lab_path) & 
                                   (df_inliers['before_after'] == stage)])
            counts.append(count)
        
        offset = (i - n_stages/2 + 0.5) * width
        ax6.bar(x + offset, counts, width, label=stage, 
               alpha=0.8, color=stage_color_map[stage])
    
    ax6.set_xlabel('Lab_OpticalPath')
    ax6.set_ylabel('Number of Peaks')
    ax6.set_title('Peak Count by Stage')
    ax6.set_xticks(x)
    ax6.set_xticklabels(lab_paths, rotation=45, ha='right')
    ax6.legend()
    ax6.grid(True, alpha=0.3, axis='y')
    
    # Plot 7: Stage comparison scatter (only if exactly 2 stages)
    ax7 = fig.add_subplot(gs[2, 2])
    if n_stages == 2:
        stage1, stage2 = stages[0], stages[1]
        
        lab_colors = plt.cm.tab10(np.linspace(0, 1, len(df_inliers['lab_path'].unique())))
        
        for idx, lab_path in enumerate(sorted(df_inliers['lab_path'].unique())):
            subset = df_inliers[df_inliers['lab_path'] == lab_path]
            data1 = subset[subset['before_after'] == stage1]['abs_error_nm'].mean()
            data2 = subset[subset['before_after'] == stage2]['abs_error_nm'].mean()
            
            if not np.isnan(data1) and not np.isnan(data2):
                ax7.scatter(data1, data2, s=100, alpha=0.7, 
                           label=lab_path, color=lab_colors[idx])
        
        # Add diagonal line (no change)
        if len(ax7.collections) > 0:
            max_val = max(ax7.get_xlim()[1], ax7.get_ylim()[1])
            ax7.plot([0, max_val], [0, max_val], 'k--', alpha=0.5, label='No change')
        
        ax7.set_xlabel(f'Mean Abs Error {stage1} (nm)')
        ax7.set_ylabel(f'Mean Abs Error {stage2} (nm)')
        ax7.set_title(f'{stage1} vs {stage2}')
        ax7.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
        ax7.grid(True, alpha=0.3)
    else:
        ax7.text(0.5, 0.5, 'Scatter plot\nonly for 2 stages', 
                ha='center', va='center', transform=ax7.transAxes)
    
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print("\n📊 Saved: calibration_analysis_comprehensive.png")
    
    return fig


# Usage
if __name__ == "__main__":
    # Load your dataframe
    df = pd.read_csv('peak_matches.csv')
    
    # Run analyses
    summary = analyze_peak_matching_quality(df)
    comparison = compare_before_after_calibration(df)
    systematic_analysis = analyze_systematic_vs_random_errors(df)
    
    # Visualize
    fig = plot_calibration_analysis(df)
    
    plt.show()