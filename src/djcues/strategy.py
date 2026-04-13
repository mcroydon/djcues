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
        notes.append("A (First Beat): beat 1")

        # --- B: Loop In (same as A) ---
        positions["B"] = positions["A"]
        confidence["B"] = 0.6
        notes.append("B (Loop In): same position as First Beat")

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
            ups_before = [
                p for p in phrases
                if p.label in ("Up", "Verse1", "Verse2", "Verse3", "Verse4", "Verse5", "Verse6")
                and p.position_ms < drop_ms
            ]
            if ups_before:
                vocal_phrase = ups_before[-1]
                positions["C"] = vocal_phrase.position_ms
                confidence["C"] = 0.7
                notes.append(f"C (Vocal/Buildup): {vocal_phrase.label} at beat {vocal_phrase.beat_start}")
            else:
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
                first_beat_ms = bg.beat_to_ms(1)
                if mem_pos < first_beat_ms:
                    mem_pos = first_beat_ms
                else:
                    # Snap to nearest downbeat (bar start)
                    mem_beat = bg.ms_to_beat(mem_pos)
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
