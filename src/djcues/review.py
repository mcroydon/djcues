"""Review HTML generation — interactive review page for cue proposals."""

from __future__ import annotations

import html
import json
from datetime import datetime

from djcues.constants import CUE_SYSTEM_BY_PAD, KIND_TO_PAD
from djcues.models import CueProposal, Track
from djcues.viz import _PAGE_CSS, _render_track_body


def create_session(
    playlist_name: str,
    playlist_id: int,
    tracks_and_proposals: list[tuple[Track, CueProposal]],
    memory_offset_bars: int = 16,
    loop_length_bars: int = 4,
) -> dict:
    """Create a session dict from tracks and their cue proposals.

    The returned dict is JSON-serializable and follows the session schema
    used for persisting review state.
    """
    tracks_dict: dict[str, dict] = {}

    for track, proposal in tracks_and_proposals:
        has_existing_cues = any(c.kind > 0 for c in track.cues)

        # Hot cues keyed by pad letter
        cues_dict: dict[str, dict] = {}
        for hc in proposal.hot_cues:
            pad = KIND_TO_PAD.get(hc.kind)
            if pad is None:
                continue
            cues_dict[pad] = {
                "position_ms": hc.position_ms,
                "loop_end_ms": hc.loop_end_ms,
                "status": "pending",
            }

        # Memory cues keyed by 1-indexed string
        memory_cues_dict: dict[str, dict] = {}
        for i, mc in enumerate(proposal.memory_cues):
            memory_cues_dict[str(i + 1)] = {
                "position_ms": mc.position_ms,
                "loop_end_ms": mc.loop_end_ms,
                "status": "pending",
            }

        tracks_dict[str(track.id)] = {
            "title": track.title,
            "bpm": track.bpm,
            "first_beat_ms": track.beat_grid.first_beat_ms,
            "status": "pending",
            "has_existing_cues": has_existing_cues,
            "cues": cues_dict,
            "memory_cues": memory_cues_dict,
        }

    return {
        "playlist": playlist_name,
        "playlist_id": playlist_id,
        "created": datetime.now().replace(microsecond=0).isoformat(),
        "settings": {
            "memory_offset_bars": memory_offset_bars,
            "loop_length_bars": loop_length_bars,
        },
        "tracks": tracks_dict,
    }


def render_review_html(
    playlist_name: str,
    tracks_and_proposals: list[tuple[Track, CueProposal]],
    session_path: str,
    server_url: str,
) -> str:
    """Generate an interactive HTML review page for cue proposals.

    The page extends the viz module's styling with review-specific controls
    for accepting, skipping, and adjusting individual cues. All actions
    communicate with the review server via fetch() POST requests.
    """
    escaped_name = html.escape(playlist_name)
    count = len(tracks_and_proposals)
    escaped_session_path = html.escape(session_path)

    # Build track cards with data attributes for JS interaction
    track_cards = []
    for track, proposal in tracks_and_proposals:
        has_existing = any(c.kind > 0 for c in track.cues)
        body = _render_track_body(track, proposal, compare=has_existing)

        # Build cue positions JSON for the data-cues attribute
        cues_data: dict[str, dict] = {}
        for hc in proposal.hot_cues:
            pad = KIND_TO_PAD.get(hc.kind)
            if pad is None:
                continue
            cues_data[pad] = {
                "position_ms": hc.position_ms,
                "loop_end_ms": hc.loop_end_ms,
            }

        cues_json = html.escape(json.dumps(cues_data), quote=True)

        warning_badge = ""
        if has_existing:
            warning_badge = (
                '<span class="overwrite-badge" '
                'title="This track has existing cues that will be overwritten">'
                "OVERWRITE</span>"
            )

        track_cards.append(
            f'<div class="track-card review-card" '
            f'data-track-id="{track.id}" '
            f'data-bpm="{track.bpm}" '
            f'data-first-beat-ms="{track.beat_grid.first_beat_ms}" '
            f'data-duration-ms="{track.duration_ms}" '
            f"data-cues='{cues_json}'>"
            f'<div class="review-controls">'
            f'<div class="review-controls-left">'
            f'<span class="status-indicator" data-status="pending">pending</span>'
            f"{warning_badge}"
            f"</div>"
            f'<div class="review-controls-right">'
            f'<button class="btn btn-accept" onclick="acceptTrack(\'{track.id}\')">Accept</button>'
            f'<button class="btn btn-skip" onclick="skipTrack(\'{track.id}\')">Skip</button>'
            f"</div>"
            f"</div>"
            f"{body}"
            f"</div>"
        )

    cards_html = "\n".join(track_cards)

    review_css = _REVIEW_CSS
    review_js = _render_review_js(server_url)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>djcues review &mdash; {escaped_name}</title>
