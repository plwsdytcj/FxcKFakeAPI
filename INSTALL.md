# Install

## Claude Code

Clone this repository into a Claude skills directory.

Project-local:

```bash
mkdir -p .claude/skills
git clone https://github.com/<owner>/FxckFakeAPI .claude/skills/api-relay-audit
```

Global:

```bash
git clone https://github.com/<owner>/FxckFakeAPI ~/.claude/skills/api-relay-audit
```

Then ask Claude Code to use `api-relay-audit`.

Optional slash command wrapper:

```bash
mkdir -p ~/.claude/commands
ln -sf ~/.claude/skills/api-relay-audit/.claude/commands/audit-relay.md \
  ~/.claude/commands/audit-relay.md
```

Then use:

```text
/audit-relay https://example.com/v1 api_key=... provider=auto
```

## Codex

Install from GitHub:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo <owner>/FxckFakeAPI \
  --path . \
  --name api-relay-audit
```

Or clone manually:

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/<owner>/FxckFakeAPI ~/.agents/skills/api-relay-audit
```

## OpenSkills

```bash
npx openskills install https://github.com/<owner>/FxckFakeAPI
npx openskills sync
```

## Quick Use

```text
Use api-relay-audit to inspect this relay:
base_url=...
api_key=...
claimed_provider=...
```

Deep probe example:

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
