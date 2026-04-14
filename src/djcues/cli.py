"""CLI for djcues — propose and compare cue placements."""

from __future__ import annotations

import json
import logging
import warnings
import click

# Suppress noisy pyrekordbox warnings (PVDI tag, rekordbox running, etc.)
for _name in ("pyrekordbox", "pyrekordbox.db6", "pyrekordbox.anlz"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", module="pyrekordbox")

from djcues.constants import CUE_SYSTEM_BY_PAD, KIND_TO_PAD
from djcues.db import find_playlist, load_playlist_tracks
from djcues.strategy import CueStrategy


def _format_time(ms: float) -> str:
    """Format milliseconds as M:SS.s"""
    total_seconds = ms / 1000
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:04.1f}"


def _print_proposal(proposal, track):
    """Print a full cue proposal for a single track."""
    click.echo(f"\n{'=' * 60}")
    click.echo(f"  {track.title} — {track.artist}")
    click.echo(f"  BPM: {track.bpm:.1f}")
    click.echo(f"{'=' * 60}")

    # Phrases
    click.echo(f"\n  Phrases ({len(track.phrases)}):")
    for p in track.phrases:
        bars = p.beat_length // 4
        click.echo(
            f"    {p.label:<12s}  beat {p.beat_start:>4d}–{p.beat_end:<4d}"
            f"  ({bars:>2d} bars)  {_format_time(p.position_ms)}"
        )

    # Hot cues (sorted by kind)
    click.echo(f"\n  Hot Cues ({len(proposal.hot_cues)}):")
    for hc in sorted(proposal.hot_cues, key=lambda c: c.kind):
        pad = KIND_TO_PAD.get(hc.kind, "?")
        conf = proposal.confidence.get(pad, 0.0)
        beat = track.beat_grid.ms_to_beat(hc.position_ms)
        loop_info = ""
        if hc.is_loop and hc.loop_end_ms is not None:
            loop_info = f"  loop→{_format_time(hc.loop_end_ms)}"
        click.echo(
            f"    [{pad}] {hc.comment:<20s}  {_format_time(hc.position_ms)}"
            f"  beat {beat:>4d}  conf={conf:.0%}{loop_info}"
        )

    # Memory cues (sorted by position)
    click.echo(f"\n  Memory Cues ({len(proposal.memory_cues)}):")
    for i, mc in enumerate(sorted(proposal.memory_cues, key=lambda c: c.position_ms)):
        slot_info = ""
        # Find which slot this memory cue belongs to by matching comment
        for pad, slot in CUE_SYSTEM_BY_PAD.items():
            if slot.memory_cue_label == mc.comment:
                if slot.memory_offset_bars > 0:
                    slot_info = f"  ({slot.memory_offset_bars} bars before {slot.hot_cue_label})"
                else:
                    slot_info = f"  (same as {slot.hot_cue_label})"
                break
        loop_info = ""
        if mc.is_loop and mc.loop_end_ms is not None:
            loop_info = f"  loop→{_format_time(mc.loop_end_ms)}"
        click.echo(
            f"    [{i + 1}] {mc.comment:<20s}  {_format_time(mc.position_ms)}"
            f"{slot_info}{loop_info}"
        )

    # Notes
    if proposal.notes:
        click.echo(f"\n  Notes:")
        for note in proposal.notes:
            click.echo(f"    • {note}")


def _print_comparison(proposal, track):
    """Print side-by-side comparison of existing vs proposed hot cues."""
    click.echo(f"\n{'=' * 60}")
    click.echo(f"  {track.title} — {track.artist}")
    click.echo(f"  BPM: {track.bpm:.1f}")
    click.echo(f"{'=' * 60}")

    # Build lookup of existing hot cues by kind
    existing_by_kind = {}
    for c in track.cues:
        if c.kind > 0:  # hot cues only (kind > 0)
            existing_by_kind[c.kind] = c

    # Build lookup of proposed hot cues by kind
    proposed_by_kind = {}
    for c in proposal.hot_cues:
        proposed_by_kind[c.kind] = c

    # Get all kinds present in either set
    all_kinds = sorted(set(existing_by_kind.keys()) | set(proposed_by_kind.keys()))

    matches = 0
    total = 0

    click.echo(f"\n  {'Pad':<5s} {'Label':<20s} {'Existing':<12s} {'Proposed':<12s} {'Delta':>8s}")
    click.echo(f"  {'-' * 5} {'-' * 20} {'-' * 12} {'-' * 12} {'-' * 8}")

    for kind in all_kinds:
        pad = KIND_TO_PAD.get(kind, "?")
        slot = CUE_SYSTEM_BY_PAD.get(pad)
        label = slot.hot_cue_label if slot else f"Kind {kind}"

        existing = existing_by_kind.get(kind)
        proposed = proposed_by_kind.get(kind)

        existing_str = _format_time(existing.position_ms) if existing else "—"
        proposed_str = _format_time(proposed.position_ms) if proposed else "—"

        delta_str = ""
        if existing and proposed:
            total += 1
            delta_ms = proposed.position_ms - existing.position_ms
            delta_str = f"{delta_ms:+.0f}ms"
            if abs(delta_ms) <= 1000:
                matches += 1
                delta_str += " ✓"
        elif existing:
            total += 1
            delta_str = "missing"
        elif proposed:
            delta_str = "new"

        click.echo(
            f"  [{pad}]   {label:<20s} {existing_str:<12s} {proposed_str:<12s} {delta_str:>8s}"
        )

    if total > 0:
        pct = matches / total * 100
        click.echo(f"\n  Match rate: {matches}/{total} ({pct:.0f}%) within 1s tolerance")
    else:
        click.echo(f"\n  No existing hot cues to compare.")

    return matches, total