<style>{_PAGE_CSS}</style>
<style>{review_css}</style>
</head>
<body>
<div class="sticky-header">
  <div class="sticky-header-content">
    <div class="sticky-header-left">
      <h1>{escaped_name}</h1>
      <p class="meta">{count} tracks &middot; Session: {escaped_session_path}</p>
    </div>
    <div class="sticky-header-center">
      <div class="summary-bar">
        <span class="summary-item" id="count-pending">0 pending</span>
        <span class="summary-item" id="count-accepted">0 accepted</span>
        <span class="summary-item" id="count-skipped">0 skipped</span>
        <span class="summary-item" id="count-adjusted">0 adjusted</span>
      </div>
    </div>
    <div class="sticky-header-right">
      <button class="btn btn-accept-all" onclick="acceptAll()">Accept All</button>
      <div class="apply-command" title="Click to copy">
        <code id="apply-command-text">uv run djcues apply {escaped_session_path}</code>
        <button class="btn btn-copy" onclick="copyApplyCommand()">Copy</button>
      </div>
    </div>
  </div>
</div>
<div class="review-body">
{cards_html}
</div>
<script>
{review_js}
</script>
</body>
</html>"""


_REVIEW_CSS = """
  /* Sticky header */
  .sticky-header {
    position: sticky;
    top: 0;
    z-index: 100;
    background: #12122a;
    border-bottom: 1px solid #2a2a3e;
    padding: 12px 24px;
    margin: -24px -24px 24px -24px;
  }
  .sticky-header-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }
  .sticky-header-left h1 { font-size: 1.3rem; margin-bottom: 0; }
  .sticky-header-left .meta { font-size: 0.8rem; color: #888; }
  .sticky-header-center { flex: 1; text-align: center; }
  .sticky-header-right { display: flex; align-items: center; gap: 12px; }

  /* Summary bar */
  .summary-bar {
    display: inline-flex;
    gap: 16px;
    font-size: 0.85rem;
  }
  .summary-item { color: #888; }
  #count-pending { color: #ffc107; }
  #count-accepted { color: #28a745; }
  #count-skipped { color: #dc3545; }
  #count-adjusted { color: #17a2b8; }

  /* Apply command */
  .apply-command {
    display: flex;
    align-items: center;
    gap: 6px;
    background: #1e1e3a;
    border: 1px solid #2a2a3e;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .apply-command code {
    color: #aaa;
    font-family: monospace;
    font-size: 0.8rem;
  }

  /* Buttons */
  .btn {
    border: none;
    border-radius: 4px;
    padding: 6px 14px;
    font-size: 0.85rem;
    cursor: pointer;
    font-weight: 600;
    transition: opacity 0.15s;
  }
  .btn:hover { opacity: 0.85; }
  .btn-accept { background: #28a745; color: #fff; }
  .btn-skip { background: #dc3545; color: #fff; }
  .btn-accept-all { background: #28a745; color: #fff; }
  .btn-copy { background: #444; color: #ddd; padding: 4px 8px; font-size: 0.75rem; }

  /* Review card controls */
  .review-card { position: relative; }
  .review-controls {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    padding-bottom: 12px;
    border-bottom: 1px solid #2a2a3e;
  }
  .review-controls-left { display: flex; align-items: center; gap: 10px; }
  .review-controls-right { display: flex; gap: 8px; }

  /* Status indicator */
  .status-indicator {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .status-indicator[data-status="pending"] { background: #ffc10733; color: #ffc107; }
  .status-indicator[data-status="accepted"] { background: #28a74533; color: #28a745; }
  .status-indicator[data-status="skipped"] { background: #dc354533; color: #dc3545; }
  .status-indicator[data-status="adjusted"] { background: #17a2b833; color: #17a2b8; }

  /* Overwrite warning badge */
  .overwrite-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.7rem;
    font-weight: 700;
    background: #e67e2233;
    color: #e67e22;
    letter-spacing: 0.5px;
  }

  /* Review body (push below sticky header) */
  .review-body { padding-top: 8px; }

  /* Selected cue marker */
  .hot-cue-marker.selected {
    border-left-width: 4px !important;
    filter: brightness(1.3);
  }

  /* Existing cue markers are non-interactive */
  .hot-cue-marker.existing,
  .mem-cue-marker.existing {
    cursor: default;
    opacity: 0.6;
  }
"""


def _render_review_js(server_url: str) -> str:
    """Render the review page JavaScript with the given server URL."""
    escaped_url = server_url.replace("\\", "\\\\").replace("'", "\\'")
    return f"""
'use strict';

const SERVER = '{escaped_url}';
let selectedMarker = null;
let selectedTrackCard = null;

// --- Status updates ---

function updateSummaryCounts() {{
  const cards = document.querySelectorAll('.review-card');
  const counts = {{ pending: 0, accepted: 0, skipped: 0, adjusted: 0 }};
  cards.forEach(card => {{
    const indicator = card.querySelector('.status-indicator');
    const status = indicator.getAttribute('data-status');
    if (counts.hasOwnProperty(status)) counts[status]++;
  }});
  document.getElementById('count-pending').textContent = counts.pending + ' pending';
  document.getElementById('count-accepted').textContent = counts.accepted + ' accepted';
  document.getElementById('count-skipped').textContent = counts.skipped + ' skipped';
  document.getElementById('count-adjusted').textContent = counts.adjusted + ' adjusted';
}}

function setTrackStatus(trackId, status) {{
  const card = document.querySelector('[data-track-id="' + trackId + '"]');
  if (!card) return;
  const indicator = card.querySelector('.status-indicator');
  indicator.setAttribute('data-status', status);
  indicator.textContent = status;
  updateSummaryCounts();
}}

// --- Track actions ---

function acceptTrack(trackId) {{
  setTrackStatus(trackId, 'accepted');
  fetch(SERVER + '/session/track/' + trackId + '/status', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ status: 'accepted' }})
  }});
}}

function skipTrack(trackId) {{
  setTrackStatus(trackId, 'skipped');
  fetch(SERVER + '/session/track/' + trackId + '/status', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ status: 'skipped' }})
  }});
}}

