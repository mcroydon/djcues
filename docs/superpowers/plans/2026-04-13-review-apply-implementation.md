# Review & Apply Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add interactive browser-based cue review with accept/skip/adjust controls, and a CLI apply command that writes accepted cues to the rekordbox database with auto-backup and overwrite protection.

**Architecture:** Four new modules: `writer.py` (DB writes + backup), `server.py` (local HTTP server for browser communication), `review.py` (interactive HTML generation + session management), plus interactive JavaScript in the browser HTML. Two new CLI commands: `review` and `apply`. The existing `viz.py` rendering functions are reused by `review.py`.

**Tech Stack:** Python 3.10+, pyrekordbox (DB writes via ORM), stdlib `http.server` (local server), vanilla JavaScript (browser interactivity)

**Spec:** `docs/superpowers/specs/2026-04-13-review-apply-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `src/djcues/writer.py` | Create: `backup_database()`, `write_cues_for_track()`, `apply_session()` |
| `src/djcues/server.py` | Create: minimal HTTP server with REST endpoints for session updates |
| `src/djcues/review.py` | Create: `create_session()`, `render_review_html()` — interactive HTML + session JSON |
| `src/djcues/cli.py` | Modify: add `review` and `apply` commands |
| `tests/test_writer.py` | Create: unit tests for backup, cue creation, apply logic |

---

### Task 1: Writer — backup and cue creation

**Files:**
- Create: `src/djcues/writer.py`
- Create: `tests/test_writer.py`

This task builds the core DB write logic independently of the browser UI. It reads a session dict (Python dict matching the JSON schema) and writes cues to the database.

- [ ] **Step 1: Write backup test**

Create `tests/test_writer.py`:

```python
import json
import pathlib
import tempfile

from djcues.writer import backup_database, build_cue_rows


def test_backup_creates_timestamped_copy(tmp_path):
    """backup_database copies the file and returns the backup path."""
    fake_db = tmp_path / "master.db"
    fake_db.write_text("fake database content")

    backup_path = backup_database(fake_db)

    assert backup_path.exists()
    assert backup_path.name.startswith("master.db.djcues-backup-")
    assert backup_path.read_text() == "fake database content"
    assert backup_path.parent == tmp_path


def test_build_cue_rows_creates_hot_and_memory():
    """build_cue_rows returns (hot_cues, memory_cues) dicts ready for DB insert."""
    track_cues = {
        "A": {"position_ms": 77.0, "loop_end_ms": None, "status": "accepted"},
        "B": {"position_ms": 77.0, "loop_end_ms": 7577.0, "status": "accepted"},
        "C": {"position_ms": 30077.0, "loop_end_ms": None, "status": "accepted"},
        "D": {"position_ms": 67577.0, "loop_end_ms": None, "status": "accepted"},
        "E": {"position_ms": 97577.0, "loop_end_ms": None, "status": "accepted"},
        "F": {"position_ms": 127577.0, "loop_end_ms": None, "status": "accepted"},
        "G": {"position_ms": 202577.0, "loop_end_ms": None, "status": "accepted"},
        "H": {"position_ms": 210077.0, "loop_end_ms": 217577.0, "status": "accepted"},
    }
    memory_cues = {
        "1": {"position_ms": 77.0, "loop_end_ms": None, "status": "accepted"},
        "2": {"position_ms": 77.0, "loop_end_ms": 7577.0, "status": "accepted"},
        "3": {"position_ms": 577.0, "loop_end_ms": None, "status": "accepted"},
        "4": {"position_ms": 37577.0, "loop_end_ms": None, "status": "accepted"},
        "5": {"position_ms": 67577.0, "loop_end_ms": None, "status": "accepted"},
        "6": {"position_ms": 97577.0, "loop_end_ms": None, "status": "accepted"},
        "7": {"position_ms": 172577.0, "loop_end_ms": None, "status": "accepted"},
        "8": {"position_ms": 210077.0, "loop_end_ms": 217577.0, "status": "accepted"},
    }

    hot_rows, mem_rows = build_cue_rows(track_cues, memory_cues)

    # 8 hot cues, 8 memory cues
    assert len(hot_rows) == 8
    assert len(mem_rows) == 8

    # Check hot cue A
    a = next(r for r in hot_rows if r["Kind"] == 1)
    assert a["InMsec"] == 77
    assert a["OutMsec"] == -1
    assert a["ColorTableIndex"] == 18
    assert a["Comment"] == "First Beat"

    # Check hot cue B (loop)
    b = next(r for r in hot_rows if r["Kind"] == 2)
    assert b["InMsec"] == 77
    assert b["OutMsec"] == 7577
    assert b["ActiveLoop"] == 0

    # Check hot cue D (Drop, Kind=5)
    d = next(r for r in hot_rows if r["Kind"] == 5)
    assert d["InMsec"] == 67577
    assert d["Comment"] == "Drop"

    # Check memory cue 1
    m1 = mem_rows[0]
    assert m1["Kind"] == 0
    assert m1["InMsec"] == 77
    assert m1["Comment"] == "First Beat"


