#!/usr/bin/env python3
"""Regression tests for the Markdown report renderer."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "render_report.py"


class RenderReportTests(unittest.TestCase):
    def run_report(
        self, extra_args: List[str], probe_payload: Optional[Dict[str, Any]] = None
    ) -> str:
        with tempfile.TemporaryDirectory() as temp_dir:
            cmd = [sys.executable, str(SCRIPT_PATH)]
            if probe_payload is not None:
                probe_path = Path(temp_dir) / "probe.json"
                probe_path.write_text(
                    json.dumps(probe_payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                cmd.extend(["--probe-json", str(probe_path)])
            cmd.extend(extra_args)
            completed = subprocess.run(
                cmd,
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            return completed.stdout

    def test_live_probe_report_can_reach_likely_legit(self) -> None:
        probe_payload = {
            "metadata": {
                "generated_at": "2026-04-07T07:00:00+00:00",
                "deep_probes": True,
            },
            "results": {
                "models": {"ok": True},
                "models_openai": {"ok": True},
                "models_anthropic": {"ok": True},
                "openai_completion": {"ok": True},
                "anthropic_completion": {"ok": True},
                "openai_stream": {"ok": True},
                "anthropic_stream": {"ok": True},
                "openai_tools": {"ok": True},
                "anthropic_tools": {"ok": True},
            },
            "summary": {
                "surface_support": {
                    "openai_completion_ok": True,
                    "anthropic_completion_ok": True,
                },
                "quality_signals": {
                    "openai_context_recall": {"exact_match": True},
                    "anthropic_context_recall": {"exact_match": True},
                    "openai_burst": {"all_ok": True},
                    "anthropic_burst": {"all_ok": True},
                    "anthropic_cache_probe": {"cache_read_seen": True},
                },
                "findings": [],
            },
        }

        report = self.run_report(
            [
                "--claimed-provider",
                "Claude",
                "--claimed-upstream",
                "official direct API",
                "--claimed-feature",
                "streaming",
                "--claimed-feature",
                "Claude Code",
                "--claimed-pricing",
                "$3 / 1M tokens input, $15 / 1M tokens output",
                "--docs-url",
                "https://vendor.example/docs",
                "--pricing-url",
                "https://vendor.example/pricing",
                "--status-url",
                "https://vendor.example/status",
                "--security-note",
                "Docs say prompts are retained for 0 days and only aggregated metrics are logged.",
            ],
            probe_payload=probe_payload,
        )

        self.assertIn("`Verdict`: `Likely Legit`", report)
        self.assertIn("`Confidence`: `high`", report)
        self.assertIn("`Hard fails`: none", report)
        self.assertIn("native cache-read signal", report)
        self.assertIn("Authenticity `5/5`", report)

    def test_docs_only_report_flags_opaque_pricing_and_shared_accounts(self) -> None:
        report = self.run_report(
            [
                "--claimed-provider",
                "Claude",
                "--claim",
                "官方直连",
                "--claim",
                "共享账号",
                "--claimed-pricing",
                "积分倍率月卡",
            ]
        )

        self.assertIn("`Verdict`: `Avoid`", report)
        self.assertIn("shared accounts or account-pool style access", report)
        self.assertIn("points/ratios/packages without a raw token", report)
        self.assertNotIn("no coherent live API surface succeeded", report)


if __name__ == "__main__":
    unittest.main()
