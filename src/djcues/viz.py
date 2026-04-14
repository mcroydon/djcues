"""HTML timeline visualizer for djcues cue proposals."""

from __future__ import annotations

import html

from djcues.constants import CUE_SYSTEM_BY_PAD, KIND_TO_PAD
from djcues.models import CuePoint, CueProposal, Track, WaveformPoint

PHRASE_COLORS: dict[str, str] = {
    "Intro": "#6c757d",
    "Up": "#28a745",
    "Down": "#17a2b8",
    "Chorus": "#dc3545",
    "Outro": "#ffc107",
    "Bridge": "#6f42c1",
    "Verse1": "#20c997",
    "Verse2": "#17a2b8",
    "Unknown": "#adb5bd",
}

CUE_COLORS: dict[str, str] = {
    "A": "#2ecc71",
    "B": "#2ecc71",
    "C": "#f1c40f",
    "D": "#e74c3c",
    "E": "#3498db",
    "F": "#9b59b6",
    "G": "#00bcd4",
    "H": "#e67e22",
}


def _format_time(ms: float) -> str:
    """Format milliseconds as M:SS.s"""
    total_seconds = ms / 1000
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:04.1f}"


def _render_phrase_bar(phrases, total_ms: float) -> str:
    """Render the phrase timeline bar as HTML segments."""
    segments = []
    for phrase in phrases:
        left_pct = (phrase.position_ms / total_ms) * 100
        width_pct = (phrase.duration_ms / total_ms) * 100
        color = PHRASE_COLORS.get(phrase.label, PHRASE_COLORS["Unknown"])
        label = html.escape(phrase.label)
        segments.append(
            f'<div class="phrase-segment" style="left:{left_pct:.4f}%;'
            f"width:{width_pct:.4f}%;background:{color};\">"
            f'<span class="phrase-label">{label}</span></div>'
        )
    return "\n".join(segments)


def _render_cue_markers(
    hot_cues: list[CuePoint],
    memory_cues: list[CuePoint],
    total_ms: float,
    css_class_prefix: str = "",
) -> str:
    """Render hot cue markers (above) and memory cue markers (below) the phrase bar."""
    markers = []
    # Track label offsets to nudge overlapping labels
    OVERLAP_THRESHOLD_PCT = 0.3  # positions within this % are considered overlapping
    NUDGE_PX = 14  # pixels to nudge each successive overlapping label

    # Hot cue markers (above the bar)
    prev_hot_pct = -999.0
    hot_nudge_count = 0
    for cue in sorted(hot_cues, key=lambda c: c.position_ms):
        pad = KIND_TO_PAD.get(cue.kind, "?")
        left_pct = (cue.position_ms / total_ms) * 100
        color = CUE_COLORS.get(pad, "#aaa")
        comment = html.escape(cue.comment)
        if abs(left_pct - prev_hot_pct) < OVERLAP_THRESHOLD_PCT:
            hot_nudge_count += 1
        else:
            hot_nudge_count = 0
        prev_hot_pct = left_pct
        label_offset = 4 + hot_nudge_count * NUDGE_PX
        markers.append(
            f'<div class="hot-cue-marker {css_class_prefix}" '
            f'style="left:{left_pct:.4f}%;border-left-color:{color};" '
            f'title="{comment} @ {_format_time(cue.position_ms)}">'
            f'<span class="marker-label" style="color:{color};left:{label_offset}px;">{html.escape(pad)}</span>'
            f"</div>"
        )
        # Loop range indicator for hot cues
        if cue.is_loop and cue.loop_end_ms is not None:
            loop_left = left_pct
            loop_width = ((cue.loop_end_ms - cue.position_ms) / total_ms) * 100
            markers.append(
                f'<div class="loop-range hot-loop {css_class_prefix}" '
                f'style="left:{loop_left:.4f}%;width:{loop_width:.4f}%;'
                f'background:{color};"></div>'
            )

    # Memory cue markers (below the bar)
    prev_mem_pct = -999.0
    mem_nudge_count = 0
    for i, cue in enumerate(sorted(memory_cues, key=lambda c: c.position_ms)):
        left_pct = (cue.position_ms / total_ms) * 100
        # Find which pad this memory cue belongs to via comment matching
        marker_color = "#aaa"
        for pad, slot in CUE_SYSTEM_BY_PAD.items():
            if slot.memory_cue_label == cue.comment:
                marker_color = CUE_COLORS.get(pad, "#aaa")
                break
        comment = html.escape(cue.comment)
        if abs(left_pct - prev_mem_pct) < OVERLAP_THRESHOLD_PCT:
            mem_nudge_count += 1
        else:
            mem_nudge_count = 0
        prev_mem_pct = left_pct
        label_offset = 4 + mem_nudge_count * NUDGE_PX
        markers.append(
            f'<div class="mem-cue-marker {css_class_prefix}" '
            f'style="left:{left_pct:.4f}%;border-left-color:{marker_color};" '
            f'title="{comment} @ {_format_time(cue.position_ms)}">'
            f'<span class="marker-label" style="color:{marker_color};left:{label_offset}px;">{i + 1}</span>'
            f"</div>"
        )
        # Loop range indicator for memory cues
        if cue.is_loop and cue.loop_end_ms is not None:
            loop_left = left_pct
            loop_width = ((cue.loop_end_ms - cue.position_ms) / total_ms) * 100
            markers.append(
                f'<div class="loop-range mem-loop {css_class_prefix}" '
                f'style="left:{loop_left:.4f}%;width:{loop_width:.4f}%;'
                f'background:{marker_color};"></div>'
            )

    return "\n".join(markers)


