#!/usr/bin/env python3
"""Regression tests for the relay probe."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "probe_relay.py"


class MockRelayState:
    def __init__(self) -> None:
        self.cache_hits = 0
        self.openai_burst_seen = 0
        self.anthropic_burst_seen = 0
        self.requests: List[Dict[str, object]] = []


class MockRelayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state: MockRelayState

    def _read_json(self) -> Dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _write_json(self, status: int, payload: Dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("x-request-id", "mock-req")
        self.end_headers()
        self.wfile.write(body)

    def _write_sse(self, payload: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _record_request(self, body: Dict[str, object]) -> None:
        self.state.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "x_api_key": self.headers.get("x-api-key"),
                "anthropic_version": self.headers.get("anthropic-version"),
                "body": body,
            }
        )

    def _require_openai_auth(self) -> bool:
        return (
            self.headers.get("Authorization") == "Bearer test-key"
            and self.headers.get("x-api-key") is None
        )

    def _require_anthropic_auth(self) -> bool:
        return (
            self.headers.get("Authorization") is None
            and self.headers.get("x-api-key") == "test-key"
            and self.headers.get("anthropic-version") == "2023-06-01"
        )

    def do_GET(self) -> None:  # noqa: N802
        body: Dict[str, object] = {}
        self._record_request(body)
        if self.path != "/v1/models":
            self._write_json(404, {"error": "not found"})
            return

        if self.headers.get("Authorization") == "Bearer test-key":
            self._write_json(
                200,
                {"data": [{"id": "claude-sonnet-4-5"}, {"id": "gpt-4.1-mini"}]},
            )
            return

        if self.headers.get("x-api-key") == "test-key":
            self._write_json(
                200,
                {"data": [{"id": "claude-sonnet-4-5"}, {"id": "claude-haiku-3"}]},
            )
            return

        self._write_json(401, {"error": "missing auth"})

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_json()
        self._record_request(body)

        if self.path == "/v1/chat/completions":
            if not self._require_openai_auth():
                self._write_json(401, {"error": {"message": "bad openai auth"}})
                return

            model = body.get("model")
            if model == "__api_relay_audit_invalid_model__":
                self._write_json(400, {"error": {"message": "invalid model"}})
                return

            if body.get("stream"):
                self._write_sse(
                    b'data: {"id":"cmpl-1","choices":[{"delta":{"content":"OK"}}]}\n\n'
                )
                return

            messages = body.get("messages", [])
            prompt = ""
            if isinstance(messages, list) and messages:
                first = messages[0]
                if isinstance(first, dict):
                    prompt = str(first.get("content", ""))

            if "SECRET_TOKEN:" in prompt:
                token = prompt.split("SECRET_TOKEN:", 1)[1].splitlines()[0].strip()
                self._write_json(
                    200,
                    {"choices": [{"message": {"content": token}}], "usage": {}},
                )
                return

            if body.get("tools"):
                self._write_json(
                    200,
                    {
                        "choices": [
                            {
                                "message": {
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "ping",
                                                "arguments": '{"value":"ok"}',
                                            },
                                        }
                                    ]
                                }
                            }
                        ],
                        "usage": {},
                    },
                )
                return

            self.state.openai_burst_seen += 1
            if self.state.openai_burst_seen == 3:
                self._write_json(429, {"error": {"message": "rate limited"}})
                return

            self._write_json(
                200,
                {"choices": [{"message": {"content": "OK"}}], "usage": {}},
            )
            return

        if self.path == "/v1/messages":
            if not self._require_anthropic_auth():
                self._write_json(401, {"type": "error", "error": {"message": "bad anthropic auth"}})
                return

            model = body.get("model")
            if model == "__api_relay_audit_invalid_model__":
                self._write_json(
                    400,
                    {
                        "type": "error",
                        "error": {
                            "type": "invalid_request_error",
                            "message": "invalid model",
                        },
                    },
                )
                return

            if body.get("stream"):
                self._write_sse(
                    b'event: message_start\ndata: {"type":"message_start"}\n\n'
                )
                return

            messages = body.get("messages", [])
            prompt = ""
            if isinstance(messages, list) and messages:
                first = messages[0]
                if isinstance(first, dict):
                    prompt = str(first.get("content", ""))

            if "SECRET_TOKEN:" in prompt:
                token = prompt.split("SECRET_TOKEN:", 1)[1].splitlines()[0].strip()
                self._write_json(
                    200,
                    {
                        "content": [{"type": "text", "text": token}],
                        "usage": {"input_tokens": 10, "output_tokens": 1},
                    },
                )
                return

            if body.get("tools"):
                self._write_json(
                    200,
                    {
                        "content": [
                            {"type": "tool_use", "name": "ping", "input": {"value": "ok"}}
                        ],
                        "usage": {"input_tokens": 10, "output_tokens": 1},
                    },
                )
                return

            system_blocks = body.get("system")
            if isinstance(system_blocks, list) and system_blocks:
                self.state.cache_hits += 1
                if self.state.cache_hits == 1:
                    usage = {
                        "cache_creation_input_tokens": 1500,
                        "cache_read_input_tokens": 0,
                    }
                else:
                    usage = {
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 1500,
                    }
                self._write_json(
                    200,
                    {"content": [{"type": "text", "text": "OK"}], "usage": usage},
                )
                return

            self.state.anthropic_burst_seen += 1
            self._write_json(
                200,
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "OK"}],
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            )
            return

        self._write_json(404, {"error": "not found"})

    def log_message(self, *_args: object) -> None:
        return


class ProbeRelayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = MockRelayState()
        handler = type("BoundMockRelayHandler", (MockRelayHandler,), {})
        handler.state = self.state
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def run_probe(self) -> Dict[str, object]:
        with tempfile.NamedTemporaryFile("r+", suffix=".json", delete=False) as handle:
            output_path = handle.name

        cmd = [
            sys.executable,
            str(SCRIPT_PATH),
            "--base-url",
            self.base_url,
            "--api-key",
            "test-key",
            "--provider",
            "auto",
            "--auth-mode",
            "auto",
            "--deep-probes",
            "--probe-anthropic-cache",
            "--burst-count",
            "3",
            "--output",
            output_path,
        ]
        completed = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        with open(output_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def test_surface_specific_auth_and_deep_probes(self) -> None:
        result = self.run_probe()

        metadata = result["metadata"]
        self.assertEqual(metadata["auth_mode"], "auto")
        self.assertIn("Authorization", metadata["request_headers"]["openai"])
        self.assertNotIn("x-api-key", metadata["request_headers"]["openai"])
        self.assertIn("x-api-key", metadata["request_headers"]["anthropic"])
        self.assertNotIn("Authorization", metadata["request_headers"]["anthropic"])

        summary = result["summary"]
        self.assertTrue(summary["quality_signals"]["openai_context_recall"]["exact_match"])
        self.assertTrue(summary["quality_signals"]["anthropic_context_recall"]["exact_match"])
        self.assertTrue(summary["quality_signals"]["anthropic_cache_probe"]["cache_read_seen"])
        self.assertEqual(summary["quality_signals"]["openai_burst"]["rate_limited_count"], 1)

        findings = summary["findings"]
        self.assertTrue(
            any("tiny burst" in finding for finding in findings),
            msg=findings,
        )
        self.assertFalse(
            any("cache-read signal" in finding for finding in findings),
            msg=findings,
        )


if __name__ == "__main__":
    unittest.main()
