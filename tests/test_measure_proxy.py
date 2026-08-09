"""Tests for lib/measure-proxy.py — the capture-only local API proxy."""

import json
import threading
import urllib.request


# ---- path matching ----------------------------------------------------------

def test_capture_path_matches_messages_endpoint(measureproxy):
    assert measureproxy.is_capture_path("/v1/messages")
    assert measureproxy.is_capture_path("/v1/messages?beta=true")


def test_capture_path_ignores_other_endpoints(measureproxy):
    assert not measureproxy.is_capture_path("/v1/models")
    assert not measureproxy.is_capture_path("/health")


# ---- synthetic response shape ----------------------------------------------

def test_sse_events_follow_the_messages_streaming_order(measureproxy):
    kinds = [e for e, _ in measureproxy.sse_events("m", "PONG")]
    assert kinds == ["message_start", "content_block_start", "content_block_delta",
                     "content_block_stop", "message_delta", "message_stop"]


def test_sse_events_echo_model_and_text(measureproxy):
    events = dict(measureproxy.sse_events("claude-haiku-4-5", "PONG"))
    assert events["message_start"]["message"]["model"] == "claude-haiku-4-5"
    assert events["content_block_delta"]["delta"]["text"] == "PONG"


def test_sse_body_is_wire_formatted(measureproxy):
    body = measureproxy.sse_body("m", "PONG").decode()
    assert body.startswith("event: message_start\ndata: {")
    assert body.endswith("\n\n")


def test_json_body_is_a_valid_message(measureproxy):
    msg = json.loads(measureproxy.json_body("m", "PONG"))
    assert msg["type"] == "message" and msg["role"] == "assistant"
    assert msg["content"][0]["text"] == "PONG"


def test_wants_stream_reads_the_request_flag(measureproxy):
    assert measureproxy.wants_stream({"stream": True})
    assert not measureproxy.wants_stream({"stream": False})
    assert not measureproxy.wants_stream({})


# ---- round trip -------------------------------------------------------------

def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, resp.read().decode()


def test_proxy_captures_request_and_answers_without_upstream(measureproxy, tmp_path):
    capture = tmp_path / "capture.json"
    httpd, port = measureproxy.make_server(str(capture))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        payload = {"model": "claude-haiku-4-5", "stream": True,
                   "tools": [{"name": "Bash", "description": "run"}],
                   "messages": [{"role": "user", "content": "hi"}]}
        status, body = _post(f"http://127.0.0.1:{port}/v1/messages", payload)
    finally:
        httpd.shutdown()

    assert status == 200
    assert "PONG" in body
    assert json.loads(capture.read_text())["tools"][0]["name"] == "Bash"


def test_proxy_keeps_the_first_capture_when_called_twice(measureproxy, tmp_path):
    capture = tmp_path / "capture.json"
    httpd, port = measureproxy.make_server(str(capture))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        for tag in ("first", "second"):
            _post(f"http://127.0.0.1:{port}/v1/messages",
                  {"model": tag, "stream": True, "messages": []})
    finally:
        httpd.shutdown()

    assert json.loads(capture.read_text())["model"] == "first"