def _render_confidence_bars(confidence: dict[str, float]) -> str:
    """Render per-slot confidence bars."""
    bars = []
    for pad in "ABCDEFGH":
        conf = confidence.get(pad, 0.0)
        slot = CUE_SYSTEM_BY_PAD.get(pad)
        label = html.escape(slot.hot_cue_label) if slot else pad
        color = CUE_COLORS.get(pad, "#aaa")
        pct = conf * 100
        bars.append(
            f'<div class="conf-row">'
            f'<span class="conf-pad" style="color:{color};">[{pad}]</span>'
            f'<span class="conf-label">{label}</span>'
            f'<div class="conf-bar-bg">'
            f'<div class="conf-bar-fill" style="width:{pct:.0f}%;background:{color};"></div>'
            f"</div>"
            f'<span class="conf-pct">{pct:.0f}%</span>'
            f"</div>"
        )
    return "\n".join(bars)


def _render_waveform(waveform: list[WaveformPoint] | None) -> str:
    """Render the color waveform as an inline SVG (half-waveform, bars grow upward)."""
    if not waveform:
        return ""
    n = len(waveform)
    bar_width = 1
    svg_w = n * bar_width
    svg_h = 32

    bars = []
    for i, pt in enumerate(waveform):
        x = i * bar_width
        bar_h = max(1, int(pt.height * svg_h))
        color = pt.rgb_hex
        # Half-waveform: bars grow upward from bottom
        bars.append(
            f'<rect x="{x}" y="{svg_h - bar_h}" width="{bar_width}" '
            f'height="{bar_h}" fill="{color}" />'
        )

    return (
        f'<svg class="waveform-svg" viewBox="0 0 {svg_w} {svg_h}" '
        f'preserveAspectRatio="none">'
        + "".join(bars)
        + "</svg>"
    )


def _render_timeline_section(
    title: str,
    hot_cues: list[CuePoint],
    memory_cues: list[CuePoint],
    phrases,
    total_ms: float,
    css_class_prefix: str = "",
    waveform: list[WaveformPoint] | None = None,
) -> str:
    """Render one full timeline section (label + hot markers + waveform + phrase bar + mem markers)."""
    phrase_bar = _render_phrase_bar(phrases, total_ms)
    cue_markers = _render_cue_markers(hot_cues, memory_cues, total_ms, css_class_prefix)
    waveform_html = _render_waveform(waveform)
    return f"""
    <div class="timeline-section">
      <h3>{html.escape(title)}</h3>
      <div class="timeline-container">
        {cue_markers}
        <div class="waveform-container">
          {waveform_html}
        </div>
        <div class="phrase-bar">
          {phrase_bar}
        </div>
      </div>
    </div>
    """