def test_build_cue_rows_skips_skipped_cues():
    """Cues with status 'skipped' are excluded from the output."""
    track_cues = {
        "A": {"position_ms": 77.0, "loop_end_ms": None, "status": "accepted"},
        "B": {"position_ms": 77.0, "loop_end_ms": 7577.0, "status": "skipped"},
        "C": {"position_ms": 30077.0, "loop_end_ms": None, "status": "accepted"},
        "D": {"position_ms": 67577.0, "loop_end_ms": None, "status": "accepted"},
        "E": {"position_ms": 97577.0, "loop_end_ms": None, "status": "accepted"},
        "F": {"position_ms": 127577.0, "loop_end_ms": None, "status": "accepted"},
        "G": {"position_ms": 202577.0, "loop_end_ms": None, "status": "accepted"},
        "H": {"position_ms": 210077.0, "loop_end_ms": 217577.0, "status": "skipped"},
    }
    memory_cues = {
        "1": {"position_ms": 77.0, "loop_end_ms": None, "status": "accepted"},
        "2": {"position_ms": 77.0, "loop_end_ms": 7577.0, "status": "skipped"},
        "3": {"position_ms": 577.0, "loop_end_ms": None, "status": "accepted"},
        "4": {"position_ms": 37577.0, "loop_end_ms": None, "status": "accepted"},
        "5": {"position_ms": 67577.0, "loop_end_ms": None, "status": "accepted"},
        "6": {"position_ms": 97577.0, "loop_end_ms": None, "status": "accepted"},
        "7": {"position_ms": 172577.0, "loop_end_ms": None, "status": "accepted"},
        "8": {"position_ms": 210077.0, "loop_end_ms": 217577.0, "status": "skipped"},
    }

    hot_rows, mem_rows = build_cue_rows(track_cues, memory_cues)

    assert len(hot_rows) == 6  # B and H skipped
    assert len(mem_rows) == 6  # 2 and 8 skipped
    kinds = {r["Kind"] for r in hot_rows}
    assert 2 not in kinds  # B
    assert 9 not in kinds  # H


def test_build_cue_rows_handles_auto_status():
    """Memory cues with 'auto' status are treated as accepted."""
    track_cues = {
        "A": {"position_ms": 77.0, "loop_end_ms": None, "status": "accepted"},
        "B": {"position_ms": 77.0, "loop_end_ms": 7577.0, "status": "accepted"},
        "C": {"position_ms": 30077.0, "loop_end_ms": None, "status": "adjusted", "original_ms": 37577.0},
        "D": {"position_ms": 67577.0, "loop_end_ms": None, "status": "accepted"},
        "E": {"position_ms": 97577.0, "loop_end_ms": None, "status": "accepted"},
        "F": {"position_ms": 127577.0, "loop_end_ms": None, "status": "accepted"},
        "G": {"position_ms": 202577.0, "loop_end_ms": None, "status": "accepted"},
        "H": {"position_ms": 210077.0, "loop_end_ms": 217577.0, "status": "accepted"},
    }
    memory_cues = {
        "1": {"position_ms": 77.0, "loop_end_ms": None, "status": "accepted"},
        "2": {"position_ms": 77.0, "loop_end_ms": 7577.0, "status": "accepted"},
        "3": {"position_ms": 577.0, "loop_end_ms": None, "status": "auto"},
        "4": {"position_ms": 37577.0, "loop_end_ms": None, "status": "accepted"},
        "5": {"position_ms": 67577.0, "loop_end_ms": None, "status": "accepted"},
        "6": {"position_ms": 97577.0, "loop_end_ms": None, "status": "accepted"},
        "7": {"position_ms": 172577.0, "loop_end_ms": None, "status": "accepted"},
        "8": {"position_ms": 210077.0, "loop_end_ms": 217577.0, "status": "accepted"},
    }

    hot_rows, mem_rows = build_cue_rows(track_cues, memory_cues)
    assert len(mem_rows) == 8  # auto is treated as accepted
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_writer.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'djcues.writer'`

- [ ] **Step 3: Implement writer.py**

Create `src/djcues/writer.py`:

```python
"""Write cue points to the rekordbox database with backup and safety."""

from __future__ import annotations

import json
import pathlib
import shutil
from datetime import datetime
from typing import Any
from uuid import uuid4

from djcues.constants import CUE_SYSTEM, CUE_SYSTEM_BY_PAD

# Pad letter -> memory cue slot index (1-8)
_PAD_TO_MEM_SLOT = {s.pad: str(i + 1) for i, s in enumerate(CUE_SYSTEM)}


