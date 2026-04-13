"""Data model for djcues — decoupled from pyrekordbox ORM types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BeatGrid:
    """Beat timing derived from BPM and first beat position."""

    first_beat_ms: float
    bpm: float

    @property
    def ms_per_beat(self) -> float:
        return 60_000 / self.bpm

    def beat_to_ms(self, beat: int) -> float:
        """Convert a 1-indexed beat number to milliseconds."""
        return self.first_beat_ms + (beat - 1) * self.ms_per_beat

    def ms_to_beat(self, ms: float) -> int:
        """Convert milliseconds to the nearest 1-indexed beat number."""
        raw = (ms - self.first_beat_ms) / self.ms_per_beat + 1
        return max(1, round(raw))

    def bars_to_ms(self, bars: int) -> float:
        """Convert a number of bars (4 beats each) to milliseconds."""
        return bars * 4 * self.ms_per_beat


@dataclass
class CuePoint:
    """A single cue point (hot cue or memory cue)."""

    kind: int  # 0=memory, 1-9=hot cue slot
    position_ms: float
    loop_end_ms: float | None  # None if not a loop
    color_table_index: int | None
    color: int
    comment: str

    @property
    def is_loop(self) -> bool:
        return self.loop_end_ms is not None


@dataclass
class Phrase:
    """A phrase segment from PSSI analysis."""

    beat_start: int
    beat_end: int  # start beat of next phrase (exclusive)
    kind: int  # raw PSSI kind value
    label: str  # resolved label (Intro, Up, Down, Chorus, Outro)
    position_ms: float
    duration_ms: float

    @property
    def beat_length(self) -> int:
        return self.beat_end - self.beat_start


@dataclass
class Track:
    """A rekordbox track with analysis data."""

    id: int
    title: str
    artist: str
    bpm: float  # actual BPM (128.0, not 12800)
    duration_ms: float
    analysis_path: str
    cues: list[CuePoint]
    phrases: list[Phrase]
    beat_grid: BeatGrid


@dataclass
class CueSlot:
    """One row from the cue system definition."""

    pad: str  # A-H
    kind: int  # DB Kind value (1,2,3,5,6,7,8,9)
    hot_cue_label: str
    memory_cue_label: str
    hot_cue_color_table_index: int
    hot_cue_color: int
    memory_cue_color_table_index: int | None
    memory_cue_color: int
    is_loop: bool
    memory_offset_bars: int  # 0 for same-position slots, 16 for others


@dataclass
class CueProposal:
    """The result of running the cue strategy on a track."""

    track: Track
    hot_cues: list[CuePoint]
    memory_cues: list[CuePoint]
    confidence: dict[str, float]  # pad letter -> 0.0-1.0
    notes: list[str]  # human-readable explanations
