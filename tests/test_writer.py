"""Tests for djcues.writer — backup, cue row building, DB write."""

from __future__ import annotations

from djcues.constants import CUE_SYSTEM, CUE_SYSTEM_BY_PAD


# ---------------------------------------------------------------------------
# Test 1: backup_database creates a timestamped copy
# ---------------------------------------------------------------------------


def test_backup_creates_timestamped_copy(tmp_path):
    fake_db = tmp_path / "master.db"
    fake_db.write_bytes(b"sqlite-fake-content")

    from djcues.writer import backup_database

    backup_path = backup_database(fake_db)

    assert backup_path.exists()
    assert backup_path.parent == tmp_path
    assert backup_path.name.startswith("master-backup-")
    assert backup_path.name.endswith(".db")
    assert backup_path.read_bytes() == b"sqlite-fake-content"


# ---------------------------------------------------------------------------
# Helpers for build_cue_rows tests
# ---------------------------------------------------------------------------


def _make_hot_cues(statuses: dict[str, str] | None = None) -> dict:
    """Build a hot cues dict keyed by pad letter with position data.

    *statuses* overrides the default 'accepted' status per pad.
    """
    if statuses is None:
        statuses = {}
    cues: dict[str, dict] = {}
    for pad in "ABCDEFGH":
        slot = CUE_SYSTEM_BY_PAD[pad]
        entry: dict = {
            "status": statuses.get(pad, "accepted"),
            "position_ms": 1000.0 * (ord(pad) - ord("A") + 1),
        }
        if slot.is_loop:
            entry["loop_end_ms"] = entry["position_ms"] + 7500.0
        else:
            entry["loop_end_ms"] = None
        cues[pad] = entry
    return cues


def _make_memory_cues(statuses: dict[str, str] | None = None) -> dict:
    """Build a memory cues dict keyed by slot number string '1'-'8'."""
    if statuses is None:
        statuses = {}
    cues: dict[str, dict] = {}
    for i in range(8):
        slot_num = str(i + 1)
        slot = CUE_SYSTEM[i]
        entry: dict = {
            "status": statuses.get(slot_num, "accepted"),
            "position_ms": 500.0 * (i + 1),
        }
        if slot.is_loop:
            entry["loop_end_ms"] = entry["position_ms"] + 7500.0
        else:
            entry["loop_end_ms"] = None
        cues[slot_num] = entry
    return cues


# ---------------------------------------------------------------------------
# Test 2: build_cue_rows creates hot and memory rows
# ---------------------------------------------------------------------------


def test_build_cue_rows_creates_hot_and_memory():
    from djcues.writer import build_cue_rows

    hot_cues = _make_hot_cues()
    memory_cues = _make_memory_cues()

    hot_rows, mem_rows = build_cue_rows(hot_cues, memory_cues)

    assert len(hot_rows) == 8
    assert len(mem_rows) == 8

    # Verify hot cue fields
    for row in hot_rows:
        assert "Kind" in row
        assert "InMsec" in row
        assert "OutMsec" in row
        assert "ColorTableIndex" in row
        assert "Comment" in row
        assert row["InFrame"] == 0
        assert row["InMpegFrame"] == 0
        assert row["InMpegAbs"] == 0
        assert row["BeatLoopSize"] == 0
        assert row["CueMicrosec"] == 0

    # Check specific hot cue: pad A (kind=1, not a loop)
    hot_a = next(r for r in hot_rows if r["Kind"] == 1)
    assert hot_a["InMsec"] == 1000
    assert hot_a["OutMsec"] == -1
    assert hot_a["ColorTableIndex"] == 18
    assert hot_a["Color"] == -1
    assert hot_a["Comment"] == "First Beat"
    assert hot_a["ActiveLoop"] == -1
    assert hot_a["OutFrame"] == -1
    assert hot_a["OutMpegFrame"] == -1
    assert hot_a["OutMpegAbs"] == -1

    # Check loop cue: pad B (kind=2, is_loop)
    hot_b = next(r for r in hot_rows if r["Kind"] == 2)
    assert hot_b["InMsec"] == 2000
    assert hot_b["OutMsec"] == int(2000.0 + 7500.0)  # 9500
    assert hot_b["ActiveLoop"] == 0
    assert hot_b["OutFrame"] == 0
    assert hot_b["OutMpegFrame"] == 0
    assert hot_b["OutMpegAbs"] == 0

    # All memory cues should have Kind=0
    for row in mem_rows:
        assert row["Kind"] == 0

    # Check memory cue for slot 1 (pad A)
    mem_1 = mem_rows[0]  # first in iteration order
    assert mem_1["Comment"] == "First Beat"
    assert mem_1["Color"] == 4
    assert mem_1["InMsec"] == 500


# ---------------------------------------------------------------------------
# Test 3: build_cue_rows skips skipped cues
# ---------------------------------------------------------------------------


def test_build_cue_rows_skips_skipped_cues():
    from djcues.writer import build_cue_rows

    hot_cues = _make_hot_cues(statuses={"B": "skipped", "H": "skipped"})
    memory_cues = _make_memory_cues(statuses={"2": "skipped", "8": "skipped"})

    hot_rows, mem_rows = build_cue_rows(hot_cues, memory_cues)

    assert len(hot_rows) == 6
    assert len(mem_rows) == 6

    # Kind 2 (B) and Kind 9 (H) should not be present
    hot_kinds = {r["Kind"] for r in hot_rows}
    assert 2 not in hot_kinds
    assert 9 not in hot_kinds


# ---------------------------------------------------------------------------
# Test 4: build_cue_rows handles auto status
# ---------------------------------------------------------------------------


def test_build_cue_rows_handles_auto_status():
    from djcues.writer import build_cue_rows

    hot_cues = _make_hot_cues()
    memory_cues = _make_memory_cues(statuses={"3": "auto"})

    hot_rows, mem_rows = build_cue_rows(hot_cues, memory_cues)

    # "auto" should be treated as accepted — all 8 memory rows present
    assert len(mem_rows) == 8
