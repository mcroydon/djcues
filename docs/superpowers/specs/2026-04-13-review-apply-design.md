# djcues Review & Apply — Interactive Cue Editing and DB Writes

## Overview

Adds a two-phase workflow for writing proposed cues to the rekordbox database: an interactive browser-based **review** phase where you accept, skip, or adjust cues per-track, and a CLI **apply** phase that writes accepted cues to the DB with auto-backup and overwrite protection.

## Workflow

### Review Phase

1. Run `djcues review "April 2026" --all` (or `djcues review "Playlist" "Track Name"` for a single track).
2. djcues starts a minimal local HTTP server, generates an interactive HTML page, and opens it in the browser.
3. In the browser, review proposed cues on the waveform/phrase timeline. For each track: accept, skip, or adjust individual cues.
4. The browser communicates with the local server via POST requests. The server updates a `session.json` file that records the state of every track and cue.
5. When done reviewing, note the `djcues apply` command shown in the browser and close.

### Apply Phase

1. Run `djcues apply <session-file>`.
2. Reads `session.json`, shows a dry-run summary of what will be written.
3. Auto-backs up `master.db` to `master.db.djcues-backup-<timestamp>`.
4. If any accepted tracks have existing cues, lists them and prompts for confirmation (or use `--force`).
5. Verifies rekordbox is closed (pyrekordbox enforces this — commit raises if running).
6. Writes cues to the DB via `DjmdCue` ORM, one commit per track.
7. Reports what was written and the backup file path.

`djcues apply <session-file> --dry-run` shows the summary without writing.

## Browser Interactive Controls

### Track-Level Controls (top-right of each card)

- **Accept** button — marks all 16 cues (8 hot + 8 memory) as accepted
- **Skip** button — marks entire track as skipped (card greys out)
- Status indicator: pending / accepted / skipped / adjusted

### Page-Level Controls (sticky header)

- **Accept All** button — marks all pending tracks as accepted
- **Summary bar** — "42 accepted, 3 adjusted, 2 skipped, 77 pending"
- **Copy Apply Command** — shows the `djcues apply <session>` command to run

### Per-Cue Adjustment

- Click a hot cue marker to select it (highlighted with thicker border)
- Left/right arrow keys nudge by 1 bar, snapped to beat grid
- Cue marker moves on the waveform in real time
- Corresponding memory cue auto-recalculates (offset N bars before, or same position for slots 1/2/8)
- Escape to deselect, Delete/Backspace to skip that individual cue
- Adjusted cues show a visual indicator to distinguish from original proposals

### Overwrite Warning

Tracks with existing cues show a warning badge on the card. Accepting such a track marks it as "accept-overwrite" which the apply command treats with extra confirmation.

The non-interactive viz (`djcues viz`) continues to work exactly as before.

## Session File

Stored as `<playlist-name>-session.json` alongside the HTML output.

```json
{
  "playlist": "April 2026",
  "playlist_id": 629968975,
  "created": "2026-04-13T21:30:00",
  "settings": {
    "memory_offset_bars": 16,
    "loop_length_bars": 4
  },
  "tracks": {
    "224489124": {
      "title": "Song 2 - Freejak Remix",
      "status": "accepted",
      "has_existing_cues": false,
      "cues": {
        "A": {"position_ms": 77.0, "loop_end_ms": null, "status": "accepted"},
        "B": {"position_ms": 77.0, "loop_end_ms": 7577.0, "status": "accepted"},
        "C": {"position_ms": 30077.0, "loop_end_ms": null, "status": "adjusted", "original_ms": 37577.0},
        "D": {"position_ms": 67577.0, "loop_end_ms": null, "status": "accepted"},
        "E": {"position_ms": 97577.0, "loop_end_ms": null, "status": "accepted"},
        "F": {"position_ms": 127577.0, "loop_end_ms": null, "status": "accepted"},
        "G": {"position_ms": 202577.0, "loop_end_ms": null, "status": "accepted"},
        "H": {"position_ms": 210077.0, "loop_end_ms": 217577.0, "status": "skipped"}
      },
      "memory_cues": {
        "1": {"position_ms": 77.0, "loop_end_ms": null, "status": "accepted"},
        "2": {"position_ms": 77.0, "loop_end_ms": 7577.0, "status": "accepted"},
        "3": {"position_ms": 577.0, "loop_end_ms": null, "status": "auto"},
        "4": {"position_ms": 37577.0, "loop_end_ms": null, "status": "accepted"},
        "5": {"position_ms": 67577.0, "loop_end_ms": null, "status": "accepted"},
        "6": {"position_ms": 97577.0, "loop_end_ms": null, "status": "accepted"},
        "7": {"position_ms": 172577.0, "loop_end_ms": null, "status": "accepted"},
        "8": {"position_ms": 210077.0, "loop_end_ms": 217577.0, "status": "skipped"}
      }
    }
  }
}
```

