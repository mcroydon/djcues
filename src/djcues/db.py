"""Read tracks, cues, and phrase data from the rekordbox database."""

from __future__ import annotations

import logging
from typing import Any

from pyrekordbox import Rekordbox6Database

from djcues.constants import resolve_phrase_label
from djcues.models import BeatGrid, CuePoint, Phrase, Track, WaveformPoint

logger = logging.getLogger(__name__)

_db: Rekordbox6Database | None = None


def get_db() -> Rekordbox6Database:
    """Get or create the shared database connection."""
    global _db
    if _db is None:
        _db = Rekordbox6Database()
    return _db


def find_playlist(name: str) -> Any | None:
    """Find a playlist by exact name. Returns the pyrekordbox playlist object or None."""
    db = get_db()
    for pl in db.get_playlist():
        if pl.Name == name:
            return pl
    return None


def _extract_beat_grid(track_content: Any) -> BeatGrid:
    """Extract BPM and first beat position from a track's analysis files."""
    db = get_db()
    bpm = track_content.BPM / 100

    # Try to get first beat from ANLZ beat grid
    first_beat_ms = 0.0
    try:
        anlz_files = db.read_anlz_files(track_content)
        for path, af in anlz_files.items():
            if path.suffix == ".DAT":
                for tag in af.tags:
                    if type(tag).__name__ == "PQTZAnlzTag":
                        times = tag.get_times()
                        if len(times) > 0:
                            # times are in seconds, convert to ms
                            first_beat_ms = float(times[0]) * 1000
                        break
    except Exception as e:
        logger.warning("Could not read beat grid for %s: %s", track_content.Title, e)

    return BeatGrid(first_beat_ms=first_beat_ms, bpm=bpm)


def _extract_phrases(track_content: Any, beat_grid: BeatGrid) -> list[Phrase]:
    """Extract PSSI phrase structure from a track's ANLZ EXT file."""
    db = get_db()
    phrases: list[Phrase] = []

    try:
        anlz_files = db.read_anlz_files(track_content)
        for path, af in anlz_files.items():
            if path.suffix == ".EXT":
                for tag in af.tags:
                    if type(tag).__name__ == "PSSIAnlzTag":
                        content = tag.content
                        mood = content.mood
                        entries = list(content.entries)

                        for i, entry in enumerate(entries):
                            next_beat = (
                                entries[i + 1].beat
                                if i + 1 < len(entries)
                                else content.end_beat
                            )
                            label = resolve_phrase_label(mood, entry.kind)
                            pos_ms = beat_grid.beat_to_ms(entry.beat)
                            end_ms = beat_grid.beat_to_ms(next_beat)

                            phrases.append(Phrase(
                                beat_start=entry.beat,
                                beat_end=next_beat,
                                kind=entry.kind,
                                label=label,
                                position_ms=pos_ms,
                                duration_ms=end_ms - pos_ms,
                            ))
                        break  # only process first PSSI tag
    except Exception as e:
        logger.warning("Could not read phrases for %s: %s", track_content.Title, e)

    return phrases


def _extract_cues(track_content: Any) -> list[CuePoint]:
    """Extract cue points from the database."""
    db = get_db()
    cues: list[CuePoint] = []

    for c in db.get_cue(ContentID=track_content.ID):
        loop_end = None
        if c.OutMsec is not None and c.OutMsec > 0:
            loop_end = float(c.OutMsec)

        cues.append(CuePoint(
            kind=c.Kind,
            position_ms=float(c.InMsec),
            loop_end_ms=loop_end,
            color_table_index=c.ColorTableIndex,
            color=c.Color if c.Color is not None else -1,
            comment=c.Comment or "",
        ))

    return cues


def _extract_waveform(track_content: Any, max_points: int = 800) -> list[WaveformPoint] | None:
    """Extract color waveform from PWV5 tag, downsampled for display."""
    db = get_db()
    try:
        anlz_files = db.read_anlz_files(track_content)
        for path, af in anlz_files.items():
            if path.suffix == ".EXT":
                for tag in af.tags:
                    if type(tag).__name__ == "PWV5AnlzTag":
                        heights, colors = tag.get()
                        n = len(heights)
                        step = max(1, n // max_points)
                        points: list[WaveformPoint] = []
                        for i in range(0, n, step):
                            # Take max height in each chunk for peak representation
                            chunk_end = min(i + step, n)
                            peak_idx = i
                            for j in range(i, chunk_end):
                                if heights[j] > heights[peak_idx]:
                                    peak_idx = j
                            points.append(WaveformPoint(
                                height=float(heights[peak_idx]),
                                red=int(colors[peak_idx, 0]),
                                green=int(colors[peak_idx, 1]),
                                blue=int(colors[peak_idx, 2]),
                            ))
                        return points
    except Exception as e:
        logger.warning("Could not read waveform for %s: %s", track_content.Title, e)
    return None


def _extract_vocal_track(track_content: Any) -> list[int] | None:
    """Extract PVDI vocal detection data from the .2EX ANLZ file.

    Returns a list of per-frame vocal confidence values (0-4),
    where each frame covers 1024/22050 ≈ 46.4ms.
    """
    import struct
    anlz_rel = track_content.AnalysisDataPath
    if not anlz_rel:
        return None
    base = __import__("pathlib").Path.home() / "Library/Pioneer/rekordbox/share"
    ex2_path = base / anlz_rel.lstrip("/").replace("ANLZ0000.DAT", "ANLZ0000.2EX")
    if not ex2_path.exists():
        return None
    try:
        with open(ex2_path, "rb") as f:
            data = f.read()
        pos = data.find(b"PVDI")
        if pos < 0:
            return None
        header_len = struct.unpack(">I", data[pos + 4 : pos + 8])[0]
        tag_len = struct.unpack(">I", data[pos + 8 : pos + 12])[0]
        body = data[pos + header_len : pos + tag_len]
        return list(body)
    except Exception as e:
        logger.warning("Could not read vocal track for %s: %s", track_content.Title, e)
        return None


def load_track(track_content: Any) -> Track:
    """Load a single track with all analysis data."""
    beat_grid = _extract_beat_grid(track_content)
    phrases = _extract_phrases(track_content, beat_grid)
    cues = _extract_cues(track_content)
    waveform = _extract_waveform(track_content)
    vocal_track = _extract_vocal_track(track_content)

    artist_name = ""
    if track_content.Artist:
        artist_name = track_content.Artist.Name or ""

    return Track(
        id=track_content.ID,
        title=track_content.Title or "",
        artist=artist_name,
        bpm=track_content.BPM / 100,
        duration_ms=float(track_content.Length or 0) * 1000,
        analysis_path=track_content.AnalysisDataPath or "",
        cues=cues,
        phrases=phrases,
        beat_grid=beat_grid,
        waveform=waveform,
        vocal_track=vocal_track,
    )


def load_playlist_tracks(playlist_id: int) -> list[Track]:
    """Load all tracks from a playlist with full analysis data."""
    db = get_db()
    songs = list(db.get_playlist_songs(PlaylistID=playlist_id))
    tracks: list[Track] = []
    for song in songs:
        try:
            tracks.append(load_track(song.Content))
        except Exception as e:
            logger.warning("Skipping track %s: %s", song.Content.Title, e)
    return tracks
