# djcues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python library and CLI that reads the rekordbox database, analyzes phrase structure, and proposes cue placements based on a standardized cue strategy.

**Architecture:** Core library (`djcues`) with four modules — models (dataclasses), constants (lookup tables), db (rekordbox reader), strategy (PSSI-to-cue mapping). CLI built with click. HTML visualizer generates static timeline pages. All read-only against the live DB.

**Tech Stack:** Python 3.10+, pyrekordbox (DB + ANLZ), click (CLI), uv (package management)

**Spec:** `docs/superpowers/specs/2026-04-12-djcues-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Modify: add `src` layout, click dep, `[project.scripts]` entry |
| `src/djcues/__init__.py` | Create: package init, version |
| `src/djcues/models.py` | Create: Track, CuePoint, Phrase, BeatGrid, CueSlot, CueProposal dataclasses |
| `src/djcues/constants.py` | Create: PSSI mood/kind tables, hot cue color table, memory cue color table, Kind-to-pad mapping |
| `src/djcues/db.py` | Create: `load_track()`, `load_playlist_tracks()`, `find_playlist()` — reads pyrekordbox and returns our dataclasses |
| `src/djcues/strategy.py` | Create: `CueStrategy` class with `propose()` method |
| `src/djcues/cli.py` | Create: click CLI with `propose`, `compare`, `viz` commands |
| `src/djcues/viz.py` | Create: `render_timeline()` — generates HTML timeline |
| `tests/test_models.py` | Create: BeatGrid conversion tests |
| `tests/test_constants.py` | Create: mood table lookup tests |
| `tests/test_strategy.py` | Create: cue placement heuristic tests with fixture data |
| `tests/test_db.py` | Create: integration tests (skipped without DB) |
| `tests/conftest.py` | Create: shared fixtures (sample phrases, beat grids, tracks) |

---

### Task 1: Project setup — src layout, dependencies, package scaffolding

**Files:**
- Modify: `pyproject.toml`
- Create: `src/djcues/__init__.py`
- Remove: `hello.py` (uv init boilerplate)

- [ ] **Step 1: Update pyproject.toml for src layout and dependencies**

```toml
[project]
name = "djcues"
version = "0.1.0"
description = "Automated rekordbox cue placement based on phrase analysis"
requires-python = ">=3.10"
dependencies = [
    "pyrekordbox>=0.4.4",
    "click>=8.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
]

[project.scripts]
djcues = "djcues.cli:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/djcues"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package init**

Create `src/djcues/__init__.py`:

```python
"""djcues — Automated rekordbox cue placement based on phrase analysis."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Remove hello.py boilerplate**

```bash
rm hello.py
```

- [ ] **Step 4: Install dependencies and verify**

```bash
uv add click>=8.0
uv add --dev pytest>=8.0
uv pip install -e .
uv run python -c "import djcues; print(djcues.__version__)"
```

Expected: `0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/djcues/__init__.py uv.lock .python-version
git rm hello.py
git commit -m "feat: set up djcues package with src layout and dependencies"
```

---

### Task 2: Data model — models.py

**Files:**
- Create: `src/djcues/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write BeatGrid tests**

Create `tests/test_models.py`:

```python
from djcues.models import BeatGrid, CuePoint, Phrase, Track, CueSlot, CueProposal


def test_beat_grid_beat_to_ms():
    """Beat-to-ms conversion uses first beat offset + BPM math."""
    # 128 BPM, first beat at 77ms
    grid = BeatGrid(first_beat_ms=77.0, bpm=128.0)
    # beat 1 = first beat
    assert grid.beat_to_ms(1) == 77.0
    # beat 2 = 77 + 468.75
    assert grid.beat_to_ms(2) == 77.0 + 60000 / 128
    # beat 5 = one bar later
    assert grid.beat_to_ms(5) == 77.0 + 4 * 60000 / 128


def test_beat_grid_ms_to_beat():
    grid = BeatGrid(first_beat_ms=77.0, bpm=128.0)
    assert grid.ms_to_beat(77.0) == 1
    # Halfway between beat 1 and 2 rounds to nearest
    assert grid.ms_to_beat(77.0 + 60000 / 128 / 2) == 1 or grid.ms_to_beat(77.0 + 60000 / 128 / 2) == 2


def test_beat_grid_bars_to_ms():
    grid = BeatGrid(first_beat_ms=0.0, bpm=120.0)
    # 120 BPM: 1 beat = 500ms, 1 bar = 2000ms
    assert grid.bars_to_ms(1) == 2000.0
    assert grid.bars_to_ms(4) == 8000.0
    assert grid.bars_to_ms(16) == 32000.0


def test_cue_point_is_loop():
    loop = CuePoint(kind=2, position_ms=100.0, loop_end_ms=3900.0,
                    color_table_index=18, color=255, comment="Loop In")
    not_loop = CuePoint(kind=1, position_ms=100.0, loop_end_ms=None,
                        color_table_index=18, color=-1, comment="First Beat")
    assert loop.is_loop
    assert not not_loop.is_loop


def test_phrase_duration():
    p = Phrase(beat_start=1, beat_end=33, kind=1, label="Intro",
              position_ms=77.0, duration_ms=15000.0)
    assert p.duration_ms == 15000.0
    assert p.beat_length == 32
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'djcues.models'`

- [ ] **Step 3: Implement models.py**

Create `src/djcues/models.py`:

```python
"""Data model for djcues — decoupled from pyrekordbox ORM types."""

from __future__ import annotations

from dataclasses import dataclass, field


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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_models.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/djcues/models.py tests/test_models.py
git commit -m "feat: add data model (Track, CuePoint, Phrase, BeatGrid, CueSlot, CueProposal)"
```

---

### Task 3: Constants — PSSI mood tables, color mappings, cue system

**Files:**
- Create: `src/djcues/constants.py`
- Create: `tests/test_constants.py`

- [ ] **Step 1: Write constants tests**

Create `tests/test_constants.py`:

```python
from djcues.constants import (
    resolve_phrase_label,
    CUE_SYSTEM,
    KIND_TO_PAD,
    PAD_TO_KIND,
)


def test_high_mood_phrase_labels():
    assert resolve_phrase_label(mood=1, kind=1) == "Intro"
    assert resolve_phrase_label(mood=1, kind=2) == "Up"
    assert resolve_phrase_label(mood=1, kind=3) == "Down"
    assert resolve_phrase_label(mood=1, kind=5) == "Chorus"
    assert resolve_phrase_label(mood=1, kind=6) == "Outro"


def test_mid_mood_phrase_labels():
    assert resolve_phrase_label(mood=2, kind=1) == "Intro"
    assert resolve_phrase_label(mood=2, kind=9) == "Chorus"
    assert resolve_phrase_label(mood=2, kind=8) == "Bridge"
    assert resolve_phrase_label(mood=2, kind=10) == "Outro"


def test_low_mood_phrase_labels():
    assert resolve_phrase_label(mood=3, kind=1) == "Intro"
    assert resolve_phrase_label(mood=3, kind=2) == "Verse1"
    assert resolve_phrase_label(mood=3, kind=5) == "Verse2"
    assert resolve_phrase_label(mood=3, kind=9) == "Chorus"


def test_unknown_kind_returns_unknown():
    assert resolve_phrase_label(mood=1, kind=99) == "Unknown"


def test_cue_system_has_8_slots():
    assert len(CUE_SYSTEM) == 8
    pads = [s.pad for s in CUE_SYSTEM]
    assert pads == ["A", "B", "C", "D", "E", "F", "G", "H"]


def test_cue_system_kind_values():
    kinds = [s.kind for s in CUE_SYSTEM]
    assert kinds == [1, 2, 3, 5, 6, 7, 8, 9]


def test_cue_system_loops():
    loops = {s.pad: s.is_loop for s in CUE_SYSTEM}
    assert loops["B"] is True
    assert loops["H"] is True
    assert loops["A"] is False
    assert loops["D"] is False


def test_kind_to_pad_mapping():
    assert KIND_TO_PAD[1] == "A"
    assert KIND_TO_PAD[5] == "D"
    assert KIND_TO_PAD[9] == "H"


def test_pad_to_kind_mapping():
    assert PAD_TO_KIND["A"] == 1
    assert PAD_TO_KIND["D"] == 5
    assert PAD_TO_KIND["H"] == 9
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_constants.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement constants.py**

Create `src/djcues/constants.py`:

```python
"""Lookup tables for PSSI phrase mapping and cue system definition."""

