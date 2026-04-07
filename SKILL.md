---
name: api-relay-audit
description: Audit third-party AI API relays, proxy endpoints, and 中转站 for authenticity, compatibility, pricing transparency, reliability, and security. Use when the task is to determine whether a Claude/OpenAI-compatible relay is real, official/direct, degraded, oversold, or risky based on vendor claims, HTTP probes, response schemas, headers, rate-limit behavior, and public evidence.
---

# API Relay Audit

Determine whether a relay endpoint is worth trusting. Prefer observable evidence over marketing copy: collect claims, probe the API surface, compare behavior to what was promised, then issue a verdict with explicit confidence and limitations.

## Resource layout

Use these bundled resources:

- `tools/probe_relay.py`
- `docs/audit-rubric.md`
- `docs/public-signals.md`
- `prompts/report-template.md`

When running inside Claude Code, the skill directory is usually available through `${CLAUDE_SKILL_DIR}`. In other agents, resolve paths relative to the skill directory.

## Workflow

### 1. Gather inputs

Collect as many of these as the user can provide:

- `base_url`
- `api_key` or temporary audit key
- claimed provider and models
- docs URL, pricing URL, and status page
- exact claims such as `官转`, `官方直连`, `满血`, `Pro/Max`, `prompt caching`, `不记录日志`, `不限速`

If no credential is available, perform a documentation and public-evidence audit only. State that confidence is limited without live probes.

### 2. Record the vendor claims

Write down only claims that are explicit on the vendor site or in support chat screenshots:

- upstream type: official API, shared account, reverse-engineered client, or unspecified
- pricing model: pass-through,倍率,积分,套餐, daily cap, weekly cap
- supported features: streaming, tools, prompt caching, images, batch, Claude Code, Cursor, OpenAI-compatible
- operational promises: refund, compensation, no logs, dedicated channel, exclusive rate limits

Treat vague phrases such as `专线`, `高速`, `独享`, `企业级`, `满血` as marketing, not evidence.

### 3. Run technical probes

Use `tools/probe_relay.py` whenever you have an endpoint and key. Save the JSON output.

Generic invocation:

```bash
python3 tools/probe_relay.py \
  --base-url https://example.com/v1 \
  --api-key "$API_KEY" \
  --provider auto \
  --model claude-sonnet-4-5 \
  --output relay-audit.json
```

Deep audit mode:

```bash
python3 tools/probe_relay.py \
  --base-url https://example.com/v1 \
  --api-key "$API_KEY" \
  --provider auto \
  --auth-mode auto \
  --deep-probes \
  --probe-anthropic-cache \
  --burst-count 3 \
  --output relay-audit-deep.json
```

Claude Code style invocation:

```bash
python3 "${CLAUDE_SKILL_DIR}/tools/probe_relay.py" \
  --base-url https://example.com/v1 \
  --api-key "$API_KEY" \
  --provider auto \
  --output relay-audit.json
```

Probe goals:

- check whether `/models` exists and is coherent
- verify whether chat/messages requests actually work
- verify whether streaming behaves like SSE
- verify whether tool calling is accepted
- inspect error handling with an invalid model name
- in deep mode, verify exact-token context recall and tiny-burst stability
- optionally, verify native Anthropic prompt-cache signals on repeated requests
- capture headers and response schema clues without sending sensitive business data

Do not send production secrets or proprietary code to an untrusted relay just to test it.
Do not run deep probes blindly on expensive production keys; they generate extra traffic and the cache probe sends a long prompt.

### 4. Interpret the evidence

Read `docs/audit-rubric.md` and score the relay on:

- authenticity
- compatibility
- transparency
- reliability
- security

Read `docs/public-signals.md` for common red-flag patterns in vendor copy and community reports.

Pay extra attention to:

- claims of `official/direct` with no technical evidence
- support for Claude models only through an OpenAI wrapper, while native Anthropic semantics fail
- missing stream support or broken tool calls despite being sold for agents or Claude Code
- context-recall mismatch in deep mode, which can indicate wrapper drift or degraded routing
- burst failures under only 2-3 small requests, which can indicate oversold pools or weak rate-limit handling
- missing native cache-read signals when the relay explicitly sells Anthropic prompt caching
- generic `500` errors for user mistakes such as an invalid model
- prices that only make sense if quality is reduced, account sharing is involved, or caching claims are false

Absence of upstream-specific headers is not proof either way. Presence of native semantics is stronger evidence than branding on a landing page.

### 5. Search public evidence when needed

If the user asks whether a relay has recent incidents, reputation issues, or policy risk, browse the web.

Prefer:

- official docs
- pricing pages
- status pages
- terms of service
- dated community reports with concrete screenshots or error traces

Use exact dates in the conclusion, especially when discussing outages, policy changes, or account-sharing enforcement.

### 6. Report the result

Use `prompts/report-template.md` as the reporting skeleton.

Minimum output fields:

- `Verdict`: `Likely Legit`, `Mixed / Needs Caution`, `High Risk`, or `Avoid`
- `Confidence`: low, medium, or high
- `Claims vs observed`
- `Positive evidence`
- `Red flags`
- `Recommended action`
- `Artifacts`

Separate what is proven from what is inferred.

## Decision rules

- Do not call a relay `official` or `direct` unless the evidence supports it.
- Do not infer model quality from one short prompt.
- Do not equate low price with fraud by itself; tie conclusions to observable technical or policy signals.
- Distinguish `OpenAI-compatible wrapper exists` from `wrapper preserves upstream behavior`.
- Treat missing cache-read signals as "unproven" unless the probe length clearly exceeded the model's cache minimum.
- If the user provides sensitive keys, advise rotating them after testing a suspicious relay.