### Session Rules

- When a hot cue is adjusted, its corresponding memory cue auto-recalculates (offset N bars before, or same position for slots 1/2/8).
- When a hot cue is skipped, its corresponding memory cue is also skipped.
- Track-level "accept" sets all cues to accepted.
- Individual cue adjustments override the track-level status (track shows "adjusted").
- Track-level "skip" overrides all individual cue states.
- Memory cues with status "auto" (recalculated from an adjusted hot cue) are treated as "accepted" during apply.

## Local Server

Minimal Python HTTP server based on `http.server` (stdlib, no dependencies). Started by `djcues review` in the background.

Responsibilities:
- Serve the interactive HTML file
- Handle POST requests from the browser to update `session.json`
- Auto-shutdown after 30 minutes of inactivity

Endpoints:
- `GET /` — serves the review HTML
- `GET /session` — returns current session JSON
- `POST /session/track/<track_id>` — update track status (accept/skip)
- `POST /session/track/<track_id>/cue/<pad>` — update individual cue (adjust position, skip)
- `POST /session/accept-all` — mark all pending tracks as accepted

## Apply Command & Safety

### CLI

```bash
djcues apply <session-file>              # preview + apply
djcues apply <session-file> --dry-run    # preview only
djcues apply <session-file> --force      # skip overwrite confirmation
```

### Apply Flow

1. **Read session** — parse JSON, count accepted/adjusted/skipped tracks.
2. **Summary** (always shown):
   ```
   April 2026 — 120 accepted, 2 adjusted, 2 skipped
   960 hot cues + 960 memory cues to write across 122 tracks
   3 tracks have existing cues (will overwrite)
   ```
3. **Backup** — copies `master.db` to `master.db.djcues-backup-<timestamp>` in the rekordbox directory. Prints backup path.
4. **Overwrite check** — lists tracks with existing cues, prompts for confirmation. Skippable with `--force`.
5. **Rekordbox check** — aborts if rekordbox is running: "Close rekordbox before applying. Your session is saved and will be here when you're ready."
6. **Write** — for each accepted/adjusted track: generate `DjmdCue` objects, `db.add()`, `db.commit()`. One commit per track so a failure doesn't lose previous progress.
7. **Report** — summary of what was written, backup file path.

### DB Write Details

For each track, for each non-skipped cue:
- Generate ID via `db.generate_unused_id(tables.DjmdCue)`
- Generate UUID4
- Create `DjmdCue` via `tables.DjmdCue.create()` with correct Kind, InMsec, OutMsec, Color, ColorTableIndex, Comment fields from the cue system constants
- For overwrite tracks: delete existing `DjmdCue` rows for that ContentID before writing new ones
- DB writes go to `master.db` only (not ANLZ files). Rekordbox reads cues from the DB for its own UI. ANLZ sync happens when rekordbox exports to USB.

## File Structure

### New Files

- `src/djcues/writer.py` — `backup_database()`, `write_cues_for_track()`, `apply_session()`
- `src/djcues/server.py` — minimal HTTP server for review sessions
- `src/djcues/review.py` — generates interactive HTML (extends viz rendering), manages session files
- `tests/test_writer.py` — unit tests for cue creation logic, backup logic

### Modified Files

- `src/djcues/cli.py` — add `review` and `apply` commands

### Unchanged

- `models.py`, `constants.py`, `strategy.py`, `db.py` — the read path and strategy engine stay as-is.

## Testing

- `test_writer.py` — test `write_cues_for_track()` creates correct DjmdCue objects (mock DB session). Test overwrite detection. Test backup file creation (temp directory).
- Manual testing — run `review` on a small playlist, adjust cues in browser, `apply --dry-run`, then `apply` on a test track and verify in rekordbox.