from __future__ import annotations

from djcues.models import CueSlot

# PSSI mood → kind → label
# Reference: https://djl-analysis.deepsymmetry.org/djl-analysis/anlz.html#song-structure-tag
MOOD_PHRASE_MAP: dict[int, dict[int, str]] = {
    1: {  # High
        1: "Intro",
        2: "Up",
        3: "Down",
        5: "Chorus",
        6: "Outro",
    },
    2: {  # Mid
        1: "Intro",
        2: "Verse1",
        3: "Verse2",
        4: "Verse3",
        5: "Verse4",
        6: "Verse5",
        7: "Verse6",
        8: "Bridge",
        9: "Chorus",
        10: "Outro",
    },
    3: {  # Low
        1: "Intro",
        2: "Verse1",
        3: "Verse1",
        4: "Verse1",
        5: "Verse2",
        6: "Verse2",
        7: "Verse2",
        8: "Bridge",
        9: "Chorus",
        10: "Outro",
    },
}

MOOD_NAMES: dict[int, str] = {1: "High", 2: "Mid", 3: "Low"}


def resolve_phrase_label(mood: int, kind: int) -> str:
    """Resolve a PSSI phrase kind to a human-readable label given the mood."""
    return MOOD_PHRASE_MAP.get(mood, {}).get(kind, "Unknown")


# Cue system definition — matches cue-system.csv and verified DB values.
# Hot cue colors use ColorTableIndex. Memory cue colors use Color field.
CUE_SYSTEM: list[CueSlot] = [
    CueSlot(
        pad="A", kind=1,
        hot_cue_label="First Beat", memory_cue_label="First Beat",
        hot_cue_color_table_index=18, hot_cue_color=-1,
        memory_cue_color_table_index=None, memory_cue_color=4,
        is_loop=False, memory_offset_bars=0,
    ),
    CueSlot(
        pad="B", kind=2,
        hot_cue_label="Loop In", memory_cue_label="Loop In",
        hot_cue_color_table_index=18, hot_cue_color=255,
        memory_cue_color_table_index=0, memory_cue_color=4,
        is_loop=True, memory_offset_bars=0,
    ),
    CueSlot(
        pad="C", kind=3,
        hot_cue_label="Vocal / Buildup", memory_cue_label="Before Buildup",
        hot_cue_color_table_index=32, hot_cue_color=-1,
        memory_cue_color_table_index=None, memory_cue_color=3,
        is_loop=False, memory_offset_bars=16,
    ),
    CueSlot(
        pad="D", kind=5,
        hot_cue_label="Drop", memory_cue_label="Before Drop",
        hot_cue_color_table_index=42, hot_cue_color=-1,
        memory_cue_color_table_index=None, memory_cue_color=1,
        is_loop=False, memory_offset_bars=16,
    ),
    CueSlot(
        pad="E", kind=6,
        hot_cue_label="Breakdown", memory_cue_label="Before Breakdown",
        hot_cue_color_table_index=1, hot_cue_color=-1,
        memory_cue_color_table_index=None, memory_cue_color=6,
        is_loop=False, memory_offset_bars=16,
    ),
    CueSlot(
        pad="F", kind=7,
        hot_cue_label="Special", memory_cue_label="Before Special",
        hot_cue_color_table_index=56, hot_cue_color=-1,
        memory_cue_color_table_index=None, memory_cue_color=7,
        is_loop=False, memory_offset_bars=16,
    ),
    CueSlot(
        pad="G", kind=8,
        hot_cue_label="Outro", memory_cue_label="Before Outro",
        hot_cue_color_table_index=9, hot_cue_color=-1,
        memory_cue_color_table_index=None, memory_cue_color=5,
        is_loop=False, memory_offset_bars=16,
    ),
    CueSlot(
        pad="H", kind=9,
        hot_cue_label="Loop Out", memory_cue_label="Loop Out",
        hot_cue_color_table_index=0, hot_cue_color=255,
        memory_cue_color_table_index=0, memory_cue_color=2,
        is_loop=True, memory_offset_bars=0,
    ),
]

# Quick lookups
KIND_TO_PAD: dict[int, str] = {s.kind: s.pad for s in CUE_SYSTEM}
PAD_TO_KIND: dict[str, int] = {s.pad: s.kind for s in CUE_SYSTEM}
CUE_SYSTEM_BY_PAD: dict[str, CueSlot] = {s.pad: s for s in CUE_SYSTEM}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_constants.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/djcues/constants.py tests/test_constants.py
git commit -m "feat: add PSSI mood tables, color mappings, and cue system definition"
```

---

### Task 4: Database reader — db.py

**Files:**
- Create: `src/djcues/db.py`
- Create: `tests/test_db.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write integration tests (skipped without DB)**

Create `tests/conftest.py`:

```python
import pathlib
import pytest

from djcues.models import BeatGrid, Phrase

REKORDBOX_DB_EXISTS = pathlib.Path.home().joinpath(
    "Library/Pioneer/rekordbox/master.db"
).exists()

requires_rekordbox = pytest.mark.skipif(
    not REKORDBOX_DB_EXISTS, reason="Rekordbox database not found"
)


@pytest.fixture
def sample_beat_grid() -> BeatGrid:
    """128 BPM beat grid with first beat at 77ms (World Gone Wild)."""
    return BeatGrid(first_beat_ms=77.0, bpm=128.0)


@pytest.fixture
def sample_phrases(sample_beat_grid: BeatGrid) -> list[Phrase]:
    """Phrase data from 'World Gone Wild' — mood=1 (High)."""
    bg = sample_beat_grid
    raw = [
        (1, 1, "Intro"),
        (33, 2, "Up"),
        (65, 2, "Up"),
        (81, 2, "Up"),
        (145, 5, "Chorus"),
        (209, 3, "Down"),
        (241, 2, "Up"),
        (273, 5, "Chorus"),
        (305, 5, "Chorus"),
        (337, 5, "Chorus"),
        (401, 5, "Chorus"),
        (433, 6, "Outro"),
    ]
    phrases = []
    for i, (beat, kind, label) in enumerate(raw):
        next_beat = raw[i + 1][0] if i + 1 < len(raw) else 461
        pos = bg.beat_to_ms(beat)
        end_pos = bg.beat_to_ms(next_beat)
        phrases.append(Phrase(
            beat_start=beat,
            beat_end=next_beat,
            kind=kind,
            label=label,
            position_ms=pos,
            duration_ms=end_pos - pos,
        ))
    return phrases
```

Create `tests/test_db.py`:

