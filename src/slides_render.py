"""HTML rendering of the presentation deck.

Separated from `slides_content.py` (which computes the numbers) and
`slides_figures.py` (which draws the plots), so the statistics stay testable
without carrying a page of CSS through every test. `render_deck` takes
already-computed values and returns one HTML string; figures are referenced by
filename from the `figures/` directory beside the deck.
"""
from __future__ import annotations

import math
import re
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

# Public references, spelled out because the audience is not assumed to know
# any of these projects.
LINKS = dict(
    ramanchada2="https://github.com/h2020charisma/ramanchada2",
    ramanchada2_doi="https://doi.org/10.1002/jrs.6789",
    pipeline="https://github.com/h2020charisma/vamas_twa42_p6_raman_calibration",
    spectrastream="https://github.com/h2020charisma/spectrastream",
    app="https://spectra.adma.ai/stream",
    calibrate="https://spectra.adma.ai/calibrate",
    search="https://spectra.adma.ai/search",
    cwa="https://www.cencenelec.eu/media/CEN-CENELEC/CWAs/RI/cwa18133-1.pdf",
    cwa18134="https://www.cencenelec.eu/media/CEN-CENELEC/CWAs/RI/2024/cwa18134-1.pdf",
    vamas="https://www.vamas.org/twa42/",
)

CITATION = ("Georgiev, G., Coca-Lopez, N., Lellinger, D., Iliev, L., Marinov, E., "
            "Tsoneva, S., Kochev, N., Ba&ntilde;ares, M. A., Portela, R. and "
            "Jeliazkova, N. (2025), Open Source for Raman Spectroscopy Data "
            "Harmonization. <i>J Raman Spectrosc.</i>")

STYLE = """
:root {
  --ink: #1c2024; --paper: #ffffff; --raised: #f4f2ed; --rule: #d8d4ca;
  --muted: #5f6670; --teal: #2f6f63; --teal-soft: #e4efec;
  --red: #b1502f; --red-soft: #f7e9e2; --tick: #c9c2b2; --link: #245a8d;
}
:root[data-theme="dark"] {
  --ink: #eae7df; --paper: #14161a; --raised: #1c1f24; --rule: #32363c;
  --muted: #9aa1a8; --teal: #6fb6a6; --teal-soft: #1c2b28;
  --red: #d98b6a; --red-soft: #2e2019; --tick: #3a3d44; --link: #7fb3e0;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ink: #eae7df; --paper: #14161a; --raised: #1c1f24; --rule: #32363c;
    --muted: #9aa1a8; --teal: #6fb6a6; --teal-soft: #1c2b28;
    --red: #d98b6a; --red-soft: #2e2019; --tick: #3a3d44; --link: #7fb3e0;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink);
       font-family: 'Charter', 'Iowan Old Style', Georgia, serif; }
a { color: var(--link); }
.deck { max-width: 1180px; margin: 0 auto; padding: 2rem 1.5rem 5rem; }
.deck-header { display: flex; justify-content: space-between; align-items: baseline;
  padding-bottom: 1rem; border-bottom: 1px solid var(--rule); margin-bottom: 2rem;
  font-family: ui-monospace, 'SF Mono', Consolas, monospace; font-size: 0.7rem;
  letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
.deck-header b { color: var(--ink); font-weight: 600; }
.slide { position: relative; background: var(--paper); border: 1px solid var(--rule);
  border-radius: 3px; margin-bottom: 2rem; min-height: 620px;
  padding: 2.8rem 3rem 2.2rem; display: flex; flex-direction: column;
  overflow: hidden; }
.slide-tag { position: absolute; top: 1rem; right: 3rem;
  font-family: ui-monospace, monospace; font-size: 0.62rem; letter-spacing: 0.09em;
  text-transform: uppercase; color: var(--muted); }
.axis-tick { position: absolute; bottom: 0; left: 0; right: 0; height: 3px;
  background: repeating-linear-gradient(90deg, var(--tick) 0 1px, transparent 1px 14px);
  opacity: 0.5; }
h1.title { font-family: ui-monospace, monospace; font-weight: 600; font-size: 2.1rem;
  line-height: 1.12; text-wrap: balance; margin: 0 0 0.7rem; }
.slide h2 { font-family: ui-monospace, monospace; font-weight: 600; font-size: 1.3rem;
  text-wrap: balance; margin: 0 0 1.1rem; line-height: 1.25; }
.eyebrow { font-family: ui-monospace, monospace; font-size: 0.66rem;
  letter-spacing: 0.14em; text-transform: uppercase; color: var(--red);
  margin-bottom: 0.7rem; }
.lede { font-size: 1.05rem; line-height: 1.5; max-width: 64ch; }
.slide p, .slide li { font-size: 0.95rem; line-height: 1.5; }
.body { flex: 1; display: grid; gap: 1.2rem; min-height: 0; }
.cols-2 { grid-template-columns: 1fr 1fr; }
.cols-3 { grid-template-columns: repeat(3, 1fr); }
.split { grid-template-columns: 1fr 1fr; }
.split-wide-left { grid-template-columns: 1.25fr 0.75fr; }
.card { background: var(--raised); border: 1px solid var(--rule); border-radius: 2px;
  padding: 0.9rem 1.1rem; }
.card h3 { font-family: ui-monospace, monospace; font-size: 0.7rem;
  letter-spacing: 0.05em; text-transform: uppercase; color: var(--teal);
  margin: 0 0 0.45rem; font-weight: 600; }
.card.warn h3 { color: var(--red); }
.card p { margin: 0; font-size: 0.9rem; }
.card p + p { margin-top: 0.4rem; }
ul.plain { margin: 0; padding: 0; list-style: none; }
ul.plain li { padding: 0.4rem 0 0.4rem 0.9rem; border-left: 2px solid var(--rule);
  margin-bottom: 0.4rem; font-size: 0.92rem; }
.chain { display: flex; align-items: stretch; flex: 1; }
.chain .step { flex: 1; border: 1px solid var(--rule); background: var(--raised);
  padding: 0.8rem 0.85rem; display: flex; flex-direction: column; gap: 0.3rem; }
.chain .step + .step { border-left: none; }
.chain .step .t { font-family: ui-monospace, monospace; font-weight: 600;
  font-size: 0.8rem; }
.chain .step .d { font-size: 0.75rem; color: var(--muted); line-height: 1.35; }
.chain .step .step-list { margin: 0; padding-left: 1rem; font-size: 0.72rem;
  color: var(--muted); line-height: 1.5; }
.chain .step .step-list li { margin-bottom: 0.15rem; }
.chain .step .p { font-family: ui-monospace, monospace; font-size: 0.66rem;
  color: var(--teal); margin-top: auto; }
table.data { border-collapse: collapse; width: 100%; font-size: 0.82rem;
  font-variant-numeric: tabular-nums; }
table.data th { font-family: ui-monospace, monospace; font-size: 0.62rem;
  letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted);
  text-align: right; padding: 0.4rem 0.55rem; border-bottom: 1px solid var(--ink); }
table.data th:first-child { text-align: left; }
table.data td { padding: 0.4rem 0.55rem; border-bottom: 1px solid var(--rule);
  text-align: right; }
table.data td:first-child { text-align: left; }
table.data tr:last-child td { border-bottom: none; }
table.data td.good { color: var(--teal); }
table.data td.bad { color: var(--red); }
.table-wrap { overflow-x: auto; }
.stat { font-family: ui-monospace, monospace; font-weight: 600; font-size: 1.5rem;
  font-variant-numeric: tabular-nums; line-height: 1.1; }
.stat .arr { color: var(--tick); font-size: 1rem; margin: 0 0.2rem; }
.stat .good { color: var(--teal); }
.stat .bad { color: var(--red); }
.stat-label { font-family: ui-monospace, monospace; font-size: 0.62rem;
  letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted);
  margin-top: 0.28rem; line-height: 1.4; }
figure { margin: 0; border: 1px solid var(--rule); background: var(--raised);
  padding: 0.7rem 0.8rem 0.5rem; display: flex; flex-direction: column; }
figure img { width: 100%; height: auto; display: block; background: #fff;
  border-radius: 2px; }
figcaption { font-size: 0.72rem; color: var(--muted); margin-top: 0.45rem;
  line-height: 1.35; }
.placeholder { border: 2px dashed var(--rule); background: var(--raised);
  border-radius: 3px; min-height: 210px; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 0.4rem; text-align: center;
  padding: 1rem; color: var(--muted); }
.placeholder .ph-title { font-family: ui-monospace, monospace; font-size: 0.78rem;
  letter-spacing: 0.06em; text-transform: uppercase; color: var(--red); }
.placeholder .ph-hint { font-size: 0.82rem; max-width: 42ch; line-height: 1.4; }
.mono { font-family: ui-monospace, monospace; }
.muted { color: var(--muted); }
.note { font-family: ui-monospace, monospace; font-size: 0.66rem; color: var(--muted);
  margin-top: auto; padding-top: 0.7rem; border-top: 1px dashed var(--rule);
  line-height: 1.5; }
.refs { font-size: 0.82rem; line-height: 1.5; }
.refs li { margin-bottom: 0.4rem; }
@media (max-width: 900px) {
  .slide { min-height: auto; padding: 1.8rem 1.2rem; }
  .cols-2, .cols-3, .split, .split-wide-left { grid-template-columns: 1fr; }
  .chain { flex-direction: column; }
  .chain .step + .step { border-left: 1px solid var(--rule); border-top: none; }
}
@media print { .slide { break-after: page; } }
"""


