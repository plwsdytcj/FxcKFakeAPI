---
description: Audit an AI API relay or proxy using the api-relay-audit skill, probe script, and Markdown report renderer
argument-hint: [base_url] [api_key=...] [provider=auto|openai|anthropic] [deep=0|1] [claimed_provider=...] [claimed_upstream=...] [docs_url=...] [pricing_url=...] [status_url=...] [claim=...]
---

Use the `api-relay-audit` skill workflow to audit an AI API relay or proxy endpoint.

Parse `$ARGUMENTS` with these rules:

- If the first token looks like `http://` or `https://` and no `base_url=` pair is present, treat it as `base_url`.
- Parse any `key=value` pairs for:
  - `base_url`
  - `api_key`
  - `provider`
  - `deep`
  - `claimed_provider`
  - `claimed_upstream`
  - `claimed_pricing`
  - `docs_url`
  - `pricing_url`
  - `status_url`
  - `claim`
- Normalize `provider` to one of `auto`, `openai`, or `anthropic`. Default to `auto`.
- Treat `deep=1`, `deep=true`, or `deep=yes` as deep mode. Otherwise deep mode is off.

Language rule:

- Reply in Chinese if the user invoked the command in Chinese.
- Otherwise reply in English.

Before doing anything else, resolve `SKILL_ROOT` in this order:

1. `./.claude/skills/api-relay-audit`
2. `~/.claude/skills/api-relay-audit`
3. The current working directory, but only if it contains both `SKILL.md` and `tools/probe_relay.py`

If none of these paths exist, stop and tell the user exactly how to install the skill and command wrapper.

After resolving `SKILL_ROOT`, read these files for instructions and reporting structure:

- `${SKILL_ROOT}/SKILL.md`
- `${SKILL_ROOT}/docs/audit-rubric.md`
- `${SKILL_ROOT}/docs/public-signals.md`
- `${SKILL_ROOT}/docs/troubleshooting.md`
- `${SKILL_ROOT}/prompts/report-template.md`

If `base_url` is missing, ask only for the missing minimum input:

- `base_url`
- optional `api_key` or temporary audit key

If `api_key` is present, run the probe script with Bash.

Use this baseline command:

```bash
python3 "${SKILL_ROOT}/tools/probe_relay.py" \
  --base-url "$BASE_URL" \
  --api-key "$API_KEY" \
  --provider "$PROVIDER" \
  --auth-mode auto \
  --output "$ARTIFACT_PATH"
```

If deep mode is enabled, add:

```bash
--deep-probes --probe-anthropic-cache --burst-count 3
```

Artifact path rules:

- Write the JSON result to `/tmp/api-relay-audit-<timestamp>.json`
- Tell the user the exact artifact path after the audit

Report rendering baseline:

```bash
python3 "${SKILL_ROOT}/tools/render_report.py" \
  --probe-json "$ARTIFACT_PATH" \
  --claimed-provider "$CLAIMED_PROVIDER" \
  --claimed-upstream "$CLAIMED_UPSTREAM" \
  --claimed-pricing "$CLAIMED_PRICING" \
  --docs-url "$DOCS_URL" \
  --pricing-url "$PRICING_URL" \
  --status-url "$STATUS_URL"
```

Only pass arguments that were actually supplied by the user or confirmed from public evidence.

After the probe finishes:

- Run `${SKILL_ROOT}/tools/render_report.py` against the JSON artifact and pass through any supplied claims or URLs
- Read the generated Markdown report
- Compare observed behavior with the user's claims and any provided docs/pricing URLs
- If web access is available and the user asked about reputation, incidents, or policy risk, search recent public evidence
- Use the rendered Markdown as the baseline and refine it where public evidence adds useful dated context
- Output the final report following `${SKILL_ROOT}/prompts/report-template.md`

If no `api_key` is available:

- Skip live probing
- Render a documentation-only report with `${SKILL_ROOT}/tools/render_report.py`, passing the claim and URL fields that were actually collected
- Perform a documentation-and-public-evidence audit only
- Clearly state that confidence is limited without live probes

Decision rules:

- Do not call a relay `official` or `direct` unless the evidence supports it
- Distinguish what was proven by the probe from what was inferred from docs or public reports
- If the relay claims Anthropic prompt caching but the deep cache probe shows no cache-read signal, call that out explicitly as `unproven`
- If the relay fails exact-token recall or tiny burst stability in deep mode, treat that as a meaningful red flag