```python
import pytest
from tests.conftest import requires_rekordbox


@requires_rekordbox
def test_find_playlist():
    from djcues.db import find_playlist
    pl = find_playlist("Processed")
    assert pl is not None
    assert pl.Name == "Processed"


@requires_rekordbox
def test_load_playlist_tracks():
    from djcues.db import find_playlist, load_playlist_tracks
    pl = find_playlist("Processed")
    tracks = load_playlist_tracks(pl.ID)
    assert len(tracks) > 0
    first = tracks[0]
    assert first.title is not None
    assert first.bpm > 0


@requires_rekordbox
def test_track_has_phrases():
    from djcues.db import find_playlist, load_playlist_tracks
    pl = find_playlist("Processed")
    tracks = load_playlist_tracks(pl.ID)
    # At least some tracks should have phrases
    tracks_with_phrases = [t for t in tracks if len(t.phrases) > 0]
    assert len(tracks_with_phrases) > 0


@requires_rekordbox
def test_track_has_cues():
    from djcues.db import find_playlist, load_playlist_tracks
    pl = find_playlist("Processed")
    tracks = load_playlist_tracks(pl.ID)
    # Processed tracks should all have cues
    for t in tracks:
        assert len(t.cues) > 0, f"{t.title} has no cues"


@requires_rekordbox
def test_track_beat_grid():
    from djcues.db import find_playlist, load_playlist_tracks
    pl = find_playlist("Processed")
    tracks = load_playlist_tracks(pl.ID)
    first = tracks[0]
    assert first.beat_grid.bpm > 0
    assert first.beat_grid.first_beat_ms >= 0
```

- [ ] **Step 2: Run tests to verify they fail (or skip)**

```bash
uv run pytest tests/test_db.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'djcues.db'` (or skip if DB not present, but the import error should happen first)

- [ ] **Step 3: Implement db.py**

Create `src/djcues/db.py`:

```python
"""Read tracks, cues, and phrase data from the rekordbox database."""

from __future__ import annotations

import logging
from typing import Any

from pyrekordbox import Rekordbox6Database

from djcues.constants import MOOD_PHRASE_MAP, resolve_phrase_label
from djcues.models import BeatGrid, CuePoint, Phrase, Track

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


def load_track(track_content: Any) -> Track:
    """Load a single track with all analysis data."""
    beat_grid = _extract_beat_grid(track_content)
    phrases = _extract_phrases(track_content, beat_grid)
    cues = _extract_cues(track_content)

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_db.py -v
```

Expected: all 5 tests PASS (if rekordbox DB is present)

- [ ] **Step 5: Commit**

```bash
git add src/djcues/db.py tests/test_db.py tests/conftest.py
git commit -m "feat: add rekordbox database reader (tracks, cues, phrases, beat grid)"
```

---

### Task 5: Strategy engine — strategy.py

**Files:**
- Create: `src/djcues/strategy.py`
- Create: `tests/test_strategy.py`

- [ ] **Step 1: Write strategy tests — high mood placement**

Create `tests/test_strategy.py`:

