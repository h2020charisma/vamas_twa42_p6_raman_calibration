"""HTML rendering of the ICORS poster: one portrait page, same numbers and
figures as the deck (`slides_render.py`), sized for the ICORS 2026 poster
board (portrait, max 70 cm wide x 90 cm high — not A0).

Kept as a separate module rather than another branch inside
`slides_render.py`: the deck is a sequence of independent slides and the
poster is one continuously-flowing page, so the two have little structural
code in common beyond the design tokens and a few formatting helpers, which
are imported rather than duplicated.
"""
from __future__ import annotations

import math
import time

import numpy as np

from slides_content import (
    MATERIAL_LABELS,
    SAMPLE_STAGES,
    _esc,
    fmt,
    fmt_pct,
    pct_change,
)
from slides_render import CITATION, LINKS, STYLE, _num, _stage_label

POSTER_STYLE = """
.poster { max-width: 1000px; margin: 0 auto; padding: 2.2rem 2.4rem 3rem;
  font-family: 'Charter', 'Iowan Old Style', Georgia, serif; }
.poster-head { border-bottom: 3px solid var(--ink); padding-bottom: 1rem;
  margin-bottom: 1.6rem; }
.poster-head .eyebrow { font-family: ui-monospace, monospace; font-size: 0.72rem;
  letter-spacing: 0.14em; text-transform: uppercase; color: var(--red);
  margin-bottom: 0.5rem; }
.poster-head h1 { font-family: ui-monospace, monospace; font-weight: 600;
  font-size: 1.9rem; line-height: 1.15; text-wrap: balance; margin: 0 0 0.8rem; }
.poster-authors { font-size: 0.95rem; line-height: 1.5; margin: 0 0 0.4rem; }
.poster-affil { font-size: 0.74rem; color: var(--muted); line-height: 1.5; }
.poster-section { margin-bottom: 1.6rem; }
.poster-section > h2 { font-family: ui-monospace, monospace; font-weight: 600;
  font-size: 1.05rem; text-transform: uppercase; letter-spacing: 0.03em;
  border-bottom: 1px solid var(--rule); padding-bottom: 0.35rem;
  margin: 0 0 0.8rem; color: var(--teal); }
.poster-cols-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.4rem; }
.poster-cols-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.2rem; }
.poster p { font-size: 0.88rem; line-height: 1.5; margin: 0 0 0.6rem; }
.poster .stat-row { display: flex; gap: 1.6rem; flex-wrap: wrap;
  margin: 0.4rem 0 0.8rem; }
.poster-footer { border-top: 1px solid var(--rule); margin-top: 1.4rem;
  padding-top: 0.8rem; font-family: ui-monospace, monospace; font-size: 0.68rem;
  color: var(--muted); line-height: 1.5; }
.poster figure { max-width: 620px; margin: 0 auto; }
.poster figure.compact { max-width: 420px; }
.poster figure img { width: 100%; height: auto; max-height: 340px;
  object-fit: contain; }
.poster-app { display: grid; grid-template-columns: 1fr 260px; gap: 1.4rem;
  align-items: start; margin-top: 0.8rem; }
.poster-app .url-badge { display: inline-block; font-family: ui-monospace, monospace;
  font-size: 0.92rem; font-weight: 600; color: var(--paper); background: var(--teal);
  padding: 0.35rem 0.7rem; border-radius: 3px; margin: 0.3rem 0 0.6rem; }
.poster-split-narrow { display: grid; grid-template-columns: 1fr 340px;
  gap: 1.2rem; align-items: start; }
table.poster-mini { font-size: 0.72rem; }
table.poster-mini th, table.poster-mini td { padding: 0.25rem 0.4rem; }
/* Sized for the ICORS 2026 poster board: portrait, max 70 x 90 cm. */
@page { size: 700mm 900mm; margin: 12mm; }
@media print {
  .poster { max-width: none; padding: 0; width: 700mm; }
  .poster-section { break-inside: avoid; }
}
"""


