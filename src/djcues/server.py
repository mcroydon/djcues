"""Local HTTP server for djcues review sessions.

Bridges the browser review UI to the session JSON file, handling CORS,
session reads/writes, and cue adjustment logic including memory cue
recalculation.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class ReviewHandler(BaseHTTPRequestHandler):
    """Request handler for the review session server.

    Class-level attributes ``html_path`` and ``session_path`` must be set
    before the handler is used (set by ``start_server`` via dynamic subclass).
    """

    html_path: Path
    session_path: Path

    # --- helpers --------------------------------------------------------

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Suppress default stderr logging."""

    def _read_session(self) -> dict:
        """Read and parse the session JSON file."""
        return json.loads(self.session_path.read_text(encoding="utf-8"))

    def _write_session(self, session: dict) -> None:
        """Write session dict back to JSON (pretty-printed)."""
        self.session_path.write_text(
            json.dumps(session, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _send_json(self, data: dict, status: int = 200) -> None:
        """Send a JSON response with CORS headers."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        """Read and parse the request body as JSON."""
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw) if raw else {}

    def _touch_activity(self) -> None:
        """Update the server's last-activity timestamp."""
        if hasattr(self.server, "_last_activity"):
            self.server._last_activity = time.monotonic()

    # --- CORS -----------------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802
        """Handle CORS preflight requests."""
        self._touch_activity()
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # --- GET ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        """Handle GET requests."""
        self._touch_activity()
        path = self.path.split("?")[0]  # strip query string

        if path in ("/", "/index.html"):
            self._serve_html()
        elif path == "/session":
            session = self._read_session()
            self._send_json(session)
        else:
            self._send_json({"error": "not found"}, status=404)

    def _serve_html(self) -> None:
        """Serve the review HTML file."""
        body = self.html_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # --- POST -----------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        """Handle POST requests."""
        self._touch_activity()
        path = self.path.split("?")[0]

        if path == "/session/accept-all":
            self._handle_accept_all()
        elif path.startswith("/session/track/"):
            self._route_track_post(path)
        else:
            self._send_json({"error": "not found"}, status=404)

    def _handle_accept_all(self) -> None:
        """Set all pending tracks and their cues to accepted."""
        session = self._read_session()
        for tdata in session.get("tracks", {}).values():
            if tdata.get("status") == "pending":
                tdata["status"] = "accepted"
                for cue in tdata.get("cues", {}).values():
                    if cue.get("status") == "pending":
                        cue["status"] = "accepted"
                for mc in tdata.get("memory_cues", {}).values():
                    if mc.get("status") == "pending":
                        mc["status"] = "accepted"
        self._write_session(session)
        self._send_json({"ok": True})

    def _route_track_post(self, path: str) -> None:
        """Route track-level POST requests to the right handler."""
        # Strip the prefix to get the remainder
        remainder = path[len("/session/track/"):]
        parts = remainder.split("/")

        # POST /session/track/<track_id>
        # POST /session/track/<track_id>/status  (alias used by JS)
        if len(parts) == 1 or (len(parts) == 2 and parts[1] == "status"):
            track_id = parts[0]
            self._handle_track_status(track_id)
        # POST /session/track/<track_id>/cue/<pad>
        elif len(parts) == 3 and parts[1] == "cue":
            track_id = parts[0]
            pad = parts[2]
            self._handle_cue_update(track_id, pad)
        else:
            self._send_json({"error": "not found"}, status=404)

    def _handle_track_status(self, track_id: str) -> None:
        """Update a track's status, cascading to all cues and memory cues."""
        body = self._read_body()
        new_status = body.get("status")
        if new_status not in ("accepted", "skipped"):
            self._send_json({"error": "invalid status"}, status=400)
            return

        session = self._read_session()
        tracks = session.get("tracks", {})
        if track_id not in tracks:
            self._send_json({"error": "track not found"}, status=404)
            return

        tdata = tracks[track_id]
        tdata["status"] = new_status
        # Cascade to all cues and memory cues
        for cue in tdata.get("cues", {}).values():
            cue["status"] = new_status
        for mc in tdata.get("memory_cues", {}).values():
            mc["status"] = new_status

        self._write_session(session)
        self._send_json({"ok": True})

    def _handle_cue_update(self, track_id: str, pad: str) -> None:
        """Update an individual cue, recalculating the memory cue."""
        from djcues.constants import CUE_SYSTEM

        body = self._read_body()
        new_status = body.get("status")
        if new_status not in ("adjusted", "skipped"):
            self._send_json({"error": "invalid status"}, status=400)
            return

        session = self._read_session()
        tracks = session.get("tracks", {})
        if track_id not in tracks:
            self._send_json({"error": "track not found"}, status=404)
            return

        tdata = tracks[track_id]
        cues = tdata.get("cues", {})
        if pad not in cues:
            self._send_json({"error": "cue not found"}, status=404)
            return

        pads = list("ABCDEFGH")
        if pad not in pads:
            self._send_json({"error": "invalid pad"}, status=400)
            return
        slot_idx = pads.index(pad)
        slot = CUE_SYSTEM[slot_idx]
        memory_key = str(slot_idx + 1)

        memory_cues = tdata.get("memory_cues", {})
        cue_entry = cues[pad]

        if new_status == "adjusted":
            # Store original position if not already stored
            if "original_ms" not in cue_entry:
                cue_entry["original_ms"] = cue_entry["position_ms"]

            # Update position
            new_position = body.get("position_ms", cue_entry["position_ms"])
            new_loop_end = body.get("loop_end_ms", cue_entry.get("loop_end_ms"))
            cue_entry["position_ms"] = new_position
            cue_entry["loop_end_ms"] = new_loop_end
            cue_entry["status"] = "adjusted"

            # Recalculate corresponding memory cue
            offset_bars = session.get("settings", {}).get(
                "memory_offset_bars", 16
            )
            if memory_key in memory_cues:
                mc = memory_cues[memory_key]
                if slot.memory_offset_bars == 0:
                    mc["position_ms"] = new_position
                    mc["loop_end_ms"] = new_loop_end
                else:
                    bpm = tdata.get("bpm", 128.0)
                    bar_ms = (60_000 / bpm) * 4
                    mem_pos = new_position - offset_bars * bar_ms
                    first_beat = tdata.get("first_beat_ms", 0)
                    mc["position_ms"] = max(mem_pos, first_beat)
                    mc["loop_end_ms"] = None
                mc["status"] = "auto"

        elif new_status == "skipped":
            cue_entry["status"] = "skipped"
            # Also skip the corresponding memory cue
            if memory_key in memory_cues:
                memory_cues[memory_key]["status"] = "skipped"

        # Set track status to adjusted
        tdata["status"] = "adjusted"

        self._write_session(session)
        self._send_json({"ok": True})


def start_server(
    html_path: Path,
    session_path: Path,
    port: int = 0,
    timeout_minutes: int = 30,
) -> tuple[HTTPServer, int]:
    """Start the review server in a daemon thread.

    Returns ``(server, actual_port)`` where *actual_port* is the
    OS-assigned port when *port* is 0.
    """
    # Dynamically create a handler subclass with paths baked in as class
    # attributes, so each request handler instance can access them via self.
    handler = type(
        "BoundReviewHandler",
        (ReviewHandler,),
        {"html_path": html_path, "session_path": session_path},
    )

    server = HTTPServer(("127.0.0.1", port), handler)
    actual_port = server.server_address[1]
    server._last_activity = time.monotonic()  # type: ignore[attr-defined]
    server._shutdown_flag = False  # type: ignore[attr-defined]

    timeout_seconds = timeout_minutes * 60

    def _serve() -> None:
        server.timeout = 10  # handle_request blocks at most 10 s
        while not server._shutdown_flag:  # type: ignore[attr-defined]
            server.handle_request()
            elapsed = time.monotonic() - server._last_activity  # type: ignore[attr-defined]
            if elapsed > timeout_seconds:
                break
        server.server_close()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    return server, actual_port