```python
import pytest
from djcues.models import BeatGrid, CuePoint, Phrase, Track, CueProposal
from djcues.strategy import CueStrategy


@pytest.fixture
def beat_grid() -> BeatGrid:
    return BeatGrid(first_beat_ms=77.0, bpm=128.0)


@pytest.fixture
def high_mood_phrases(beat_grid: BeatGrid) -> list[Phrase]:
    """World Gone Wild phrase structure — mood=1 (High)."""
    bg = beat_grid
    raw = [
        (1, 1, "Intro"),
        (33, 2, "Up"),
        (65, 2, "Up"),
        (81, 2, "Up"),
        (145, 5, "Chorus"),
        (209, 3, "Down"),
        (241, 2, "Up"),
        (273, 5, "Chorus"),
        (305, 5, "Chorus"),
        (337, 5, "Chorus"),
        (401, 5, "Chorus"),
        (433, 6, "Outro"),
    ]
    end_beat = 461
    phrases = []
    for i, (beat, kind, label) in enumerate(raw):
        next_beat = raw[i + 1][0] if i + 1 < len(raw) else end_beat
        pos = bg.beat_to_ms(beat)
        end_pos = bg.beat_to_ms(next_beat)
        phrases.append(Phrase(
            beat_start=beat, beat_end=next_beat, kind=kind, label=label,
            position_ms=pos, duration_ms=end_pos - pos,
        ))
    return phrases


@pytest.fixture
def world_gone_wild(beat_grid: BeatGrid, high_mood_phrases: list[Phrase]) -> Track:
    return Track(
        id=1, title="World Gone Wild", artist="Cyril", bpm=128.0,
        duration_ms=218000.0, analysis_path="", cues=[], phrases=high_mood_phrases,
        beat_grid=beat_grid,
    )


def test_propose_returns_8_hot_cues_and_8_memory_cues(world_gone_wild: Track):
    strategy = CueStrategy()
    proposal = strategy.propose(world_gone_wild)
    assert len(proposal.hot_cues) == 8
    assert len(proposal.memory_cues) == 8


def test_first_beat_at_beat_1(world_gone_wild: Track):
    strategy = CueStrategy()
    proposal = strategy.propose(world_gone_wild)
    hot_a = next(c for c in proposal.hot_cues if c.kind == 1)
    assert hot_a.position_ms == 77.0
    assert hot_a.comment == "First Beat"
    assert hot_a.color_table_index == 18


def test_drop_at_first_chorus(world_gone_wild: Track):
    """Drop should land at beat 145 (first Chorus)."""
    strategy = CueStrategy()
    proposal = strategy.propose(world_gone_wild)
    hot_d = next(c for c in proposal.hot_cues if c.kind == 5)
    bg = world_gone_wild.beat_grid
    assert hot_d.position_ms == bg.beat_to_ms(145)
    assert hot_d.comment == "Drop"


def test_vocal_before_drop(world_gone_wild: Track):
    """Vocal/Buildup should be the Up phrase preceding the Drop (Chorus at 145)."""
    strategy = CueStrategy()
    proposal = strategy.propose(world_gone_wild)
    hot_c = next(c for c in proposal.hot_cues if c.kind == 3)
    bg = world_gone_wild.beat_grid
    # The Up phrase at beat 81 is the last Up before the Chorus at 145
    assert hot_c.position_ms == bg.beat_to_ms(81)


def test_breakdown_after_drop(world_gone_wild: Track):
    """Breakdown should be the first Down after the Drop."""
    strategy = CueStrategy()
    proposal = strategy.propose(world_gone_wild)
    hot_e = next(c for c in proposal.hot_cues if c.kind == 6)
    bg = world_gone_wild.beat_grid
    assert hot_e.position_ms == bg.beat_to_ms(209)


def test_special_second_chorus(world_gone_wild: Track):
    """Special should be the Chorus after the Breakdown (Down)."""
    strategy = CueStrategy()
    proposal = strategy.propose(world_gone_wild)
    hot_f = next(c for c in proposal.hot_cues if c.kind == 7)
    bg = world_gone_wild.beat_grid
    # After Down at 209, next Chorus is at 273
    assert hot_f.position_ms == bg.beat_to_ms(273)


def test_outro_at_outro_phrase(world_gone_wild: Track):
    strategy = CueStrategy()
    proposal = strategy.propose(world_gone_wild)
    hot_g = next(c for c in proposal.hot_cues if c.kind == 8)
    bg = world_gone_wild.beat_grid
    assert hot_g.position_ms == bg.beat_to_ms(433)


def test_loop_in_is_loop(world_gone_wild: Track):
    strategy = CueStrategy()
    proposal = strategy.propose(world_gone_wild)
    hot_b = next(c for c in proposal.hot_cues if c.kind == 2)
    assert hot_b.is_loop
    assert hot_b.loop_end_ms is not None
    # Default 4 bars = 16 beats at 128 BPM = 7500ms
    expected_loop_end = hot_b.position_ms + world_gone_wild.beat_grid.bars_to_ms(4)
    assert hot_b.loop_end_ms == expected_loop_end


def test_memory_cue_offset_16_bars(world_gone_wild: Track):
    """Memory cues 3-7 should be 16 bars before their hot cue."""
    strategy = CueStrategy()
    proposal = strategy.propose(world_gone_wild)
    bg = world_gone_wild.beat_grid
    offset_ms = bg.bars_to_ms(16)

    hot_d = next(c for c in proposal.hot_cues if c.kind == 5)  # Drop
    mem_4 = next(c for c in proposal.memory_cues if c.comment == "Before Drop")
    assert mem_4.position_ms == hot_d.position_ms - offset_ms


def test_memory_cue_same_position_slots(world_gone_wild: Track):
    """Memory cues 1, 2, 8 should be at the same position as their hot cue."""
    strategy = CueStrategy()
    proposal = strategy.propose(world_gone_wild)

    hot_a = next(c for c in proposal.hot_cues if c.kind == 1)
    mem_1 = next(c for c in proposal.memory_cues if c.comment == "First Beat")
    assert mem_1.position_ms == hot_a.position_ms

    hot_h = next(c for c in proposal.hot_cues if c.kind == 9)
    mem_8 = next(c for c in proposal.memory_cues if c.comment == "Loop Out")
    assert mem_8.position_ms == hot_h.position_ms


def test_memory_cue_clamp_to_beat_1(beat_grid: BeatGrid):
    """If offset would go before beat 1, clamp to beat 1."""
    # Track with Chorus very early — only 8 beats in
    bg = beat_grid
    phrases = [
        Phrase(beat_start=1, beat_end=9, kind=1, label="Intro",
               position_ms=bg.beat_to_ms(1), duration_ms=bg.bars_to_ms(2)),
        Phrase(beat_start=9, beat_end=41, kind=5, label="Chorus",
               position_ms=bg.beat_to_ms(9), duration_ms=bg.bars_to_ms(8)),
        Phrase(beat_start=41, beat_end=73, kind=3, label="Down",
               position_ms=bg.beat_to_ms(41), duration_ms=bg.bars_to_ms(8)),
        Phrase(beat_start=73, beat_end=105, kind=5, label="Chorus",
               position_ms=bg.beat_to_ms(73), duration_ms=bg.bars_to_ms(8)),
        Phrase(beat_start=105, beat_end=137, kind=6, label="Outro",
               position_ms=bg.beat_to_ms(105), duration_ms=bg.bars_to_ms(8)),
    ]
    track = Track(
        id=99, title="Early Chorus", artist="Test", bpm=128.0,
        duration_ms=60000.0, analysis_path="", cues=[], phrases=phrases,
        beat_grid=bg,
    )
    strategy = CueStrategy()
    proposal = strategy.propose(track)
    # The "Before Drop" memory cue can't go 16 bars before beat 9
    mem_drop = next(c for c in proposal.memory_cues if c.comment == "Before Drop")
    assert mem_drop.position_ms >= bg.beat_to_ms(1)


def test_configurable_offset():
    """Memory offset should be configurable."""
    bg = BeatGrid(first_beat_ms=0.0, bpm=120.0)
    phrases = [
        Phrase(beat_start=1, beat_end=65, kind=1, label="Intro",
               position_ms=bg.beat_to_ms(1), duration_ms=bg.bars_to_ms(16)),
        Phrase(beat_start=65, beat_end=129, kind=2, label="Up",
               position_ms=bg.beat_to_ms(65), duration_ms=bg.bars_to_ms(16)),
        Phrase(beat_start=129, beat_end=193, kind=5, label="Chorus",
               position_ms=bg.beat_to_ms(129), duration_ms=bg.bars_to_ms(16)),
        Phrase(beat_start=193, beat_end=257, kind=3, label="Down",
               position_ms=bg.beat_to_ms(193), duration_ms=bg.bars_to_ms(16)),
        Phrase(beat_start=257, beat_end=321, kind=5, label="Chorus",
               position_ms=bg.beat_to_ms(257), duration_ms=bg.bars_to_ms(16)),
        Phrase(beat_start=321, beat_end=385, kind=6, label="Outro",
               position_ms=bg.beat_to_ms(321), duration_ms=bg.bars_to_ms(16)),
    ]
    track = Track(
        id=99, title="Test", artist="Test", bpm=120.0,
        duration_ms=200000.0, analysis_path="", cues=[], phrases=phrases,
        beat_grid=bg,
    )

    strategy_8 = CueStrategy(memory_offset_bars=8)
    proposal_8 = strategy_8.propose(track)
    hot_d = next(c for c in proposal_8.hot_cues if c.kind == 5)
    mem_4 = next(c for c in proposal_8.memory_cues if c.comment == "Before Drop")
    assert mem_4.position_ms == hot_d.position_ms - bg.bars_to_ms(8)

    strategy_16 = CueStrategy(memory_offset_bars=16)
    proposal_16 = strategy_16.propose(track)
    hot_d16 = next(c for c in proposal_16.hot_cues if c.kind == 5)
    mem_416 = next(c for c in proposal_16.memory_cues if c.comment == "Before Drop")
    assert mem_416.position_ms == hot_d16.position_ms - bg.bars_to_ms(16)


def test_no_chorus_flags_low_confidence(beat_grid: BeatGrid):
    """Tracks with no Chorus should still produce a proposal with low confidence."""
    bg = beat_grid
    phrases = [
        Phrase(beat_start=1, beat_end=65, kind=1, label="Intro",
               position_ms=bg.beat_to_ms(1), duration_ms=bg.bars_to_ms(16)),
        Phrase(beat_start=65, beat_end=129, kind=2, label="Up",
               position_ms=bg.beat_to_ms(65), duration_ms=bg.bars_to_ms(16)),
        Phrase(beat_start=129, beat_end=193, kind=3, label="Down",
               position_ms=bg.beat_to_ms(129), duration_ms=bg.bars_to_ms(16)),
        Phrase(beat_start=193, beat_end=257, kind=6, label="Outro",
               position_ms=bg.beat_to_ms(193), duration_ms=bg.bars_to_ms(16)),
    ]
    track = Track(
        id=99, title="No Chorus", artist="Test", bpm=128.0,
        duration_ms=120000.0, analysis_path="", cues=[], phrases=phrases,
        beat_grid=bg,
    )
    strategy = CueStrategy()
    proposal = strategy.propose(track)
    # Should still have A, B, G, H at minimum
    kinds = {c.kind for c in proposal.hot_cues}
    assert 1 in kinds  # A
    assert 8 in kinds  # G (Outro)
    # D (Drop) should be low confidence or absent
    if 5 in kinds:
        assert proposal.confidence["D"] < 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_strategy.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'djcues.strategy'`

- [ ] **Step 3: Implement strategy.py**

Create `src/djcues/strategy.py`:

