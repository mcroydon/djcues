# djcues — Automated Rekordbox Cue Placement

## Overview

A Python library and CLI tool that reads the rekordbox database, analyzes track phrase structure (PSSI), and proposes hot cue and memory cue placements based on a standardized cue strategy. Read-only — no writes to the live database.

## Cue System

Defined in `cue-system.csv` at the project root. 8 hot cues and 8 memory cues per track:

| Pad | DB Kind | Hot Cue Label     | Memory Cue Label   | Color (CTI) | Loop |
|-----|---------|-------------------|--------------------|-------------|------|
| A   | 1       | First Beat        | First Beat         | 18 (Green)  | No   |
| B   | 2       | Loop In           | Loop In            | 18 (Green)  | Yes  |
| C   | 3       | Vocal / Buildup   | Before Buildup     | 32 (Yellow) | No   |
| D   | 5       | Drop              | Before Drop        | 42 (Red)    | No   |
| E   | 6       | Breakdown         | Before Breakdown   | 1 (Blue)    | No   |
| F   | 7       | Special / 2nd Drop| Before Special     | 56 (Purple) | No   |
| G   | 8       | Outro             | Before Outro       | 9 (Cyan)    | No   |
| H   | 9       | Loop Out          | Loop Out           | 0 (Orange)  | Yes  |

DB Kind values skip 4 — this is the actual encoding in rekordbox's DjmdCue table. Kind=4 is only used for extra cues beyond the standard 8.

Memory cue colors use a separate system. Non-loop memory cues use `ColorTableIndex=None` with a `Color` value. Loop memory cues use `ColorTableIndex=0` with a `Color` value.

- First Beat: ColorTableIndex=None, Color=4 (Green)
- Loop In: ColorTableIndex=0, Color=4 (Green, loop)
- Before Buildup: ColorTableIndex=None, Color=3 (Yellow)
- Before Drop: ColorTableIndex=None, Color=1 (Red)
- Before Breakdown: ColorTableIndex=None, Color=6 (Blue)
- Before Special: ColorTableIndex=None, Color=7 (Purple)
- Before Outro: ColorTableIndex=None, Color=5 (Cyan)
- Loop Out: ColorTableIndex=0, Color=2 (Orange, loop)

### Memory Cue Offset

- Slots 1, 2, 8: same position as their hot cue counterpart
- Slots 3–7: placed N bars before the corresponding hot cue (configurable, default 16 bars)
- Snapped to nearest beat grid downbeat
- If position would be before track start, placed at beat 1

### Loop Length

Default 4 bars for both Loop In (B) and Loop Out (H). Configurable.

## PSSI Phrase Mapping

### Mood Tables

Rekordbox phrase structure uses mood + kind to determine phrase labels:

**High mood (mood=1):** kind 1=Intro, 2=Up, 3=Down, 5=Chorus, 6=Outro

**Mid mood (mood=2):** kind 1=Intro, 2=Verse1, 3=Verse2, 4=Verse3, 5=Verse4, 6=Verse5, 7=Verse6, 8=Bridge, 9=Chorus, 10=Outro

**Low mood (mood=3):** kind 1=Intro, 2-4=Verse1, 5-7=Verse2, 8=Bridge, 9=Chorus, 10=Outro

### Placement Heuristics

Resolved in this order (D first, since C, E, F are defined relative to it):

| Slot | Rule | Confidence |
|------|------|------------|
| A    | First beat of track (beat grid entry 1) | Very high |
| B    | Same position as A, 4-bar loop | Medium |
| D    | First Chorus phrase. If first Chorus starts within first 16 bars, use second Chorus. | High |
| C    | First Up phrase that precedes the Drop (D). Fallback: the phrase immediately before Drop. For Mid/Low mood: last Verse before Chorus. | Medium |
| E    | First Down phrase after the Drop. For Mid/Low mood: Bridge after Chorus. | High |
| F    | Second Chorus after the Drop (the Chorus following the Breakdown). Fallback: any later Chorus. | Medium |
| G    | First Outro phrase. If no Outro detected, last phrase. | High |
| H    | Same position as G, 4-bar loop | Low |

### Edge Cases

- No Chorus → skip Drop/Special, flag as low confidence, place other cues where possible
- No Outro → use last phrase, flag it
- Very short tracks → place what fits, note what's missing
- Memory cue before track start → place at beat 1

## Data Model