_PAGE_CSS = """
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #1a1a2e;
    color: #eee;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 24px;
    line-height: 1.5;
  }
  h1 { font-size: 1.6rem; margin-bottom: 4px; }
  h2 { font-size: 1.1rem; font-weight: 400; color: #aaa; margin-bottom: 16px; }
  h3 { font-size: 1rem; color: #ccc; margin-bottom: 8px; }
  .header { margin-bottom: 24px; }
  .header .meta { color: #888; font-size: 0.9rem; }

  /* Track card (playlist view) */
  .track-card {
    border: 1px solid #2a2a3e;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 28px;
  }
  .track-card .header { margin-bottom: 16px; }

  /* Legend */
  .legend { margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 12px; }
  .legend-item { display: inline-flex; align-items: center; gap: 5px; font-size: 0.85rem; }
  .legend-swatch {
    display: inline-block; width: 14px; height: 14px;
    border-radius: 3px; flex-shrink: 0;
  }

  /* Timeline */
  .timeline-section { margin-bottom: 32px; }
  .timeline-container {
    position: relative;
    height: 200px;
    margin: 0 10px;
  }

  /* Waveform */
  .waveform-container {
    position: absolute;
    top: 40px;
    left: 0; right: 0;
    height: 80px;
    background: #111122;
    border-radius: 4px 4px 0 0;
    overflow: hidden;
  }
  .waveform-svg {
    width: 100%;
    height: 100%;
    display: block;
  }

  /* Phrase bar */
  .phrase-bar {
    position: absolute;
    top: 120px;
    left: 0; right: 0;
    height: 40px;
    background: #2a2a3e;
    border-radius: 0 0 4px 4px;
    overflow: hidden;
  }
  .phrase-segment {
    position: absolute;
    top: 0; height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    border-right: 1px solid rgba(0,0,0,0.3);
  }
  .phrase-label {
    font-size: 0.7rem;
    color: #fff;
    text-shadow: 0 1px 2px rgba(0,0,0,0.6);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: 0 3px;
  }

  /* Hot cue markers (above waveform) */
  .hot-cue-marker {
    position: absolute;
    top: 0;
    width: 0;
    height: 40px;
    border-left: 2px solid;
    z-index: 10;
  }
  .hot-cue-marker .marker-label {
    position: absolute;
    top: -2px;
    left: 4px;
    font-size: 0.75rem;
    font-weight: 700;
    white-space: nowrap;
  }

  /* Memory cue markers (below phrase bar) */
  .mem-cue-marker {
    position: absolute;
    top: 160px;
    width: 0;
    height: 40px;
    border-left: 2px dashed;
    z-index: 10;
  }
  .mem-cue-marker .marker-label {
    position: absolute;
    bottom: -2px;
    left: 4px;
    font-size: 0.75rem;
    font-weight: 700;
    white-space: nowrap;
  }

  /* Loop range bars */
  .loop-range {
    position: absolute;
    height: 4px;
    opacity: 0.5;
    border-radius: 2px;
    z-index: 5;
  }
  .hot-loop { top: 36px; }
  .mem-loop { top: 160px; }

  /* Confidence bars */
  .confidence-section { margin-bottom: 24px; }
  .conf-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }
  .conf-pad { font-weight: 700; font-family: monospace; width: 28px; text-align: center; }
  .conf-label { width: 140px; font-size: 0.85rem; color: #aaa; }
  .conf-bar-bg {
    flex: 1;
    height: 14px;
    background: #2a2a3e;
    border-radius: 3px;
    overflow: hidden;
    max-width: 300px;
  }
  .conf-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s;
  }
  .conf-pct { width: 40px; text-align: right; font-size: 0.85rem; color: #888; }

  /* Notes */
  .notes-section { margin-top: 20px; }
  .notes-section ul { list-style: none; padding-left: 0; }
  .notes-section li {
    font-size: 0.85rem;
    color: #aaa;
    padding: 2px 0;
  }
  .notes-section li::before {
    content: "\\2022\\00a0";
    color: #555;
  }
"""


