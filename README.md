# API Relay Audit Skill

面向 `Claude Code`、`Codex` 和兼容 `SKILL.md` 的 agent 的 API 中转站审计 Skill。

它用于识别第三方 AI API relay / proxy / 中转站是否真的可用、是否存在以次充好、是否宣称 `官转` 却只是在做套壳、号池、共享账号或功能缩水。

## 仓库定位

这个仓库本身就是一个 Skill 目录，也就是：

```text
FxckFakeAPI/
  SKILL.md
  tools/probe_relay.py
  docs/audit-rubric.md
  docs/public-signals.md
  prompts/report-template.md
  agents/openai.yaml
```

## 安装

### Claude Code

项目内安装：

```bash
mkdir -p .claude/skills
git clone https://github.com/<owner>/FxckFakeAPI .claude/skills/api-relay-audit
```

全局安装：

```bash
git clone https://github.com/<owner>/FxckFakeAPI ~/.claude/skills/api-relay-audit
```

如果要直接用 slash command，再加一个命令包装：

```bash
mkdir -p ~/.claude/commands
ln -sf ~/.claude/skills/api-relay-audit/.claude/commands/audit-relay.md \
  ~/.claude/commands/audit-relay.md
```

### Codex

使用安装脚本：

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo <owner>/FxckFakeAPI \
  --path . \
  --name api-relay-audit
```

或者手动放到用户技能目录：

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/<owner>/FxckFakeAPI ~/.agents/skills/api-relay-audit
```

安装后如果没有立刻出现，重启 agent。

### OpenSkills

```bash
npx openskills install https://github.com/<owner>/FxckFakeAPI
npx openskills sync
```

## 使用

显式调用时，直接在提示词里提到 `api-relay-audit` 即可。典型输入：

```text
Use api-relay-audit to audit this relay:
base_url=https://example.com/v1
api_key=...
claimed_provider=Claude
docs_url=...
pricing_url=...
```

如果你装了 Claude Code 命令包装，可以直接这样用：

```text
/audit-relay https://example.com/v1 api_key=... provider=auto
```

或者深度模式：

```text
/audit-relay base_url=https://example.com/v1 api_key=... provider=auto deep=1
```

如果你已经拿到了临时 key，Skill 会优先运行 `tools/probe_relay.py`，然后结合文档声明和公开证据给出：

- `Verdict`
- `Confidence`
- `Claims vs observed`
- `Positive evidence`
- `Red flags`
- `Recommended action`

深度探测建议在你怀疑对方有 `号池`、`缩水模型`、`假缓存`、`高峰限流` 时开启：

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

这会额外检查：

- surface-specific 认证头是否需要分开
- 隐藏 token 的精确回忆能力
- 2-3 次小突发请求下是否直接 429 / 5xx
- Anthropic 原生 prompt caching 是否真的有 cache-read 信号

## 核心文件

- `SKILL.md`: 审计流程主说明
- `tools/probe_relay.py`: HTTP 探测脚本
- `docs/audit-rubric.md`: 评分规则
- `docs/public-signals.md`: 常见营销话术和红旗
- `prompts/report-template.md`: 报告输出模板

## 设计原则

- 先看证据，再下结论
- 区分“官方 API 兼容”与“真的保留上游语义”
- 不把低价直接等同于造假，但要求价格、能力、限流、日志策略能自洽
- 不用一次短对话就断定模型是否 `满血`