def _figure(src, caption, cache_bust="", compact=False):
    if not src:
        return f'<p class="muted">{_esc(caption)}</p>'
    cls = ' class="compact"' if compact else ""
    return (f'<figure{cls}><img src="figures/{_esc(src)}{cache_bust}" '
            f'alt="{_esc(caption)}"><figcaption>{caption}</figcaption></figure>')


def _head(title, authors, affiliations, ctx):
    return f"""
<div class="poster-head">
  <div class="eyebrow">VAMAS TWA42 &middot; Project 6 &middot; ICORS 2026</div>
  <h1>{_esc(title)}</h1>
  <p class="poster-authors">{authors}</p>
  <p class="poster-affil">{affiliations}</p>
</div>"""


def _intro_section(ctx):
    part = ctx.get("participation") or {}
    total = part.get("total_labs")
    excluded = part.get("excluded") or []
    excluded_txt = (
        f" A further {part.get('n_excluded', 0)} submitted datasets could not "
        f"be calibrated for lack of a required reference measurement "
        f"({', '.join(excluded)})." if excluded else "")
    return f"""
<div class="poster-section">
  <h2>Study</h2>
  <p>The rapid diversification of Raman instruments has increased the need for
  calibration procedures that support reliable comparison of spectra acquired
  using different systems. VAMAS TWA 42 Project 06, &ldquo;Protocols for Raman
  instrument calibration and harmonisation of Raman data&rdquo;, addresses this
  through an interlaboratory comparison (ILC){f' of approximately {total} laboratories worldwide' if total else ''}.
  The study evaluates procedures for Raman-shift and relative intensity
  calibration, spectral resolution verification, and harmonisation of
  measurements from different instrument configurations.</p>
  <p>We present an open-source, reproducible workflow built around the
  <span class="mono">ramanchada2</span> Python library ({CITATION}
  &mdash; doi.org/10.1002/jrs.6789), applied to <b>{ctx['n_keys']}</b> ILC
  datasets that provided sufficiently complete reference measurements to be
  calibrated, covering <b>{ctx['n_paths']}</b> optical configurations at
  {ctx['lasers']}&nbsp;nm excitation.{excluded_txt}</p>
</div>"""


def _app_section(fig, caption, cache_bust):
    shot = (_figure(fig, caption, cache_bust, compact=True) if fig else
            '<p class="muted">screenshot not available</p>')
    return f"""
<div class="poster-section">
  <h2>Software &mdash; one open library, two interfaces</h2>
  <p>All processing is implemented once in the open-source
  <span class="mono">ramanchada2</span> Python library
  ({_esc(_url_text(LINKS['ramanchada2']))}): vendor-format readers, peak
  finding and fitting, neon-to-NIST line matching, interpolation,
  laser-zeroing and resolution calculations. Two applications use it without
  reimplementing any of it, so a correction to the library propagates to both
  and results are directly comparable between them.</p>
  <div class="poster-app">
    <div>
      <div class="card">
        <h3>Analysis pipeline</h3>
        <p>Batch workflow processing the complete ILC, one task chain per
        laboratory. Produced every result on this poster. Source:
        {_esc(_url_text(LINKS['pipeline']))}</p>
        <div class="url-badge">https://github.com/h2020charisma/vamas_twa42_p6_raman_calibration</div>
      </div>
      <div class="card" style="margin-top:0.7rem">
        <h3>SpectraStream</h3>
        <p>Interactive web application for a single spectrum: file
        conversion, calibration, verification and export &mdash; the same
        engine, outside the batch pipeline. Source:
        {_esc(_url_text(LINKS['spectrastream']))}</p>
        <div class="url-badge">spectra.adma.ai/stream</div>
      </div>
    </div>
    {shot}
  </div>
</div>"""