```python
"""Cue placement strategy engine — maps PSSI phrases to cue points."""

from __future__ import annotations

from djcues.constants import CUE_SYSTEM, CUE_SYSTEM_BY_PAD
from djcues.models import BeatGrid, CuePoint, CueProposal, Phrase, Track


class CueStrategy:
    """Proposes cue placements based on phrase analysis and the cue system."""

    def __init__(
        self,
        memory_offset_bars: int = 16,
        loop_length_bars: int = 4,
    ) -> None:
        self.memory_offset_bars = memory_offset_bars
        self.loop_length_bars = loop_length_bars

    def propose(self, track: Track) -> CueProposal:
        """Generate a cue proposal for a track based on its phrase structure."""
        bg = track.beat_grid
        phrases = track.phrases
        hot_cues: list[CuePoint] = []
        memory_cues: list[CuePoint] = []
        confidence: dict[str, float] = {}
        notes: list[str] = []

        # Build positions dict keyed by pad letter
        positions: dict[str, float] = {}

        # --- A: First Beat ---
        positions["A"] = bg.beat_to_ms(1)
        confidence["A"] = 1.0
        notes.append(f"A (First Beat): beat 1")

        # --- B: Loop In (same as A) ---
        positions["B"] = positions["A"]
        confidence["B"] = 0.6
        notes.append(f"B (Loop In): same position as First Beat")

        # --- D: Drop (first Chorus, resolve before C/E/F) ---
        choruses = [p for p in phrases if p.label == "Chorus"]
        if choruses:
            # Skip first Chorus if it starts within first 16 bars (64 beats)
            drop_phrase = choruses[0]
            if drop_phrase.beat_start <= 16 * 4 and len(choruses) > 1:
                drop_phrase = choruses[1]
                notes.append(
                    f"D (Drop): skipped early Chorus at beat {choruses[0].beat_start}, "
                    f"using beat {drop_phrase.beat_start}"
                )
            else:
                notes.append(f"D (Drop): first Chorus at beat {drop_phrase.beat_start}")
            positions["D"] = drop_phrase.position_ms
            confidence["D"] = 0.85
        else:
            notes.append("D (Drop): no Chorus found — skipped")
            confidence["D"] = 0.0

        # --- C: Vocal / Buildup (last Up/Verse before Drop) ---
        if "D" in positions:
            drop_ms = positions["D"]
            # Find Up phrases before the drop
            ups_before = [p for p in phrases if p.label in ("Up", "Verse1", "Verse2", "Verse3", "Verse4", "Verse5", "Verse6") and p.position_ms < drop_ms]
            if ups_before:
                vocal_phrase = ups_before[-1]
                positions["C"] = vocal_phrase.position_ms
                confidence["C"] = 0.7
                notes.append(f"C (Vocal/Buildup): {vocal_phrase.label} at beat {vocal_phrase.beat_start}")
            else:
                # Fallback: phrase immediately before drop
                before_drop = [p for p in phrases if p.position_ms < drop_ms]
                if before_drop:
                    fallback = before_drop[-1]
                    positions["C"] = fallback.position_ms
                    confidence["C"] = 0.4
                    notes.append(f"C (Vocal/Buildup): fallback to {fallback.label} at beat {fallback.beat_start}")
                else:
                    confidence["C"] = 0.0
                    notes.append("C (Vocal/Buildup): no phrase found before Drop")
        else:
            # No drop — try first Up phrase
            ups = [p for p in phrases if p.label in ("Up", "Verse1", "Verse2")]
            if ups:
                positions["C"] = ups[0].position_ms
                confidence["C"] = 0.3
                notes.append(f"C (Vocal/Buildup): no Drop, using first Up at beat {ups[0].beat_start}")
            else:
                confidence["C"] = 0.0
                notes.append("C (Vocal/Buildup): no suitable phrase found")

        # --- E: Breakdown (first Down/Bridge after Drop) ---
        if "D" in positions:
            drop_ms = positions["D"]
            downs_after = [p for p in phrases if p.label in ("Down", "Bridge") and p.position_ms > drop_ms]
            if downs_after:
                breakdown_phrase = downs_after[0]
                positions["E"] = breakdown_phrase.position_ms
                confidence["E"] = 0.85
                notes.append(f"E (Breakdown): {breakdown_phrase.label} at beat {breakdown_phrase.beat_start}")
            else:
                confidence["E"] = 0.0
                notes.append("E (Breakdown): no Down/Bridge found after Drop")
        else:
            downs = [p for p in phrases if p.label in ("Down", "Bridge")]
            if downs:
                positions["E"] = downs[0].position_ms
                confidence["E"] = 0.3
                notes.append(f"E (Breakdown): no Drop, using first Down at beat {downs[0].beat_start}")
            else:
                confidence["E"] = 0.0
                notes.append("E (Breakdown): no Down/Bridge found")

        # --- F: Special / Second Drop (Chorus after Breakdown) ---
        if "E" in positions:
            breakdown_ms = positions["E"]
            choruses_after = [p for p in phrases if p.label == "Chorus" and p.position_ms > breakdown_ms]
            if choruses_after:
                special_phrase = choruses_after[0]
                positions["F"] = special_phrase.position_ms
                confidence["F"] = 0.7
                notes.append(f"F (Special): Chorus at beat {special_phrase.beat_start}")
            else:
                confidence["F"] = 0.0
                notes.append("F (Special): no Chorus found after Breakdown")
        elif "D" in positions:
            # No breakdown, try any Chorus after Drop that isn't the Drop itself
            drop_ms = positions["D"]
            later_choruses = [p for p in phrases if p.label == "Chorus" and p.position_ms > drop_ms]
            if later_choruses:
                positions["F"] = later_choruses[0].position_ms
                confidence["F"] = 0.5
                notes.append(f"F (Special): fallback Chorus at beat {later_choruses[0].beat_start}")
            else:
                confidence["F"] = 0.0
                notes.append("F (Special): no later Chorus found")
        else:
            confidence["F"] = 0.0
            notes.append("F (Special): no Drop or Breakdown to anchor from")

        # --- G: Outro ---
        outros = [p for p in phrases if p.label == "Outro"]
        if outros:
            positions["G"] = outros[0].position_ms
            confidence["G"] = 0.9
            notes.append(f"G (Outro): Outro at beat {outros[0].beat_start}")
        elif phrases:
            positions["G"] = phrases[-1].position_ms
            confidence["G"] = 0.4
            notes.append(f"G (Outro): no Outro found, using last phrase at beat {phrases[-1].beat_start}")
        else:
            confidence["G"] = 0.0
            notes.append("G (Outro): no phrases at all")

        # --- H: Loop Out (same as Outro) ---
        if "G" in positions:
            positions["H"] = positions["G"]
            confidence["H"] = 0.4
            notes.append("H (Loop Out): same position as Outro")
        else:
            confidence["H"] = 0.0
            notes.append("H (Loop Out): no Outro to anchor from")

        # --- Build CuePoint objects ---
        for slot in CUE_SYSTEM:
            pad = slot.pad
            if pad not in positions:
                continue

            pos_ms = positions[pad]
            loop_end = None
            if slot.is_loop:
                loop_end = pos_ms + bg.bars_to_ms(self.loop_length_bars)

            hot_cues.append(CuePoint(
                kind=slot.kind,
                position_ms=pos_ms,
                loop_end_ms=loop_end,
                color_table_index=slot.hot_cue_color_table_index,
                color=slot.hot_cue_color,
                comment=slot.hot_cue_label,
            ))

            # Memory cue
            if slot.memory_offset_bars == 0:
                mem_pos = pos_ms
            else:
                mem_pos = pos_ms - bg.bars_to_ms(self.memory_offset_bars)
                # Clamp to first beat
                first_beat_ms = bg.beat_to_ms(1)
                if mem_pos < first_beat_ms:
                    mem_pos = first_beat_ms
                # Snap to nearest downbeat
                mem_beat = bg.ms_to_beat(mem_pos)
                # Round down to nearest bar start (beats 1, 5, 9, ...)
                bar_beat = ((mem_beat - 1) // 4) * 4 + 1
                mem_pos = bg.beat_to_ms(bar_beat)

            mem_loop_end = None
            if slot.is_loop:
                mem_loop_end = mem_pos + bg.bars_to_ms(self.loop_length_bars)

            memory_cues.append(CuePoint(
                kind=0,
                position_ms=mem_pos,
                loop_end_ms=mem_loop_end,
                color_table_index=slot.memory_cue_color_table_index,
                color=slot.memory_cue_color,
                comment=slot.memory_cue_label,
            ))

        return CueProposal(
            track=track,
            hot_cues=hot_cues,
            memory_cues=memory_cues,
            confidence=confidence,
            notes=notes,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_strategy.py -v
```