def backup_database(db_path: pathlib.Path) -> pathlib.Path:
    """Copy master.db to a timestamped backup file in the same directory.

    Returns the path to the backup file.
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.parent / f"{db_path.name}.djcues-backup-{timestamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def build_cue_rows(
    cues: dict[str, dict],
    memory_cues: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    """Convert session cue data into lists of field dicts for DjmdCue creation.

    Args:
        cues: Hot cue data keyed by pad letter (A-H).
        memory_cues: Memory cue data keyed by slot number (1-8).

    Returns:
        (hot_cue_rows, memory_cue_rows) — each row is a dict of DjmdCue fields.
    """
    hot_rows: list[dict] = []
    mem_rows: list[dict] = []

    for pad, slot in CUE_SYSTEM_BY_PAD.items():
        cue_data = cues.get(pad)
        if not cue_data or cue_data.get("status") == "skipped":
            continue

        pos_ms = int(cue_data["position_ms"])
        loop_end = cue_data.get("loop_end_ms")
        out_ms = int(loop_end) if loop_end is not None else -1

        hot_rows.append({
            "Kind": slot.kind,
            "InMsec": pos_ms,
            "OutMsec": out_ms,
            "InFrame": 0,
            "InMpegFrame": 0,
            "InMpegAbs": 0,
            "OutFrame": -1 if out_ms == -1 else 0,
            "OutMpegFrame": -1 if out_ms == -1 else 0,
            "OutMpegAbs": -1 if out_ms == -1 else 0,
            "Color": slot.hot_cue_color,
            "ColorTableIndex": slot.hot_cue_color_table_index,
            "ActiveLoop": 0 if slot.is_loop else -1,
            "Comment": slot.hot_cue_label,
            "BeatLoopSize": 0,
            "CueMicrosec": 0,
        })

    for slot_num_str, mem_data in memory_cues.items():
        if not mem_data or mem_data.get("status") == "skipped":
            continue
        # "auto" status is treated as accepted

        slot_idx = int(slot_num_str) - 1
        if slot_idx < 0 or slot_idx >= len(CUE_SYSTEM):
            continue
        slot = CUE_SYSTEM[slot_idx]

        pos_ms = int(mem_data["position_ms"])
        loop_end = mem_data.get("loop_end_ms")
        out_ms = int(loop_end) if loop_end is not None else -1

        mem_rows.append({
            "Kind": 0,  # memory cue
            "InMsec": pos_ms,
            "OutMsec": out_ms,
            "InFrame": 0,
            "InMpegFrame": 0,
            "InMpegAbs": 0,
            "OutFrame": -1 if out_ms == -1 else 0,
            "OutMpegFrame": -1 if out_ms == -1 else 0,
            "OutMpegAbs": -1 if out_ms == -1 else 0,
            "Color": slot.memory_cue_color,
            "ColorTableIndex": slot.memory_cue_color_table_index,
            "ActiveLoop": 0 if slot.is_loop else -1,
            "Comment": slot.memory_cue_label,
            "BeatLoopSize": 0,
            "CueMicrosec": 0,
        })

    return hot_rows, mem_rows


def write_cues_for_track(
    db: Any,
    content: Any,
    hot_rows: list[dict],
    mem_rows: list[dict],
    overwrite: bool = False,
) -> int:
    """Write cue point rows to the database for a single track.

    Args:
        db: The Rekordbox6Database instance.
        content: The DjmdContent object for the track.
        hot_rows: Hot cue field dicts from build_cue_rows.
        mem_rows: Memory cue field dicts from build_cue_rows.
        overwrite: If True, delete existing cues before writing.

    Returns:
        Number of cues written.
    """
    from pyrekordbox.db6 import tables

    if overwrite:
        existing = list(db.get_cue(ContentID=content.ID))
        for cue in existing:
            db.delete(cue)

    count = 0
    for row in hot_rows + mem_rows:
        cue_id = db.generate_unused_id(tables.DjmdCue)
        cue_uuid = str(uuid4())
        cue = tables.DjmdCue.create(
            ID=str(cue_id),
            ContentID=str(content.ID),
            ContentUUID=content.UUID,
            UUID=cue_uuid,
            **row,
        )
        db.add(cue)
        count += 1

    return count


def apply_session(
    session_path: pathlib.Path,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """Apply a review session to the rekordbox database.

    Returns a summary dict with counts and backup path.
    """
    import click
    from djcues.db import get_db

    session = json.loads(session_path.read_text())
    tracks_data = session.get("tracks", {})

    # Count states
    accepted = 0
    adjusted = 0
    skipped = 0
    overwrite_tracks: list[str] = []

    for track_id, tdata in tracks_data.items():
        status = tdata.get("status", "pending")
        if status == "skipped":
            skipped += 1
        elif status == "adjusted":
            adjusted += 1
            if tdata.get("has_existing_cues"):
                overwrite_tracks.append(tdata.get("title", track_id))
        elif status == "accepted":
            accepted += 1
            if tdata.get("has_existing_cues"):
                overwrite_tracks.append(tdata.get("title", track_id))
        # pending tracks are not written

    total_write = accepted + adjusted
    click.echo(f"\n{session.get('playlist', '?')} — {accepted} accepted, {adjusted} adjusted, {skipped} skipped")
    click.echo(f"{total_write * 16} cues to write across {total_write} tracks")

    if overwrite_tracks:
        click.echo(f"\n{len(overwrite_tracks)} track(s) have existing cues that will be replaced:")
        for title in overwrite_tracks:
            click.echo(f"  - {title}")

    if dry_run:
        click.echo("\n(dry run — no changes made)")
        return {"written": 0, "backup": None}

    if overwrite_tracks and not force:
        if not click.confirm("\nContinue?"):
            click.echo("Aborted.")
            return {"written": 0, "backup": None}

    # Backup
    db = get_db()
    db_path = pathlib.Path(db.db_path)
    backup_path = backup_database(db_path)
    click.echo(f"\nBackup saved to: {backup_path}")

    # Write
    written_tracks = 0
    written_cues = 0

    for track_id, tdata in tracks_data.items():
        status = tdata.get("status", "pending")
        if status not in ("accepted", "adjusted"):
            continue

        hot_rows, mem_rows = build_cue_rows(
            tdata.get("cues", {}),
            tdata.get("memory_cues", {}),
        )

        # Find the content object
        content = db.get_content(ID=int(track_id))
        if content is None:
            click.echo(f"  Warning: track {track_id} not found in DB, skipping", err=True)
            continue

        has_existing = tdata.get("has_existing_cues", False)
        count = write_cues_for_track(db, content, hot_rows, mem_rows, overwrite=has_existing)
        db.commit()
        written_tracks += 1
        written_cues += count
        click.echo(f"  Wrote {count} cues for {tdata.get('title', track_id)}")

    click.echo(f"\nDone: {written_cues} cues across {written_tracks} tracks")
    click.echo(f"Backup at: {backup_path}")

    return {"written": written_cues, "backup": str(backup_path)}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_writer.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/djcues/writer.py tests/test_writer.py
git commit -m "feat: add writer module — backup, cue row building, DB write"
```

---

### Task 2: Session management and review HTML generation

**Files:**
- Create: `src/djcues/review.py`

This task builds the session JSON creation and the interactive HTML that extends the existing viz rendering. The HTML includes JavaScript for accept/skip/adjust controls that communicate with the local server via fetch() calls.

- [ ] **Step 1: Implement review.py**

Create `src/djcues/review.py`:

```python
"""Interactive review HTML generation and session management."""

from __future__ import annotations

import html as html_mod
import json
import pathlib
from datetime import datetime

from djcues.constants import CUE_SYSTEM, CUE_SYSTEM_BY_PAD, KIND_TO_PAD
from djcues.models import CueProposal, Track
from djcues.viz import _PAGE_CSS, _render_track_body


def create_session(
    playlist_name: str,
    playlist_id: int,
    tracks_and_proposals: list[tuple[Track, CueProposal]],
    memory_offset_bars: int = 16,
    loop_length_bars: int = 4,
) -> dict:
    """Create a session dict from tracks and their proposals.

    Returns a dict matching the session JSON schema.
    """
    session = {
        "playlist": playlist_name,
        "playlist_id": playlist_id,
        "created": datetime.now().isoformat(timespec="seconds"),
        "settings": {
            "memory_offset_bars": memory_offset_bars,
            "loop_length_bars": loop_length_bars,
        },
        "tracks": {},
    }

    for track, proposal in tracks_and_proposals:
        has_existing = any(c.kind > 0 for c in track.cues)

        cues = {}
        for hc in proposal.hot_cues:
            pad = KIND_TO_PAD.get(hc.kind)
            if pad:
                cues[pad] = {
                    "position_ms": hc.position_ms,
                    "loop_end_ms": hc.loop_end_ms,
                    "status": "pending",
                }

        memory_cues = {}
        for i, mc in enumerate(proposal.memory_cues):
            slot_num = str(i + 1)
            memory_cues[slot_num] = {
                "position_ms": mc.position_ms,
                "loop_end_ms": mc.loop_end_ms,
                "status": "pending",
            }

        session["tracks"][str(track.id)] = {
            "title": track.title,
            "bpm": track.bpm,
            "first_beat_ms": track.beat_grid.first_beat_ms,
            "status": "pending",
            "has_existing_cues": has_existing,
            "cues": cues,
            "memory_cues": memory_cues,
        }

    return session


def render_review_html(
    playlist_name: str,
    tracks_and_proposals: list[tuple[Track, CueProposal]],
    session_path: str,
    server_url: str,
) -> str:
    """Render the interactive review HTML page.

    This extends the static viz with interactive JavaScript controls
    for accept/skip/adjust that POST to the local server.
    """
    escaped_name = html_mod.escape(playlist_name)
    count = len(tracks_and_proposals)

    track_cards = []
    for track, proposal in tracks_and_proposals:
        track_id = str(track.id)
        has_existing = any(c.kind > 0 for c in track.cues)
        body = _render_track_body(track, proposal)

        # Wrap in a review card with controls
        warning = ""
        if has_existing:
            warning = '<span class="overwrite-badge">has existing cues</span>'

        # Embed beat grid info as data attributes for cue adjustment
        beat_data = (
            f'data-bpm="{track.bpm}" '
            f'data-first-beat-ms="{track.beat_grid.first_beat_ms}" '
            f'data-duration-ms="{track.duration_ms}"'
        )

        # Embed cue positions as JSON for JS to use
        cue_positions = {}
        for hc in proposal.hot_cues:
            pad = KIND_TO_PAD.get(hc.kind)
            if pad:
                slot = CUE_SYSTEM_BY_PAD[pad]
                cue_positions[pad] = {
                    "position_ms": hc.position_ms,
                    "loop_end_ms": hc.loop_end_ms,
                    "memory_offset_bars": slot.memory_offset_bars,
                }
        cue_json = html_mod.escape(json.dumps(cue_positions))

        track_cards.append(
            f'<div class="track-card" id="track-{track_id}" '
            f'data-track-id="{track_id}" {beat_data} '
            f'data-cues=\'{cue_json}\'>'
            f'<div class="review-controls">'
            f'  <span class="track-status" id="status-{track_id}">pending</span>'
            f'  {warning}'
            f'  <button class="btn btn-accept" onclick="acceptTrack(\'{track_id}\')">Accept</button>'
            f'  <button class="btn btn-skip" onclick="skipTrack(\'{track_id}\')">Skip</button>'
            f'</div>'
            f'{body}'
            f'</div>'
        )

    cards_html = "\n".join(track_cards)
    session_json_escaped = html_mod.escape(session_path)

    review_css = """
  .review-header {
    position: sticky; top: 0; z-index: 100;
    background: #1a1a2e; border-bottom: 2px solid #2a2a3e;
    padding: 16px 24px; margin: -24px -24px 24px;
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  }
  .review-header h1 { font-size: 1.3rem; margin: 0; }
  .summary-bar { color: #aaa; font-size: 0.9rem; flex: 1; }
  .btn { border: none; border-radius: 4px; padding: 6px 14px; cursor: pointer; font-size: 0.85rem; font-weight: 600; }
  .btn-accept { background: #2ecc71; color: #111; }
  .btn-accept:hover { background: #27ae60; }
  .btn-skip { background: #555; color: #eee; }
  .btn-skip:hover { background: #666; }
  .btn-accept-all { background: #3498db; color: #fff; }
  .btn-accept-all:hover { background: #2980b9; }
  .review-controls { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
  .track-status {
    font-size: 0.8rem; font-weight: 600; padding: 2px 8px;
    border-radius: 3px; background: #333; color: #aaa;
  }
  .track-status.accepted { background: #1a4d2e; color: #2ecc71; }
  .track-status.skipped { background: #4d1a1a; color: #e74c3c; }
  .track-status.adjusted { background: #4d3d1a; color: #f1c40f; }
  .overwrite-badge {
    font-size: 0.75rem; padding: 2px 6px; border-radius: 3px;
    background: #4d3d1a; color: #f39c12;
  }
  .track-card.skipped { opacity: 0.4; }
  .apply-command {
    background: #111; border: 1px solid #333; border-radius: 4px;
    padding: 8px 12px; font-family: monospace; font-size: 0.85rem;
    color: #2ecc71; cursor: pointer;
  }
  .apply-command:hover { background: #1a1a2e; }
  .hot-cue-marker.selected { border-left-width: 4px !important; }
  .hot-cue-marker.cue-adjusted .marker-label::after { content: '*'; }
  .hot-cue-marker.cue-skipped { opacity: 0.3; }
"""

    review_js = """
const SERVER = '""" + server_url + """';

// --- Track-level actions ---

function acceptTrack(trackId) {
  fetch(`${SERVER}/session/track/${trackId}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status: 'accepted'})
  }).then(() => updateTrackUI(trackId, 'accepted'));
}

function skipTrack(trackId) {
  fetch(`${SERVER}/session/track/${trackId}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status: 'skipped'})
  }).then(() => updateTrackUI(trackId, 'skipped'));
}

function acceptAll() {
  fetch(`${SERVER}/session/accept-all`, {method: 'POST'})
    .then(() => {
      document.querySelectorAll('.track-card').forEach(card => {
        const tid = card.dataset.trackId;
        const st = document.getElementById('status-' + tid);
        if (st && st.textContent === 'pending') {
          updateTrackUI(tid, 'accepted');
        }
      });
    });
}

function updateTrackUI(trackId, status) {
  const card = document.getElementById('track-' + trackId);
  const st = document.getElementById('status-' + trackId);
  if (st) {
    st.textContent = status;
    st.className = 'track-status ' + status;
  }
  if (card) {
    card.classList.toggle('skipped', status === 'skipped');
  }
  updateSummary();
}

function updateSummary() {
  let accepted = 0, adjusted = 0, skipped = 0, pending = 0;
  document.querySelectorAll('.track-status').forEach(el => {
    switch (el.textContent) {
      case 'accepted': accepted++; break;
      case 'adjusted': adjusted++; break;
      case 'skipped': skipped++; break;
      default: pending++; break;
    }
  });
  const bar = document.getElementById('summary-bar');
  if (bar) {
    bar.textContent = `${accepted} accepted, ${adjusted} adjusted, ${skipped} skipped, ${pending} pending`;
  }
}

// --- Per-cue adjustment ---

let selectedCue = null;
let selectedTrackId = null;

document.addEventListener('click', function(e) {
  const marker = e.target.closest('.hot-cue-marker');
  if (marker) {
    e.stopPropagation();
    selectCue(marker);
    return;
  }
  // Click elsewhere deselects
  if (selectedCue) deselectCue();
});

document.addEventListener('keydown', function(e) {
  if (!selectedCue) return;
  const card = selectedCue.closest('.track-card');
  if (!card) return;

  const bpm = parseFloat(card.dataset.bpm);
  const firstBeatMs = parseFloat(card.dataset.firstBeatMs);
  const durationMs = parseFloat(card.dataset.durationMs);
  const barMs = (60000 / bpm) * 4;

  const pad = selectedCue.querySelector('.marker-label').textContent.trim();
  const cues = JSON.parse(card.dataset.cues);
  const cueData = cues[pad];
  if (!cueData) return;

  if (e.key === 'ArrowRight') {
    e.preventDefault();
    cueData.position_ms = Math.min(cueData.position_ms + barMs, durationMs);
    if (cueData.loop_end_ms !== null) cueData.loop_end_ms = cueData.position_ms + barMs * 4;
    updateCuePosition(card, pad, cueData);
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault();
    cueData.position_ms = Math.max(cueData.position_ms - barMs, firstBeatMs);
    if (cueData.loop_end_ms !== null) cueData.loop_end_ms = cueData.position_ms + barMs * 4;
    updateCuePosition(card, pad, cueData);
  } else if (e.key === 'Escape') {
    deselectCue();
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    e.preventDefault();
    skipCue(card, pad);
  }
});

function selectCue(marker) {
  if (selectedCue) selectedCue.classList.remove('selected');
  selectedCue = marker;
  selectedCue.classList.add('selected');
  selectedTrackId = marker.closest('.track-card')?.dataset.trackId;
}

function deselectCue() {
  if (selectedCue) selectedCue.classList.remove('selected');
  selectedCue = null;
  selectedTrackId = null;
}

function updateCuePosition(card, pad, cueData) {
  const trackId = card.dataset.trackId;
  const durationMs = parseFloat(card.dataset.durationMs);

  // Update data attribute
  const cues = JSON.parse(card.dataset.cues);
  cues[pad] = cueData;
  card.dataset.cues = JSON.stringify(cues);

  // Move the marker visually
  const pct = (cueData.position_ms / durationMs) * 100;
  selectedCue.style.left = pct.toFixed(4) + '%';
  selectedCue.classList.add('cue-adjusted');

  // Post to server
  fetch(`${SERVER}/session/track/${trackId}/cue/${pad}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      position_ms: cueData.position_ms,
      loop_end_ms: cueData.loop_end_ms,
      status: 'adjusted'
    })
  });

  // Update track status
  updateTrackUI(trackId, 'adjusted');
}

function skipCue(card, pad) {
  const trackId = card.dataset.trackId;
  selectedCue.classList.add('cue-skipped');
  deselectCue();

  fetch(`${SERVER}/session/track/${trackId}/cue/${pad}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status: 'skipped'})
  });

  updateTrackUI(trackId, 'adjusted');
}

// Initialize summary on load
updateSummary();
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>djcues review &mdash; {escaped_name}</title>
<style>
{_PAGE_CSS}
{review_css}
</style>
</head>
<body>
<div class="review-header">
  <h1>Review: {escaped_name}</h1>
  <span class="summary-bar" id="summary-bar">{count} pending</span>
  <button class="btn btn-accept-all" onclick="acceptAll()">Accept All</button>
  <span class="apply-command" onclick="navigator.clipboard.writeText(this.textContent)" title="Click to copy">djcues apply {session_json_escaped}</span>
</div>

{cards_html}

<script>
{review_js}
</script>
</body>
</html>"""
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
uv run python -c "from djcues.review import create_session, render_review_html; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/djcues/review.py
git commit -m "feat: add review module — session creation and interactive HTML generation"
```

---

### Task 3: Local HTTP server

**Files:**
- Create: `src/djcues/server.py`

- [ ] **Step 1: Implement server.py**

Create `src/djcues/server.py`:

```python
"""Minimal HTTP server for djcues review sessions."""

from __future__ import annotations

import json
import pathlib
import threading
import time
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer


class ReviewHandler(BaseHTTPRequestHandler):
    """Handles GET/POST requests for the review session."""

    html_path: pathlib.Path
    session_path: pathlib.Path
    last_activity: float

    def log_message(self, format, *args):
        """Suppress default request logging."""
        pass

    def _update_activity(self):
        self.server._last_activity = time.time()

    def _read_session(self) -> dict:
        return json.loads(self.session_path.read_text())

    def _write_session(self, session: dict):
        self.session_path.write_text(json.dumps(session, indent=2))

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        self._update_activity()

        if self.path == "/" or self.path == "/index.html":
            content = self.html_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif self.path == "/session":
            session = self._read_session()
            self._send_json(session)

        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        self._update_activity()
        body = self._read_body()

        if self.path == "/session/accept-all":
            session = self._read_session()
            for tid, tdata in session.get("tracks", {}).items():
                if tdata.get("status") == "pending":
                    tdata["status"] = "accepted"
                    for cue in tdata.get("cues", {}).values():
                        if cue.get("status") == "pending":
                            cue["status"] = "accepted"
                    for mc in tdata.get("memory_cues", {}).values():
                        if mc.get("status") == "pending":
                            mc["status"] = "accepted"
            self._write_session(session)
            self._send_json({"ok": True})

        elif self.path.startswith("/session/track/"):
            parts = self.path.split("/")
            # /session/track/<id> or /session/track/<id>/cue/<pad>
            if len(parts) == 4:
                # Track-level update
                track_id = parts[3]
                session = self._read_session()
                tdata = session.get("tracks", {}).get(track_id)
                if tdata is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                new_status = body.get("status", "pending")
                tdata["status"] = new_status
                if new_status in ("accepted", "skipped"):
                    for cue in tdata.get("cues", {}).values():
                        cue["status"] = new_status
                    for mc in tdata.get("memory_cues", {}).values():
                        mc["status"] = new_status
                self._write_session(session)
                self._send_json({"ok": True})

            elif len(parts) == 6 and parts[4] == "cue":
                # Per-cue update
                track_id = parts[3]
                pad = parts[5]
                session = self._read_session()
                tdata = session.get("tracks", {}).get(track_id)
                if tdata is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                cue = tdata.get("cues", {}).get(pad)
                if cue is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return

                new_status = body.get("status")
                if new_status == "adjusted":
                    if "original_ms" not in cue:
                        cue["original_ms"] = cue["position_ms"]
                    cue["position_ms"] = body.get("position_ms", cue["position_ms"])
                    cue["loop_end_ms"] = body.get("loop_end_ms", cue.get("loop_end_ms"))
                    cue["status"] = "adjusted"

                    # Auto-recalculate memory cue
                    slot_idx = list("ABCDEFGH").index(pad)
                    from djcues.constants import CUE_SYSTEM
                    slot = CUE_SYSTEM[slot_idx]
                    mem_key = str(slot_idx + 1)
                    mc = tdata.get("memory_cues", {}).get(mem_key)
                    if mc:
                        if slot.memory_offset_bars == 0:
                            mc["position_ms"] = cue["position_ms"]
                            mc["loop_end_ms"] = cue["loop_end_ms"]
                        else:
                            settings = session.get("settings", {})
                            offset_bars = settings.get("memory_offset_bars", 16)
                            bpm = tdata.get("bpm", 128.0)
                            bar_ms = (60000 / bpm) * 4
                            first_beat_ms = tdata.get("first_beat_ms", 0)
                            mc["position_ms"] = max(first_beat_ms, cue["position_ms"] - bar_ms * offset_bars)
                        mc["status"] = "auto"

                elif new_status == "skipped":
                    cue["status"] = "skipped"
                    slot_idx = list("ABCDEFGH").index(pad)
                    mem_key = str(slot_idx + 1)
                    mc = tdata.get("memory_cues", {}).get(mem_key)
                    if mc:
                        mc["status"] = "skipped"

                tdata["status"] = "adjusted"
                self._write_session(session)
                self._send_json({"ok": True})
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)


def start_server(
    html_path: pathlib.Path,
    session_path: pathlib.Path,
    port: int = 0,
    timeout_minutes: int = 30,
) -> tuple[HTTPServer, int]:
    """Start the review server in a background thread.

    Args:
        html_path: Path to the review HTML file.
        session_path: Path to the session JSON file.
        port: Port to bind (0 = auto-select).
        timeout_minutes: Auto-shutdown after this many minutes of inactivity.

    Returns:
        (server, port) tuple.
    """
    handler = partial(ReviewHandler)
    handler.html_path = html_path
    handler.session_path = session_path

    server = HTTPServer(("127.0.0.1", port), handler)
    server._last_activity = time.time()
    actual_port = server.server_address[1]

    def serve_with_timeout():
        server.timeout = 10  # check every 10 seconds
        while True:
            server.handle_request()
            if time.time() - server._last_activity > timeout_minutes * 60:
                break
        server.server_close()

    thread = threading.Thread(target=serve_with_timeout, daemon=True)
    thread.start()

    return server, actual_port
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
uv run python -c "from djcues.server import start_server; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/djcues/server.py
git commit -m "feat: add local HTTP server for review sessions"
```

---

### Task 4: CLI commands — review and apply

**Files:**
- Modify: `src/djcues/cli.py`

- [ ] **Step 1: Add review and apply commands to cli.py**

Append to `src/djcues/cli.py` after the `viz` command:

```python
@cli.command()
@click.argument("playlist")
@click.argument("track_name", required=False)
@click.option("--all", "all_tracks", is_flag=True, help="Review all tracks in playlist")
@click.option("--offset", default=16, help="Memory cue offset in bars (default: 16)")
@click.option("--loop-bars", default=4, help="Loop length in bars (default: 4)")
@click.option("--output", "-o", default=None, help="Output directory (default: current dir)")
def review(playlist, track_name, all_tracks, offset, loop_bars, output):
    """Launch interactive review session in browser."""
    import pathlib
    import webbrowser
    from djcues.review import create_session, render_review_html
    from djcues.server import start_server

    pl = find_playlist(playlist)
    if pl is None:
        click.echo(f"Playlist '{playlist}' not found.", err=True)
        raise SystemExit(1)

    tracks = load_playlist_tracks(pl.ID)
    strategy = CueStrategy(memory_offset_bars=offset, loop_length_bars=loop_bars)

    if all_tracks:
        pairs = [(t, strategy.propose(t)) for t in tracks if t.phrases]
        click.echo(f"Preparing review for {len(pairs)} tracks...")
    elif track_name:
        matches = [t for t in tracks if track_name.lower() in t.title.lower()]
        if not matches:
            click.echo(f"No track matching '{track_name}' in '{playlist}'.", err=True)
            raise SystemExit(1)
        pairs = [(t, strategy.propose(t)) for t in matches if t.phrases]
    else:
        click.echo("Provide a track name or use --all.", err=True)
        raise SystemExit(1)

    if not pairs:
        click.echo("No tracks with phrase data to review.", err=True)
        raise SystemExit(1)

    # Create session
    session = create_session(playlist, pl.ID, pairs, offset, loop_bars)

    # Write session file
    out_dir = pathlib.Path(output) if output else pathlib.Path(".")
    safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in playlist).strip().replace(" ", "-").lower()
    session_path = out_dir / f"{safe_name}-session.json"
    session_path.write_text(json.dumps(session, indent=2))

    # Generate HTML and start server
    html_path = out_dir / f"{safe_name}-review.html"

    # Start server first to get port
    server, port = start_server(html_path, session_path)
    server_url = f"http://localhost:{port}"

    # Generate HTML with server URL embedded
    html_content = render_review_html(playlist, pairs, str(session_path), server_url)
    html_path.write_text(html_content, encoding="utf-8")

    click.echo(f"Session: {session_path}")
    click.echo(f"Server running at {server_url}")
    click.echo(f"Opening browser...")
    webbrowser.open(server_url)
    click.echo(f"\nWhen done reviewing, run:")
    click.echo(f"  djcues apply {session_path}")
    click.echo(f"\nPress Ctrl+C to stop the server.")

    # Keep main thread alive while server runs
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nServer stopped.")


@cli.command()
@click.argument("session_file", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Show what would be written without making changes")
@click.option("--force", is_flag=True, help="Skip overwrite confirmation")
def apply(session_file, dry_run, force):
    """Apply a review session to the rekordbox database."""
    import pathlib
    from djcues.writer import apply_session

    session_path = pathlib.Path(session_file)
    apply_session(session_path, dry_run=dry_run, force=force)
```

Also add the missing `json` import at the top of cli.py (near the existing imports):

```python
import json
```

- [ ] **Step 2: Verify CLI commands exist**

```bash
uv run djcues review --help
uv run djcues apply --help
```

Expected: help text for both commands.

- [ ] **Step 3: Commit**

```bash
git add src/djcues/cli.py
git commit -m "feat: add review and apply CLI commands"
```

---

### Task 5: Integration test — end-to-end review and apply

This task does a manual smoke test of the full workflow. No new files.

- [ ] **Step 1: Run all unit tests**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS (including the new writer tests).

- [ ] **Step 2: Smoke test review on a single track**

```bash
uv run djcues review "April 2026" "Song 2 - Freejak" &
```

Expected: browser opens with the review page. Verify:
- Track card shows with waveform, phrases, cue markers
- Accept/Skip buttons work
- Clicking a cue marker selects it (thicker border)
- Arrow keys move the marker
- Summary bar updates
- Apply command shown at top

Press Ctrl+C to stop the server.

- [ ] **Step 3: Smoke test apply --dry-run**

```bash
uv run djcues apply *-session.json --dry-run
```

Expected: shows summary of what would be written, no DB changes.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: integration test fixes for review/apply workflow"
```

Note: this step only applies if fixes were needed during smoke testing. Skip if everything works.

- [ ] **Step 5: Test apply on a real track (requires rekordbox closed)**

Close rekordbox first, then:

```bash
uv run djcues apply *-session.json
```

Expected: backup created, cues written, verify in rekordbox after reopening.
