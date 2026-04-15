"""Cue placement strategy engine — maps PSSI phrases to cue points."""

from __future__ import annotations

from djcues.constants import CUE_SYSTEM, CUE_SYSTEM_BY_PAD
from djcues.models import BeatGrid, CuePoint, CueProposal, Phrase, Track


def _spectral_similarity(wf_points: list, i0: int, i_mid: int, i1: int) -> float:
    """Compare the RGB (bass/mid/treble) profile of two halves of a waveform section.

    Returns a similarity score from 0.0 (completely different) to 1.0 (identical).
    Uses mean-squared-error of the per-point RGB values, normalized.
    """
    half_len = min(i_mid - i0, i1 - i_mid)
    if half_len < 2:
        return 0.0

    first_half = wf_points[i0 : i0 + half_len]
    second_half = wf_points[i_mid : i_mid + half_len]

    total_mse = 0.0
    for a, b in zip(first_half, second_half):
        # RGB values are 0-7, normalize to 0-1
        dr = (a.red - b.red) / 7
        dg = (a.green - b.green) / 7
        db = (a.blue - b.blue) / 7
        dh = a.height - b.height  # already 0-1
        total_mse += dr * dr + dg * dg + db * db + dh * dh

    # Max possible MSE per point = 4 (all channels off by 1.0)
    mse = total_mse / half_len / 4
    return max(0.0, 1.0 - mse)