Expected: all 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/djcues/strategy.py tests/test_strategy.py
git commit -m "feat: add cue placement strategy engine with PSSI phrase mapping"
```

---

### Task 6: CLI — propose and compare commands

**Files:**
- Create: `src/djcues/cli.py`

- [ ] **Step 1: Implement cli.py with propose and compare commands**

Create `src/djcues/cli.py`:

```python
"""CLI for djcues — propose and compare cue placements."""

from __future__ import annotations

import click

from djcues.db import find_playlist, load_playlist_tracks, load_track
from djcues.strategy import CueStrategy
from djcues.constants import KIND_TO_PAD, CUE_SYSTEM_BY_PAD


def _format_time(ms: float) -> str:
    """Format milliseconds as M:SS.s"""
    total_seconds = ms / 1000
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:04.1f}"


def _print_proposal(proposal, track):
    """Print a single track's proposal to stdout."""
    bg = track.beat_grid

    click.echo(f"\n{track.title} — {track.artist} — {track.bpm} BPM")
    click.echo("=" * 60)

    # Phrases
    if track.phrases:
        click.echo("\nPhrases:")
        for p in track.phrases:
            click.echo(
                f"  {p.label:<10s} beat {p.beat_start:>4}–{p.beat_end:<4}  "
                f"{_format_time(p.position_ms):>7} – {_format_time(p.position_ms + p.duration_ms)}"
            )

    # Hot cues
    click.echo("\nProposed Hot Cues:")
    for hc in sorted(proposal.hot_cues, key=lambda c: c.kind):
        pad = KIND_TO_PAD.get(hc.kind, "?")
        beat = bg.ms_to_beat(hc.position_ms)
        conf = proposal.confidence.get(pad, 0)
        conf_label = "high" if conf >= 0.8 else "medium" if conf >= 0.5 else "low"
        loop_str = f"  {bg.bars_to_ms(4)/1000:.0f}s loop" if hc.is_loop else ""
        click.echo(
            f"  {pad}  {hc.comment:<20s} {_format_time(hc.position_ms):>7}  "
            f"beat {beat:<5}{loop_str}  [{conf_label}]"
        )

    # Memory cues
    click.echo("\nProposed Memory Cues:")
    for mc in sorted(proposal.memory_cues, key=lambda c: c.position_ms):
        slot = CUE_SYSTEM_BY_PAD.get(
            next((p for p, s in CUE_SYSTEM_BY_PAD.items() if s.memory_cue_label == mc.comment), "?"),
            None,
        )
        slot_num = list(CUE_SYSTEM_BY_PAD.keys()).index(slot.pad) + 1 if slot else "?"
        offset_info = ""
        if slot and slot.memory_offset_bars > 0:
            offset_info = f"  {slot.memory_offset_bars} bars before Hot {slot.pad}"
        elif slot and slot.memory_offset_bars == 0:
            offset_info = f"  (= Hot {slot.pad})"
        loop_str = " loop" if mc.is_loop else ""
        click.echo(
            f"  {slot_num}  {mc.comment:<20s} {_format_time(mc.position_ms):>7}{offset_info}{loop_str}"
        )

    # Notes
    if proposal.notes:
        click.echo("\nPlacement Notes:")
        for note in proposal.notes:
            click.echo(f"  - {note}")


def _print_comparison(proposal, track):
    """Print existing vs proposed cues side-by-side."""
    bg = track.beat_grid
    click.echo(f"\n{track.title} — {track.bpm} BPM")
    click.echo("=" * 60)

    existing_hot = {c.kind: c for c in track.cues if c.kind > 0}
    proposed_hot = {c.kind: c for c in proposal.hot_cues}

    click.echo(f"\n{'Pad':<4} {'Existing':>12} {'Proposed':>12} {'Delta':>10}")
    click.echo("-" * 42)

    matches = 0
    total = 0
    tolerance_ms = 1000  # 1 second

    for slot in sorted(set(list(existing_hot.keys()) + list(proposed_hot.keys()))):
        pad = KIND_TO_PAD.get(slot, "?")
        ex = existing_hot.get(slot)
        pr = proposed_hot.get(slot)

        if ex and pr:
            total += 1
            delta_ms = abs(ex.position_ms - pr.position_ms)
            if delta_ms < tolerance_ms:
                matches += 1
                delta_str = "match" if delta_ms < 100 else f"~{delta_ms/1000:.1f}s"
            else:
                delta_str = f"{delta_ms/1000:.1f}s off"
            click.echo(
                f"  {pad:<4} {_format_time(ex.position_ms):>10} {_format_time(pr.position_ms):>12} {delta_str:>10}"
            )
        elif ex:
            total += 1
            click.echo(f"  {pad:<4} {_format_time(ex.position_ms):>10} {'—':>12} {'missing':>10}")
        elif pr:
            click.echo(f"  {pad:<4} {'—':>10} {_format_time(pr.position_ms):>12} {'new':>10}")

    if total > 0:
        click.echo(f"\nMatch rate: {matches}/{total} within {tolerance_ms/1000:.0f}s tolerance")


@click.group()
def cli():
    """djcues — Automated rekordbox cue placement."""
    pass


@cli.command()
@click.argument("playlist")
@click.argument("track_name", required=False)
@click.option("--all", "all_tracks", is_flag=True, help="Process all tracks in playlist")
@click.option("--offset", default=16, help="Memory cue offset in bars (default: 16)")
@click.option("--loop-bars", default=4, help="Loop length in bars (default: 4)")
def propose(playlist: str, track_name: str | None, all_tracks: bool, offset: int, loop_bars: int):
    """Propose cue placements for tracks in a playlist."""
    pl = find_playlist(playlist)
    if pl is None:
        click.echo(f"Playlist '{playlist}' not found.", err=True)
        raise SystemExit(1)

    tracks = load_playlist_tracks(pl.ID)
    strategy = CueStrategy(memory_offset_bars=offset, loop_length_bars=loop_bars)

    if all_tracks:
        for track in tracks:
            if track.phrases:
                proposal = strategy.propose(track)
                _print_proposal(proposal, track)
            else:
                click.echo(f"\n{track.title} — no phrase data, skipping")
    elif track_name:
        matches = [t for t in tracks if track_name.lower() in t.title.lower()]
        if not matches:
            click.echo(f"No track matching '{track_name}' in playlist '{playlist}'.", err=True)
            raise SystemExit(1)
        for track in matches:
            if track.phrases:
                proposal = strategy.propose(track)
                _print_proposal(proposal, track)
            else:
                click.echo(f"\n{track.title} — no phrase data")
    else:
        click.echo("Provide a track name or use --all.", err=True)
        raise SystemExit(1)


