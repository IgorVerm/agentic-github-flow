# agentic-github-flow: design decisions

Rulings of the maintainers named in `HANDOFF.md`, newest first, with their words. Detail lives on
the linked issue.

## Codex as the worker of a Claude issue chat, 2026-11-20

**Decision (the maintainer):** the aim: "astra 6.2 is very good but apparently very bad at
interfacing with humans. Is it possible to let the claude orchestrator also manage codex 6.2
chats the same way it handles local chats for claude". After the source review and the trial of
OpenAI's Codex plugin for Claude Code: "Meteen de issue-handover-route" (the issue-handover
route right away, over a line in `docs/install.md`, an installer opt-in, or nothing). How the
chat starts Codex: "codex exec direct" (over the plugin). The call outside Claude Code's
sandbox: "Allow-regel voor dat commando" (an allow rule for that command, over asking each
time). Commits: "Codex commit, Claude reviewt" (Codex commits, Claude reviews). Which issues:
"we hebben al labels voor astra" (we already have labels for Astra). Asked against an own client
on `codex app-server` that relays each approval: "codex exec houden, app-server later" (keep
codex exec, the app-server client later, as its own issue).
**What:** the settings row `codex worker` names a label and a Codex model; on an issue with that
label the Claude issue chat stays the owner and hands the implementation to Codex through
`plugins/issue-chats/scripts/codex_worker.py`, which runs `codex exec` in the chat's worktree in
Codex's `workspace-write` sandbox with no network and approval `never`, writable only the
worktree and its branch's git folders. The chat records the Codex thread id on the issue and
reviews each Codex commit. The person allows that script alone and excludes it from the sandbox
(`docs/install.md`); the team edition writes no allow rule. The plugin `openai/codex-plugin-cc`
is not used.
**Why:** measured on 2026-11-20: the plugin cannot run inside Claude Code's sandbox; it answers
every approval request with an error; its app-server threads got write access to the person's
whole projects folder; its `SessionEnd` hook drops the session's jobs; and its rescue agent may
delegate unasked in every session. `codex exec` through one script needs no third-party
dependency and fixes the sandbox per call.
**Binds:** `plugins/issue-chats/skills/issue-handover/method.md` (§1 settings, §4 *Codex as the
worker*), `SKILL.md` (the start brief), `plugins/issue-chats/scripts/codex_worker.py`,
`tests/codex_worker.py`, `docs/install.md`.
**Detail:** issue #103.

## Signatures name the model, 2026-11-19

**Decision (the maintainer):** "bijkomend wil ik dat elke github issue niet enkel signed is als
claude maar als claude opus 5.5 of claude fable 5.2" (in addition, I want every GitHub issue
signed not just as Claude but as Claude Opus 5.5 or Claude Fable 5.2), "zodat ik weet welk model
het deed" (so that I know which model did it). **What:** agents sign comments, issues and pull
request bodies `🤖 <model> (<role>):`, where `<model>` is the client and its model without
parentheses: `Claude Opus 5.5`, `Claude Fable 5.2`, and for Codex `Codex` with its model (for
example `Codex GPT-5.5`). The parsers of signed comments accept any such name, so earlier
signatures (`Claude Code`, `Codex`) stay valid. **Binds:** `rules/core.md` §Work and documents,
`review-change` (the `--agent` value), `requirements`, `open-issue`, `ship-change`,
`local-main.md`, `review-security`. **Detail:** issue #95.

## Google Cloud guard: ask, by permission rules, opt-in, 2026-11-19

**Decision (the maintainer):** "A, opt-in", choosing from the options on issue #89: ask before
`gcloud`, `gsutil`, `bq` and `cloud-sql-proxy` and deny reading the gcloud configuration folder
with permission rules (A), over a new hook that refuses with a per-folder exemption (B) or no
guard (C); and opt-in as `--guards gcloud` over a default of `--guards`.
**What:** the `gcloud` lists of `plugins/guards/policy/claude-permissions.json` and
`plugins/guards/policy/gcloud.rules`, installed only with `--guards gcloud`. No hook: a user's
deny and ask rules cannot be relaxed by a repository, so a per-repository exemption would have
needed one, and the ask leaves each command to the user instead.
**Why:** an agent can act with the user's own Google Cloud login on live data; most users of the
team edition do not use Google Cloud, and an agent that deploys there on purpose would ask at
every command.
**Binds:** `tools/installer.py` (`GUARD_EXTRAS`), `docs/install.md` §The Google Cloud guard,
`tests/claude_permissions.py`, `tests/codex_policy.py`, `tests/installer.py`.
**Detail:** issue #89.

