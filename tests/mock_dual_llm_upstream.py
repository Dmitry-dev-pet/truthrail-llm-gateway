#!/usr/bin/env python3
"""Synthetic dual-model upstream and client; no external network or secrets.

This fixture runs on an internal-only Docker network against the real pinned
CLIProxyAPI binary. Only exact coding-task protocols and model IDs are accepted.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import sys
import time
import urllib.error
import urllib.request

CLIENT_KEY = "c" * 64
UPSTREAM_KEY = "g" * 64
AGENT_ID = "Truthrail-Coding-Agent/1.0"
MODEL_GLM = "glm-5.3-flash"
MODEL_LUNA = "gpt-6-luna"
STUB_PORT = 8766
BASE_GATEWAY = "http://gateway:8317/v1"
COUNTS = {
    "total": 0, "glm": 0, "luna": 0, "wrong_path": 0,
    "wrong_auth": 0, "wrong_model": 0, "wrong_session": 0,
    "wrong_agent": 0, "unexpected_tools": 0, "oversize_request": 0,
}


def expected_stats():
    return {
        "total": 2, "glm": 1, "luna": 1, "wrong_path": 0,
        "wrong_auth": 0, "wrong_model": 0, "wrong_session": 0,
        "wrong_agent": 0, "unexpected_tools": 0, "oversize_request": 0,
    }


def glm_response():
    return {
        "id": "chatcmpl-local-glm", "object": "chat.completion", "created": 1780000000,
        "model": MODEL_GLM,
        "choices": [{
            "index": 0, "message": {"role": "assistant", "content": "PASS"},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 18, "completion_tokens": 1, "total_tokens": 19},
    }


def luna_response():
    return {
        "id": "resp-local-luna", "object": "response", "created_at": 1780000000,
        "model": MODEL_LUNA, "status": "completed",
        "output": [{
            "id": "msg-local-luna", "type": "message", "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "PASS", "annotations": []}],
        }],
        "usage": {"input_tokens": 21, "output_tokens": 1, "total_tokens": 22},
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *unused):
        return  # Never log incoming prompts, bearer values, or headers.

    def _send(self, code: int, body: dict):
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path != "/_stats":
            return self._send(404, {"error": "no_route"})
        return self._send(200, COUNTS)

    def do_POST(self):
        COUNTS["total"] += 1
        route = {
            "/v1/chat/completions": (MODEL_GLM, "glm", "dual-glm-session"),
            "/v1/responses": (MODEL_LUNA, "luna", "dual-luna-session"),
        }.get(self.path)
        if route is None:
            COUNTS["wrong_path"] += 1
            return self._send(400, {"error": "wrong_path"})
        model, kind, session = route
        length = self.headers.get("Content-Length", "")
        if not length.isdecimal() or not 0 < int(length) <= 8192:
            COUNTS["oversize_request"] += 1
            return self._send(413, {"error": "oversize"})
        try:
            payload = json.loads(self.rfile.read(int(length)))
        except (ValueError, UnicodeError):
            return self._send(400, {"error": "invalid_json"})
        if not isinstance(payload, dict):
            return self._send(400, {"error": "invalid_shape"})
        if self.headers.get("Authorization") != "Bearer " + UPSTREAM_KEY:
            COUNTS["wrong_auth"] += 1
        if self.headers.get("X-OpenCode-Session") != session:
            COUNTS["wrong_session"] += 1
        if self.headers.get("User-Agent") != AGENT_ID:
            COUNTS["wrong_agent"] += 1
        if payload.get("model") != model:
            COUNTS["wrong_model"] += 1
        if payload.get("tools"):
            COUNTS["unexpected_tools"] += 1
        if kind == "glm":
            if not payload.get("messages") or not isinstance(payload.get("messages"), list):
                COUNTS["wrong_model"] += 1
            max_tokens = payload.get("max_tokens", 32)
        else:
            if not payload.get("input"):
                COUNTS["wrong_model"] += 1
            max_tokens = payload.get("max_output_tokens", 32)
        if (type(max_tokens) is not int or max_tokens > 64 or max_tokens < 1):
            COUNTS["wrong_model"] += 1
        if any(COUNTS[k] for k in ("wrong_auth", "wrong_session", "wrong_agent",
                                  "wrong_model", "unexpected_tools")):
            return self._send(400, {"error": "synthetic_contract_mismatch"})
        COUNTS[kind] += 1
        return self._send(200, glm_response() if kind == "glm" else luna_response())


def _client_request(model: str, proto: str, session: str, authorized=True):
    req = {"model": "opencode-go/" + model, "stream": False}
    if proto == "chat/completions":
        req["messages"] = [{"role": "user", "content": "Check increment(3)==4; reply PASS."}]
        req["max_tokens"] = 32
    else:
        req["input"] = [{"role": "user", "content": [
            {"type": "input_text", "text": "Check increment(3)==4; reply PASS."},
        ]}]
        req["max_output_tokens"] = 32
    headers = {"Content-Type": "application/json", "X-OpenCode-Session": session}
    if authorized:
        headers["Authorization"] = "Bearer " + CLIENT_KEY
    return urllib.request.Request(
        BASE_GATEWAY + "/" + proto, data=json.dumps(req).encode("utf-8"),
        method="POST", headers=headers,
    )


def run_client():
    for _ in range(80):
        try:
            with socket.create_connection(("gateway", 8317), timeout=0.5):
                break
        except OSError:
            time.sleep(0.15)
    else:
        raise RuntimeError("gateway_not_ready")

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for model, proto, session in (
        (MODEL_GLM, "chat/completions", "dual-glm-session"),
        (MODEL_LUNA, "responses", "dual-luna-session"),
    ):
        # A bad caller must be denied *before* contacting either upstream.
        try:
            with opener.open(_client_request(model, proto, session, False), timeout=4):
                raise RuntimeError("gateway_accepted_anonymous_call")
        except urllib.error.HTTPError as exc:
            if exc.code not in (401, 403):
                raise RuntimeError("anonymous_status_not_denied") from exc
    with opener.open("http://127.0.0.1:8766/_stats", timeout=2) as response:
        if json.load(response)["total"] != 0:
            raise RuntimeError("anonymous_request_reached_upstream")

    for model, proto, session in (
        (MODEL_GLM, "chat/completions", "dual-glm-session"),
        (MODEL_LUNA, "responses", "dual-luna-session"),
    ):
        with opener.open(_client_request(model, proto, session), timeout=25) as response:
            if response.status != 200:
                raise RuntimeError("gateway_returned_non_success")
            raw = response.read(65537)
            if len(raw) > 65536:
                raise RuntimeError("gateway_reply_exceeds_limit")
        reply = json.loads(raw)
        if reply.get("model") not in (model, "opencode-go/" + model):
            raise RuntimeError("unexpected_gateway_model")
        if proto == "responses":
            if reply.get("status") != "completed":
                raise RuntimeError("luna_response_not_completed")
            texts = [p.get("text") for item in reply.get("output", [])
                     if item.get("type") == "message"
                     for p in item.get("content", [])
                     if p.get("type") == "output_text"]
            if texts != ["PASS"]:
                raise RuntimeError("unexpected_responses_content")
        else:
            choices = reply.get("choices", [])
            if not isinstance(choices, list) or len(choices) != 1:
                raise RuntimeError("bad_chat_choice")
            if choices[0].get("message", {}).get("content") != "PASS":
                raise RuntimeError("unexpected_chat_content")

    with opener.open("http://127.0.0.1:8766/_stats", timeout=2) as response:
        counts = json.load(response)
    if counts != expected_stats():
        raise RuntimeError("upstream_dual_contract_mismatch")
    print("dual_gateway_smoke=PASS glm=1 luna=1 anonymous_denied=2 "
          "upstream_calls=2 protocol_isolation=true no_external_provider=true")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("server", "client"):
        raise SystemExit("Only fixed client/server modes are supported")
    if sys.argv[1] == "server":
        ThreadingHTTPServer(("0.0.0.0", STUB_PORT), Handler).serve_forever()
        return 0
    try:
        run_client()
    except urllib.error.HTTPError as exc:
        print(f"dual_gateway_smoke=FAIL gateway_http_status={exc.code}", file=sys.stderr)
        return 2
    except (ValueError, TypeError, KeyError, IndexError, OSError,
            urllib.error.URLError, RuntimeError, json.JSONDecodeError) as exc:
        # Enumerated error class only. No raw provider request or response.
        reason = str(exc)
        allowed = {
            "gateway_not_ready", "gateway_accepted_anonymous_call",
            "anonymous_status_not_denied", "anonymous_request_reached_upstream",
            "gateway_returned_non_success", "gateway_reply_exceeds_limit",
            "unexpected_gateway_model", "luna_response_not_completed",
            "unexpected_responses_content", "bad_chat_choice",
            "unexpected_chat_content", "upstream_dual_contract_mismatch",
        }
        print("dual_gateway_smoke=FAIL reason=" +
              (reason if reason in allowed else "local_contract_error"),
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
