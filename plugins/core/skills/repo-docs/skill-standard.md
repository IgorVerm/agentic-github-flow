# Writing a skill: the Agent Skills standard

The fixed reference for writing and changing a skill is the **Agent Skills standard** at
[agentskills.io](https://agentskills.io/home), an open standard that originated at Anthropic and
that both Claude Code and Codex follow. Claude Code's documentation stays Anthropic's guidance for
Claude Code, and Codex's OpenAI's for Codex. This file copies nothing from the standard beyond
what the checks below need. Before you write or change a skill, read the page for that kind of
change; check the [index](https://agentskills.io/llms.txt) for new pages.

The pages were read on 2026-10-30. None shows a version or a date.

## The standard

| Source | Read it for |
|---|---|
| [Overview](https://agentskills.io/home) | What loads when: discovery, activation, execution |
| [Specification](https://agentskills.io/specification) | The format: every check below |
| [Quickstart](https://agentskills.io/skill-creation/quickstart) | The smallest working skill |
| [Best practices](https://agentskills.io/skill-creation/best-practices) | Writing or revising a body: what to cut, scope, when to load a support file, gotchas, checklists, validation loops |
| [Optimizing descriptions](https://agentskills.io/skill-creation/optimizing-descriptions) | Changing a description |
| [Evaluating skills](https://agentskills.io/skill-creation/evaluating-skills) | Judging whether a change made a skill better |
| [Using scripts](https://agentskills.io/skill-creation/using-scripts) | A skill that runs commands, and any script it calls: no prompts, `--help`, errors, stdout and stderr, exit codes, output size |
| [Adding skills support](https://agentskills.io/client-implementation/adding-skills-support) | What a client does with a skill: a bad file is warned about or skipped, the `.agents/skills/` convention, opting out of model invocation |

## The clients and the validator

| Source | Backs |
|---|---|
| [Claude Code: skills](https://code.claude.com/docs/en/skills) | The fields Claude Code adds; the skill listing has a budget of about 1% of the context window and drops the least-used descriptions when it overflows; malformed YAML leaves a skill with empty metadata, so it is never picked; `claude plugin validate` |
| [Codex: build skills](https://learn.chatgpt.com/docs/build-skills) | The initial list takes at most 2% of the context window, or 8,000 characters when the window is unknown, and shortens descriptions first; `agents/openai.yaml` and `allow_implicit_invocation` |
| [`skills-ref` validator source](https://github.com/agentskills/agentskills/blob/main/skills-ref/src/skills_ref/validator.py) | What the standard's own validator checks: six fields, an unknown field is an error, the name, description and `compatibility` rules |

## The checks

| The specification says | Check it as |
|---|---|
| `name`: 1-64 characters, lowercase letters, digits, single inner hyphens, equal to the folder | The same |
| `description`: 1-1024 characters | 40-500 (below) |
| `compatibility`: 1-500 characters if present | The same |
| Frontmatter is YAML | Each value on one line, except the keys indented under `metadata:`; a plain value holds no `: ` (an error to a strict parser) and no ` #` (starts a comment and cuts the value) |
| Six fields | Those six, plus `disable-model-invocation` (below) |
| `SKILL.md` under 500 lines | The same, the whole file |
| Body under 5000 tokens (recommended) | Estimated as characters divided by 4 |
| File references one level deep | Every file that a linked `.md` support file links to is linked from `SKILL.md` itself; every relative link resolves |

## Where these checks are stricter, on purpose

| Subject | The standard | Here | Why |
|---|---|---|---|
| Description length | 1-1024 | 40-500 | Every description sits in every session's list. Twelve skills at 1024 characters are 12,288, past the 8,000 at which Codex shortens descriptions; at 500, 6,000. The floor stops a description too short to pick its skill |
| `disable-model-invocation` | Not a field | Allowed for a skill only the user starts, always with `agents/openai.yaml` setting `policy.allow_implicit_invocation: false` | Claude Code's and Codex's ways to keep a skill from the model; such a skill fails `skills-ref` and cannot be uploaded to claude.ai |
| Description wording | Err on the side of triggering | Narrow triggers where a skill can do damage or costs much | Broad descriptions load cleanup procedures for unrelated tasks |
| Testing a description | About 20 queries, 3 runs each | One request that should pick the skill and one that should not | A mini test catches a wrong trigger at a fraction of the cost |
| Scripts | `scripts/`, `references/`, `assets/` recommended | Support files beside `SKILL.md`; scripts in a `scripts/` folder the skill names by a relative path | One script can serve several skills of a plugin |

## Where skills live

In a repository, a skill is `.agents/skills/<name>/SKILL.md` (Codex reads it there) with
`.claude/skills/<name>` as a symlink to the folder (Claude Code reads that), so it is written
once. No client command checks a single skill's frontmatter (`claude plugin validate` checks a
plugin's layout and passed malformed frontmatter when tried), so check it against the table
above, and after changing a description, try the two requests in a fresh session of each client.