## A Codex issue chat starts its integrator and waits for the receipt, 2026-11-18

**Decision (the maintainer):** "zorg dat voortaan elke codex issuechat zelf de integrator start
en pas stopt als die de overdracht heeft aangenomen" (make sure that from now on every Codex
issue chat starts the integrator itself and stops only once it has accepted the hand-over).
**What:** on the independent local-main route a Codex issue chat freezes its commit, starts the
integrator in its own turn, and ends the turn or hands over only after the integrator explicitly
accepted that exact commit with access to the worktree and evidence, recorded on the issue;
before a retry it looks for an existing integrator, and without a receipt it keeps custody and
reports. Which changes take the independent route is unchanged. **Binds:**
`plugins/issue-chats/skills/issue-handover/codex.md` *Start the integrator*, the reference in
`SKILL.md` step 2. **Detail:** issue #85.

## Issue chats hand over at 300k context; past 600k the user decides, 2026-11-17

**Decision (the maintainer):** "zet de grens op 300k" (set the limit to 300k); "boven 2x grens
moet de chat manueel toestemming van mij krijgen om door te werken" (above twice the limit the
chat needs my manual permission to work on); subagents "zelfde grens" (the same limit); for all
repositories ("2 ja voor alle repos"); "boven 300k doorwerken mag als een chat dicht bij een
oplossing denkt te zitten" (working on past 300k is allowed when a chat thinks it is close to a
solution); "zorg dat we af en toe die 300k waarde herzien indien de werking van context zou
wijzigen" (make sure we review the 300k value now and then, should the way context works
change). **What:** `context limit` defaults to 300,000 tokens in every repository with issue
chats; the issue-chats hook `context_limit.py` tells a chat past it to hand over after its step
unless it is close to a solution, and past twice it lets only asking the user and the hand-over
run until the user answers. Measured before (30 days, Igor's transcripts): in pax_deorum, with a
150k limit as a sentence, 335 of 349 issue chats passed it and 51% of their usage came from calls
above 300k. **Binds:** `plugins/issue-chats/scripts/context_limit.py`, `context-gate.sh`,
`hooks/hooks.json`, `skills/issue-handover/method.md` §1 and §4, `tests/context_limit.py`.
**Review by:** 2027-02-17 — and earlier when Claude Code's context window, prompt-cache lifetime
or compaction changes; measure the share of issue-chat usage above the limit again and compare.
**Detail:** issue #77.

## The question label enforced by a hook, not by a rule or a GitHub Action, 2026-11-17

**Decision (the maintainer):** asked whether the rule could be enforced "via script/hook zodat
het afgedwongen is ipv een suggestie voor een agent" (by a script or hook, so that it is
enforced instead of a suggestion to an agent), then on the proposed design "Ja, zo bouwen" (yes,
build it like that), and on its GitHub Action for closed issues "niet via actions" (not through
Actions). **What:** the issue-chats hook `question_label.py` refuses a question the work waits
on while the issue lacks the question label, and removes the label at the answer and when a
merge or `gh issue close` by an agent closes the issue; it posts no words to GitHub. No bullet in
`rules/core.md` (its budget, and the gap is in issue chats only); no workflow, so an issue closed
on github.com keeps its label until `cleanup-merged` step 4. **Binds:**
`plugins/issue-chats/scripts/question_label.py`, `plugins/issue-chats/hooks/hooks.json`,
`tests/question_label.py`. **Detail:** issue #75.

## Worktree clones on by default on macOS, 2026-11-11

**Decision (the maintainer):** "B, standaard aan op macOS, overal waar klonen lukt: APFS,
hetzelfde volume, geen sparse checkout. Uitzetten kan met --no-clones of
AGENTIC_GITHUB_FLOW_CLONES=0. Op andere systemen verandert niets." (B: on by default on macOS
wherever cloning works: APFS, the same volume, no sparse checkout. It can be switched off with
--no-clones or AGENTIC_GITHUB_FLOW_CLONES=0. On other systems nothing changes.) The issue had
proposed opt-in; integrator worktrees of ~14 GB each filled the disk twice the same day.
**What:** `new_worktree.py` makes the tracked files APFS clones of the primary checkout's on
macOS unless switched off; where cloning cannot work there it says why and makes a plain
worktree. Elsewhere the default is today's plain worktree, without a note; `--clones` or
`AGENTIC_GITHUB_FLOW_CLONES=1` there gives one note and the same plain worktree.
**Binds:** `plugins/core/scripts/new_worktree.py`, `clone_dedupe_worktree.py`,
`tests/new_worktree.py`.
**Detail:** issue #19.