def _slide(tag, inner, note=None):
    note_html = f'<div class="note">{note}</div>' if note else ""
    return (f'<section class="slide"><span class="slide-tag">{_esc(tag)}</span>'
            f"{inner}{note_html}<div class=\"axis-tick\"></div></section>")


# Set once per render_deck() call, so every figure in one build shares the
# same cache-busting query string. Without it, a rebuilt PNG under an
# unchanged filename (e.g. after a `slides --force` regenerates
# sample_errors.png) can keep showing a browser- or Nextcloud-cached copy of
# the old image, since the <img src="..."> URL itself never changes.
_CACHE_BUST = ""


def _figure(src, caption):
    if not src:
        return f'<p class="muted">{_esc(caption)}</p>'
    return (f'<figure><img src="figures/{_esc(src)}{_CACHE_BUST}" '
            f'alt="{_esc(caption)}">'
            f"<figcaption>{caption}</figcaption></figure>")


def _placeholder(title, hint):
    """A clearly marked slot for a screenshot to be dropped in by hand."""
    return (f'<div class="placeholder"><span class="ph-title">{_esc(title)}</span>'
            f'<span class="ph-hint">{_esc(hint)}</span></div>')


def _stage_label(stage):
    return stage.split(".", 1)[-1] if "." in stage else stage


def _num(value, digits=3, cls=""):
    attr = f' class="{cls}"' if cls else ""
    return f"<td{attr}>{fmt(value, digits)}</td>"


# --- slides -----------------------------------------------------------------


def _title_slide(ctx):
    part = ctx.get("participation") or {}
    total = part.get("total_labs")
    excluded = part.get("excluded") or []
    excluded_txt = (
        f"{part.get('n_excluded', 0)} further datasets were loaded but could not "
        f"be calibrated for lack of a required reference measurement "
        f"({', '.join(excluded)})." if excluded else "")
    return _slide("1 / 15", f"""
<div style="flex:1;display:flex;flex-direction:column;justify-content:center;max-width:80%">
  <div class="eyebrow">VAMAS TWA42 &middot; Project 6</div>
  <h1 class="title"> Automated processing tools to analyse the results of an interlaboratory study: wavenumber and relative intensity calibration of Raman spectrometers</h1>
  <p class="lede">Implementation and assessment of the CWA 18133:2024 calibration protocol using neon emission lamp for wavenumber calibration, a silicon reference for Raman shift, calcite and polystyrene reference samples for resolution and calibration assessment, and a NIST SRM / certified broadband LED intensity reference. Samples provided by ELODIZ.</p>
  <p class="lede" style="margin-top:0.8rem">
  {f'Of approximately {total} laboratories in the study, ' if total else ''}
  <b>{ctx['n_keys']}</b> contributed complete enough measurements to be calibrated,
  covering <b>{ctx['n_paths']}</b> optical configurations at
  {ctx['lasers']}&nbsp;nm excitation. {excluded_txt}</p>
</div>
<div class="note">Processing configuration:
<span class="mono">{_esc(ctx['context'])}</span> &middot; generated
{_esc(ctx['generated'])} from the analysis pipeline.<br>
ILC measurement data are not publicly available; the figures shown are
aggregate results.</div>""")


