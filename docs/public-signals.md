# Public Signals

Use this file when reviewing the vendor site, FAQ, screenshots, or public community reports.

## Marketing phrases that require proof

Treat these as claims to verify, not facts:

- `官转`
- `官方直连`
- `满血`
- `企业级`
- `专线`
- `独享`
- `零封号`
- `不限速`
- `不掉线`

Ask what these phrases mean operationally: native API key, account pool, reverse-engineered client path, or another upstream.

## Common red flags

- the site advertises `Pro/Max`, `共享账号`, `代登`, `号池`, or unusually cheap `周卡/月卡`
- the site sells special low-price channels by client name instead of provider name
- pricing is shown only as积分 or倍率, with no raw token mapping
- docs hide the actual upstream type but heavily emphasize `官方同款`
- support refuses to explain why usage, cache hit rate, or context size differs from official behavior
- the site asks the user to trust that logs are not retained without publishing any policy

## Questions to ask the vendor

- Is this backed by native provider API keys, shared subscription accounts, or reverse-engineered client traffic?
- Are usage limits organization-level, account-level, or pooled across customers?
- How are prompt caching and cache hit rates measured?
- What features are fully supported today: tools, streaming, images, batch, responses API, Claude Code?
- What gets logged, for how long, and who can access it?
- What triggers refunds or compensation during upstream incidents?

## Public evidence checklist

- pricing page with raw numbers
- changelog or status page
- terms of service or acceptable-use terms
- documented model list
- concrete incident reports with dates
- independent user reports that include raw errors, screenshots, or trace IDs

## Reporting rule

When summarizing public evidence, separate:

- what the vendor says
- what users report
- what your own probes observed

Do not collapse these into one conclusion without labeling the source of each claim.