```python
@dataclass
class Track:
    id: int
    title: str
    artist: str
    bpm: float                    # actual BPM (128.0, not 12800)
    duration_ms: float
    analysis_path: str
    cues: list[CuePoint]
    phrases: list[Phrase]
    beat_grid: BeatGrid

@dataclass
class CuePoint:
    kind: int                     # 0=memory, 1-9=hot cue slot
    position_ms: float
    loop_end_ms: float | None     # None if not a loop
    color_table_index: int
    color: int
    comment: str

@dataclass
class Phrase:
    beat_start: int
    beat_end: int                 # derived from next phrase's start
    kind: int                     # raw PSSI kind value
    label: str                    # resolved label (Intro, Up, Down, Chorus, Outro)
    position_ms: float
    duration_ms: float

@dataclass
class BeatGrid:
    entries: list[tuple[int, float]]  # (beat_number, ms_position)
    bpm: float

    def beat_to_ms(self, beat: int) -> float: ...
    def ms_to_beat(self, ms: float) -> int: ...
    def bars_to_ms(self, bars: int) -> float: ...

@dataclass
class CueSlot:
    pad: str                      # A-H
    kind: int                     # DB Kind value
    hot_cue_label: str
    memory_cue_label: str
    color_table_index: int
    color: int
    is_loop: bool
    memory_offset_bars: int       # 0 for same-position, 16 for others

@dataclass
class CueProposal:
    track: Track
    hot_cues: list[CuePoint]
    memory_cues: list[CuePoint]
    confidence: dict[str, float]  # per-slot confidence score
    notes: list[str]              # explanations for placement decisions
```

## CLI Interface

Entry point: `uv run djcues <command>`

### `propose` — Generate cue proposals

```bash
uv run djcues propose "Processed" "World Gone Wild"
uv run djcues propose "Processed" --all
```

Single track output shows phrases, then proposed hot cues and memory cues with positions, beat numbers, phrase associations, and confidence levels.

### `compare` — Validate against existing cues

```bash
uv run djcues compare "Processed" "World Gone Wild"
uv run djcues compare "Processed" --all
```

Shows existing vs. proposed cue positions with deltas. `--all` mode produces match-rate stats across the playlist — this is the primary heuristic tuning tool.

### `viz` — HTML timeline visualization

```bash
uv run djcues viz "Processed" "World Gone Wild"
uv run djcues viz "Processed" "World Gone Wild" --compare
```

Generates an HTML file and opens it in the default browser. Shows phrase timeline with color-coded segments and cue markers. Compare mode overlays existing and proposed cues.

## HTML Visualizer

Single-page HTML per track:

1. **Phrase timeline** — horizontal bar spanning track duration with colored segments for each phrase type. Labels inside segments.
2. **Cue markers** — vertical lines overlaid on timeline. Hot cues above the bar, memory cues below. Color-coded per cue system.
3. **Two modes:**
   - Propose: phrase timeline + proposed cues
   - Compare: existing cues (top) vs. proposed cues (bottom) with delta indicators

Not in v1: audio waveform rendering, interactive editing, audio playback. Waveform data is available in ANLZ PWV3/PWV4/PWV5 tags for future use.

## Project Structure

```
dj/
├── pyproject.toml
├── cue-system.csv
├── src/
│   └── djcues/
│       ├── __init__.py
│       ├── models.py           # dataclasses
│       ├── constants.py        # PSSI mood/kind tables, color mappings
│       ├── db.py               # rekordbox DB reader
│       ├── strategy.py         # CueStrategy + PSSI mapping
│       ├── viz.py              # HTML generator
│       └── cli.py              # click CLI
└── tests/
    ├── test_strategy.py
    └── test_db.py
```

## Dependencies

- `pyrekordbox` — DB + ANLZ reading (requires SQLCipher)
- `click` — CLI subcommands
- Standard library for everything else

## Testing

- `test_strategy.py` — unit tests: feed known phrase data, assert correct cue placements. Use real data from Processed playlist as fixtures.
- `test_db.py` — integration tests that read actual rekordbox DB. Skipped when DB not present.
- `compare --all` against the 48-track Processed playlist is the end-to-end validation suite for heuristic accuracy.

## Future Considerations

- Waveform rendering from ANLZ tags
- Smarter Loop In/Out detection (find smooth-looping sections)
- Vocal detection alignment (if analysis data available)
- Write support (apply proposals to DB — requires careful dual-write to DB + ANLZ)
- Additional analyzer info on Track model