def _render_track_body(
    track: Track, proposal: CueProposal, compare: bool = False
) -> str:
    """Render the body content for a single track (no page shell)."""
    total_ms = track.duration_ms
    title = html.escape(track.title)
    artist = html.escape(track.artist)
    duration_str = _format_time(total_ms)

    # Phrase legend
    seen_labels: list[str] = []
    for p in track.phrases:
        if p.label not in seen_labels:
            seen_labels.append(p.label)
    legend_items = []
    for label in seen_labels:
        color = PHRASE_COLORS.get(label, PHRASE_COLORS["Unknown"])
        legend_items.append(
            f'<span class="legend-item">'
            f'<span class="legend-swatch" style="background:{color};"></span>'
            f"{html.escape(label)}</span>"
        )
    legend_html = " ".join(legend_items)

    # Timeline sections
    timelines_html = ""
    wf = track.waveform
    if compare and track.cues:
        existing_hot = [c for c in track.cues if c.kind > 0]
        existing_mem = [c for c in track.cues if c.kind == 0]
        timelines_html += _render_timeline_section(
            "Existing Cues", existing_hot, existing_mem,
            track.phrases, total_ms, css_class_prefix="existing", waveform=wf,
        )
        timelines_html += _render_timeline_section(
            "Proposed Cues", proposal.hot_cues, proposal.memory_cues,
            track.phrases, total_ms, css_class_prefix="proposed", waveform=wf,
        )
    else:
        timelines_html += _render_timeline_section(
            "Proposed Cues", proposal.hot_cues, proposal.memory_cues,
            track.phrases, total_ms, waveform=wf,
        )

    confidence_html = _render_confidence_bars(proposal.confidence)

    notes_html = ""
    if proposal.notes:
        notes_items = "\n".join(
            f"<li>{html.escape(note)}</li>" for note in proposal.notes
        )
        notes_html = f'<div class="notes-section"><h3>Placement Notes</h3><ul>{notes_items}</ul></div>'

    return f"""
  <div class="header">
    <h1>{title}</h1>
    <h2>{artist}</h2>
    <p class="meta">BPM: {track.bpm:.1f} &middot; Duration: {duration_str} &middot; Phrases: {len(track.phrases)}</p>
  </div>
  <div class="legend">{legend_html}</div>
  {timelines_html}
  <div class="confidence-section">
    <h3>Confidence</h3>
    {confidence_html}
  </div>
  {notes_html}
"""


def render_timeline(track: Track, proposal: CueProposal, compare: bool = False) -> str:
    """Render a complete HTML page with phrase timeline and cue markers for one track."""
    title = html.escape(track.title)
    body = _render_track_body(track, proposal, compare)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>djcues &mdash; {title}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""


def render_playlist(
    playlist_name: str,
    tracks_and_proposals: list[tuple[Track, CueProposal]],
    compare: bool = False,
) -> str:
    """Render a single HTML page with all tracks in a playlist."""
    escaped_name = html.escape(playlist_name)
    count = len(tracks_and_proposals)

    track_cards = []
    for track, proposal in tracks_and_proposals:
        body = _render_track_body(track, proposal, compare)
        track_cards.append(f'<div class="track-card">{body}</div>')

    cards_html = "\n".join(track_cards)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>djcues &mdash; {escaped_name} ({count} tracks)</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<div class="header" style="margin-bottom:32px;">
  <h1>{escaped_name}</h1>
  <p class="meta">{count} tracks</p>
</div>
{cards_html}
</body>
</html>"""