## Automatic merging only where the user switches it on; unasked push of the own task branch, 2026-11-11

**Decision (the maintainer):** on merging, "automatisch mergen mag enkel voor repos waar ik dit
manueel aanzet" (automatic merging only in repositories where I switch it on by hand), and on
the form of that switch, "auto merge is defaulth uit maar kan aan op wens net zoals local en
pull mode" (automatic merge is off by default but can be switched on at will, just like local
and pull mode). On the
push, from the issue: "pushing to the non main remote branch should be allowed without me giving
it permissions since it doesn't enter main and stays on the pull request". On the steps after
the pull request: "start en voeg die stappen na PR toe aan die issue" (start, and add those
steps after the PR to the issue).
**What:** automatic merging needs the row `automatic merge` | `on` in the repository's own
`HANDOFF.md` §Landing settings, next to `landing`, on the default branch, set by the user;
missing, it is off. `landing.py` owns the setting and `--explain` reports it; `merge_pr.py`
refuses while it is off, whatever an overlay or `--grant` says, and with `--ready`
marks the draft ready only when every other condition holds. The push of an agent's own task
branch in pull-request mode needs no word where a standing grant allows it (the repository's
§Standing permissions or an overlay, as a line `standing grant | push_branch.py` that the script
reads), and goes only through `push_branch.py`: not the default
or landing branch, no force, pull-request mode, the pre-push hook installed (secret scan and
personal-data check on every outgoing commit), no path that merges only on the user's word,
the overlap result in the body; anything it refuses still asks. After its pull request is open
the agent switches on the client's CI monitor, has a subagent run `review-change`, turns
findings into new commits, waits for CI and merges through `merge_pr.py --ready` where the
switch is on, else asks for the merge; an issue chat stays until the merge and its cleanup.
**Why:** a task branch enters the default branch only through a merge, so its push integrates
nothing; what a push cannot take back (secrets, personal data) and what changes later sessions'
powers (rules, guards, hooks, CI, the installer) are checked or still asked. Merging integrates,
so the user decides per repository, not once for all.
**Narrows:** the ruling of 2026-11-09 below: an overlay's grant no longer switches automatic
merging on.
**Binds:** `rules/core.md` §Git, `plugins/core/scripts/landing.py` (and its copy in the
issue-chats plugin), `merge_pr.py`, `push_branch.py`, `tests/landing.py`, `tests/merge_pr.py`,
`tests/push_branch.py`, `plugins/core/skills/ship-change/SKILL.md` steps 6
to 8, `plugins/issue-chats/skills/issue-handover/` (`SKILL.md` steps 2, 6 and 7, `method.md`).
**Detail:** issue #26.

## Merging the landing branch inside the sandbox: frozen .claude (option D), 2026-11-11

**Decision (the maintainer):** "Ja, D vastleggen" (yes, record D).
**What:** a chat merges the landing branch into its task branch with
`plugins/core/scripts/merge_landing.py`. When the merge changes `.claude/` or `.mcp.json`, which
the Claude Code sandbox keeps a session from writing in its own working directory, those paths
get the skip-worktree bit and a per-worktree sparse-checkout exclusion, their on-disk state goes
into a manifest in the worktree's git dir, and the merge runs with the sparse settings passed by
`-c`: the merge commit is the ordinary one, the files on disk stay as the chat started with
them. A conflict inside those paths is refused. The cleanup and archive checks accept the frozen
paths only while the disk matches the manifest. The cost: a running chat's gates test the
`.claude/` it started with; new skills and agents arrive in the next chat.
**Rejected:** B, a merge tool outside the sandbox (git still reads repository configuration the
chat can write, and a check before the merge is racy); H, no longer tracking `.claude/`.
**Not in this decision, on the maintainer's word:** a guard rule refusing a bare merge or pull
that touches `.claude/`, and removing `git pull *` from `sandbox.excludedCommands`
(agent-rules#67, the maintainer's own rules repository).
**Binds:** `plugins/core/scripts/merge_landing.py`, `work_proof.py` (`frozen_unexplained`),
`remove_merged_worktree.py`, `plugins/issue-chats/scripts/chat_archivable.py`,
`plugins/core/skills/ship-change/SKILL.md` step 2, `local-main.md`.
**Detail:** issue #50; the report agent-rules#65.

## Efficient design: a skill and a review rule, for any kind of software, 2026-11-11

**Decision (the maintainer):** "Skill + regel" (a skill and a rule), adding "maar algemener dan
wereld want we maken ook andere zaken dan game wereld" (but more general than the world, because
we build other things than a game world too). The request: a way to enforce algorithmically
efficient solutions, because "ik moet deze vraag vaak stellen er er bestaat vaak een
efficientere oplossing" (I often have to ask this question and there often is a more efficient
solution).
**What:** the core skill `efficient-design`, a checklist loaded at design and at review for
games, web apps, data pipelines and tools; the core rule *Work grows with what changed, not with
all data*: the author writes an `Efficient design:` line in the pull request body or landing
comment, the reviewer checks it against the diff, and a cost growing with all data where what
changed would do goes back, unless its bound is stated.
**Why not a hook:** a hook sees a command or a file, not a design.
**Binds:** `rules/core.md` §How to work, `plugins/core/skills/efficient-design/SKILL.md`,
`plugins/core/skills/ship-change/SKILL.md` steps 1, 4 and 6, `local-main.md` §1 and §2.
**Detail:** issue #37.