def _participants_slide(df_participants):
    if df_participants is None or df_participants.empty:
        return _slide("2 / 15", "<h2>Participants</h2>"
                                "<p class=\"muted\">No participant list available.</p>")

    rows = []
    for _, r in df_participants.sort_values(
            ["id", "laser_wl", "optical_path"]).iterrows():
        instrument = " ".join(
            str(v) for v in (r.get("instrument_make"), r.get("instrument_model"))
            if isinstance(v, str) and v.strip())
        used = bool(r.get("calibrated"))
        cls = "good" if used else "bad"
        mark = "yes" if used else "no"
        laser = r.get("laser_wl")
        laser_txt = f"{laser:g}" if isinstance(laser, (int, float)) else str(laser)
        rows.append(
            f"<tr><td class=\"mono\">{_esc(r.get('id', ''))}</td>"
            f"<td>{_esc(instrument or '&mdash;')}</td>"
            f"<td>{_esc(r.get('optical_path', ''))}</td>"
            f"<td>{_esc(laser_txt)}</td>"
            f"<td class=\"{cls}\">{mark}</td></tr>")

    table = (
        '<div class="table-wrap"><table class="data"><thead><tr>'
        '<th>participant</th><th>instrument</th><th>optical path</th>'
        '<th>&lambda; / nm</th><th>calibrated</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>")

    return _slide("2 / 15", f"""
<h2>Participants and optical configurations</h2>
<div class="body" style="grid-template-rows:1fr">{table}</div>
<div class="note">One row per optical configuration submitted; a participant
with several excitation wavelengths or gratings appears more than once.
"Calibrated" marks configurations that entered the analysis on this run.</div>""")


def _tools_slide():
    return _slide("2 / 12", f"""
<h2>Software: one open library, two interfaces</h2>
<div class="body split-wide-left">
  <div>
    <p>All processing is implemented in <b class="mono">ramanchada2</b>, an open-source
    Python library for Raman spectrum input/output and processing
    [<a href="{LINKS['ramanchada2_doi']}">1</a>]. It provides the vendor-format readers,
    peak finding and fitting, neon-to-NIST line matching, the interpolation and
    laser-zeroing components, and the resolution calculations.</p>
    <p>Two applications use the library without reimplementing any of it:</p>
    <ul class="plain">
      <li><b>Analysis pipeline</b> — a batch workflow that processes the complete
      ILC, one task chain per laboratory. Used to produce every result in
      this presentation.</li>
      <li><b>SpectraStream</b> — an interactive web application for a single
      spectrum: file conversion, calibration, verification and export.</li>
    </ul>
    <p>Consequently a correction to the library propagates to both, and results
    obtained interactively are directly comparable with the ILC analysis.</p>
    <p>Calibrations are exported in the portable form required by CWA 18133
    section 8, and additionally as NeXus <span class="mono">NXcalibration</span>
    records, so a calibrated spectrum carries the reference measurements and the
    fitted model that produced it.</p>
  </div>
  <div style="display:flex;flex-direction:column;gap:0.8rem">
    <div class="card">
      <h3>Source code</h3>
      <p class="mono" style="font-size:0.78rem;line-height:1.7">
      <a href="{LINKS['ramanchada2']}">github.com/h2020charisma/ramanchada2</a><br>
      <a href="{LINKS['pipeline']}">github.com/h2020charisma/<br>vamas_twa42_p6_raman_calibration</a><br>
      <a href="{LINKS['spectrastream']}">github.com/h2020charisma/spectrastream</a></p>
    </div>
    <div class="card">
      <h3>Services</h3>
      <p class="mono" style="font-size:0.78rem;line-height:1.7">
      <a href="{LINKS['app']}">spectra.adma.ai/stream</a> — application<br>
      <a href="{LINKS['calibrate']}">spectra.adma.ai/calibrate</a> — pipeline output<br>
      <a href="{LINKS['search']}">spectra.adma.ai/search</a> — data search</p>
    </div>
  </div>
</div>
<div class="note">[1] {CITATION}
<a href="{LINKS['ramanchada2_doi']}">doi:10.1002/jrs.6789</a></div>""")


def _pipeline_slide():
    steps = [
        ("Load", [
            "Read the metadata template",
            "Load all spectra",
            "Subtract the measured background",
            "Assign material tags",
        ], "HDF5, XLSX"),
        ("x-calibration", [
            "Fit neon peaks",
            "Match peaks to NIST lines",
            "Fit the wavelength interpolation curve",
            "Fit the silicon band",
            "Zero the Raman shift axis on it",
        ], "calibration models"),
        ("y-calibration", [
            "Fit the measured NIST-SRM/LED spectrum",
            "Compare it with its certificate",
            "Derive the relative-intensity correction",
        ], "intensity models"),
        ("Resolution", [
            "Neon FWHM against position",
            "Calcite band width (ASTM E2529)",
            "Spectral resolution (CWA sections 3-4)",
        ], "resolution curves"),
        ("Assessment", [
            "Re-extract peak positions at each stage",
            "Compare with reference values",
            "Aggregate across all laboratories",
        ], "peak tables"),
        ("Export", [
            "Portable calibration files (CWA section 8)",
            "NeXus records",
        ], "CSV, JSON, NXS"),
    ]
    chain = "".join(
        f'<div class="step"><span class="t">{_esc(t)}</span>'
        f'<ul class="step-list">'
        + "".join(f"<li>{_esc(item)}</li>" for item in items)
        + f'</ul><span class="p">{_esc(p)}</span></div>'
        for t, items, p in steps)
    return _slide("3 / 15", f"""
<h2>Analysis pipeline: processing stages</h2>
<div class="body" style="grid-template-rows:auto 1fr">
  <p style="margin:0;max-width:78ch">A directed acyclic graph of processing tasks.
  Each stage runs independently for every laboratory, so the complete study is
  reproducible from the raw files and a configuration file.</p>
  <div class="chain">{chain}</div>
</div>
<div class="note">Results are written to a directory named after the processing
options, so alternative peak-matching and interpolation settings can be compared
without overwriting each other.</div>""")


def _app_slide(derive_fig=None, verify_fig=None):
    derive = (_figure(derive_fig[0], derive_fig[1]) if derive_fig and derive_fig[0]
             else _placeholder("Screenshot", "Derive calibration page — "
                                "insert a screenshot here."))
    verify = (_figure(verify_fig[0], verify_fig[1]) if verify_fig and verify_fig[0]
             else _placeholder("Screenshot", "Verify page — insert a "
                                "screenshot showing peak comparison or "
                                "resolution curves here."))
    return _slide("4 / 15", f"""
<h2>SpectraStream: interactive calibration of a single spectrum</h2>
<div class="body split">
  <div>
    <p>A web application built on the same library, intended for laboratories that
    wish to apply the protocol to their own measurements without running the batch
    pipeline.</p>
    <ul class="plain">
      <li><b>Convert and export</b> — read common vendor formats; write NeXus, CSV
      and the CWA section 8 calibration files.</li>
      <li><b>Derive calibration</b> — obtain the wavenumber from Ne, Si and intensity
      correction from NIST-SRM/LED reference measurements.</li>
      <li><b>Verify</b> — compare Si, Calcite and Polystyrene peak positions against reference values and
      compute the resolution curves.</li>
      <li><b>Instruments</b> — record instruments and optical configurations; a
      calibration is bound to a configuration, since it is not transferable
      between excitation wavelengths or gratings.</li>
    </ul>
    <p>Only the x-axis unit and the excitation wavelength are required; all
    other metadata are optional. Instrument profiles are held in the browser and
    uploaded spectra are not retained on the server.</p>
  </div>
  <div style="display:flex;flex-direction:column;gap:0.8rem">
    {derive}
    {verify}
  </div>
</div>
<div class="note">Available at <a href="{LINKS['app']}">{LINKS['app']}</a> &middot;
source at <a href="{LINKS['spectrastream']}">{LINKS['spectrastream']}</a></div>""")


def _method_slide(ctx):
    return _slide("5 / 15", f"""
<h2>Wavenumber calibration (CWA 18133:2024, section 6.2)</h2>
<div class="body cols-2">
  <div class="card">
    <h3>Step 1 &mdash; wavelength scale from neon</h3>
    <p>Neon emission lines have precisely known wavelengths and are independent of
    the laser, so they establish the spectrograph scale. Peaks are located and
    assigned to NIST reference lines (assignment method
    <span class="mono">{_esc(ctx['match_mode'])}</span>), then an interpolating
    function (<span class="mono">{_esc(ctx['interpolator'])}</span>) is fitted
    through the assigned pairs.</p>
    <p>Beyond the range covered by neon lines the edge correction is continued at
    constant offset rather than extrapolating the fitted function, which would
    diverge in the C&ndash;H stretching region.</p>
  </div>
  <div class="card">
    <h3>Step 2 &mdash; wavenumber scale from silicon</h3>
    <p>An accurate wavelength scale still leaves the Raman shift origin undefined,
    because that depends on the actual laser wavelength, which differs from its
    nominal value. The silicon band at 520.45&nbsp;cm<sup>&minus;1</sup>
    &mdash; a reliably reproducible reference value [2] &mdash; is used to fix this zero. Both boron-doped Si(100)
    (S0B) and undoped Si(100) (S0N) silicon wafers were used across the
    ILC.</p>
    <p>The silicon band is fitted on the calibrated wavelength scale and its
    position taken as the effective laser wavelength:</p>
    <p class="mono" style="font-size:0.85rem">&Delta;&nu;&#771; =
    10<sup>7</sup>(1/&lambda;<sub>Si</sub> &minus; 1/&lambda;) +
    520.45&nbsp;cm<sup>&minus;1</sup></p>
    <p>Any error at that single wavelength therefore propagates to the whole
    wavenumber scale.</p>
  </div>
</div>
<div class="note">[2] Itoh, N. and Shirono, K. (2020), Reliable estimation of
Raman shift and its uncertainty for a non-doped Si substrate (NMIJ CRM 5606-a).
J. Raman Spectrosc., 51: 2496-2504.
<a href="https://doi.org/10.1002/jrs.6003">doi:10.1002/jrs.6003</a><br>
Protocol: <a href="{LINKS['cwa']}">CWA 18133:2024</a> &middot;
study: <a href="{LINKS['vamas']}">VAMAS TWA 42</a> &middot; implementation in
<span class="mono">ramanchada2</span>, driven by this pipeline.<br>
Out of scope here: intensity <i>twinning</i> between instruments and the TiPS
(epoxy + TiO<sub>2</sub>) sample are covered by a separate protocol,
<a href="{LINKS['cwa18134']}">CWA 18134:2024, Raman instruments twinning
protocol</a> &mdash; not analysed in this presentation.</div>""")


def _ycal_method_slide(ycal, fig, caption, ref_fig=None, ref_caption=""):
    rows = "".join(
        f"<tr><td class=\"mono\">{_esc(r['certificate'])}</td>"
        f"<td>{int(r['n_models'])}</td><td>{int(r['n_labs'])}</td></tr>"
        for _, r in ycal.iterrows()) if ycal is not None and not ycal.empty else ""
    table = (
        '<div class="table-wrap"><table class="data"><thead><tr>'
        '<th>reference</th><th>models</th><th>laboratories</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>" if rows else
        '<p class="muted">No relative-intensity models available.</p>')

    return _slide("6 / 15", f"""
<h2>Relative intensity calibration (CWA 18133:2024, section 7)</h2>
<div class="body split">
  <div>
    <p>Every instrument has a wavelength-dependent sensitivity arising from the
    grating, detector and optics. Relative intensity calibration removes it by
    measuring a broadband emitter &mdash; a NIST-SRM fluorescent glass or a
    certified LED - and comparing it with its known
    response.</p>
    <p>The measured reference spectrum is fitted with the functional form given in
    its own reference response rather than interpolated directly, which suppresses
    noise without distorting the shape. The correction is then</p>
    <p class="mono" style="font-size:0.85rem">factor(&Delta;&nu;&#771;) =
    reference(&Delta;&nu;&#771;) / measured(&Delta;&nu;&#771;)</p>
    <p>restricted to the reference's validity range; outside it no correction is
    defined and none is applied. The measurement must itself be on a calibrated
    wavenumber scale first, so this step follows wavenumber calibration.</p>
    {table}
  </div>
  <div style="display:flex;flex-direction:column;gap:0.7rem;min-height:0">
    {_figure(ref_fig, ref_caption)}
    {_figure(fig, caption)}
  </div>
</div>
<div class="note">Unlike wavenumber calibration, the intensity correction is
required per optical configuration and is not transferable between them.</div>""")


def _worked_example_slide(label, stats_row, figures, slot, is_first=False):
    """Follow one optical configuration through the whole procedure.

    The four panels are the same for every worked example, so the panel-by-panel
    walkthrough is only spelled out once, on the first slide; later slides go
    straight to the outcome so the repetition doesn't eat the audience's
    attention.
    """
    fig, caption = figures.get(slot, (None, "figure not available"))
    outcome = ""
    if stats_row is not None:
        first = stats_row[f"median_{SAMPLE_STAGES[0]}"]
        outcome = (
            f"Median absolute deviation of the verification samples for this "
            f"configuration: {fmt(first, 2)} &rarr; "
            f"<b>{fmt(stats_row['final'], 2)}</b>&nbsp;cm<sup>&minus;1</sup> "
            f"({fmt_pct(stats_row['improvement_pct'])}).")

    if is_first:
        intro = (
            "The four panels show what is actually fitted. "
            "<b>(1)</b> The neon reference spectrum, whose peaks are assigned to "
            "NIST lines. <b>(2)</b> The wavelength calibration curve fitted "
            "through those assigned pairs; the points are the surviving matched "
            "lines after outlier rejection. <b>(3)</b> The silicon band, fitted "
            "on the corrected wavelength scale, whose position fixes the "
            "wavenumber origin at 520.45&nbsp;cm<sup>&minus;1</sup>. "
            "<b>(4)</b> A verification sample on the resulting calibrated scale. "
            + outcome)
    else:
        intro = outcome

    return _slide("worked example", f"""
<h2>Worked example: {_esc(label)}</h2>
<div class="body" style="grid-template-rows:auto 1fr">
  <p style="margin:0;max-width:92ch">{intro}</p>
  {_figure(fig, caption)}
</div>
<div class="note">The same sequence runs for every optical configuration; the
per-laboratory report contains these plots together with the peak assignment
diagnostics.</div>""")


def _neon_slide(ne, fig, caption):
    all_rows = ne.loc[ne["laser_wl"] == "all"].set_index("stage")
    before = all_rows.loc["1.original"] if "1.original" in all_rows.index else None
    after = all_rows.loc["2.Ne_clbr"] if "2.Ne_clbr" in all_rows.index else None
    if before is None or after is None:
        return _slide("8 / 15", "<h2>Neon line positions</h2>"
                                "<p>No neon data available.</p>")

    factor = before["median"] / after["median"] if after["median"] else math.nan
    rows = []
    for _, r in ne.iterrows():
        label = ("all" if r["laser_wl"] == "all" else f"{r['laser_wl']} nm")
        rows.append(
            f"<tr><td>{_esc(_stage_label(r['stage']))}</td><td>{_esc(label)}</td>"
            f"<td>{int(r['n'])}</td>{_num(r['median'], 4)}{_num(r['mean'], 4)}"
            f"{_num(r['sd'], 4)}{_num(r['rmse'], 4)}"
            f"<td>{int(r['outliers'])}</td></tr>")
    table = (
        '<div class="table-wrap"><table class="data"><thead><tr><th>stage</th>'
        '<th>&lambda;</th><th>n</th><th>median</th><th>mean</th><th>SD</th>'
        '<th>RMSE</th><th>&gt;1 nm</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>")

    return _slide("8 / 15", f"""
<h2>Result 1: agreement of neon peaks with NIST reference lines</h2>
<div class="body split">
  <div>
    <div class="stat">{fmt(before['median'], 3)}
      <span class="arr">&rarr;</span>
      <span class="good">{fmt(after['median'], 3)}</span> nm</div>
    <div class="stat-label">median absolute residual, all optical configurations
      &mdash; a factor of {fmt(factor, 1)} reduction</div>
    <p style="margin-top:0.9rem">Deviation of each fitted neon peak from its
    assigned NIST line, before and after applying the calibration function. The
    number of residuals exceeding 1&nbsp;nm falls from
    {int(before['outliers'])} to {int(after['outliers'])}.</p>
    {table}
  </div>
  {_figure(fig, caption)}
</div>
<div class="note">Residuals in nm on the wavelength scale. All subsequent
quantities are derived from this scale, so its accuracy bounds everything that
follows.</div>""")


def _samples_slide(samples, overall, artifact_cm1, fig, caption, by_laser=None):
    source = by_laser if by_laser is not None and not by_laser.empty else None
    rows = []
    if source is not None:
        for material in sorted(source["sample"].unique()):
            for laser in sorted(source.loc[source["sample"] == material,
                                           "laser_wl"].unique()):
                sub = source.loc[(source["sample"] == material)
                                 & (source["laser_wl"] == laser)]
                sub = sub.set_index("stage")
                cells = [f"<td>{_esc(MATERIAL_LABELS.get(material, material))}</td>",
                         f"<td>{_esc(laser)}</td>"]
                first = last = math.nan
                for i, stage in enumerate(SAMPLE_STAGES):
                    if stage in sub.index:
                        r = sub.loc[stage]
                        cells.append(f"<td>{int(r['n'])}</td>")
                        cells.append(_num(r["median"], 3))
                        cells.append(_num(r["sd"], 3))
                        if i == 0:
                            first = r["median"]
                        last = r["median"]
                    else:
                        cells += ["<td>&mdash;</td>"] * 3
                change = pct_change(first, last)
                cls = "good" if np.isfinite(change) and change > 0 else "bad"
                cells.append(f'<td class="{cls}">{fmt_pct(change)}</td>')
                rows.append(f"<tr>{''.join(cells)}</tr>")
        head = ('<tr><th rowspan="2">material</th><th rowspan="2">&lambda;/nm</th>'
                + "".join(f'<th colspan="3">{_esc(_stage_label(s))}</th>'
                          for s in SAMPLE_STAGES)
                + '<th rowspan="2">change</th></tr><tr>'
                + "<th>n</th><th>median</th><th>SD</th>" * len(SAMPLE_STAGES)
                + "</tr>")
    else:
        for material in sorted(samples["sample"].unique()):
            sub = samples.loc[samples["sample"] == material].set_index("stage")
            cells = [f"<td>{_esc(MATERIAL_LABELS.get(material, material))}</td>"]
            first = last = math.nan
            for i, stage in enumerate(SAMPLE_STAGES):
                if stage in sub.index:
                    r = sub.loc[stage]
                    cells.append(f"<td>{int(r['n'])}</td>")
                    cells.append(_num(r["median"], 3))
                    cells.append(_num(r["sd"], 3))
                    if i == 0:
                        first = r["median"]
                    last = r["median"]
                else:
                    cells += ["<td>&mdash;</td>"] * 3
            change = pct_change(first, last)
            cls = "good" if np.isfinite(change) and change > 0 else "bad"
            cells.append(f'<td class="{cls}">{fmt_pct(change)}</td>')
            rows.append(f"<tr>{''.join(cells)}</tr>")
        head = ("<tr><th rowspan=\"2\">material</th>"
                + "".join(f'<th colspan="3">{_esc(_stage_label(s))}</th>'
                          for s in SAMPLE_STAGES)
                + '<th rowspan="2">change</th></tr><tr>'
                + "<th>n</th><th>median</th><th>SD</th>" * len(SAMPLE_STAGES)
                + "</tr>")

    table = (f'<div class="table-wrap"><table class="data"><thead>{head}</thead>'
             f"<tbody>{''.join(rows)}</tbody></table></div>")

    ov = overall.loc[overall["laser_wl"] == "all"].sort_values("stage")
    ov_txt = " &rarr; ".join(fmt(v, 3) for v in ov["median"])

    return _slide("9 / 15", f"""
<h2>Result 2: deviation of reference sample peaks after calibration</h2>
<div class="body" style="grid-template-rows:auto auto auto 1fr">
  <p style="margin:0;max-width:80ch">Absolute deviation of measured peak positions
  from  reference sample values, in cm<sup>&minus;1</sup>, at each processing stage.
  Silicon is not an independent test, since the Raman shift scale is zeroed on
  that band; calcite and polystyrene are. Median absolute deviation, all
  materials pooled, excluding assignment artefacts beyond
  {artifact_cm1:.0f}&nbsp;cm<sup>&minus;1</sup>:
  <b class="mono">{ov_txt}</b>&nbsp;cm<sup>&minus;1</sup>.</p>
  {table}
  {_figure(fig, caption)}
</div>
<div class="note">The silicon samples improve substantially, calcite marginally,
while polystyrene deteriorates slightly: the procedure constrains the scale at the
positions of its reference lines, and polystyrene serves here for verification
rather than as an anchor.</div>""")


def _materials_slide(samples, figures, materials):
    """One panel per material, so it is explicit what each shows.

    A combined chart makes it look as though calibration acts uniformly; the
    per-material panels show that it does not.
    """
    panels = []
    for material in materials:
        name, caption = figures.get(f"material_{material}", (None, ""))
        sub = samples.loc[samples["sample"] == material].set_index("stage")
        first = last = math.nan
        n = 0
        if SAMPLE_STAGES[0] in sub.index:
            first = sub.loc[SAMPLE_STAGES[0], "median"]
            n = int(sub.loc[SAMPLE_STAGES[0], "n"])
        for stage in reversed(SAMPLE_STAGES):
            if stage in sub.index:
                last = sub.loc[stage, "median"]
                break
        change = pct_change(first, last)
        cls = "good" if np.isfinite(change) and change > 0 else "bad"
        panels.append(f"""
<div class="card">
  <h3>{_esc(MATERIAL_LABELS.get(material, material))}</h3>
  <p class="stat" style="font-size:1.05rem">{fmt(first, 3)}
    <span class="arr">&rarr;</span>
    <span class="{cls}">{fmt(last, 3)}</span></p>
  <p class="stat-label">median |error| cm<sup>&minus;1</sup> &middot;
    {fmt_pct(change)} &middot; n&nbsp;=&nbsp;{n} peaks</p>
  <div style="margin-top:0.5rem">{_figure(name, caption)}</div>
</div>""")

    return _slide("10 / 15", f"""
<h2>Result 2 in detail: behaviour differs between materials</h2>
<div class="body cols-{min(len(panels), 4) if panels else 2}">
  {''.join(panels) or '<p class="muted">No material data.</p>'}
</div>
<div class="note">Each panel: absolute deviation of measured peak positions from
reference values at the three processing stages, median and mean with one
standard deviation. Silicon (S0B, S0N) is where the wavenumber origin is fixed and
is therefore not an independent test; calcite (CAL) and polystyrene (PST) are.</div>""")


def _resolution_slide(res, fig, caption):
    fail_rows = "".join(
        f"<tr><td class=\"mono\">{_esc(f['key'])}</td>"
        f"<td>{_esc(f['laser_wl'])}</td><td class=\"mono\">{_esc(f['optical_path'])}</td>"
        f"<td style=\"text-align:left\">{_esc(f['reason'])}</td></tr>"
        for f in res["failures"])
    fail_table = (
        '<div class="table-wrap"><table class="data"><thead><tr><th>laboratory</th>'
        '<th>&lambda;</th><th>config.</th><th style="text-align:left">reason</th>'
        f"</tr></thead><tbody>{fail_rows}</tbody></table></div>"
        if fail_rows else
        '<p class="muted">All configurations within the CWA boundary.</p>')

    return _slide("12 / 15", f"""
<h2>Result 4: resolution against the CWA acceptance boundary</h2>
<div class="body split">
  <div>
    <div class="stat">{fmt(res['sres_min'], 2)} &ndash;
      {fmt(res['sres_max'], 2)} cm<sup>&minus;1</sup></div>
    <div class="stat-label">ASTM E2529 spectral resolution over
      {res['n_paths']} optical configurations; median
      {fmt(res['sres_median'], 2)}&nbsp;cm<sup>&minus;1</sup>, a factor of
      {fmt(res['spread_factor'], 0)} between the extremes</div>
    <p style="margin-top:0.9rem"><b>{res['n_within']} of {res['n_paths']}</b>
    configurations satisfy the CWA 18133 boundary condition. The remainder, with
    the reason each was rejected:</p>
    {fail_table}
  </div>
  {_figure(fig, caption)}
</div>
<div class="note">Spectral resolution is obtained from the calcite band width via
the ASTM E2529 relation; where the calcite fit was rejected as implausible, no
value is reported rather than an unverified one.</div>""")


def _curves_slide(fig, caption):
    return _slide("11 / 15", f"""
<h2>Result 3: resolution curves (CWA 18133, sections 3 and 4)</h2>
<div class="body" style="grid-template-rows:auto 1fr">
  <p style="margin:0;max-width:88ch"><b>Upper panels:</b> spectral resolution,
  as FWHM in cm<sup>&minus;1</sup>, against Raman shift. Neon lines have
  negligible intrinsic width, so their fitted FWHM against position gives the
  instrument response; the calcite band near 1085.9&nbsp;cm<sup>&minus;1</sup>,
  converted through the ASTM E2529 relation, supplies the single scale factor
  that turns that curve into spectral resolution.
  <b>Lower panels:</b> the ratio of spectral distribution to spectral resolution
  (SpeD:SRes), that is, how many points of the calibrated axis fall within one
  resolution element &mdash; a check that the sampling is adequate for the
  resolution actually achieved.</p>
  {_figure(fig, caption)}
</div>
<div class="note">Curves are evaluated only within the range covered by fitted
neon lines; the low-order polynomial is not extrapolated beyond that support.
Configurations whose calcite fit was rejected have no spectral resolution curve
and are not drawn.</div>""")


def _examples_slide(worked_examples, per_material):
    """Side-by-side outcome for the configurations walked through earlier,
    broken down by reference material."""
    cards = []
    for label, row, slot in worked_examples or []:
        table = per_material.get(slot)
        if table is None or table.empty:
            cards.append(f"""
<div class="card">
  <h3>{_esc(label)}</h3>
  <p class="muted">No verification peaks scored for this configuration.</p>
</div>""")
            continue

        body_rows = []
        for _, r in table.iterrows():
            improved = (np.isfinite(r["improvement_pct"])
                        and r["improvement_pct"] > 0)
            cls = "good" if improved else "bad"
            body_rows.append(
                f"<tr><td>{_esc(MATERIAL_LABELS.get(r['sample'], r['sample']))}</td>"
                f"<td>{int(r['n'])}</td>{_num(r['before'], 2)}"
                f"{_num(r['final'], 2, cls)}"
                f'<td class="{cls}">{fmt_pct(r["improvement_pct"])}</td></tr>')

        overall_ok = (row is not None and np.isfinite(row["improvement_pct"])
                      and row["improvement_pct"] > 0)
        cards.append(f"""
<div class="{'card' if overall_ok else 'card warn'}">
  <h3>{_esc(label)}</h3>
  <div class="table-wrap"><table class="data"><thead><tr>
    <th>material</th><th>n</th><th>before</th><th>after</th><th>change</th>
  </tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>
</div>""")

    body = "".join(cards) or '<p class="muted">No configurations selected.</p>'
    return _slide("13 / 15", f"""
<h2>The example configurations, by reference material</h2>
<div class="body cols-{min(len(cards), 3) if cards else 2}">{body}</div>
<div class="note">Median absolute deviation of measured peak positions from
 reference sample peaks values, in cm<sup>&minus;1</sup>, before calibration and after the full
correction. Silicon (S0B, S0N) is where the wavenumber origin is fixed and is not
an independent test; calcite (CAL) and polystyrene (PST) are.</div>""")


def _limitations_slide(gross, artifact_cm1, samples):
    pst = samples.loc[samples["sample"] == "PST"].sort_values("stage")
    pst_txt = " &rarr; ".join(fmt(v, 3) for v in pst["median"]) or "&mdash;"
    return _slide("14 / 15", f"""
<h2>Limitations of the present analysis</h2>
<div class="body cols-3">
  <div class="card warn">
    <h3>Peak assignment artefacts</h3>
    <p>{gross['n_gross']} of {gross['n_rows']} evaluated peaks deviate by more than
    {artifact_cm1:.0f}&nbsp;cm<sup>&minus;1</sup> from their reference, up to
    {fmt(gross['max_abs'], 1)}&nbsp;cm<sup>&minus;1</sup>, and
    {gross['n_gross_still_inlier']} of these are not rejected by the outlier
    criterion. These are assignment failures rather than calibration error, and
    they dominate any unfiltered mean or RMSE.</p>
  </div>
  <div class="card">
    <h3>Polystyrene deteriorates</h3>
    <p>Median absolute deviation {pst_txt}&nbsp;cm<sup>&minus;1</sup>. Neon and
    silicon constrain the scale at their own positions; polystyrene is used here
    for verification only, so no constraint enforces agreement with it.</p>
  </div>
  <div class="card">
    <h3>Pre-resampled abscissae</h3>
    <p>Some submissions were exported on a uniform grid by the instrument
    software. The spectral distribution then reflects that grid rather than the
    detector, and is flagged as such rather than reported as a pixel property.</p>
  </div>
  <div class="card">
    <h3>Reference line coverage</h3>
    <p>The number of usable neon lines differs considerably between
    configurations, and coverage near the silicon wavelength is sparse for some.
    Accuracy there is limited by the measurements rather than by the procedure.</p>
  </div>
  <div class="card warn">
    <h3>Evaluation re-fits peaks at every stage</h3>
    <p>Relative intensity calibration only rescales intensity; it never moves
    the wavenumber axis. But the <i>evaluation</i> independently re-locates each
    peak on the spectrum belonging to its stage, and the y-calibration stage's
    spectrum is first trimmed to the intensity certificate's validity range and
    then intensity-rescaled before that re-fit. A peak position can therefore
    shift slightly between the x-calibrated and y-calibrated rows of the same
    configuration &mdash; most visibly for broad or edge-adjacent calcite bands
    &mdash; even though calibration itself did not move it. This is a property
    of the scoring procedure, not of the calibration.</p>
  </div>
</div>""")


def _recommendations_slide(ctx=None):
    """Implementation experience and what it suggests for the protocol."""
    ctx = ctx or {}
    interpolator = ctx.get("interpolator", "?")
    return _slide("15 / 15", f"""
<h2>Implementation experience and recommendations</h2>
<div class="body cols-2">
  <div>
    <h3 style="font-family:ui-monospace,monospace;font-size:0.72rem;
      letter-spacing:0.05em;text-transform:uppercase;color:var(--teal);
      margin:0 0 0.5rem">What the implementation required beyond the text</h3>
    <ul class="plain">
      <li><b>The polyharmonic spline recommended by CWA 18133 §6.1(d) did not
      perform well in practice.</b> A polynomial fit through the same matched
      neon lines was consistently more stable, particularly beyond the
      reference-line span, where the spline is prone to unphysical excursions
      that a low-order polynomial does not exhibit. This run uses
      <span class="mono">{_esc(interpolator)}</span>.</li>
      <li><b>Peak assignment is the hard step.</b> The protocol states it in one
      sentence, but when the initial scale error approaches the neon line spacing
      every method misassigns some peaks. A robust, outlier-tolerant procedure
      with a documented rejection criterion is essential.</li>
      <li><b>Extrapolation must be bounded.</b> Neon lines do not extend to the
      C&ndash;H stretching region; an unconstrained fitted function diverges
      there. Continuing the edge correction at constant offset is what makes the
      result usable across the full range.</li>
      <li><b>The wavenumber scale must remain monotonic</b>, which an
      unconstrained interpolating function does not guarantee.</li>
      <li><b>A single calcite point carries the resolution curve,</b> so it needs
      a plausibility check: spectral resolution cannot fall below the neon-derived
      instrument response.</li>
    </ul>
  </div>
  <div>
    <h3 style="font-family:ui-monospace,monospace;font-size:0.72rem;
      letter-spacing:0.05em;text-transform:uppercase;color:var(--red);
      margin:0 0 0.5rem">Suggestions for a future revision</h3>
    <ul class="plain">
      <li>Reconsider the recommendation to use a polyharmonic spline for the
      wavelength interpolation (§6.1(d)); on this dataset a plain polynomial
      fit was the more robust choice and should at least be offered as an
      accepted alternative.</li>
      <li>Specify the assignment procedure and require reporting of the residual
      statistics and surviving line count as calibration quality indicators.</li>
      <li>Require reference line coverage around the silicon wavelength, or define
      the fallback when it falls in a gap.</li>
      <li>Define extrapolation behaviour explicitly and flag spectral regions
      outside reference support.</li>
      <li>Add acceptance criteria for the verification step: the protocol
      prescribes verification samples but no statistic or threshold.</li>
      <li>Mandate an open, self-describing calibration file format; content alone
      is specified today, which invites language-specific serialisations that
      other tools cannot read.</li>
    </ul>
    <div class="card" style="margin-top:0.6rem">
      <h3>References</h3>
      <ol class="refs" style="margin:0;padding-left:1.1rem">
        <li>{CITATION}
          <a href="{LINKS['ramanchada2_doi']}">doi:10.1002/jrs.6789</a></li>
        <li><a href="{LINKS['cwa']}">CWA 18133:2024</a> &middot;
          <a href="{LINKS['vamas']}">VAMAS TWA 42</a></li>
        <li><a href="{LINKS['ramanchada2']}">ramanchada2</a> &middot;
          <a href="{LINKS['pipeline']}">pipeline</a> &middot;
          <a href="{LINKS['spectrastream']}">SpectraStream</a> &middot;
          <a href="{LINKS['app']}">spectra.adma.ai/stream</a></li>
      </ol>
    </div>
  </div>
</div>
<div class="note">Software is open source; the ILC measurement data are
not publicly available.</div>""")


def render_deck(ctx, ne, samples, overall, resolution,
                gross, artifact_cm1=20.0, figures=None,
                ycal=None, materials=None, worked_examples=None,
                per_material=None, samples_by_laser=None,
                participants_table=None):
    """Assemble the deck as one HTML document.

    `figures` maps a slot name to (filename, caption) for pictures written into
    the `figures/` directory beside the deck.
    """
    figures = figures or {}
    ctx = dict(ctx)
    ctx.setdefault("spread_factor", resolution.get("spread_factor", math.nan))

    global _CACHE_BUST
    _CACHE_BUST = f"?v={int(time.time())}"
    if materials is None:
        materials = sorted(samples["sample"].unique()) if len(samples) else []

    def fig(name):
        return figures.get(name, (None, "figure not available"))

    slides = [
        _title_slide(ctx),
        _participants_slide(participants_table),
        _tools_slide(),
        _pipeline_slide(),
        _app_slide(fig("spectrastream_derive"), fig("spectrastream_verify")),
        _method_slide(ctx),
        _ycal_method_slide(ycal, *fig("intensity_correction"),
                           *fig("intensity_reference")),
        *[_worked_example_slide(lbl, st, figures, slot, is_first=(i == 0))
          for i, (lbl, st, slot) in enumerate(worked_examples or [])],
        _neon_slide(ne, *fig("neon")),
        _samples_slide(samples, overall, artifact_cm1, *fig("samples"),
                       by_laser=samples_by_laser),
        _materials_slide(samples, figures, materials),
        _curves_slide(*fig("resolution_curves")),
        _resolution_slide(resolution, *fig("resolution_spread")),
        _examples_slide(worked_examples, per_material or {}),
        _limitations_slide(gross, artifact_cm1, samples),
        _recommendations_slide(ctx),
    ]
    # Slide tags are numbered here, from actual position and count, rather
    # than hand-maintained per _slide() call - the numbering cannot drift out
    # of sync with the real sequence when a slide is added, removed or
    # reordered, which is exactly what happened before this pass.
    total = len(slides)
    slides = [
        re.sub(r'(<span class="slide-tag">)[^<]*(</span>)',
              rf'\g<1>{i} / {total}\g<2>', s, count=1)
        for i, s in enumerate(slides, start=1)
    ]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(ctx['title'])}</title>
<style>{STYLE}</style></head>
<body><div class="deck">
<div class="deck-header"><span>{_esc(ctx['meeting'])}</span>
<span>VAMAS TWA42 Project 6 &middot; <b>{_esc(ctx['generated'])}</b></span></div>
{''.join(slides)}
</div></body></html>"""
