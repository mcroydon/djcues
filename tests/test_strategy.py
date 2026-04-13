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
    kinds = {c.kind for c in proposal.hot_cues}
    assert 1 in kinds  # A
    assert 8 in kinds  # G (Outro)
    if 5 in kinds:
        assert proposal.confidence["D"] < 0.5