def _method_section(ctx):
    return f"""
<div class="poster-section">
  <h2>Method &mdash; CWA 18133:2024 ({_esc(_url_text(LINKS['cwa']))}),
  VAMAS TWA 42 ({_esc(_url_text(LINKS['vamas']))})</h2>
  <div class="poster-cols-2">
    <div>
      <p><b>Wavenumber calibration.</b> Neon emission lines are located and
      assigned to NIST reference lines (assignment method
      <span class="mono">{_esc(ctx['match_mode'])}</span>), and an interpolating
      function (<span class="mono">{_esc(ctx['interpolator'])}</span>) fitted
      through the assigned pairs gives the wavelength scale. The silicon band at
      520.45&nbsp;cm<sup>&minus;1</sup> &mdash; a reliably reproducible reference
      value (Itoh &amp; Shirono 2020, J. Raman Spectrosc. 51: 2496&ndash;2504
      &mdash; doi.org/10.1002/jrs.6003) &mdash; fixes the Raman-shift origin,
      since the effective laser wavelength differs from its nominal value.
      Beyond the neon line range the edge correction is held at constant
      offset rather than extrapolated, which would diverge in the C&ndash;H
      stretching region.</p>
    </div>
    <div>
      <p><b>Relative intensity calibration.</b> A broadband reference (NIST-SRM
      fluorescent glass or certified LED) measured on the calibrated wavenumber
      scale is compared with its known response to obtain a wavelength-dependent
      correction factor, restricted to the reference's validity range.</p>
      <p><b>Resolution.</b> Spectral resolution (ASTM E2529) is obtained from
      neon line FWHM against position, scaled by the calcite band width near
      1085.9&nbsp;cm<sup>&minus;1</sup>, and checked against the CWA 18133
      acceptance boundary.</p>
    </div>
  </div>
</div>"""


