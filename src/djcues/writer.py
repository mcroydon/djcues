"""Write cue data to the rekordbox database."""

from __future__ import annotations

import json
import pathlib
import shutil
from datetime import datetime
from uuid import uuid4

from djcues.constants import CUE_SYSTEM, CUE_SYSTEM_BY_PAD


def backup_database(db_path: pathlib.Path) -> pathlib.Path:
    """Copy master.db to a timestamped backup. Returns the backup path."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = db_path.stem
    backup_name = f"{stem}-backup-{timestamp}.db"
    backup_path = db_path.parent / backup_name
    shutil.copy2(db_path, backup_path)
    return backup_path


def build_cue_rows(
    cues: dict, memory_cues: dict
) -> tuple[list[dict], list[dict]]:
    """Convert session cue data into lists of field dicts for DjmdCue creation.

    Hot cues are keyed by pad letter A-H; memory cues by slot number "1"-"8".
    Skips entries with status "skipped". Treats "auto" and "adjusted" as accepted.
    """
    hot_rows: list[dict] = []
    mem_rows: list[dict] = []

    # --- Hot cues ---
    for pad, slot in CUE_SYSTEM_BY_PAD.items():
        entry = cues.get(pad)
        if entry is None:
            continue
        if entry.get("status") == "skipped":
            continue

        is_loop = slot.is_loop
        in_msec = int(entry["position_ms"])
        if is_loop and entry.get("loop_end_ms") is not None:
            out_msec = int(entry["loop_end_ms"])
        else:
            out_msec = -1

        hot_rows.append({
            "Kind": slot.kind,
            "InMsec": in_msec,
            "InFrame": 0,
            "InMpegFrame": 0,
            "InMpegAbs": 0,
            "OutMsec": out_msec,
            "OutFrame": 0 if is_loop else -1,
            "OutMpegFrame": 0 if is_loop else -1,
            "OutMpegAbs": 0 if is_loop else -1,
            "Color": slot.hot_cue_color,
            "ColorTableIndex": slot.hot_cue_color_table_index,
            "ActiveLoop": 0 if is_loop else -1,
            "Comment": slot.hot_cue_label,
            "BeatLoopSize": 0,
            "CueMicrosec": 0,
        })

    # --- Memory cues ---
    for slot_num_str, entry in memory_cues.items():
        if entry.get("status") == "skipped":
            continue

        slot_idx = int(slot_num_str) - 1
        slot = CUE_SYSTEM[slot_idx]

        is_loop = slot.is_loop
        in_msec = int(entry["position_ms"])
        if is_loop and entry.get("loop_end_ms") is not None:
            out_msec = int(entry["loop_end_ms"])
        else:
            out_msec = -1

        mem_rows.append({
            "Kind": 0,
            "InMsec": in_msec,
            "InFrame": 0,
            "InMpegFrame": 0,
            "InMpegAbs": 0,
            "OutMsec": out_msec,
            "OutFrame": 0 if is_loop else -1,
            "OutMpegFrame": 0 if is_loop else -1,
            "OutMpegAbs": 0 if is_loop else -1,
            "Color": slot.memory_cue_color,
            "ColorTableIndex": slot.memory_cue_color_table_index,
            "ActiveLoop": 0 if is_loop else -1,
            "Comment": slot.memory_cue_label,
            "BeatLoopSize": 0,
            "CueMicrosec": 0,
        })

    return hot_rows, mem_rows


def write_cues_for_track(db, content, hot_rows, mem_rows, overwrite=False) -> int:
    """Write cue rows to the DB.

    If overwrite is True, deletes existing cues first.
    Returns the count of cues written.
    """
    from pyrekordbox.db6 import tables

    if overwrite:
        existing = db.get_cue(ContentID=content.ID)
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


def apply_session(session_path, dry_run=False, force=False) -> dict:
    """Read a session JSON file, show summary, back up DB, and write cues.

    One commit per track. Returns a summary dict.
    """
    import click
    from djcues.db import get_db

    session_path = pathlib.Path(session_path)
    with open(session_path) as f:
        session = json.load(f)

    tracks = session.get("tracks", {})

    # Count statuses
    accepted = 0
    adjusted = 0
    skipped = 0
    overwrite_ids: list[str] = []

    for track_id, track_data in tracks.items():
        status = track_data.get("status", "")
        if status == "accepted":
            accepted += 1
        elif status == "adjusted":
            adjusted += 1
        elif status == "skipped":
            skipped += 1

        if status in ("accepted", "adjusted"):
            if track_data.get("has_existing_cues", False):
                overwrite_ids.append(track_id)

    total_write = accepted + adjusted

    click.echo(f"Session: {session_path.name}")
    click.echo(f"  Accepted: {accepted}  Adjusted: {adjusted}  Skipped: {skipped}")
    click.echo(f"  Tracks to write: {total_write}")
    if overwrite_ids:
        click.echo(f"  Tracks with existing cues (overwrite): {len(overwrite_ids)}")

    result = {
        "accepted": accepted,
        "adjusted": adjusted,
        "skipped": skipped,
        "written": 0,
        "cues_written": 0,
    }

    if dry_run:
        click.echo("Dry run — no changes written.")
        return result

    if overwrite_ids and not force:
        click.confirm(
            f"{len(overwrite_ids)} track(s) have existing cues. Overwrite?",
            abort=True,
        )

    db = get_db()
    backup_path = backup_database(pathlib.Path(db.db_path))
    click.echo(f"Backup: {backup_path}")

    written = 0
    cues_written = 0

    for track_id, track_data in tracks.items():
        status = track_data.get("status", "")
        if status not in ("accepted", "adjusted"):
            continue

        hot_cues_data = track_data.get("hot_cues", {})
        mem_cues_data = track_data.get("memory_cues", {})
        hot_rows, mem_rows = build_cue_rows(hot_cues_data, mem_cues_data)

        content = db.get_content(ID=int(track_id))
        overwrite = track_id in overwrite_ids
        count = write_cues_for_track(db, content, hot_rows, mem_rows, overwrite=overwrite)
        db.commit()

        title = track_data.get("title", f"ID {track_id}")
        click.echo(f"  Wrote {count} cues for {title}")
        written += 1
        cues_written += count

    result["written"] = written
    result["cues_written"] = cues_written
    click.echo(f"Done: {written} tracks, {cues_written} cues written.")
    return result