@click.group()
def cli():
    """djcues — automated rekordbox cue placement based on phrase analysis."""
    pass


@cli.command()
@click.argument("playlist_name")
@click.argument("track_name", required=False)
@click.option("--all", "all_tracks", is_flag=True, help="Process all tracks in the playlist.")
@click.option("--offset", default=16, show_default=True, help="Memory cue offset in bars.")
@click.option("--loop-bars", default=4, show_default=True, help="Loop length in bars.")
def propose(playlist_name, track_name, all_tracks, offset, loop_bars):
    """Propose cue placements for tracks in a playlist."""
    playlist = find_playlist(playlist_name)
    if playlist is None:
        click.echo(f"Error: playlist '{playlist_name}' not found.", err=True)
        raise SystemExit(1)

    tracks = load_playlist_tracks(playlist.ID)
    if not tracks:
        click.echo(f"Error: no tracks found in playlist '{playlist_name}'.", err=True)
        raise SystemExit(1)

    strategy = CueStrategy(memory_offset_bars=offset, loop_length_bars=loop_bars)

    if all_tracks:
        for t in tracks:
            proposal = strategy.propose(t)
            _print_proposal(proposal, t)
    elif track_name:
        matched = [t for t in tracks if track_name.lower() in t.title.lower()]
        if not matched:
            click.echo(f"Error: no track matching '{track_name}' in playlist.", err=True)
            raise SystemExit(1)
        for t in matched:
            proposal = strategy.propose(t)
            _print_proposal(proposal, t)
    else:
        click.echo("Error: provide a track name or use --all.", err=True)
        raise SystemExit(1)


@cli.command()
@click.argument("playlist_name")
@click.argument("track_name", required=False)
@click.option("--all", "all_tracks", is_flag=True, help="Compare all tracks in the playlist.")
@click.option("--offset", default=16, show_default=True, help="Memory cue offset in bars.")
@click.option("--loop-bars", default=4, show_default=True, help="Loop length in bars.")
def compare(playlist_name, track_name, all_tracks, offset, loop_bars):
    """Compare existing cues with proposed placements."""
    playlist = find_playlist(playlist_name)
    if playlist is None:
        click.echo(f"Error: playlist '{playlist_name}' not found.", err=True)
        raise SystemExit(1)

    tracks = load_playlist_tracks(playlist.ID)
    if not tracks:
        click.echo(f"Error: no tracks found in playlist '{playlist_name}'.", err=True)
        raise SystemExit(1)

    strategy = CueStrategy(memory_offset_bars=offset, loop_length_bars=loop_bars)

    total_matches = 0
    total_cues = 0

    if all_tracks:
        for t in tracks:
            proposal = strategy.propose(t)
            m, c = _print_comparison(proposal, t)
            total_matches += m
            total_cues += c
        if total_cues > 0:
            pct = total_matches / total_cues * 100
            click.echo(f"\n{'=' * 60}")
            click.echo(f"  Overall accuracy: {total_matches}/{total_cues} ({pct:.0f}%)")
            click.echo(f"{'=' * 60}")
    elif track_name:
        matched = [t for t in tracks if track_name.lower() in t.title.lower()]
        if not matched:
            click.echo(f"Error: no track matching '{track_name}' in playlist.", err=True)
            raise SystemExit(1)
        for t in matched:
            proposal = strategy.propose(t)
            _print_comparison(proposal, t)
    else:
        click.echo("Error: provide a track name or use --all.", err=True)
        raise SystemExit(1)


