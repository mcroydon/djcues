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