## Agents may merge their own pull request under a standing grant, 2026-11-09

**Decision (the maintainer):** "ja zo wil ik dat het werkt" (that is how I want it to work), on
the rule below; for what is excluded, "Not rules, guards, CI (recommended)".
**What:** in pull-request mode an agent merges its own pull request without a word for that pull
request only where a standing grant allows it: the repository's `HANDOFF.md` §Standing
permissions, or an overlay the user installed. It merges through
`plugins/core/scripts/merge_pr.py`, and only when all hold: pull-request mode; not a draft and
merge state CLEAN, no review requesting changes; every required check (the ruleset's or branch
protection's, and the `required checks` row) passed on the head, so every platform; the newest
signed review by the user's own account (agents post under it), role `review`, by an agent
that did not write the change, approves the head commit (or an earlier one followed only by
conflict-free merges of the base branch, which need green checks again and no new review); the
overlap check's result in the body; no path that merges only on the user's word.
**Excluded, merged only on the user's word:** `rules/core.md` and a repository's own rules
(`AGENTS.md`, `CLAUDE.md`), a personal or company overlay, the guards, permission settings,
hooks and plugin manifests beyond their versions, the installer, CI and `.github/`
configuration, deployment configuration, the merge gate itself (`merge_pr.py`, `landing.py`),
and the `HANDOFF.md` sections that hold the grant and these settings (§Standing permissions,
§Landing settings); a repository adds patterns in `## Landing settings`. Skills, scripts,
tests and documents may merge automatically. Paths compare without case.
**Why:** a green CI on three systems and an independent review are what the user's word checked
for; the excluded paths change what every later session may do, so they stay with the user.
**Where the grant lives:** this repository grants nothing (`HANDOFF.md`: Standing permissions:
None); the maintainer's grant is in a private overlay, so it never extends to other
contributors. Narrowed on 2026-11-11 (above): only the repository's own switch counts. A bare
`gh pr merge` stays an ask rule in the guards.
**Binds:** `rules/core.md` §Git, `plugins/core/scripts/merge_pr.py`, `tests/merge_pr.py`,
`plugins/core/skills/ship-change/SKILL.md` steps 1, 4 and 7.
**Detail:** issue #13.

## Landing mode: local main or pull request, per repository, 2026-11-09

**Decision (the maintainer):** "er moet een automatische landing modus in de teams zitten, kies
tussen lokale main of pull requests op basis van industry standaarden" (an automatic landing
mode in the team edition, choosing local main or pull requests by industry practice). On the
open points: "Always worktree" (local-main mode also works on a branch in a worktree and lands by
a checked fast-forward, never directly on main) and "Reviewer lands" (a large or risky change is
reviewed and landed by an agent that did not write it). The `landing branch` setting stays.
**What:** `plugins/core/scripts/landing.py` decides at every landing (its header owns the rule);
`ship-change` and `cleanup-merged` follow both modes; this repository declares pull request.
**Binds:** `rules/core.md` §Git, `plugins/core/scripts/landing.py`, `promote_main.py`,
`plugins/core/skills/ship-change/`, `cleanup-merged`, the issue-chats plugin.
**Detail:** issue #13.
