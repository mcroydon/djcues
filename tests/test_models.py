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
