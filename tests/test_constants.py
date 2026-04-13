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
