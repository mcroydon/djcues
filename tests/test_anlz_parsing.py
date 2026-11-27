"""Regression tests for ANLZ parsing of files written by newer rekordbox.

pyrekordbox 0.4.4 rejected PQT2 (extended beat grid) tags whose version
field was anything other than 0x01000002. Tracks analyzed by recent
rekordbox versions carry 0x02000002 (0x03000002 has also been observed in
the wild), which made ``read_anlz_files`` raise on the whole file and broke
beat grid, phrase (PSSI) and waveform (PWV5) extraction for the track.
"""

from __future__ import annotations

import struct

import pytest
from pyrekordbox.anlz import AnlzFile


def _build_anlz_with_pqt2(version: int, entry_count: int = 4) -> bytes:
    """Build a minimal ANLZ file containing a single PQT2 tag."""
    beats = struct.pack(
        ">HHIHHI",
        1, 17400, 0,      # first beat anchor: beat, tempo (BPM*100), time (ms)
        4, 17400, 1379,   # last beat anchor
    )
    content = struct.pack(">4xI4x", version) + beats + struct.pack(
        ">IIII",
        entry_count, 0, 0, 0,
    )
    entries = b"\x01\x00" * entry_count
    len_tag = 12 + len(content) + len(entries)
    tag = struct.pack(">4sII", b"PQT2", 56, len_tag) + content + entries
    file_header = struct.pack(">4sIIIIII", b"PMAI", 28, 28 + len(tag), 0, 0, 0, 0)
    return file_header + tag


@pytest.mark.parametrize("version", [0x01000002, 0x02000002, 0x03000002])
def test_pqt2_tag_with_any_observed_version_parses(version):
    anlz = AnlzFile.parse(_build_anlz_with_pqt2(version))
    tag = anlz.get_tag("PQT2")
    assert tag.content.u1 == version
    assert tag.content.entry_count == 4
    assert len(tag.content.entries) == 4