@cli.command()
@click.argument("playlist")
@click.argument("track_name", required=False)
@click.option("--all", "all_tracks", is_flag=True, help="Compare all tracks in playlist")
@click.option("--offset", default=16, help="Memory cue offset in bars (default: 16)")
@click.option("--loop-bars", default=4, help="Loop length in bars (default: 4)")
def compare(playlist: str, track_name: str | None, all_tracks: bool, offset: int, loop_bars: int):
    """Compare proposed cues against existing cues."""
    pl = find_playlist(playlist)
    if pl is None:
        click.echo(f"Playlist '{playlist}' not found.", err=True)
        raise SystemExit(1)

    tracks = load_playlist_tracks(pl.ID)
    strategy = CueStrategy(memory_offset_bars=offset, loop_length_bars=loop_bars)

    if all_tracks:
        total_matches = 0
        total_cues = 0
        for track in tracks:
            if track.phrases:
                proposal = strategy.propose(track)
                _print_comparison(proposal, track)
                # Tally stats
                existing_hot = {c.kind: c for c in track.cues if c.kind > 0}
                proposed_hot = {c.kind: c for c in proposal.hot_cues}
                for kind in existing_hot:
                    if kind in proposed_hot:
                        total_cues += 1
                        if abs(existing_hot[kind].position_ms - proposed_hot[kind].position_ms) < 1000:
                            total_matches += 1

        click.echo(f"\n{'='*60}")
        click.echo(f"Overall: {total_matches}/{total_cues} hot cues within 1s tolerance")
        if total_cues > 0:
            click.echo(f"Accuracy: {total_matches/total_cues*100:.1f}%")
    elif track_name:
        matches = [t for t in tracks if track_name.lower() in t.title.lower()]
        if not matches:
            click.echo(f"No track matching '{track_name}' in playlist '{playlist}'.", err=True)
            raise SystemExit(1)
        for track in matches:
            if track.phrases:
                proposal = strategy.propose(track)
                _print_comparison(proposal, track)
            else:
                click.echo(f"\n{track.title} — no phrase data")
    else:
        click.echo("Provide a track name or use --all.", err=True)
        raise SystemExit(1)
```

- [ ] **Step 2: Reinstall and test the CLI**

```bash
uv pip install -e .
uv run djcues --help
uv run djcues propose --help
uv run djcues compare --help
```

Expected: help text for all three commands

- [ ] **Step 3: Smoke test against real DB**

```bash
uv run djcues propose "Processed" "World Gone Wild"
```

Expected: formatted output showing phrases, proposed hot cues, and proposed memory cues with positions and confidence.

```bash
uv run djcues compare "Processed" "World Gone Wild"
```

Expected: side-by-side comparison with delta values.

- [ ] **Step 4: Commit**

```bash
git add src/djcues/cli.py
git commit -m "feat: add CLI with propose and compare commands"
```

---

### Task 7: HTML visualizer — viz.py and viz command

**Files:**
- Create: `src/djcues/viz.py`
- Modify: `src/djcues/cli.py` (add `viz` command)

- [ ] **Step 1: Implement viz.py**

Create `src/djcues/viz.py`:

```python
"""HTML timeline visualization for cue proposals."""

from __future__ import annotations

import html as html_mod
from djcues.constants import CUE_SYSTEM_BY_PAD, KIND_TO_PAD
from djcues.models import CuePoint, CueProposal, Track


# Phrase label → display color
PHRASE_COLORS: dict[str, str] = {
    "Intro": "#6c757d",
    "Up": "#28a745",
    "Down": "#17a2b8",
    "Chorus": "#dc3545",
    "Outro": "#ffc107",
    "Bridge": "#6f42c1",
    "Verse1": "#20c997",
    "Verse2": "#17a2b8",
    "Verse3": "#0dcaf0",
    "Verse4": "#20c997",
    "Verse5": "#17a2b8",
    "Verse6": "#0dcaf0",
    "Unknown": "#adb5bd",
}

# Hot cue pad → CSS color
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
    total_seconds = ms / 1000
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:04.1f}"


def _cue_marker_html(cue: CuePoint, total_ms: float, pad: str, color: str, above: bool) -> str:
    """Generate HTML for a single cue marker on the timeline."""
    left_pct = (cue.position_ms / total_ms) * 100
    pos = "top" if above else "bottom"
    label_pos = "bottom: 100%; margin-bottom: 2px" if above else "top: 100%; margin-top: 2px"
    escaped_comment = html_mod.escape(cue.comment)

    loop_html = ""
    if cue.is_loop and cue.loop_end_ms is not None:
        loop_width_pct = ((cue.loop_end_ms - cue.position_ms) / total_ms) * 100
        loop_html = (
            f'<div style="position:absolute;left:0;{pos}:0;width:{loop_width_pct/left_pct*100:.1f}%;'
            f'height:4px;background:{color};opacity:0.3;"></div>'
        )

    return (
        f'<div class="cue-marker" style="left:{left_pct:.3f}%;{pos}:0;height:100%;"'
        f' title="{pad}: {escaped_comment} ({_format_time(cue.position_ms)})">'
        f'<div style="position:absolute;left:0;{pos}:0;width:2px;height:100%;background:{color};"></div>'
        f'<div style="position:absolute;left:-8px;{label_pos};font-size:10px;'
        f'font-weight:bold;color:{color};white-space:nowrap;">{pad}</div>'
        f'{loop_html}'
        f'</div>'
    )


def render_timeline(
    track: Track,
    proposal: CueProposal,
    compare: bool = False,
) -> str:
    """Render an HTML timeline visualization."""
    total_ms = track.duration_ms if track.duration_ms > 0 else 1

    # Phrase segments
    phrase_segments = ""
    for p in track.phrases:
        left = (p.position_ms / total_ms) * 100
        width = (p.duration_ms / total_ms) * 100
        color = PHRASE_COLORS.get(p.label, PHRASE_COLORS["Unknown"])
        label = html_mod.escape(p.label)
        phrase_segments += (
            f'<div class="phrase-seg" style="left:{left:.3f}%;width:{width:.3f}%;background:{color};"'
            f' title="{label}: beat {p.beat_start}–{p.beat_end} ({_format_time(p.position_ms)})">'
            f'<span>{label}</span></div>'
        )

    # Proposed cue markers
    proposed_hot_markers = ""
    proposed_mem_markers = ""
    for hc in proposal.hot_cues:
        pad = KIND_TO_PAD.get(hc.kind, "?")
        color = CUE_COLORS.get(pad, "#fff")
        proposed_hot_markers += _cue_marker_html(hc, total_ms, pad, color, above=True)
    for i, mc in enumerate(proposal.memory_cues):
        slot_num = str(i + 1)
        # Find matching pad by label
        for p, s in CUE_SYSTEM_BY_PAD.items():
            if s.memory_cue_label == mc.comment:
                slot_num = str(list(CUE_SYSTEM_BY_PAD.keys()).index(p) + 1)
                break
        color = CUE_COLORS.get(list(CUE_SYSTEM_BY_PAD.keys())[int(slot_num)-1] if slot_num.isdigit() else "A", "#fff")
        proposed_mem_markers += _cue_marker_html(mc, total_ms, slot_num, color, above=False)

    # Existing cue markers (compare mode only)
    existing_section = ""
    if compare and track.cues:
        existing_hot_markers = ""
        existing_mem_markers = ""
        for c in track.cues:
            if c.kind > 0:
                pad = KIND_TO_PAD.get(c.kind, "?")
                color = CUE_COLORS.get(pad, "#fff")
                existing_hot_markers += _cue_marker_html(c, total_ms, pad, color, above=True)
            else:
                existing_mem_markers += _cue_marker_html(c, total_ms, "M", "#888", above=False)

        existing_section = f'''
        <h3>Existing Cues</h3>
        <div class="timeline-container">
            <div class="marker-row hot-row">{existing_hot_markers}</div>
            <div class="phrase-bar">{phrase_segments}</div>
            <div class="marker-row mem-row">{existing_mem_markers}</div>
        </div>
        <h3>Proposed Cues</h3>
        '''

    # Confidence summary
    conf_html = ""
    for pad in "ABCDEFGH":
        conf = proposal.confidence.get(pad, 0)
        bar_width = conf * 100
        color = "#2ecc71" if conf >= 0.8 else "#f1c40f" if conf >= 0.5 else "#e74c3c"
        slot = CUE_SYSTEM_BY_PAD.get(pad)
        label = slot.hot_cue_label if slot else pad
        conf_html += (
            f'<div style="display:flex;align-items:center;margin:2px 0;">'
            f'<span style="width:120px;font-size:12px;">{pad}: {html_mod.escape(label)}</span>'
            f'<div style="flex:1;background:#2a2a2a;height:12px;border-radius:3px;">'
            f'<div style="width:{bar_width:.0f}%;background:{color};height:100%;border-radius:3px;"></div>'
            f'</div>'
            f'<span style="width:40px;text-align:right;font-size:11px;color:#888;">{conf:.0%}</span>'
            f'</div>'
        )

    # Notes
    notes_html = "".join(f"<li>{html_mod.escape(n)}</li>" for n in proposal.notes)

    title = html_mod.escape(track.title)
    artist = html_mod.escape(track.artist)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title} — djcues</title>
