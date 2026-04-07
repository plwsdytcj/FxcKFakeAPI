#!/usr/bin/env python3
"""Probe an AI relay endpoint and capture raw evidence."""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, parse, request


MAX_BODY_PREVIEW = 8192
DEFAULT_ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_BURST_COUNT = 3
DEFAULT_CACHE_PROBE_TARGET_TOKENS = 1500


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_headers(values: List[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise SystemExit(f"Invalid --extra-header value: {item!r}")
        key, value = item.split("=", 1)
        headers[key.strip()] = value.strip()
    return headers


def normalize_api_root(base_url: str) -> str:
    parsed = parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit(f"Invalid base URL: {base_url!r}")

    path = parsed.path.rstrip("/")
    if path.endswith("/v1") or path.endswith("/v1beta"):
        api_path = path
    elif path:
        api_path = f"{path}/v1"
    else:
        api_path = "/v1"

    return parse.urlunparse(
        (parsed.scheme, parsed.netloc, api_path, "", "", "")
    ).rstrip("/")


def join_url(api_root: str, suffix: str) -> str:
    return f"{api_root}/{suffix.lstrip('/')}"


def redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    redacted: Dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in {"authorization", "x-api-key"} and value:
            redacted[key] = value[:8] + "..." if len(value) > 8 else "***"
        else:
            redacted[key] = value
    return redacted


def preview_bytes(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    if len(text) > MAX_BODY_PREVIEW:
        return text[:MAX_BODY_PREVIEW] + "\n...[truncated]"
    return text


def send_request(
    *,
    method: str,
    url: str,
    headers: Dict[str, str],
    payload: Optional[Dict[str, Any]],
    timeout: float,
    stream: bool = False,
) -> Dict[str, Any]:
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = request.Request(url=url, data=body, method=method.upper())
    for key, value in headers.items():
        req.add_header(key, value)

    context = ssl.create_default_context()
    started = time.time()

    try:
        with request.urlopen(req, timeout=timeout, context=context) as response:
            elapsed_ms = round((time.time() - started) * 1000, 1)
            raw_headers = dict(response.headers.items())
            content_type = response.headers.get("Content-Type", "")

            if stream:
                chunks: List[str] = []
                for _ in range(6):
                    line = response.readline()
                    if not line:
                        break
                    chunks.append(preview_bytes(line))
                    if "data:" in chunks[-1]:
                        break
                body_text = "".join(chunks)
                parsed_body = None
            else:
                raw_body = response.read()
                body_text = preview_bytes(raw_body)
                parsed_body = None
                if "json" in content_type.lower():
                    try:
                        parsed_body = json.loads(raw_body.decode("utf-8"))
                    except json.JSONDecodeError:
                        parsed_body = None

            return {
                "ok": True,
                "status": response.status,
                "elapsed_ms": elapsed_ms,
                "url": url,
                "headers": raw_headers,
                "content_type": content_type,
                "body_preview": body_text,
                "json_body": parsed_body,
            }
    except error.HTTPError as exc:
        elapsed_ms = round((time.time() - started) * 1000, 1)
        raw_body = exc.read()
        body_text = preview_bytes(raw_body)
        content_type = exc.headers.get("Content-Type", "")
        parsed_body = None
        if "json" in content_type.lower():
            try:
                parsed_body = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError:
                parsed_body = None

        return {
            "ok": False,
            "status": exc.code,
            "elapsed_ms": elapsed_ms,
            "url": url,
            "headers": dict(exc.headers.items()),
            "content_type": content_type,
            "body_preview": body_text,
            "json_body": parsed_body,
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = round((time.time() - started) * 1000, 1)
        return {
            "ok": False,
            "status": None,
            "elapsed_ms": elapsed_ms,
            "url": url,
            "headers": {},
            "content_type": "",
            "body_preview": "",
            "json_body": None,
            "error": repr(exc),
        }


def make_surface_headers(
    *,
    api_key: Optional[str],
    extra_headers: Dict[str, str],
    auth_mode: str,
    surface: str,
    anthropic_version: str,
) -> Dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "api-relay-audit/0.2",
    }

    if auth_mode == "auto":
        resolved_mode = surface
    else:
        resolved_mode = auth_mode

    if api_key and resolved_mode in {"openai", "both"}:
        headers["Authorization"] = f"Bearer {api_key}"
    if api_key and resolved_mode in {"anthropic", "both"}:
        headers["x-api-key"] = api_key
    if surface == "anthropic":
        headers["anthropic-version"] = anthropic_version

    headers.update(extra_headers)
    return headers


def pick_model(
    preferred: Optional[str], models_response: Optional[Dict[str, Any]]
) -> Optional[str]:
    if preferred:
        return preferred
    if not models_response:
        return None
    payload = models_response.get("json_body")
    if not isinstance(payload, dict):
        return None

    data = payload.get("data")
    if not isinstance(data, list):
        return None

    ids: List[str] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.append(item["id"])

    preferred_prefixes = ("claude", "gpt", "o3", "o4", "gemini", "deepseek")
    excluded_substrings = (
        "embedding",
        "moderation",
        "whisper",
        "tts",
        "transcribe",
        "image",
        "vision-preview",
    )
    for model_id in ids:
        lower = model_id.lower()
        if any(token in lower for token in excluded_substrings):
            continue
        if lower.startswith(preferred_prefixes):
            return model_id
    for model_id in ids:
        lower = model_id.lower()
        if any(token in lower for token in excluded_substrings):
            continue
        return model_id
    return ids[0] if ids else None


def extract_model_ids(probe: Optional[Dict[str, Any]]) -> List[str]:
    if not probe:
        return []
    payload = probe.get("json_body")
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []

    model_ids: List[str] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            model_ids.append(item["id"])
    return model_ids


def summarize_headers(headers: Dict[str, str]) -> Dict[str, str]:
    interesting = {}
    for key, value in headers.items():
        lower = key.lower()
        if (
            lower.startswith("anthropic-")
            or lower.startswith("openai-")
            or lower in {"server", "via", "cf-ray", "x-request-id", "request-id"}
            or "ratelimit" in lower
        ):
            interesting[key] = value
    return interesting


def extract_openai_text(response: Dict[str, Any]) -> str:
    payload = response.get("json_body")
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""


def extract_anthropic_text(response: Dict[str, Any]) -> str:
    payload = response.get("json_body")
    if not isinstance(payload, dict):
        return ""
    content = payload.get("content")
    if not isinstance(content, list):
        return ""

    parts: List[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def inspect_openai_tool_call(response: Dict[str, Any]) -> str:
    payload = response.get("json_body")
    if not isinstance(payload, dict):
        return "no_json"
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return "no_choices"
    message = choices[0].get("message", {})
    tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
    return "tool_call_present" if tool_calls else "no_tool_call"


def inspect_anthropic_tool_call(response: Dict[str, Any]) -> str:
    payload = response.get("json_body")
    if not isinstance(payload, dict):
        return "no_json"
    content = payload.get("content")
    if not isinstance(content, list):
        return "no_content_list"
    for item in content:
        if isinstance(item, dict) and item.get("type") == "tool_use":
            return "tool_use_present"
    return "no_tool_use"


def extract_marker_value(text: str, marker: str) -> Optional[str]:
    if marker not in text:
        return None
    remainder = text.split(marker, 1)[1].strip()
    line = remainder.splitlines()[0].strip()
    return line or None


def build_context_probe_prompt(nonce: str) -> str:
    filler_lines = []
    for idx in range(72):
        filler_lines.append(
            "Section "
            f"{idx:03d}: relay audit filler preserves context ordering, "
            "tests deterministic recall, and helps detect wrapper drift."
        )
    filler = "\n".join(filler_lines)
    return (
        "This is a relay integrity check.\n"
        "Read the entire prompt carefully.\n"
        f"{filler}\n"
        f"SECRET_TOKEN: {nonce}\n"
        f"{filler}\n"
        "Return only the exact SECRET_TOKEN value. No punctuation. No explanation."
    )


def run_openai_context_probe(
    *, api_root: str, headers: Dict[str, str], model: str, timeout: float
) -> Dict[str, Any]:
    nonce = f"relay-audit-{int(time.time() * 1000)}"
    probe = send_request(
        method="POST",
        url=join_url(api_root, "chat/completions"),
        headers=headers,
        payload={
            "model": model,
            "messages": [
                {"role": "user", "content": build_context_probe_prompt(nonce)}
            ],
            "temperature": 0,
            "max_tokens": 64,
        },
        timeout=timeout,
    )
    observed = extract_openai_text(probe)
    probe["assessment"] = {
        "expected_token": nonce,
        "observed_text": observed,
        "exact_match": bool(probe.get("ok")) and observed == nonce,
    }
    return probe


def run_anthropic_context_probe(
    *, api_root: str, headers: Dict[str, str], model: str, timeout: float
) -> Dict[str, Any]:
    nonce = f"relay-audit-{int(time.time() * 1000)}"
    probe = send_request(
        method="POST",
        url=join_url(api_root, "messages"),
        headers=headers,
        payload={
            "model": model,
            "max_tokens": 64,
            "messages": [
                {"role": "user", "content": build_context_probe_prompt(nonce)}
            ],
        },
        timeout=timeout,
    )
    observed = extract_anthropic_text(probe)
    probe["assessment"] = {
        "expected_token": nonce,
        "observed_text": observed,
        "exact_match": bool(probe.get("ok")) and observed == nonce,
    }
    return probe


def recommended_cache_probe_tokens(model: str) -> int:
    lower = model.lower()
    if "opus-4.6" in lower or "opus-4-6" in lower:
        return 4096
    if "opus-4.5" in lower or "opus-4-5" in lower:
        return 4096
    if "sonnet-4.6" in lower or "sonnet-4-6" in lower:
        return 2048
    if "haiku-4.5" in lower or "haiku-4-5" in lower:
        return 4096
    if "haiku-3.5" in lower or "haiku-3-5" in lower:
        return 2048
    if "haiku-3" in lower:
        return 2048
    return 1024


def build_cache_probe_text(target_tokens: int) -> str:
    approx_words_per_line = 18
    line_count = max(target_tokens // approx_words_per_line, 80)
    lines = []
    for idx in range(line_count):
        lines.append(
            "Cache probe line "
            f"{idx:04d}: deterministic relay audit content repeats fixed wording "
            "to verify native Anthropic cache creation and cache reads."
        )
    return "\n".join(lines)


def usage_value(response: Dict[str, Any], key: str) -> int:
    payload = response.get("json_body")
    if not isinstance(payload, dict):
        return 0
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return 0
    value = usage.get(key)
    return value if isinstance(value, int) else 0


def run_anthropic_cache_probe(
    *,
    api_root: str,
    headers: Dict[str, str],
    model: str,
    timeout: float,
    target_tokens: int,
) -> Dict[str, Any]:
    recommended_tokens = recommended_cache_probe_tokens(model)
    nonce = f"relay-cache-{int(time.time() * 1000)}"
    system_text = build_cache_probe_text(target_tokens)
    payload = {
        "model": model,
        "max_tokens": 32,
        "system": [
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": (
                    "Reply with the exact word OK and include no other text. "
                    f"Cache probe nonce: {nonce}"
                ),
            }
        ],
    }

    first = send_request(
        method="POST",
        url=join_url(api_root, "messages"),
        headers=headers,
        payload=payload,
        timeout=timeout,
    )
    second = send_request(
        method="POST",
        url=join_url(api_root, "messages"),
        headers=headers,
        payload=payload,
        timeout=timeout,
    )

    first_write = usage_value(first, "cache_creation_input_tokens")
    first_read = usage_value(first, "cache_read_input_tokens")
    second_write = usage_value(second, "cache_creation_input_tokens")
    second_read = usage_value(second, "cache_read_input_tokens")

    note = ""
    if not first.get("ok") or not second.get("ok"):
        note = "Cache probe request failed or relay rejected native cache fields."
    elif second_read > 0:
        note = "Observed a native Anthropic cache-read signal on the repeated request."
    elif target_tokens < recommended_tokens:
        note = (
            "No cache-read signal observed. Probe length may be below this model's "
            "minimum cacheable prompt size."
        )
    else:
        note = (
            "No cache-read signal observed despite meeting the recommended probe size. "
            "Native prompt caching remains unproven."
        )

    return {
        "first": first,
        "second": second,
        "assessment": {
            "probe_nonce": nonce,
            "target_tokens": target_tokens,
            "recommended_min_tokens": recommended_tokens,
            "first_cache_creation_input_tokens": first_write,
            "first_cache_read_input_tokens": first_read,
            "second_cache_creation_input_tokens": second_write,
            "second_cache_read_input_tokens": second_read,
            "cache_write_seen": first_write > 0 or second_write > 0,
            "cache_read_seen": second_read > 0,
            "native_cache_supported": second_read > 0 or first_write > 0,
            "note": note,
        },
    }


def compact_attempt(probe: Dict[str, Any], index: int) -> Dict[str, Any]:
    return {
        "index": index,
        "ok": probe.get("ok"),
        "status": probe.get("status"),
        "elapsed_ms": probe.get("elapsed_ms"),
        "error": probe.get("error"),
    }


def summarize_burst_attempts(attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
    statuses = [item.get("status") for item in attempts]
    rate_limited = sum(1 for status in statuses if status == 429)
    server_errors = sum(
        1 for status in statuses if isinstance(status, int) and status >= 500
    )
    non_ok = sum(1 for item in attempts if not item.get("ok"))
    return {
        "count": len(attempts),
        "all_ok": non_ok == 0,
        "non_ok_count": non_ok,
        "rate_limited_count": rate_limited,
        "server_error_count": server_errors,
        "max_elapsed_ms": max((item.get("elapsed_ms") or 0) for item in attempts)
        if attempts
        else 0,
    }


def run_openai_burst_probe(
    *,
    api_root: str,
    headers: Dict[str, str],
    model: str,
    timeout: float,
    count: int,
) -> Dict[str, Any]:
    attempts: List[Dict[str, Any]] = []
    for idx in range(count):
        probe = send_request(
            method="POST",
            url=join_url(api_root, "chat/completions"),
            headers=headers,
            payload={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK only."}],
                "temperature": 0,
                "max_tokens": 8,
            },
            timeout=timeout,
        )
        attempts.append(compact_attempt(probe, idx + 1))
    return {"attempts": attempts, "assessment": summarize_burst_attempts(attempts)}


def run_anthropic_burst_probe(
    *,
    api_root: str,
    headers: Dict[str, str],
    model: str,
    timeout: float,
    count: int,
) -> Dict[str, Any]:
    attempts: List[Dict[str, Any]] = []
    for idx in range(count):
        probe = send_request(
            method="POST",
            url=join_url(api_root, "messages"),
            headers=headers,
            payload={
                "model": model,
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "Reply with OK only."}],
            },
            timeout=timeout,
        )
        attempts.append(compact_attempt(probe, idx + 1))
    return {"attempts": attempts, "assessment": summarize_burst_attempts(attempts)}


def choose_models_probe(
    *,
    api_root: str,
    provider: str,
    openai_headers: Dict[str, str],
    anthropic_headers: Dict[str, str],
    timeout: float,
) -> Tuple[Dict[str, Dict[str, Any]], Optional[str], Dict[str, Any]]:
    attempts: Dict[str, Dict[str, Any]] = {}
    order = ["openai", "anthropic"] if provider == "auto" else [provider]
    chosen_surface: Optional[str] = None
    chosen_probe: Dict[str, Any] = {}

    for surface in order:
        surface_headers = openai_headers if surface == "openai" else anthropic_headers
        probe = send_request(
            method="GET",
            url=join_url(api_root, "models"),
            headers=surface_headers,
            payload=None,
            timeout=timeout,
        )
        attempts[surface] = probe
        if probe.get("ok") and not chosen_surface:
            chosen_surface = surface
            chosen_probe = probe

    if not chosen_surface and attempts:
        chosen_surface = order[0]
        chosen_probe = attempts[order[0]]

    return attempts, chosen_surface, chosen_probe


def build_quality_signals(results: Dict[str, Any]) -> Dict[str, Any]:
    signals: Dict[str, Any] = {}

    for label in ("openai_context_recall", "anthropic_context_recall"):
        probe = results.get(label)
        if isinstance(probe, dict):
            signals[label] = probe.get("assessment")

    for label in ("openai_burst", "anthropic_burst"):
        probe = results.get(label)
        if isinstance(probe, dict):
            signals[label] = probe.get("assessment")

    cache_probe = results.get("anthropic_cache_probe")
    if isinstance(cache_probe, dict):
        signals["anthropic_cache_probe"] = cache_probe.get("assessment")

    return signals


def build_findings(results: Dict[str, Any]) -> List[str]:
    findings: List[str] = []

    models = results.get("models")
    if models and not models.get("ok"):
        status = models.get("status")
        if status and status >= 500:
            findings.append("`/models` failed with 5xx; basic discovery looks unstable.")

    openai_models = set(extract_model_ids(results.get("models_openai")))
    anthropic_models = set(extract_model_ids(results.get("models_anthropic")))
    if openai_models and anthropic_models and openai_models != anthropic_models:
        findings.append(
            "OpenAI and Anthropic model discovery returned different model lists; the relay surfaces may not be backed by the same upstream."
        )

    for label in ("openai_completion", "anthropic_completion"):
        probe = results.get(label)
        if probe and probe.get("ok") and "json" not in probe.get("content_type", "").lower():
            findings.append(f"{label} returned success without a JSON content type.")

    for label in ("openai_stream", "anthropic_stream"):
        probe = results.get(label)
        if probe and probe.get("ok"):
            body = probe.get("body_preview", "")
            content_type = probe.get("content_type", "").lower()
            if "event-stream" not in content_type and "data:" not in body:
                findings.append(f"{label} claimed success but did not look like SSE.")

    for label in ("openai_invalid_model", "anthropic_invalid_model"):
        probe = results.get(label)
        if probe and probe.get("status") and probe["status"] >= 500:
            findings.append(f"{label} returned 5xx for a client error; error handling looks poor.")

    openai_tools = results.get("openai_tools")
    if openai_tools and openai_tools.get("ok"):
        state = inspect_openai_tool_call(openai_tools)
        if state != "tool_call_present":
            findings.append("OpenAI-compatible tool call probe succeeded but did not return a tool call.")

    anthropic_tools = results.get("anthropic_tools")
    if anthropic_tools and anthropic_tools.get("ok"):
        state = inspect_anthropic_tool_call(anthropic_tools)
        if state != "tool_use_present":
            findings.append("Anthropic-native tool probe succeeded but did not return a `tool_use` block.")

    for label in ("openai_context_recall", "anthropic_context_recall"):
        probe = results.get(label)
        assessment = probe.get("assessment") if isinstance(probe, dict) else None
        if isinstance(assessment, dict) and not assessment.get("exact_match"):
            findings.append(
                f"{label} did not return the exact hidden token; context fidelity looks degraded."
            )

    for label in ("openai_burst", "anthropic_burst"):
        probe = results.get(label)
        assessment = probe.get("assessment") if isinstance(probe, dict) else None
        if isinstance(assessment, dict):
            if assessment.get("rate_limited_count", 0) > 0:
                findings.append(f"{label} hit rate limits under a tiny burst.")
            elif assessment.get("server_error_count", 0) > 0:
                findings.append(f"{label} returned 5xx under a tiny burst.")
            elif assessment.get("non_ok_count", 0) > 0:
                findings.append(f"{label} failed some burst requests.")

    cache_probe = results.get("anthropic_cache_probe")
    if isinstance(cache_probe, dict):
        first = cache_probe.get("first", {})
        second = cache_probe.get("second", {})
        assessment = cache_probe.get("assessment")
        if not first.get("ok") or not second.get("ok"):
            findings.append(
                "Anthropic cache probe failed or the relay rejected native cache fields; prompt-caching claims remain unproven."
            )
        elif isinstance(assessment, dict) and not assessment.get("cache_read_seen"):
            findings.append(
                "Anthropic cache probe showed no cache-read signal on the repeated request; native prompt caching remains unproven."
            )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe an AI relay endpoint.")
    parser.add_argument("--base-url", required=True, help="Relay base URL or API root")
    parser.add_argument("--api-key", help="API key or temporary audit key")
    parser.add_argument(
        "--provider",
        choices=("auto", "openai", "anthropic"),
        default="auto",
        help="Which API surface to probe",
    )
    parser.add_argument(
        "--auth-mode",
        choices=("auto", "openai", "anthropic", "both", "none"),
        default="auto",
        help="Which auth headers to send. `auto` uses Authorization for OpenAI and x-api-key for Anthropic.",
    )
    parser.add_argument("--model", help="Model name to use for probes")
    parser.add_argument(
        "--timeout", type=float, default=20.0, help="Request timeout in seconds"
    )
    parser.add_argument("--output", help="Write JSON results to this file")
    parser.add_argument(
        "--anthropic-version",
        default=DEFAULT_ANTHROPIC_VERSION,
        help="Anthropic version header for native messages probes",
    )
    parser.add_argument(
        "--extra-header",
        action="append",
        default=[],
        help="Additional header in KEY=VALUE format; may be repeated",
    )
    parser.add_argument(
        "--skip-stream",
        action="store_true",
        help="Skip streaming probes",
    )
    parser.add_argument(
        "--skip-tools",
        action="store_true",
        help="Skip tool calling probes",
    )
    parser.add_argument(
        "--deep-probes",
        action="store_true",
        help="Run deeper probes for context recall and tiny burst stability. Costs extra requests.",
    )
    parser.add_argument(
        "--probe-anthropic-cache",
        action="store_true",
        help="Run a native Anthropic prompt-caching probe. Costs extra input tokens.",
    )
    parser.add_argument(
        "--burst-count",
        type=int,
        default=DEFAULT_BURST_COUNT,
        help="How many requests to send in the tiny burst probe.",
    )
    parser.add_argument(
        "--cache-probe-target-tokens",
        type=int,
        default=DEFAULT_CACHE_PROBE_TARGET_TOKENS,
        help="Approximate target size for the Anthropics cache probe payload.",
    )
    args = parser.parse_args()

    if args.burst_count < 1:
        raise SystemExit("--burst-count must be at least 1")
    if args.cache_probe_target_tokens < 256:
        raise SystemExit("--cache-probe-target-tokens must be at least 256")

    extra_headers = parse_headers(args.extra_header)
    api_root = normalize_api_root(args.base_url)
    openai_headers = make_surface_headers(
        api_key=args.api_key,
        extra_headers=extra_headers,
        auth_mode=args.auth_mode,
        surface="openai",
        anthropic_version=args.anthropic_version,
    )
    anthropic_headers = make_surface_headers(
        api_key=args.api_key,
        extra_headers=extra_headers,
        auth_mode=args.auth_mode,
        surface="anthropic",
        anthropic_version=args.anthropic_version,
    )

    results: Dict[str, Any] = {
        "metadata": {
            "generated_at": utc_now(),
            "base_url": args.base_url,
            "api_root": api_root,
            "provider_mode": args.provider,
            "auth_mode": args.auth_mode,
            "requested_model": args.model,
            "timeout_seconds": args.timeout,
            "deep_probes": args.deep_probes,
            "probe_anthropic_cache": args.probe_anthropic_cache,
            "request_headers": {
                "openai": redact_headers(openai_headers),
                "anthropic": redact_headers(anthropic_headers),
            },
        },
        "results": {},
    }

    models_attempts, models_surface, models_probe = choose_models_probe(
        api_root=api_root,
        provider=args.provider,
        openai_headers=openai_headers,
        anthropic_headers=anthropic_headers,
        timeout=args.timeout,
    )
    if "openai" in models_attempts:
        results["results"]["models_openai"] = models_attempts["openai"]
    if "anthropic" in models_attempts:
        results["results"]["models_anthropic"] = models_attempts["anthropic"]
    results["results"]["models"] = models_probe

    selected_model = pick_model(args.model, models_probe)
    results["metadata"]["models_probe_surface"] = models_surface
    results["metadata"]["selected_model"] = selected_model

    if args.provider in {"auto", "openai"} and selected_model:
        results["results"]["openai_completion"] = send_request(
            method="POST",
            url=join_url(api_root, "chat/completions"),
            headers=openai_headers,
            payload={
                "model": selected_model,
                "messages": [{"role": "user", "content": "Reply with OK only."}],
                "temperature": 0,
                "max_tokens": 32,
            },
            timeout=args.timeout,
        )

        if not args.skip_stream:
            results["results"]["openai_stream"] = send_request(
                method="POST",
                url=join_url(api_root, "chat/completions"),
                headers=openai_headers,
                payload={
                    "model": selected_model,
                    "messages": [{"role": "user", "content": "Reply with OK only."}],
                    "temperature": 0,
                    "max_tokens": 32,
                    "stream": True,
                },
                timeout=args.timeout,
                stream=True,
            )

        if not args.skip_tools:
            results["results"]["openai_tools"] = send_request(
                method="POST",
                url=join_url(api_root, "chat/completions"),
                headers=openai_headers,
                payload={
                    "model": selected_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Call the ping tool with value ok.",
                        }
                    ],
                    "tool_choice": "required",
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "ping",
                                "description": "Echo a short value.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {"value": {"type": "string"}},
                                    "required": ["value"],
                                    "additionalProperties": False,
                                },
                            },
                        }
                    ],
                    "temperature": 0,
                    "max_tokens": 64,
                },
                timeout=args.timeout,
            )

        results["results"]["openai_invalid_model"] = send_request(
            method="POST",
            url=join_url(api_root, "chat/completions"),
            headers=openai_headers,
            payload={
                "model": "__api_relay_audit_invalid_model__",
                "messages": [{"role": "user", "content": "Reply with OK only."}],
                "temperature": 0,
                "max_tokens": 16,
            },
            timeout=args.timeout,
        )

        if args.deep_probes:
            results["results"]["openai_context_recall"] = run_openai_context_probe(
                api_root=api_root,
                headers=openai_headers,
                model=selected_model,
                timeout=args.timeout,
            )
            results["results"]["openai_burst"] = run_openai_burst_probe(
                api_root=api_root,
                headers=openai_headers,
                model=selected_model,
                timeout=args.timeout,
                count=args.burst_count,
            )

    if args.provider in {"auto", "anthropic"} and selected_model:
        results["results"]["anthropic_completion"] = send_request(
            method="POST",
            url=join_url(api_root, "messages"),
            headers=anthropic_headers,
            payload={
                "model": selected_model,
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "Reply with OK only."}],
            },
            timeout=args.timeout,
        )

        if not args.skip_stream:
            results["results"]["anthropic_stream"] = send_request(
                method="POST",
                url=join_url(api_root, "messages"),
                headers=anthropic_headers,
                payload={
                    "model": selected_model,
                    "max_tokens": 32,
                    "stream": True,
                    "messages": [{"role": "user", "content": "Reply with OK only."}],
                },
                timeout=args.timeout,
                stream=True,
            )

        if not args.skip_tools:
            results["results"]["anthropic_tools"] = send_request(
                method="POST",
                url=join_url(api_root, "messages"),
                headers=anthropic_headers,
                payload={
                    "model": selected_model,
                    "max_tokens": 64,
                    "messages": [
                        {
                            "role": "user",
                            "content": "Call the ping tool with value ok.",
                        }
                    ],
                    "tools": [
                        {
                            "name": "ping",
                            "description": "Echo a short value.",
                            "input_schema": {
                                "type": "object",
                                "properties": {"value": {"type": "string"}},
                                "required": ["value"],
                            },
                        }
                    ],
                },
                timeout=args.timeout,
            )

        results["results"]["anthropic_invalid_model"] = send_request(
            method="POST",
            url=join_url(api_root, "messages"),
            headers=anthropic_headers,
            payload={
                "model": "__api_relay_audit_invalid_model__",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "Reply with OK only."}],
            },
            timeout=args.timeout,
        )

        if args.deep_probes:
            results["results"]["anthropic_context_recall"] = run_anthropic_context_probe(
                api_root=api_root,
                headers=anthropic_headers,
                model=selected_model,
                timeout=args.timeout,
            )
            results["results"]["anthropic_burst"] = run_anthropic_burst_probe(
                api_root=api_root,
                headers=anthropic_headers,
                model=selected_model,
                timeout=args.timeout,
                count=args.burst_count,
            )

        if args.probe_anthropic_cache:
            results["results"]["anthropic_cache_probe"] = run_anthropic_cache_probe(
                api_root=api_root,
                headers=anthropic_headers,
                model=selected_model,
                timeout=args.timeout,
                target_tokens=args.cache_probe_target_tokens,
            )

    results["summary"] = {
        "selected_model": selected_model,
        "surface_support": {
            "openai_completion_ok": bool(
                results["results"].get("openai_completion", {}).get("ok")
            ),
            "anthropic_completion_ok": bool(
                results["results"].get("anthropic_completion", {}).get("ok")
            ),
        },
        "interesting_headers": {
            name: summarize_headers(probe.get("headers", {}))
            for name, probe in results["results"].items()
            if isinstance(probe, dict) and "headers" in probe
        },
        "quality_signals": build_quality_signals(results["results"]),
        "findings": build_findings(results["results"]),
    }

    output_text = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output_text)
            handle.write("\n")
        print(args.output)
    else:
        print(output_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
