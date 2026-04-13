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