<style>
body {{ background:#1a1a2e; color:#eee; font-family:system-ui,-apple-system,sans-serif; margin:20px; }}
h1 {{ font-size:20px; margin-bottom:4px; }}
h2 {{ font-size:16px; color:#aaa; margin-top:0; font-weight:normal; }}
h3 {{ font-size:14px; color:#888; margin:16px 0 8px; }}
.timeline-container {{ position:relative; margin:8px 0 30px; }}
.phrase-bar {{ position:relative; height:40px; display:flex; border-radius:4px; overflow:hidden; }}
.phrase-seg {{ position:absolute; height:100%; display:flex; align-items:center; justify-content:center;
               font-size:11px; font-weight:bold; color:#fff; overflow:hidden; cursor:default;
               border-right:1px solid #1a1a2e; }}
.phrase-seg span {{ text-shadow: 0 0 4px rgba(0,0,0,0.8); }}
.marker-row {{ position:relative; height:30px; }}
.cue-marker {{ position:absolute; cursor:default; }}
.legend {{ display:flex; flex-wrap:wrap; gap:12px; margin:12px 0; }}
.legend-item {{ display:flex; align-items:center; gap:4px; font-size:12px; }}
.legend-swatch {{ width:14px; height:14px; border-radius:2px; }}
.section {{ margin:20px 0; }}
ul {{ font-size:13px; color:#aaa; line-height:1.6; }}
</style>
</head>
<body>
<h1>{title}</h1>
<h2>{artist} — {track.bpm} BPM — {_format_time(track.duration_ms)}</h2>

<div class="legend">
''' + "".join(
        f'<div class="legend-item"><div class="legend-swatch" style="background:{PHRASE_COLORS.get(label, "#adb5bd")}"></div>{label}</div>'
        for label in dict.fromkeys(p.label for p in track.phrases)
    ) + f'''
</div>

{existing_section}

<div class="timeline-container">
    <div class="marker-row hot-row">{proposed_hot_markers}</div>
    <div class="phrase-bar">{phrase_segments}</div>
    <div class="marker-row mem-row">{proposed_mem_markers}</div>
</div>

<div class="section">
    <h3>Confidence</h3>
    {conf_html}
</div>

<div class="section">
    <h3>Placement Notes</h3>
    <ul>{notes_html}</ul>
</div>

</body>
</html>'''
```

- [ ] **Step 2: Add viz command to cli.py**

Append to `src/djcues/cli.py`, inside the file after the `compare` function:

```python
@cli.command()
@click.argument("playlist")
@click.argument("track_name", required=False)
@click.option("--compare", "compare_mode", is_flag=True, help="Show existing vs proposed")
@click.option("--offset", default=16, help="Memory cue offset in bars (default: 16)")
@click.option("--loop-bars", default=4, help="Loop length in bars (default: 4)")
@click.option("--output", "-o", default=None, help="Output file path (default: auto-generated)")
def viz(playlist: str, track_name: str | None, compare_mode: bool, offset: int, loop_bars: int, output: str | None):
    """Generate an HTML timeline visualization."""
    import pathlib
    import webbrowser

    from djcues.viz import render_timeline

    pl = find_playlist(playlist)
    if pl is None:
        click.echo(f"Playlist '{playlist}' not found.", err=True)
        raise SystemExit(1)

    if not track_name:
        click.echo("Track name is required for viz.", err=True)
        raise SystemExit(1)

    tracks = load_playlist_tracks(pl.ID)
    matches = [t for t in tracks if track_name.lower() in t.title.lower()]
    if not matches:
        click.echo(f"No track matching '{track_name}' in playlist '{playlist}'.", err=True)
        raise SystemExit(1)

    track = matches[0]
    if not track.phrases:
        click.echo(f"{track.title} has no phrase data.", err=True)
        raise SystemExit(1)

    strategy = CueStrategy(memory_offset_bars=offset, loop_length_bars=loop_bars)
    proposal = strategy.propose(track)

    page_html = render_timeline(track, proposal, compare=compare_mode)

    if output:
        out_path = pathlib.Path(output)
    else:
        safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in track.title).strip().replace(" ", "-").lower()
        out_path = pathlib.Path(f"{safe_name}-cues.html")

    out_path.write_text(page_html, encoding="utf-8")
    click.echo(f"Written to {out_path}")

    webbrowser.open(f"file://{out_path.resolve()}")
```

- [ ] **Step 3: Test the viz command**

```bash
uv run djcues viz "Processed" "World Gone Wild"
```

Expected: generates an HTML file, opens in browser showing phrase timeline with cue markers above and below.

```bash
uv run djcues viz "Processed" "World Gone Wild" --compare
```

Expected: shows existing cues AND proposed cues on separate timelines.

- [ ] **Step 4: Commit**

```bash
git add src/djcues/viz.py src/djcues/cli.py
git commit -m "feat: add HTML timeline visualizer with propose and compare modes"
```

---

### Task 8: End-to-end validation

No new files — this task runs the full pipeline against the Processed playlist to validate heuristic accuracy.

- [ ] **Step 1: Run compare --all against Processed playlist**

```bash
uv run djcues compare "Processed" --all 2>/dev/null
```

Review the output. Check the overall accuracy percentage and look for patterns in mismatches.

- [ ] **Step 2: Run all tests**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS (unit + integration if DB present).

- [ ] **Step 3: Add .superpowers/ to .gitignore**

Append to `.gitignore`:

```
# Superpowers brainstorm sessions
.superpowers/
```

- [ ] **Step 4: Final commit**

```bash
git add .gitignore
git commit -m "chore: add .superpowers/ to gitignore, validate end-to-end accuracy"
```

- [ ] **Step 5: Review accuracy and note areas for heuristic tuning**

Check the `compare --all` output. If accuracy is below 70%, examine which slots have the most mismatches and note them for refinement. The strategy heuristics (especially C/Vocal/Buildup and F/Special) are expected to need tuning based on real-world results.