function acceptAll() {{
  document.querySelectorAll('.review-card').forEach(card => {{
    const trackId = card.getAttribute('data-track-id');
    const indicator = card.querySelector('.status-indicator');
    const current = indicator.getAttribute('data-status');
    if (current === 'pending') {{
      acceptTrack(trackId);
    }}
  }});
}}

// --- Copy apply command ---

function copyApplyCommand() {{
  const text = document.getElementById('apply-command-text').textContent;
  navigator.clipboard.writeText(text).then(() => {{
    const btn = document.querySelector('.btn-copy');
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => {{ btn.textContent = orig; }}, 1500);
  }});
}}

// --- Per-cue selection and adjustment ---

function deselectMarker() {{
  if (selectedMarker) {{
    selectedMarker.classList.remove('selected');
    selectedMarker = null;
    selectedTrackCard = null;
  }}
}}

document.addEventListener('click', function(e) {{
  const marker = e.target.closest('.hot-cue-marker');
  if (marker) {{
    // Only allow selecting proposed cue markers, not existing ones
    if (marker.classList.contains('existing')) return;
    e.stopPropagation();
    deselectMarker();
    marker.classList.add('selected');
    selectedMarker = marker;
    selectedTrackCard = marker.closest('.review-card');
    return;
  }}
  // Click elsewhere deselects
  deselectMarker();
}});

document.addEventListener('keydown', function(e) {{
  if (!selectedMarker || !selectedTrackCard) return;

  const card = selectedTrackCard;
  const trackId = card.getAttribute('data-track-id');
  const bpm = parseFloat(card.getAttribute('data-bpm'));
  const firstBeatMs = parseFloat(card.getAttribute('data-first-beat-ms'));
  const durationMs = parseFloat(card.getAttribute('data-duration-ms'));
  const msPerBeat = 60000 / bpm;
  const msPerBar = msPerBeat * 4;

  // Get pad letter from the marker label
  const labelEl = selectedMarker.querySelector('.marker-label');
  if (!labelEl) return;
  const pad = labelEl.textContent.trim();

  // Read current cues data
  let cuesData = {{}};
  try {{ cuesData = JSON.parse(card.getAttribute('data-cues')); }} catch(ex) {{}}
  const cueInfo = cuesData[pad];
  if (!cueInfo) return;

  if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {{
    e.preventDefault();
    const direction = e.key === 'ArrowRight' ? 1 : -1;
    let newPos = cueInfo.position_ms + direction * msPerBar;

    // Snap to beat grid
    const rawBeat = (newPos - firstBeatMs) / msPerBeat + 1;
    const snappedBeat = Math.max(1, Math.round(rawBeat));
    newPos = firstBeatMs + (snappedBeat - 1) * msPerBeat;

    // Clamp to track bounds
    newPos = Math.max(0, Math.min(newPos, durationMs));

    // Update the cue data
    cueInfo.position_ms = newPos;
    card.setAttribute('data-cues', JSON.stringify(cuesData));

    // Update marker visual position
    const leftPct = (newPos / durationMs) * 100;
    selectedMarker.style.left = leftPct.toFixed(4) + '%';

    // Update loop range if present
    if (cueInfo.loop_end_ms !== null) {{
      const loopDelta = cueInfo.loop_end_ms - (cueInfo.position_ms - direction * msPerBar + direction * msPerBar);
      // Keep same loop length
    }}

    // Mark track as adjusted
    setTrackStatus(trackId, 'adjusted');

    // POST to server
    fetch(SERVER + '/session/track/' + trackId + '/cue/' + pad, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ position_ms: newPos, status: 'adjusted' }})
    }});
  }}

  if (e.key === 'Delete' || e.key === 'Backspace') {{
    e.preventDefault();
    // Skip this cue
    fetch(SERVER + '/session/track/' + trackId + '/cue/' + pad, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ status: 'skipped' }})
    }});
    // Visually hide the marker
    selectedMarker.style.opacity = '0.3';
    deselectMarker();
    setTrackStatus(trackId, 'adjusted');
  }}

  if (e.key === 'Escape') {{
    deselectMarker();
  }}
}});

// Initialize summary counts on load
updateSummaryCounts();
"""
