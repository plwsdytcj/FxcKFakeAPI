#!/usr/bin/env python3
"""Render a Markdown audit report from relay probe evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


OFFICIAL_CLAIM_TOKENS = (
    "official",
    "direct",
    "native",
    "official/direct",
    "官转",
    "官方直连",
    "直连",
)
STREAMING_CLAIM_TOKENS = ("stream", "streaming", "sse", "流式")
TOOLS_CLAIM_TOKENS = (
    "tool",
    "tools",
    "function call",
    "function calling",
    "claude code",
    "cursor",
    "agent",
    "agents",
)
SUSPICIOUS_PRICING_TOKENS = ("积分", "倍率", "套餐", "周卡", "月卡", "points", "credits")
RAW_PRICING_TOKENS = (
    "token",
    "tokens",
    "/1m",
    "1m tokens",
    "per million",
    "rpm",
    "rps",
    "tpm",
    "usd",
    "$",
)
SHARED_ACCOUNT_TOKENS = (
    "共享账号",
    "shared account",
    "代登",
    "号池",
    "pro/max credentials",
    "claude.ai account",
    "share claude",
)
CLAUDE_PROVIDER_TOKENS = ("claude", "anthropic")
OPENAI_PROVIDER_TOKENS = ("openai", "gpt", "o3", "o4")


def unique_items(values: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def clamp(value: int, lower: int = 0, upper: int = 5) -> int:
    return max(lower, min(upper, value))


def read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected a JSON object in {path!r}")
    return payload


def has_any(text: str, tokens: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(token.lower() in lowered for token in tokens)


def format_list(values: List[str], fallback: str = "not provided") -> str:
    return ", ".join(values) if values else fallback


def build_claim_bundle(args: argparse.Namespace) -> Dict[str, Any]:
    claims = unique_items(args.claim or [])
    features = unique_items(args.claimed_feature or [])
    ops = unique_items(args.claimed_op or [])
    bundle = {
        "provider": (args.claimed_provider or "").strip(),
        "upstream": (args.claimed_upstream or "").strip(),
        "pricing": (args.claimed_pricing or "").strip(),
        "limits": (args.claimed_limit or "").strip(),
        "features": features,
        "ops": ops,
        "claims": claims,
        "docs_url": (args.docs_url or "").strip(),
        "pricing_url": (args.pricing_url or "").strip(),
        "status_url": (args.status_url or "").strip(),
        "incident_urls": unique_items(args.incident_url or []),
        "security_note": (args.security_note or "").strip(),
    }
    text_parts = [
        bundle["provider"],
        bundle["upstream"],
        bundle["pricing"],
        bundle["limits"],
        bundle["security_note"],
        " ".join(features),
        " ".join(ops),
        " ".join(claims),
    ]
    bundle["all_text"] = " ".join(part for part in text_parts if part).strip()
    return bundle


def get_findings(summary: Dict[str, Any]) -> List[str]:
    findings = summary.get("findings")
    if not isinstance(findings, list):
        return []
    return [item for item in findings if isinstance(item, str)]


def probe_ok(results: Dict[str, Any], key: str) -> bool:
    probe = results.get(key)
    return isinstance(probe, dict) and bool(probe.get("ok"))


def quality_signal(summary: Dict[str, Any], key: str) -> Dict[str, Any]:
    quality = summary.get("quality_signals")
    if not isinstance(quality, dict):
        return {}
    signal = quality.get(key)
    return signal if isinstance(signal, dict) else {}


def detect_hard_fails(
    *,
    live_probe: bool,
    claims: Dict[str, Any],
    results: Dict[str, Any],
    summary: Dict[str, Any],
) -> List[str]:
    findings = get_findings(summary)
    claim_text = claims["all_text"]
    hard_fails: List[str] = []
    openai_completion_ok = bool(summary.get("surface_support", {}).get("openai_completion_ok"))
    anthropic_completion_ok = bool(
        summary.get("surface_support", {}).get("anthropic_completion_ok")
    )

    official_claimed = has_any(claim_text, OFFICIAL_CLAIM_TOKENS)
    claude_claimed = has_any(claims["provider"], CLAUDE_PROVIDER_TOKENS) or has_any(
        claims["upstream"], CLAUDE_PROVIDER_TOKENS
    )
    openai_claimed = has_any(claims["provider"], OPENAI_PROVIDER_TOKENS) or has_any(
        claims["upstream"], OPENAI_PROVIDER_TOKENS
    )
    streaming_claimed = has_any(claim_text, STREAMING_CLAIM_TOKENS)
    tools_claimed = has_any(claim_text, TOOLS_CLAIM_TOKENS)
    suspicious_pricing = has_any(claims["pricing"], SUSPICIOUS_PRICING_TOKENS)
    raw_pricing = has_any(claims["pricing"], RAW_PRICING_TOKENS)
    shared_account = has_any(claim_text, SHARED_ACCOUNT_TOKENS)

    if live_probe and official_claimed and not (openai_completion_ok or anthropic_completion_ok):
        hard_fails.append(
            "Relay claims official/direct access, but no coherent live API surface succeeded."
        )
    if claude_claimed and probe_ok(results, "openai_completion") and not probe_ok(
        results, "anthropic_completion"
    ):
        hard_fails.append(
            "Relay claims Claude/Anthropic capability, but native Anthropic `/messages` probes did not work."
        )
    if openai_claimed and probe_ok(results, "anthropic_completion") and not probe_ok(
        results, "openai_completion"
    ):
        hard_fails.append(
            "Relay claims OpenAI capability, but native OpenAI `/chat/completions` probes did not work."
        )
    if any("returned 5xx for a client error" in finding for finding in findings):
        hard_fails.append("Invalid-model probe returned 5xx instead of a clean client error.")
    if streaming_claimed and any("did not look like SSE" in finding for finding in findings):
        hard_fails.append("Streaming was sold as supported, but the observed response was not SSE-like.")
    if tools_claimed and any("tool" in finding.lower() and "did not" in finding.lower() for finding in findings):
        hard_fails.append("Relay was sold for tools/agents, but tool-call semantics did not hold.")
    if suspicious_pricing and not raw_pricing:
        hard_fails.append(
            "Pricing was described only as points/ratios/packages without a raw token or usage mapping."
        )
    if shared_account:
        hard_fails.append(
            "The claims mention shared accounts or account-pool style access, which is an operational red flag."
        )
    return unique_items(hard_fails)


def score_authenticity(
    *,
    live_probe: bool,
    claims: Dict[str, Any],
    results: Dict[str, Any],
    summary: Dict[str, Any],
) -> int:
    score = 2 if not live_probe else 3
    if probe_ok(results, "models"):
        score += 1
    if bool(summary.get("surface_support", {}).get("openai_completion_ok")):
        score += 1
    if bool(summary.get("surface_support", {}).get("anthropic_completion_ok")):
        score += 1
    if any("different model lists" in finding for finding in get_findings(summary)):
        score -= 1
    if any("context fidelity looks degraded" in finding for finding in get_findings(summary)):
        score -= 1
    if has_any(claims["all_text"], SHARED_ACCOUNT_TOKENS):
        score = min(score, 1)
    if live_probe and has_any(claims["all_text"], OFFICIAL_CLAIM_TOKENS) and not (
        bool(summary.get("surface_support", {}).get("openai_completion_ok"))
        or bool(summary.get("surface_support", {}).get("anthropic_completion_ok"))
    ):
        score = min(score, 1)
    return clamp(score)


def score_compatibility(*, live_probe: bool, results: Dict[str, Any], summary: Dict[str, Any]) -> int:
    if not live_probe:
        return 2

    feature_keys = [
        key
        for key in (
            "openai_completion",
            "anthropic_completion",
            "openai_stream",
            "anthropic_stream",
            "openai_tools",
            "anthropic_tools",
        )
        if key in results
    ]
    if not feature_keys:
        return 1

    successes = sum(1 for key in feature_keys if probe_ok(results, key))
    ratio = successes / len(feature_keys)
    if ratio == 1:
        score = 5
    elif ratio >= 0.75:
        score = 4
    elif ratio >= 0.5:
        score = 3
    elif ratio > 0:
        score = 2
    else:
        score = 1

    findings = get_findings(summary)
    if any("did not look like SSE" in finding for finding in findings):
        score -= 1
    if any("tool" in finding.lower() and "did not" in finding.lower() for finding in findings):
        score -= 1
    if any("returned 5xx for a client error" in finding for finding in findings):
        score -= 1
    if not (
        bool(summary.get("surface_support", {}).get("openai_completion_ok"))
        or bool(summary.get("surface_support", {}).get("anthropic_completion_ok"))
    ):
        score = min(score, 1)
    return clamp(score)


def score_transparency(*, claims: Dict[str, Any]) -> int:
    score = 1
    if claims["docs_url"]:
        score += 1
    if claims["pricing_url"] or claims["pricing"]:
        score += 1
    if claims["status_url"]:
        score += 1
    if claims["provider"] or claims["upstream"] or claims["features"] or claims["ops"] or claims["limits"]:
        score += 1
    if has_any(claims["pricing"], SUSPICIOUS_PRICING_TOKENS) and not has_any(
        claims["pricing"], RAW_PRICING_TOKENS
    ):
        score -= 1
    if has_any(claims["all_text"], SHARED_ACCOUNT_TOKENS):
        score = min(score, 1)
    return clamp(score)


def score_reliability(*, live_probe: bool, results: Dict[str, Any], summary: Dict[str, Any]) -> int:
    if not live_probe:
        return 2

    findings = get_findings(summary)
    score = 3
    if probe_ok(results, "models") and (
        bool(summary.get("surface_support", {}).get("openai_completion_ok"))
        or bool(summary.get("surface_support", {}).get("anthropic_completion_ok"))
    ):
        score += 1

    openai_burst = quality_signal(summary, "openai_burst")
    anthropic_burst = quality_signal(summary, "anthropic_burst")
    if (
        openai_burst.get("all_ok") is True
        or anthropic_burst.get("all_ok") is True
        or (
            not openai_burst
            and not anthropic_burst
            and bool(summary.get("surface_support", {}).get("openai_completion_ok") or summary.get("surface_support", {}).get("anthropic_completion_ok"))
        )
    ):
        score += 1

    if any("tiny burst" in finding for finding in findings):
        score -= 1
    if any("5xx" in finding for finding in findings):
        score -= 2
    if not (
        bool(summary.get("surface_support", {}).get("openai_completion_ok"))
        or bool(summary.get("surface_support", {}).get("anthropic_completion_ok"))
    ):
        score = min(score, 1)
    return clamp(score)


def score_security(*, live_probe: bool, claims: Dict[str, Any]) -> int:
    score = 3 if live_probe else 2
    if claims["security_note"]:
        score += 1
    if claims["docs_url"] and has_any(claims["all_text"], ("retention", "logging", "logs", "日志")):
        score += 1
    if has_any(claims["all_text"], ("不记录日志", "no logs", "zero logs")) and not claims["security_note"]:
        score -= 1
    if has_any(claims["all_text"], SHARED_ACCOUNT_TOKENS):
        score = 0
    return clamp(score)


def compute_confidence(
    *,
    live_probe: bool,
    results: Dict[str, Any],
    summary: Dict[str, Any],
    metadata: Dict[str, Any],
) -> str:
    if not live_probe:
        return "low"
    if not (
        bool(summary.get("surface_support", {}).get("openai_completion_ok"))
        or bool(summary.get("surface_support", {}).get("anthropic_completion_ok"))
    ):
        return "low"

    points = 1
    if bool(metadata.get("deep_probes")):
        points += 1
    if bool(summary.get("surface_support", {}).get("openai_completion_ok")) and bool(
        summary.get("surface_support", {}).get("anthropic_completion_ok")
    ):
        points += 1
    if quality_signal(summary, "anthropic_cache_probe").get("cache_read_seen") is True:
        points += 1
    if probe_ok(results, "models"):
        points += 1

    if points >= 4:
        return "high"
    return "medium"


def compute_verdict(*, live_probe: bool, scores: Dict[str, int], hard_fails: List[str]) -> str:
    if not live_probe and hard_fails:
        return "High Risk" if len(hard_fails) == 1 else "Avoid"

    low_scores = sum(1 for value in scores.values() if value <= 2)
    very_low_scores = sum(1 for value in scores.values() if value <= 1)

    if len(hard_fails) >= 2 or very_low_scores >= 2:
        return "Avoid"
    if hard_fails or low_scores >= 2:
        return "High Risk"
    if not live_probe:
        return "Mixed / Needs Caution"
    if min(scores.values()) >= 3 and sum(1 for value in scores.values() if value >= 4) >= 3:
        return "Likely Legit"
    return "Mixed / Needs Caution"


def observed_surfaces(results: Dict[str, Any]) -> List[str]:
    surfaces: List[str] = []
    if probe_ok(results, "models_openai"):
        surfaces.append("OpenAI-compatible `/models`")
    if probe_ok(results, "models_anthropic"):
        surfaces.append("Anthropic-auth `/models`")
    if probe_ok(results, "openai_completion"):
        surfaces.append("OpenAI-compatible `/chat/completions`")
    if probe_ok(results, "anthropic_completion"):
        surfaces.append("Anthropic-native `/messages`")
    return unique_items(surfaces)


def positive_evidence(*, claims: Dict[str, Any], results: Dict[str, Any], summary: Dict[str, Any]) -> List[str]:
    evidence: List[str] = []
    if probe_ok(results, "models"):
        evidence.append("`/models` responded coherently during live probing.")
    if probe_ok(results, "openai_completion"):
        evidence.append("OpenAI-compatible chat completions succeeded.")
    if probe_ok(results, "anthropic_completion"):
        evidence.append("Anthropic-native messages succeeded.")
    if probe_ok(results, "openai_stream"):
        evidence.append("OpenAI-compatible streaming returned SSE-like output.")
    if probe_ok(results, "anthropic_stream"):
        evidence.append("Anthropic-native streaming returned SSE-like output.")
    if probe_ok(results, "openai_tools"):
        evidence.append("OpenAI-compatible tool calling returned a tool call.")
    if probe_ok(results, "anthropic_tools"):
        evidence.append("Anthropic-native tools returned a `tool_use` block.")
    if quality_signal(summary, "openai_context_recall").get("exact_match") is True:
        evidence.append("OpenAI-compatible deep context recall returned the exact hidden token.")
    if quality_signal(summary, "anthropic_context_recall").get("exact_match") is True:
        evidence.append("Anthropic-native deep context recall returned the exact hidden token.")
    if quality_signal(summary, "anthropic_cache_probe").get("cache_read_seen") is True:
        evidence.append("Repeated Anthropic cache probing showed a native cache-read signal.")
    if claims["docs_url"]:
        evidence.append("Vendor documentation URL was provided for follow-up review.")
    return unique_items(evidence)


def red_flags(*, claims: Dict[str, Any], summary: Dict[str, Any], hard_fails: List[str]) -> List[str]:
    flags = list(hard_fails)
    flags.extend(get_findings(summary))
    if has_any(claims["all_text"], ("不记录日志", "no logs", "zero logs")) and not claims["security_note"]:
        flags.append("The relay claims not to log data, but no retention or access policy was supplied.")
    if claims["pricing"] and has_any(claims["pricing"], SUSPICIOUS_PRICING_TOKENS) and not has_any(
        claims["pricing"], RAW_PRICING_TOKENS
    ):
        flags.append("Pricing language used points/ratios/packages without a raw usage mapping.")
    return unique_items(flags)


def build_recommended_action(verdict: str, confidence: str, live_probe: bool) -> List[str]:
    if not live_probe:
        return [
            "Suggested trust level: documentation-only audit; require a temporary audit key before any real onboarding decision.",
            "Suitable traffic level: none for sensitive or production workloads.",
            "Follow-up checks: run live probes, then re-render the report with the fresh JSON artifact.",
        ]
    if verdict == "Likely Legit":
        return [
            "Suggested trust level: acceptable for low-to-moderate risk traffic after normal vendor due diligence.",
            "Suitable traffic level: start with staged traffic and keep upstream/provider fallbacks ready.",
            f"Follow-up checks: keep periodic probes and incident review in place even with `{confidence}` confidence.",
        ]
    if verdict == "Mixed / Needs Caution":
        return [
            "Suggested trust level: usable only after claim-by-claim verification and limited blast radius.",
            "Suitable traffic level: low-risk internal or disposable workloads only.",
            "Follow-up checks: collect clearer pricing, logging, and status evidence before wider use.",
        ]
    if verdict == "High Risk":
        return [
            "Suggested trust level: do not trust for production or sensitive prompts.",
            "Suitable traffic level: at most a disposable temporary sandbox for further verification.",
            "Follow-up checks: require better docs, cleaner error handling, and a fresh probe before reconsidering.",
        ]
    return [
        "Suggested trust level: avoid onboarding this relay.",
        "Suitable traffic level: none.",
        "Follow-up checks: rotate any test key already shared and stop sending prompts to this endpoint.",
    ]


def render_report(args: argparse.Namespace) -> str:
    probe = read_json(args.probe_json) if args.probe_json else {}
    metadata = probe.get("metadata") if isinstance(probe.get("metadata"), dict) else {}
    results = probe.get("results") if isinstance(probe.get("results"), dict) else {}
    summary = probe.get("summary") if isinstance(probe.get("summary"), dict) else {}
    claims = build_claim_bundle(args)
    live_probe = bool(probe)

    hard_fails = detect_hard_fails(
        live_probe=live_probe, claims=claims, results=results, summary=summary
    )
    scores = {
        "Authenticity": score_authenticity(
            live_probe=live_probe, claims=claims, results=results, summary=summary
        ),
        "Compatibility": score_compatibility(
            live_probe=live_probe, results=results, summary=summary
        ),
        "Transparency": score_transparency(claims=claims),
        "Reliability": score_reliability(
            live_probe=live_probe, results=results, summary=summary
        ),
        "Security": score_security(live_probe=live_probe, claims=claims),
    }
    verdict = compute_verdict(live_probe=live_probe, scores=scores, hard_fails=hard_fails)
    confidence = compute_confidence(
        live_probe=live_probe, results=results, summary=summary, metadata=metadata
    )
    positives = positive_evidence(claims=claims, results=results, summary=summary)
    flags = red_flags(claims=claims, summary=summary, hard_fails=hard_fails)
    observed = observed_surfaces(results)
    mismatches = unique_items(hard_fails + get_findings(summary))
    actions = build_recommended_action(verdict, confidence, live_probe)

    score_line = ", ".join(f"{label} `{value}/5`" for label, value in scores.items())
    artifacts = {
        "Probe JSON": str(Path(args.probe_json).resolve()) if args.probe_json else "none",
        "Vendor docs": claims["docs_url"] or "not provided",
        "Status / pricing pages": format_list(
            unique_items([item for item in (claims["status_url"], claims["pricing_url"]) if item]),
            fallback="not provided",
        ),
        "Public incident links": format_list(claims["incident_urls"], fallback="not provided"),
    }
    generated_at = metadata.get("generated_at") if metadata else None

    lines = [
        "# Relay Audit Report",
        "",
    ]
    if isinstance(generated_at, str) and generated_at:
        lines.extend([f"_Generated from probe artifact at `{generated_at}`._", ""])

    lines.extend(
        [
            "## Verdict",
            "",
            f"- `Verdict`: `{verdict}`",
            f"- `Confidence`: `{confidence}`",
            f"- `Scores`: {score_line}",
            (
                "- `Hard fails`: none"
                if not hard_fails
                else f"- `Hard fails`: {format_list(hard_fails, fallback='none')}"
            ),
            "",
            "## Claims vs Observed",
            "",
            f"- Claimed upstream: {claims['upstream'] or claims['provider'] or 'not provided'}",
            f"- Claimed features: {format_list(claims['features'])}",
            f"- Claimed pricing / limits: {format_list(unique_items([claims['pricing'], claims['limits']]), fallback='not provided')}",
            f"- Observed API surfaces: {format_list(observed, fallback='no live probe evidence')}",
            f"- Observed mismatches: {format_list(mismatches, fallback='none observed')}",
            "",
            "## Positive Evidence",
            "",
            f"- Working endpoints: {format_list([item for item in positives if 'succeeded' in item or '/models' in item], fallback='none observed')}",
            f"- Native semantics preserved: {format_list([item for item in positives if 'tool' in item.lower() or 'context recall' in item.lower() or 'cache-read signal' in item.lower()], fallback='unproven')}",
            f"- Error handling quality: {'clean invalid-model handling observed' if not any('Invalid-model probe returned 5xx' in item for item in flags) and live_probe else 'needs more evidence'}",
            f"- Public documentation quality: {claims['docs_url'] or 'not provided'}",
            "",
            "## Red Flags",
            "",
            f"- Technical failures: {format_list([item for item in flags if 'probe' in item.lower() or 'stream' in item.lower() or 'tool' in item.lower() or '5xx' in item.lower() or 'context' in item.lower() or 'burst' in item.lower()], fallback='none observed')}",
            f"- Pricing / quota opacity: {format_list([item for item in flags if 'pricing' in item.lower() or 'token' in item.lower() or 'ratio' in item.lower() or 'package' in item.lower()], fallback='none observed')}",
            f"- Shared-account or reverse-engineering signals: {format_list([item for item in flags if 'shared' in item.lower() or 'account-pool' in item.lower() or 'anthropic `/messages`' in item.lower() or 'openai `/chat/completions`' in item.lower()], fallback='none observed')}",
            f"- Security / logging concerns: {format_list([item for item in flags if 'log' in item.lower() or 'retention' in item.lower()], fallback='none observed')}",
            "",
            "## Recommended Action",
            "",
            f"- Suggested trust level: {actions[0].split(': ', 1)[1]}",
            f"- Suitable traffic level: {actions[1].split(': ', 1)[1]}",
            f"- Follow-up checks: {actions[2].split(': ', 1)[1]}",
            "",
            "## Artifacts",
            "",
            f"- Probe JSON: {artifacts['Probe JSON']}",
            f"- Vendor docs: {artifacts['Vendor docs']}",
            f"- Status / pricing pages: {artifacts['Status / pricing pages']}",
            f"- Public incident links: {artifacts['Public incident links']}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a Markdown relay audit report from probe JSON and claim metadata."
    )
    parser.add_argument("--probe-json", help="Path to a relay-audit JSON artifact")
    parser.add_argument("--claimed-provider", help="Provider or model family the vendor claims")
    parser.add_argument("--claimed-upstream", help="Upstream type claimed by the vendor")
    parser.add_argument(
        "--claimed-feature",
        action="append",
        default=[],
        help="Feature claim; may be repeated",
    )
    parser.add_argument("--claimed-pricing", help="Pricing explanation or quoted claim")
    parser.add_argument("--claimed-limit", help="Limit, quota, or rate-limit claim")
    parser.add_argument(
        "--claimed-op",
        action="append",
        default=[],
        help="Operational claim such as no-logs or refund promises; may be repeated",
    )
    parser.add_argument(
        "--claim",
        action="append",
        default=[],
        help="Additional raw claim text; may be repeated",
    )
    parser.add_argument("--docs-url", help="Vendor documentation URL")
    parser.add_argument("--pricing-url", help="Vendor pricing URL")
    parser.add_argument("--status-url", help="Vendor status URL")
    parser.add_argument(
        "--incident-url",
        action="append",
        default=[],
        help="Public incident URL; may be repeated",
    )
    parser.add_argument(
        "--security-note",
        help="Retention or logging note gathered from docs, policy, or support replies",
    )
    parser.add_argument("--output", help="Write the Markdown report to this file")
    args = parser.parse_args()

    if not args.probe_json and not any(
        (
            args.claimed_provider,
            args.claimed_upstream,
            args.claimed_feature,
            args.claimed_pricing,
            args.claimed_limit,
            args.claimed_op,
            args.docs_url,
            args.pricing_url,
            args.status_url,
            args.security_note,
            args.claim,
        )
    ):
        raise SystemExit("Provide either --probe-json or enough claim metadata to render a report.")

    report = render_report(args)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(report)
        print(args.output)
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
