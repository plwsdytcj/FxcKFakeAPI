#!/usr/bin/env python3
"""Unit tests for probe helper functions."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "probe_relay.py"
SPEC = importlib.util.spec_from_file_location("probe_relay_module", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
probe_relay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_relay)


class ProbeRelayHelperTests(unittest.TestCase):
    def test_normalize_api_root_handles_common_forms(self) -> None:
        self.assertEqual(
            probe_relay.normalize_api_root("https://relay.example"),
            "https://relay.example/v1",
        )
        self.assertEqual(
            probe_relay.normalize_api_root("https://relay.example/proxy"),
            "https://relay.example/proxy/v1",
        )
        self.assertEqual(
            probe_relay.normalize_api_root("https://relay.example/v1/"),
            "https://relay.example/v1",
        )

    def test_build_findings_catches_stream_tool_and_error_mismatches(self) -> None:
        findings = probe_relay.build_findings(
            {
                "models": {"ok": True},
                "models_openai": {
                    "json_body": {
                        "data": [{"id": "gpt-4.1"}],
                    }
                },
                "models_anthropic": {
                    "json_body": {
                        "data": [{"id": "claude-sonnet-4-5"}],
                    }
                },
                "openai_stream": {
                    "ok": True,
                    "content_type": "text/plain",
                    "body_preview": "OK",
                },
                "openai_tools": {
                    "ok": True,
                    "json_body": {
                        "choices": [{"message": {"content": "OK"}}],
                    },
                },
                "anthropic_invalid_model": {
                    "status": 500,
                },
            }
        )

        self.assertTrue(any("different model lists" in finding for finding in findings))
        self.assertTrue(any("did not look like SSE" in finding for finding in findings))
        self.assertTrue(any("returned 5xx for a client error" in finding for finding in findings))
        self.assertTrue(any("did not return a tool call" in finding for finding in findings))


if __name__ == "__main__":
    unittest.main()
