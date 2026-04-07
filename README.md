# API Relay Audit Skill

## 中文

面向 `Claude Code`、`Codex` 和兼容 `SKILL.md` 的 agent 的 API 中转站审计 Skill。

用于识别第三方 AI API relay / proxy / 中转站是否真的可用、是否存在以次充好、是否宣称 `官转` 却只是在做套壳、号池、共享账号或功能缩水。

### 仓库定位

这个仓库本身就是一个 Skill 目录：

```text
FxckFakeAPI/
  SKILL.md
  tools/probe_relay.py
  docs/audit-rubric.md
  docs/public-signals.md
  prompts/report-template.md
  agents/openai.yaml
```

### 安装

#### Claude Code

项目内安装：

```bash
mkdir -p .claude/skills
git clone https://github.com/<owner>/FxckFakeAPI .claude/skills/api-relay-audit
```

全局安装：

```bash
git clone https://github.com/<owner>/FxckFakeAPI ~/.claude/skills/api-relay-audit
```

如果要直接用 slash command，再加命令包装：

```bash
mkdir -p ~/.claude/commands
ln -sf ~/.claude/skills/api-relay-audit/.claude/commands/audit-relay.md \
  ~/.claude/commands/audit-relay.md
```

#### Codex

安装脚本：

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo <owner>/FxckFakeAPI \
  --path . \
  --name api-relay-audit
```

手动安装：

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/<owner>/FxckFakeAPI ~/.agents/skills/api-relay-audit
```

如果没有立即生效，重启 agent。

#### OpenSkills

```bash
npx openskills install https://github.com/<owner>/FxckFakeAPI
npx openskills sync
```

### 使用

显式调用示例：

```text
Use api-relay-audit to audit this relay:
base_url=https://example.com/v1
api_key=...
claimed_provider=Claude
docs_url=...
pricing_url=...
```

Claude Code 命令包装示例：

```text
/audit-relay https://example.com/v1 api_key=... provider=auto
```

深度模式：

```text
/audit-relay base_url=https://example.com/v1 api_key=... provider=auto deep=1
```

若你有临时 key，Skill 会优先运行 `tools/probe_relay.py`，并输出：

- `Verdict`
- `Confidence`
- `Claims vs observed`
- `Positive evidence`
- `Red flags`
- `Recommended action`

深度探测命令（适合怀疑号池、缩水模型、假缓存、限流）：

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

### 核心文件

- `SKILL.md`: 审计流程主说明
- `tools/probe_relay.py`: HTTP 探测脚本
- `docs/audit-rubric.md`: 评分规则
- `docs/public-signals.md`: 常见营销话术和红旗
- `prompts/report-template.md`: 报告输出模板

### 设计原则

- 先看证据，再下结论
- 区分“官方 API 兼容”与“真的保留上游语义”
- 不把低价直接等同于造假，但要求价格、能力、限流、日志策略能自洽
- 不用一次短对话就断定模型是否 `满血`

---

## English

An API relay auditing skill for `Claude Code`, `Codex`, and other agents that support `SKILL.md`.

This project helps evaluate whether a third-party AI API relay/proxy is genuinely usable or potentially degraded, oversold, wrapper-based, or risky.

### Repository Layout

This repository is itself a skill directory:

```text
FxckFakeAPI/
  SKILL.md
  tools/probe_relay.py
  docs/audit-rubric.md
  docs/public-signals.md
  prompts/report-template.md
  agents/openai.yaml
```

### Installation

#### Claude Code

Project-local install:

```bash
mkdir -p .claude/skills
git clone https://github.com/<owner>/FxckFakeAPI .claude/skills/api-relay-audit
```

Global install:

```bash
git clone https://github.com/<owner>/FxckFakeAPI ~/.claude/skills/api-relay-audit
```

Optional slash command wrapper:

```bash
mkdir -p ~/.claude/commands
ln -sf ~/.claude/skills/api-relay-audit/.claude/commands/audit-relay.md \
  ~/.claude/commands/audit-relay.md
```

#### Codex

Install via helper script:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo <owner>/FxckFakeAPI \
  --path . \
  --name api-relay-audit
```

Manual install:

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/<owner>/FxckFakeAPI ~/.agents/skills/api-relay-audit
```

If the skill does not appear immediately, restart your agent.

#### OpenSkills

```bash
npx openskills install https://github.com/<owner>/FxckFakeAPI
npx openskills sync
```

### Usage

Explicit skill invocation:

```text
Use api-relay-audit to audit this relay:
base_url=https://example.com/v1
api_key=...
claimed_provider=Claude
docs_url=...
pricing_url=...
```

Claude Code command wrapper:

```text
/audit-relay https://example.com/v1 api_key=... provider=auto
```

Deep mode:

```text
/audit-relay base_url=https://example.com/v1 api_key=... provider=auto deep=1
```

With a temporary key, the skill runs `tools/probe_relay.py` and reports:

- `Verdict`
- `Confidence`
- `Claims vs observed`
- `Positive evidence`
- `Red flags`
- `Recommended action`

Deep probe command:

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

### Key Files

- `SKILL.md`: main audit workflow
- `tools/probe_relay.py`: HTTP probe runner
- `docs/audit-rubric.md`: scoring rubric
- `docs/public-signals.md`: common red flags and claim patterns
- `prompts/report-template.md`: report template

### Design Principles

- Evidence first, verdict second
- Distinguish API compatibility from true upstream fidelity
- Do not treat low price alone as fraud; require pricing/capability/limits to be coherent
- Do not infer model quality from a single short prompt
