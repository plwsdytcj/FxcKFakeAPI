# Troubleshooting

Use this file when probe runs fail, claims are incomplete, or probe output looks ambiguous.

## 401 or 403

- Verify which auth style the relay expects.
- OpenAI-compatible probes normally use `Authorization: Bearer ...`.
- Anthropic-native probes normally use `x-api-key: ...` plus `anthropic-version`.
- Start with `--auth-mode auto` before forcing `openai`, `anthropic`, or `both`.

## 404 or 405

- The base URL is often wrong.
- Pass the vendor root or API root and let the script normalize `/v1`.
- Example: `https://relay.example`, `https://relay.example/api`, and `https://relay.example/v1` are all acceptable inputs.

## 400 Invalid Model

- A clean `400` for an invalid model is expected.
- If the relay returns `500`, HTML, or a generic gateway error for a fake model name, treat that as a serious compatibility problem.
- If a real model fails, retry with `--model` set to an ID returned by `/models`.

## Timeout, TLS, or EOF

- Increase `--timeout` to `30` or `45` seconds before concluding the relay is down.
- Retry a shallow probe before deep mode.
- Compare the probe with a basic header request such as `curl -I https://relay.example`.
- If only deep mode times out, the endpoint may be too slow or too aggressively rate-limited for agent traffic.

## Stream or Tool Probes Fail but Basic Chat Works

- That usually means the relay is only a partial wrapper.
- Do not market it as `Claude Code`, agent-safe, or fully API-compatible until streaming and tool semantics are verified.
- Keep the verdict at `Mixed / Needs Caution` or worse unless the missing features are explicitly undocumented.

## No Anthropic Cache-Read Signal

- First check whether the relay actually claims native Anthropic prompt caching.
- If it does, retry with a larger prompt using `--cache-probe-target-tokens`.
- No cache-read signal is not automatic proof of fraud, but it leaves the feature unproven.

## Docs-Only Audit

- If no temporary key is available, render a documentation-only report instead of inventing probe results.

```bash
python3 tools/render_report.py \
  --claimed-provider Claude \
  --claim "官方直连" \
  --claim "Claude Code" \
  --docs-url https://relay.example/docs \
  --pricing-url https://relay.example/pricing \
  --output relay-audit-docs-only.md
```

## Safe Handling

- Use a temporary audit key whenever possible.
- Do not paste production prompts, proprietary code, or long-lived secrets into a suspicious relay.
- If the relay looks risky, rotate the test key after probing.
