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
