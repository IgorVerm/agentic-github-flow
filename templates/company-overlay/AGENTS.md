# <Company>: rules for AI coding agents

This is the company overlay for agentic-github-flow. It lives in a private repository of
<Company>'s GitHub organisation, and each colleague adds it with
`install.sh --overlay <this repository's clone URL>` (Windows: `install.ps1 --overlay …`).
Its rules load after the core rules. The binding rules below (the AI policy and the data classes)
are never relaxed in a conversation, by anyone; where another rule here says it deviates from
the core rules, it wins over them.

## AI policy (binding)

The company's AI policy applies to all agent work: <link to the policy; do not copy its text>.
Its owner: <role or team>. In short, for agents:
- <the one or two points from the policy that agents meet daily, each with its section number>

## Data classes (binding)

| Class | Examples | May go into a prompt? | May leave the machine through a tool? |
|---|---|---|---|
| Public | <published docs, open-source code> | yes | yes |
| Internal | <internal code, designs, tickets> | <yes / only with approved clients> | <only to approved services> |
| Confidential | <customer data, contracts, HR> | <no> | <no> |
| Secret | credentials, keys, tokens | no | no |

Approved clients and services: <Claude Code / Codex under which plans; other services>.
The dependency audit of the security plugin sends package names and versions to osv.dev, the
public npm registry (`npm audit`) and the PyPI registry: <allowed / not allowed>.

## GitHub organisation

- Repositories: <org>/<…>. Branch naming, if prescribed: <pattern, else "agent/<task>">.
- Required reviewers and CODEOWNERS: <who reviews what>.
- Required CI checks: <names>. A pull request is merged by: <role>.
- Issue labels and templates: <links>.

## Deviations from the core rules

None. <A deviation names the core rule it changes and why, for example a stricter push rule.>