def _find_stable_loop(
    track: Track,
    search_start_ms: float,
    search_end_ms: float,
    bar_sizes: tuple[int, ...] = (8, 4, 2, 1),
    min_energy: float = 0.05,
    min_similarity: float = 0.7,
) -> tuple[float, int, float] | None:
    """Find a stable, loopable region using waveform energy and spectral similarity.

    Scans bar-aligned windows from search_start_ms forward. Tries 8 bars first,
    then falls back to 4, 2, 1. A good loop has non-trivial energy AND the
    second half spectrally matches the first half (so the loop repeats cleanly).

    Returns (position_ms, loop_bars, similarity_score) or None if nothing found.
    """
    if not track.waveform:
        return None

    bg = track.beat_grid
    n = len(track.waveform)
    total_ms = track.duration_ms
    if total_ms <= 0 or n == 0:
        return None

    for loop_bars in bar_sizes:
        loop_ms = bg.bars_to_ms(loop_bars)
        best_pos = None
        best_score = 0.0

        # Snap search start to bar boundary
        start_beat = bg.ms_to_beat(search_start_ms)
        bar_start = ((start_beat - 1) // 4) * 4 + 1
        pos_ms = bg.beat_to_ms(bar_start)

        while pos_ms + loop_ms <= search_end_ms and pos_ms + loop_ms <= total_ms:
            # Map to waveform indices
            i0 = int(n * pos_ms / total_ms)
            i1 = int(n * (pos_ms + loop_ms) / total_ms)
            i_mid = (i0 + i1) // 2
            if i1 - i0 < 4:
                pos_ms += bg.bars_to_ms(1)
                continue

            # Check energy
            heights = [p.height for p in track.waveform[i0:i1]]
            mean_e = sum(heights) / len(heights)
            if mean_e < min_energy:
                pos_ms += bg.bars_to_ms(1)
                continue

            # Check spectral similarity between halves
            similarity = _spectral_similarity(track.waveform, i0, i_mid, i1)
            if similarity > best_score:
                best_score = similarity
                best_pos = pos_ms

            pos_ms += bg.bars_to_ms(1)

        if best_pos is not None and best_score >= min_similarity:
            return (best_pos, loop_bars, best_score)

            pos_ms += bg.bars_to_ms(1)  # slide by 1 bar

    return None


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

        # --- B: Loop In (same as First Beat) ---
        # Data shows 88% of the time users loop at the First Beat.
        # Spectral similarity is noted for reference but doesn't override.
        positions["B"] = positions["A"]
        confidence["B"] = 0.6
        notes.append("B (Loop In): same position as First Beat")

        # --- D: Drop (first Chorus or Up after ~25% of track) ---
        # The Drop is the first major energy peak after the intro section.
        # Data shows it's typically around 30% into the track (median).
        # Look for the first Chorus (or Up preceded by a Chorus) that's
        # at least 25% into the track. Fallback to first Chorus after
        # the first Up→Chorus cycle.
        choruses = [p for p in phrases if p.label == "Chorus"]
        drop_candidates = [p for p in phrases if p.label in ("Chorus", "Up")]
        min_drop_ms = track.duration_ms * 0.20  # at least 20% into track
        if choruses:
            # Primary: first Chorus at or after 20% mark
            late_choruses = [c for c in choruses if c.position_ms >= min_drop_ms]
            if late_choruses:
                drop_phrase = late_choruses[0]
                notes.append(f"D (Drop): first Chorus after 20% at beat {drop_phrase.beat_start}")
            else:
                # All choruses are early — check for an Up after the last early Chorus
                last_early_chorus = choruses[-1]
                ups_after = [p for p in phrases
                             if p.label == "Up"
                             and p.position_ms > last_early_chorus.position_ms]
                if ups_after:
                    drop_phrase = ups_after[0]
                    notes.append(
                        f"D (Drop): Up after early Chorus, beat {drop_phrase.beat_start}"
                    )
                else:
                    # Last resort: last Chorus
                    drop_phrase = choruses[-1]
                    notes.append(f"D (Drop): last Chorus at beat {drop_phrase.beat_start}")
            positions["D"] = drop_phrase.position_ms
            confidence["D"] = 0.85
        else:
            notes.append("D (Drop): no Chorus found — skipped")
            confidence["D"] = 0.0

        # --- C: Vocal / Buildup ---
        # Primary: use PVDI vocal detection to find first strong vocal onset
        # before the Drop, snapped to nearest phrase boundary.
        # Fallback: phrase-based heuristic (last Up before Drop).
        vocal_placed = False
        c_drop_ms = positions.get("D", track.duration_ms)
        if track.vocal_track:
            frame_ms = 1024 / 22050 * 1000  # ~46.4ms per PVDI frame
            vt = track.vocal_track
            min_frames = int(2000 / frame_ms)  # require at least 2s of vocal
            i = 0
            while i < len(vt):
                if vt[i] >= 3:  # strong vocal confidence
                    start = i
                    while i < len(vt) and vt[i] > 0:
                        i += 1
                    region_ms = start * frame_ms
                    if i - start >= min_frames and region_ms < c_drop_ms:
                        # Snap to nearest phrase boundary
                        best_phrase = None
                        best_dist = float("inf")
                        for p in phrases:
                            dist = abs(p.position_ms - region_ms)
                            if dist < best_dist:
                                best_dist = dist
                                best_phrase = p
                        if best_phrase and best_dist < bg.bars_to_ms(4):
                            positions["C"] = best_phrase.position_ms
                            confidence["C"] = 0.85
                            notes.append(
                                f"C (Vocal/Buildup): vocal at {region_ms / 1000:.1f}s, "
                                f"snapped to {best_phrase.label} beat {best_phrase.beat_start}"
                            )
                        else:
                            snap_beat = bg.ms_to_beat(region_ms)
                            bar_beat = ((snap_beat - 1) // 4) * 4 + 1
                            positions["C"] = bg.beat_to_ms(bar_beat)
                            confidence["C"] = 0.8
                            notes.append(
                                f"C (Vocal/Buildup): vocal at {region_ms / 1000:.1f}s, "
                                f"snapped to beat {bar_beat}"
                            )
                        vocal_placed = True
                        break
                else:
                    i += 1

        if not vocal_placed:
            if "D" in positions:
                ups_before = [
                    p for p in phrases
                    if p.label in ("Up", "Verse1", "Verse2", "Verse3", "Verse4", "Verse5", "Verse6")
                    and p.position_ms < c_drop_ms
                ]
                if ups_before:
                    vocal_phrase = ups_before[-1]
                    positions["C"] = vocal_phrase.position_ms
                    confidence["C"] = 0.5
                    notes.append(f"C (Vocal/Buildup): no vocal data, {vocal_phrase.label} at beat {vocal_phrase.beat_start}")
                else:
                    before_drop = [p for p in phrases if p.position_ms < c_drop_ms]
                    if before_drop:
                        fallback = before_drop[-1]
                        positions["C"] = fallback.position_ms
                        confidence["C"] = 0.3
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
        # Spectral similarity analysis showed that overriding phrase-based
        # positions hurts accuracy. Keeping at Outro start as the safest default.
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
