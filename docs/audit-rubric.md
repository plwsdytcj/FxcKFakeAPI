# Audit Rubric

Use this rubric after collecting vendor claims and probe output.

## Hard fails

Treat these as severe red flags even if other checks look fine:

- the relay sells `official/direct` access but cannot produce a coherent native API surface
- invalid-model requests return `500` or HTML instead of a clear client error
- streaming is sold as supported but stream responses are not SSE-like
- the relay is marketed for agents or Claude Code but basic tool calling fails
- pricing or quotas are explained only through积分、套餐、神秘倍率 with no raw usage mapping
- the vendor asks users to share Claude.ai or Pro/Max credentials directly

## Scoring

Score each category from `0` to `5`.

### Authenticity

- `5`: vendor claims match the observable API surface; docs are specific; no evidence of account sharing or reverse-engineered client channels
- `4`: mostly consistent, with minor unanswered questions
- `3`: some claims are vague or unproven, but no hard contradiction
- `2`: several signs of wrapper behavior, hidden upstream, or claim inflation
- `1`: direct contradictions between claims and evidence
- `0`: clear deception or account-sharing model

### Compatibility

- `5`: models, normal completions, streaming, and tool calls all work as advertised
- `4`: core features work; one non-critical feature is degraded
- `3`: only basic chat works; agent-oriented features are uncertain
- `2`: multiple compatibility gaps or schema drift
- `1`: major advertised features fail
- `0`: endpoint is barely usable or incompatible with its claimed SDK surface

### Transparency

- `5`: pricing, limits, data handling, and upstream type are explained clearly
- `4`: mostly transparent with a few missing details
- `3`: some key details are implied rather than stated
- `2`: important billing or quota rules are obscured
- `1`: repeated vague marketing language and no hard numbers
- `0`: misleading pricing or undisclosed restrictions

### Reliability

- `5`: probes are stable and error handling is clean
- `4`: minor rough edges but healthy behavior
- `3`: mixed signals; likely usable for low-risk traffic only
- `2`: frequent 5xx, generic failures, or inconsistent responses
- `1`: unstable under basic probing
- `0`: effectively broken

### Security

- `5`: relay minimizes required trust, documents retention, and exposes no obvious unsafe handling
- `4`: no obvious issues, but evidence is limited
- `3`: unclear logging or retention
- `2`: asks for broad trust with little policy detail
- `1`: unsafe operational practices are visible
- `0`: the testing process itself reveals severe secret-handling risk

## Verdict mapping

- `Likely Legit`: no hard fails and most categories score `4` or `5`
- `Mixed / Needs Caution`: usable for low-risk traffic, but important unknowns remain
- `High Risk`: multiple categories at `2` or below, or one hard fail
- `Avoid`: repeated hard fails, deceptive claims, or obvious operational danger

## Interpretation rules

- A working OpenAI-compatible wrapper does not prove native upstream fidelity.
- Missing provider-specific headers are weak evidence. Broken semantics are strong evidence.
- One successful short completion does not prove model quality, caching, or `满血`.
- If public evidence and live probes disagree, prefer live probes for current behavior and explicitly mention the discrepancy.