@cli.command()
@click.argument("playlist")
@click.argument("track_name", required=False)
@click.option("--all", "all_tracks", is_flag=True, help="Visualize all tracks in playlist")
@click.option("--compare", "compare_mode", is_flag=True, help="Show existing vs proposed")
@click.option("--offset", default=16, help="Memory cue offset in bars (default: 16)")
@click.option("--loop-bars", default=4, help="Loop length in bars (default: 4)")
@click.option("--output", "-o", default=None, help="Output file path (default: auto-generated)")
def viz(playlist, track_name, all_tracks, compare_mode, offset, loop_bars, output):
    """Generate an HTML timeline visualization."""
    import pathlib
    import webbrowser
    from djcues.viz import render_timeline, render_playlist

    pl = find_playlist(playlist)
    if pl is None:
        click.echo(f"Playlist '{playlist}' not found.", err=True)
        raise SystemExit(1)

    tracks = load_playlist_tracks(pl.ID)
    strategy = CueStrategy(memory_offset_bars=offset, loop_length_bars=loop_bars)

    if all_tracks:
        pairs = []
        for t in tracks:
            if t.phrases:
                pairs.append((t, strategy.propose(t)))
            else:
                click.echo(f"  Skipping {t.title} (no phrase data)", err=True)
        click.echo(f"Rendering {len(pairs)} tracks...")
        page_html = render_playlist(playlist, pairs, compare=compare_mode)
        if output:
            out_path = pathlib.Path(output)
        else:
            safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in playlist).strip().replace(" ", "-").lower()
            out_path = pathlib.Path(f"{safe_name}-cues.html")
    else:
        if not track_name:
            click.echo("Provide a track name or use --all.", err=True)
            raise SystemExit(1)

        matches = [t for t in tracks if track_name.lower() in t.title.lower()]
        if not matches:
            click.echo(f"No track matching '{track_name}' in playlist '{playlist}'.", err=True)
            raise SystemExit(1)

        track = matches[0]
        if not track.phrases:
            click.echo(f"{track.title} has no phrase data.", err=True)
            raise SystemExit(1)

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


@cli.command()
@click.argument("playlist")
@click.argument("track_name", required=False)
@click.option("--all", "all_tracks", is_flag=True, help="Review all tracks in playlist")
@click.option("--offset", default=16, help="Memory cue offset in bars (default: 16)")
@click.option("--loop-bars", default=4, help="Loop length in bars (default: 4)")
@click.option("--output", "-o", default=None, help="Output directory (default: current dir)")
def review(playlist, track_name, all_tracks, offset, loop_bars, output):
    """Launch interactive review session in browser."""
    import pathlib
    import time
    import webbrowser
    from djcues.review import create_session, render_review_html
    from djcues.server import start_server

    pl = find_playlist(playlist)
    if pl is None:
        click.echo(f"Playlist '{playlist}' not found.", err=True)
        raise SystemExit(1)

    tracks = load_playlist_tracks(pl.ID)
    if not tracks:
        click.echo(f"No tracks found in playlist '{playlist}'.", err=True)
        raise SystemExit(1)

    strategy = CueStrategy(memory_offset_bars=offset, loop_length_bars=loop_bars)

    if all_tracks:
        selected = tracks
    elif track_name:
        selected = [t for t in tracks if track_name.lower() in t.title.lower()]
        if not selected:
            click.echo(f"No track matching '{track_name}' in playlist '{playlist}'.", err=True)
            raise SystemExit(1)
    else:
        click.echo("Provide a track name or use --all.", err=True)
        raise SystemExit(1)

    pairs = []
    for t in selected:
        if t.phrases:
            pairs.append((t, strategy.propose(t)))
        else:
            click.echo(f"  Skipping {t.title} (no phrase data)", err=True)

    if not pairs:
        click.echo("No tracks with phrase data to review.", err=True)
        raise SystemExit(1)

    # Generate session
    session = create_session(
        playlist_name=playlist,
        playlist_id=pl.ID,
        tracks_and_proposals=pairs,
        memory_offset_bars=offset,
        loop_length_bars=loop_bars,
    )

    # Determine output directory and safe name
    safe_name = "".join(
        c if c.isalnum() or c in " -_" else "" for c in playlist
    ).strip().replace(" ", "-").lower()

    if output:
        out_dir = pathlib.Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = pathlib.Path(".")

    session_path = out_dir / f"{safe_name}-session.json"
    session_path.write_text(
        json.dumps(session, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Start local server
    html_path = out_dir / f"{safe_name}-review.html"
    server, port = start_server(
        html_path=html_path,
        session_path=session_path,
    )
    server_url = f"http://127.0.0.1:{port}"

    # Generate review HTML with server URL embedded
    review_html = render_review_html(
        playlist_name=playlist,
        tracks_and_proposals=pairs,
        session_path=str(session_path),
        server_url=server_url,
    )
    html_path.write_text(review_html, encoding="utf-8")

    # Open browser
    webbrowser.open(server_url)

    # Print info
    click.echo(f"Session: {session_path}")
    click.echo(f"Server:  {server_url}")
    click.echo(f"Apply:   uv run djcues apply {session_path}")

    # Block until interrupted
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nServer stopped.")


@cli.command()
@click.argument("session_file", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Show what would be written without making changes")
@click.option("--force", is_flag=True, help="Skip overwrite confirmation")
def apply(session_file, dry_run, force):
    """Apply a review session to the rekordbox database."""
    import pathlib
    from djcues.writer import apply_session

    apply_session(
        session_path=pathlib.Path(session_file),
        dry_run=dry_run,
        force=force,
    )