def _neon_table(ne):
    per_laser = ne.loc[ne["laser_wl"] != "all"]
    rows = []
    for _, r in per_laser.iterrows():
        rows.append(
            f"<tr><td>{_esc(r['laser_wl'])} nm</td>"
            f"<td>{_esc(_stage_label(r['stage']))}</td>"
            f"<td>{int(r['n'])}</td>{_num(r['median'], 3)}{_num(r['sd'], 3)}"
            f"<td>{int(r['outliers'])}</td></tr>")
    if not rows:
        return ""
    return (
        '<div class="table-wrap"><table class="data poster-mini"><thead><tr>'
        '<th>&lambda;</th><th>stage</th><th>n</th><th>median</th><th>SD</th>'
        '<th>&gt;1 nm</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>")


def _result1_section(ne, fig, caption, cache_bust):
    all_rows = ne.loc[ne["laser_wl"] == "all"].set_index("stage")
    before = all_rows.loc["1.original"] if "1.original" in all_rows.index else None
    after = all_rows.loc["2.Ne_clbr"] if "2.Ne_clbr" in all_rows.index else None
    factor = (before["median"] / after["median"]
              if before is not None and after is not None and after["median"]
              else math.nan)
    stat = (f"<div class=\"stat-row\"><div><div class=\"stat\">"
            f"{fmt(before['median'], 3) if before is not None else '&mdash;'}"
            f" <span class=\"arr\">&rarr;</span> "
            f"<span class=\"good\">{fmt(after['median'], 3) if after is not None else '&mdash;'}</span>"
            f" nm</div><div class=\"stat-label\">median residual, "
            f"&times;{fmt(factor, 1)} reduction</div></div></div>"
            if before is not None and after is not None else "")
    return f"""
<div class="poster-section">
  <h2>Result 1 &mdash; agreement of neon peaks with NIST reference lines</h2>
  <div class="poster-split-narrow">
    <div>
      {stat}
      <p>Deviation of each fitted neon peak from its assigned NIST line,
      before and after calibration, over every optical configuration and
      both excitation wavelengths.</p>
      {_neon_table(ne)}
    </div>
    {_figure(fig, caption, cache_bust, compact=True)}
  </div>
</div>"""


def _samples_table(samples):
    rows = []
    for material in sorted(samples["sample"].unique()):
        sub = samples.loc[samples["sample"] == material].set_index("stage")
        cells = [f"<td>{_esc(MATERIAL_LABELS.get(material, material))}</td>"]
        first = last = math.nan
        for i, stage in enumerate(SAMPLE_STAGES):
            if stage in sub.index:
                r = sub.loc[stage]
                cells.append(f"<td>{int(r['n'])}</td>")
                cells.append(_num(r["median"], 3))
                if i == 0:
                    first = r["median"]
                last = r["median"]
            else:
                cells += ["<td>&mdash;</td>"] * 2
        change = pct_change(first, last)
        cls = "good" if np.isfinite(change) and change > 0 else "bad"
        cells.append(f'<td class="{cls}">{fmt_pct(change)}</td>')
        rows.append(f"<tr>{''.join(cells)}</tr>")
    head = ("<tr><th rowspan=\"2\">material</th>"
            + "".join(f'<th colspan="2">{_esc(_stage_label(s))}</th>'
                      for s in SAMPLE_STAGES)
            + '<th rowspan="2">change</th></tr><tr>'
            + "<th>n</th><th>median</th>" * len(SAMPLE_STAGES)
            + "</tr>")
    return (f'<div class="table-wrap"><table class="data poster-mini">'
            f"<thead>{head}</thead><tbody>{''.join(rows)}</tbody></table></div>")


def _result2_section(samples, overall, artifact_cm1, fig, caption, cache_bust):
    ov = overall.loc[overall["laser_wl"] == "all"].sort_values("stage")
    ov_txt = " &rarr; ".join(fmt(v, 3) for v in ov["median"])
    return f"""
<div class="poster-section">
  <h2>Result 2 &mdash; deviation of reference sample peaks after calibration</h2>
  <p>Absolute deviation of measured peak positions from reference sample values,
  in cm<sup>&minus;1</sup>, at each processing stage, per material and optical
  path. Silicon is not an independent test, since the Raman shift scale is
  zeroed on that band; calcite and polystyrene are. Median absolute deviation,
  all materials pooled, excluding assignment artefacts beyond
  {artifact_cm1:.0f}&nbsp;cm<sup>&minus;1</sup>: <b class="mono">{ov_txt}</b>
  &nbsp;cm<sup>&minus;1</sup>. The silicon samples improve substantially,
  calcite marginally, while polystyrene &mdash; used here for verification
  only, not as a calibration anchor &mdash; shows a small net degradation.</p>
  <div class="poster-split-narrow">
    {_samples_table(samples)}
    {_figure(fig, caption, cache_bust)}
  </div>
</div>"""


def _result3_section(resolution, fig, caption, cache_bust):
    return f"""
<div class="poster-section">
  <h2>Result 3 &mdash; spectral resolution curves (CWA 18133, sections 3&ndash;4)</h2>
  <p>Spectral resolution (FWHM, ASTM E2529) against Raman shift, per excitation
  wavelength: neon line width against position gives the instrument response,
  scaled by the calcite band near 1085.9&nbsp;cm<sup>&minus;1</sup> into
  spectral resolution. Range: <b>{fmt(resolution['sres_min'], 2)}&ndash;
  {fmt(resolution['sres_max'], 2)} cm<sup>&minus;1</sup></b> over
  {resolution['n_paths']} optical configurations (median
  {fmt(resolution['sres_median'], 2)}&nbsp;cm<sup>&minus;1</sup>, a factor of
  {fmt(resolution['spread_factor'], 0)} between the extremes).
  <b>{resolution['n_within']} of {resolution['n_paths']}</b> configurations
  satisfy the CWA 18133 acceptance boundary.</p>
  {_figure(fig, caption, cache_bust)}
</div>"""


def _worked_example_section(label, stats_row, fig, caption, cache_bust):
    outcome = ""
    if stats_row is not None:
        first = stats_row[f"median_{SAMPLE_STAGES[0]}"]
        outcome = (
            f" Median absolute deviation for this configuration: "
            f"{fmt(first, 2)} &rarr; <b>{fmt(stats_row['final'], 2)}</b>"
            f"&nbsp;cm<sup>&minus;1</sup> ({fmt_pct(stats_row['improvement_pct'])}).")
    return f"""
<div class="poster-section">
  <h2>Worked example &mdash; {_esc(label)}</h2>
  <p>One optical configuration followed through the whole procedure: neon
  reference spectrum and assigned NIST lines, the fitted wavelength calibration
  curve, the silicon band before and after, and a verification sample on the
  resulting calibrated scale.{outcome}</p>
  {_figure(fig, caption, cache_bust)}
</div>"""


def _recommendations_section(ctx):
    return f"""
<div class="poster-section">
  <h2>Implementation experience and recommendations</h2>
  <div class="poster-cols-2">
    <div>
      <p><b>The polyharmonic spline recommended by CWA 18133 &sect;6.1(d) did
      not perform well in practice.</b> A polynomial fit through the same
      matched neon lines was consistently more stable, particularly beyond the
      reference-line span.</p>
      <p><b>Peak assignment is the hard step</b> and needs a robust,
      outlier-tolerant procedure with a documented rejection criterion;
      extrapolation must be bounded and the wavenumber scale kept monotonic.</p>
    </div>
    <div>
      <p>Recommendations for a future protocol revision: offer a plain
      polynomial as an accepted alternative to the polyharmonic spline; specify
      the assignment procedure and require reporting of residual statistics;
      require reference-line coverage around the silicon wavelength or define a
      fallback; bound extrapolation and flag spectral regions outside reference
      support; add acceptance criteria for the verification step; and mandate an
      open, self-describing calibration file format.</p>
    </div>
  </div>
</div>"""


def _url_text(url):
    """URL as printed, readable text: a printed poster has no clickable
    links, so the address itself must be legible, not hidden behind an
    href with a hyperlink-blue that means nothing on paper."""
    return url.split("://", 1)[-1]


def render_poster(ctx, ne, samples, overall, resolution,
                  artifact_cm1=20.0, figures=None, worked_examples=None,
                  title=None, authors=None, affiliations=None):
    """One portrait page, same numbers/figures as the deck, for print.

    `title`/`authors`/`affiliations` default to the deck's own title-slide
    text if not given, but should normally be passed explicitly from the
    submitted abstract, since a poster's title and author list are fixed by
    what was submitted, not derived from the run.
    """
    figures = figures or {}
    cache_bust = f"?v={int(time.time())}"

    def fig(name):
        return figures.get(name, (None, "figure not available"))

    title = title or ctx.get("title", "")
    authors = authors or ""
    affiliations = affiliations or ""

    worked = ""
    if worked_examples:
        label, stats_row, slot = worked_examples[0]
        f_name, f_caption = fig(slot)
        worked = _worked_example_section(label, stats_row, f_name, f_caption,
                                         cache_bust)

    neon_name, neon_caption = fig("neon")
    samples_name, samples_caption = fig("samples")
    res_name, res_caption = fig("resolution_curves")
    app_name, app_caption = fig("spectrastream_derive")
    if not app_name:
        app_name, app_caption = fig("spectrastream_verify")

    body = "".join([
        _head(title, authors, affiliations, ctx),
        _intro_section(ctx),
        _app_section(app_name, app_caption, cache_bust),
        _method_section(ctx),
        _result1_section(ne, neon_name, neon_caption, cache_bust),
        _result2_section(samples, overall, artifact_cm1, samples_name,
                         samples_caption, cache_bust),
        _result3_section(resolution, res_name, res_caption, cache_bust),
        worked,
        _recommendations_section(ctx),
        f'<div class="poster-footer">VAMAS TWA 42 Project 06, “Protocols for Raman instrument calibration and harmonisation of Raman data": '
        f'<span class="mono">https://www.vamas.org/twa42/documents/2024_vamas_twa42_p6_raman_calibration.pdf</span> &middot; '
        f'</div>',
    ])

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>{STYLE}{POSTER_STYLE}</style></head>
<body><div class="poster">
{body}
</div></body></html>"""
