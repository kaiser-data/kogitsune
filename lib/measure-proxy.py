#!/usr/bin/env python3
"""kogitsune — a capture-only local stand-in for the Anthropic API.

Claude Code builds its tool schemas and system prompt on the client, so the only
place to see what a kit actually costs is the request body. Point the CLI here
with ANTHROPIC_BASE_URL, run one throwaway prompt, and the first /v1/messages
body lands on disk for lib/tool-report.py to break down.

Deliberately does NOT forward upstream. Measurement only needs the request, so
skipping the round trip makes `kit measure --proxy` free, offline, repeatable,
and impossible to bill. The probe gets a synthetic reply instead — enough for the
CLI to finish cleanly and exit. Use plain `kit measure <name>` when you want real
token counts from the API.

Binds 127.0.0.1 only. Serves until killed (the caller owns its lifetime) or until
--timeout expires, whichever comes first.

    measure-proxy.py --capture /tmp/req.json --port-file /tmp/port
"""
from __future__ import annotations

import argparse
import json
import os
import socketserver
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# What the synthetic assistant replies. The probe prompt asks for exactly this,
# so a captured run looks like a successful one to the caller.
REPLY_TEXT = "PONG"

# Only bodies posted to the Messages endpoint are worth capturing.
CAPTURE_PATH_PREFIX = "/v1/messages"

# Safety net so an abandoned proxy can never outlive the shell that spawned it.
DEFAULT_TIMEOUT_S = 120


def is_capture_path(path: str) -> bool:
    """True for the Messages endpoint, with or without a query string. Pure."""
    return path.split("?", 1)[0].rstrip("/") == CAPTURE_PATH_PREFIX


def wants_stream(request: dict) -> bool:
    """Did the client ask for SSE? Pure."""
    return bool(request.get("stream"))


def sse_events(model: str, text: str) -> list[tuple[str, dict]]:
    """The minimal streaming-event sequence a Messages client expects. Pure."""
    return [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_kogitsune_probe", "type": "message", "role": "assistant",
            "model": model, "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta",
                           "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                           "usage": {"output_tokens": 1}}),
        ("message_stop", {"type": "message_stop"}),
    ]


def sse_body(model: str, text: str) -> bytes:
    """Serialize the event sequence to the SSE wire format. Pure."""
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n"
                   for name, data in sse_events(model, text)).encode()


def json_body(model: str, text: str) -> bytes:
    """A non-streaming Messages response. Pure."""
    return json.dumps({
        "id": "msg_kogitsune_probe", "type": "message", "role": "assistant",
        "model": model, "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 1},
    }).encode()


def _write_capture(path: str, raw: bytes) -> None:
    """Persist the first request body only; later turns would overwrite the one
    we care about (the fully-loaded first request)."""
    if os.path.exists(path):
        return
    tmp = f"{path}.{os.getpid()}"
    with open(tmp, "wb") as fh:
        fh.write(raw)
    os.replace(tmp, path)


def _handler_for(capture_path: str, captured: threading.Event):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):  # keep the probe's stderr clean
            pass

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("content-type", content_type)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler's naming
            raw = self.rfile.read(int(self.headers.get("content-length") or 0))
            try:
                request = json.loads(raw or b"{}")
            except ValueError:
                request = {}
            if is_capture_path(self.path):
                _write_capture(capture_path, raw)
                captured.set()
            model = request.get("model", "unknown")
            if wants_stream(request):
                self._send(sse_body(model, REPLY_TEXT), "text/event-stream")
            else:
                self._send(json_body(model, REPLY_TEXT), "application/json")

        def do_GET(self):  # noqa: N802 — some clients probe before posting
            self._send(b"{}", "application/json")

    return Handler


def make_server(capture_path: str, port: int = 0):
    """Bind a capture server on loopback. Returns (httpd, port). The caller runs it."""
    captured = threading.Event()
    socketserver.TCPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _handler_for(capture_path, captured))
    httpd.daemon_threads = True
    httpd.captured = captured  # let callers wait on the first capture
    return httpd, httpd.server_address[1]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Capture-only Anthropic API stand-in.")
    p.add_argument("--capture", required=True, help="where to write the request body")
    p.add_argument("--port-file", help="write the bound port here once listening")
    p.add_argument("--port", type=int, default=0, help="0 picks a free port")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S,
                   help="give up if nothing is captured in this many seconds")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        httpd, port = make_server(ns.capture, ns.port)
    except OSError as exc:
        print(f"measure-proxy: cannot bind port {ns.port}: {exc}", file=sys.stderr)
        return 1
    if ns.port_file:
        with open(ns.port_file, "w") as fh:
            fh.write(str(port))
    print(f"measure-proxy: listening on http://127.0.0.1:{port}", file=sys.stderr)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    ok = httpd.captured.wait(ns.timeout)
    httpd.shutdown()
    if not ok:
        print("measure-proxy: timed out before any request arrived", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
