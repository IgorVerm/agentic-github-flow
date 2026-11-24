# agentic-github-flow: design decisions

Rulings of the maintainers named in `HANDOFF.md`, newest first, with their words. Detail lives on
the linked issue.

## Codex only where Codex is chosen: its own plugin, 2026-11-22

**Decision (the maintainer):** first, on #98: "het codex deel moet ook optioneel zijn op het werk
zijn er enkel claude users. Dit zou nutteloze tokenkost/overhead creeren" (the Codex part must be
optional too: at work there are only Claude users, and it would create useless token cost and
overhead). Then: "alles wat we hier toegevoegd hebben ivm met codex mag niet meekomen op een
andere user als die geen codex heeft enkel enkel de claude versie wil ga dit na" and "er mag
niets ivm codex meekomen in dat geval wat dat is verspilde context" (nothing added here for
Codex may come along for a user who has no Codex and wants only the Claude version; that is
wasted context). And: "alle info moet er wel zijn maar enkel geladen worden als je codex kiest"
(all the information must still be there, but loaded only when you choose Codex).
**What:** Codex counts in the installer only when the `codex` command is found, or `--codex`
asks for it; a bare `~/.codex` is skipped with a note. The plugin `agentic-github-flow-codex`
(`plugins/codex/`) holds the worker's scripts, the `codex-worker` skill (the route and the
settings row `codex worker`) and the `codex-issue-chats` skill (the Codex adapter); the installer
adds it to both clients only with issue-chats and Codex in the plan, and removes it from Claude
Code when Codex leaves the plan. Codex's side of the shared skills is `rules/codex.md`, inlined
into the Codex block only. No skill file of the other plugins and not `rules/core.md` names
Codex; where the issue-chats method needs a seam it is client-neutral ("another client's adapter
skill", "a row an installed plugin adds"). `tests/skills_format.py` and `tests/installer.py`
check both.
**Why:** a Claude-only install carried 11.3 KB of Codex lines in its skill files, 7.3 KB of
them method.md §4 *Codex as the worker*, read at every issue chat's start, besides the 7 KB
Codex adapter and 126 KB of Codex scripts (measured on a9dae85, #98).
**Binds:** `tools/installer.py`, `rules/codex.md`, `plugins/codex/`, the client-neutral seams in
`issue-handover` (`SKILL.md`, `method.md` §1, §4, §6), `requirements`, `review-change`,
`review-security`, `repo-docs/skill-standard.md`, `tests/skills_format.py`, `tests/installer.py`.
**Detail:** issue #98.

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
`codex_worker.py` (since #98 in `plugins/codex/scripts/`), which runs `codex exec` in a job folder of its
own under a permission profile: writable only that job, no network, a read deny list, approval
`never`, with a time limit per turn. The script runs outside Claude Code's sandbox and therefore
runs no git and opens no file that the chat or Codex wrote: the setup of a job, the reading of
the prompt and the export of Codex's commits as a git bundle run inside Codex's sandbox
(`codex_job.py`), and the chat imports the bundle inside its own (`codex_import.py`) and reviews
it once before the push. The chat records the Codex thread id on the issue. The person allows
that script alone and excludes it from the sandbox (`docs/install.md`); the team edition writes
no allow rule. The plugin `openai/codex-plugin-cc` is not used.
**Why:** measured on 2026-11-20: the plugin cannot run inside Claude Code's sandbox; it answers
every approval request with an error; its app-server threads got write access to the person's
whole projects folder; its `SessionEnd` hook drops the session's jobs; and its rescue agent may
delegate unasked in every session. `codex exec` through one script needs no third-party
dependency and fixes the sandbox per call. Five reviews of #105 each found git run outside every
sandbox on a repository the chat or Codex could write; Codex's own process does the same on
every turn (`git status` in its working folder). The maintainer on the clone design (#107): "ok
maak de issue aan"; and on 2026-11-21, on reads, disk and who continues: "1 ok 2 nee het is
specifiek voor pax het moet via de ontdubbelde worktree kunnen werken 3 akkoord laat fable
kijken en indien nodig onderzoek doen": a measured read deny list for Codex is a condition to
merge, a full checkout per issue and a size limit are refused (the job's files are APFS clones:
pax_deorum, 13 GiB, costs 15.7 MiB), and the architecture was redone so that the class is gone
instead of one more door closed. On what that read deny list must cover, after three reviews
each found another source of Claude Code's read limits, the maintainer chose on 2026-11-21
"(a)+(b)+(c), dan mergen": (a) a fixed floor, (b) the user's and the managed Claude Code
settings, (c) the project settings of the worktree the worker is given; a project's read limits
do not bind a chat that hands the worker another worktree, since the worker cannot know the
chat's project. Codex commits in its job and Claude reviews after the import, so "Codex commit,
Claude reviewt" holds.
**Binds:** `plugins/codex/skills/codex-worker/SKILL.md` (the settings row, the route; until
#98 method.md §1 and §4), `plugins/codex/scripts/codex_worker.py`, `codex_job.py` and
`codex_import.py` beside it, `tests/codex_worker.py`, `docs/install.md`.
**Detail:** issues #103, #107.

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
`plugins/codex/skills/codex-issue-chats/SKILL.md` *Start the integrator* (until #98
`issue-handover/codex.md`), the client-neutral reference in `issue-handover` step 2. **Detail:** issue #85.

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

## Model and animation chats get a 600k context limit, keyed by label, 2026-11-22

**Decision (the maintainer):** "dit klopt niet een modeler of een animation chat moet 600k
context krijgen. Is dit nog niet geimplementeerd?" (this is wrong: a modelling or an animation
chat must get 600k context; is this not implemented yet?); "nee er zijn ook fable lanes die niet
modelen en animeren het moet specifiek over dat soort werk gaan" (no, there are also Fable lanes
that do not model or animate; it must be about that kind of work specifically); on the proposed
labels "akkoord met work: model, animation" (agreed with work: model, animation). **What:** this
narrows the entry of 2026-11-17. The settings row `context limit` takes a limit per label
(`` `300k`; label `work: model`: `600k`; label `work: animation`: `600k` ``); an issue chat whose
issue carries such a label gets the largest of them, every other chat keeps 300k. It goes by
the kind of work, not by the model. `start_issue_chat.py` records the issue's labels before a
chat starts (a hand-over too), so the hook reads no network per tool call; a chat started
otherwise reads them once. The settings are read again whenever origin's default branch or the
local branch moves, the local one when it is ahead (a setting landed in local-main mode). The
decision point is twice the limit, at most 900k: measured, a 1M context window and automatic
compaction at about 967k–977k kept a 600k chat from reaching 1.2M; asked on #82, the maintainer
chose "optie 1, plafond op 900k" (option 1, a ceiling at 900k). Measured before (issue
#82): Fable building chats reached 190–280k before their first model code, so they handed over
at 300k at or just after their first write. **Binds:** `context_limit.py`,
`start_issue_chat.py`, `skills/issue-handover/method.md` §1 and §4, `tests/context_limit.py`,
`tests/start_issue_chat.py`. **Review by:** with the entry of 2026-11-17. **Detail:** issue #82.

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

## Git rules: the git guard judges `git -C`, not a permission `*`, 2026-11-09

**Decision (the maintainer):** "laat dit oplossen door een agent betere regel dat een correcte
commit niet gestopt wordt" (have an agent solve this: a better rule, so that a correct commit is
not stopped); split off as #33: "Yes, open it" (2026-11-10).
**What:** `plugins/guards/policy/claude-permissions.json` holds no git rule whose `*` can reach
into a commit message (`git -C * …`, `git -c * …`, `git * …`, `git commit * …`; 69 deny and 10
ask rules dropped, `git commit --all*` became `git commit --all *`). The git guard's `--claude`
mode judges those spellings by parsing instead: it blocks the commands they denied (checked on
an example of every former rule, `tests/claude_git_rules.py`) and asks for a push,
`commit --amend`, `update-ref` and a remote change; a commit's option values are never flags and
shell comments are removed first. After three review rounds each found a `#` the comment
scanner misread, the maintainer approved "#33 nieuwe aanpak" (2026-11-23): the rest of a line
after each removed `#` is judged as well when it may run git, and a block or an ask from either
side wins; a comment that names a forbidden git command is refused, which costs an agent only a
reworded comment. `git restore --staged` is refused in every spelling, as the Codex rules and
`git restore *` already did (the dropped `git -C * restore *` had refused it too). After nine
review rounds each found new spellings, the maintainer chose "(b) structureel vangnet"
(2026-11-24): when a git command's subcommand slot holds no plain word (`git $(true) stash
drop`, `git -C r <<<x stash drop`, none at all), every subcommand word after a `git` in the
whole text is judged as the subcommand (`judge_loose`), as the dropped `git -C * …` rules
matched. A tenth review showed that belt still was no superset of the dropped rules (zsh's
`git -C r >! out stash drop` passed), and the maintainer had a new design made ("Ja, start
Fable", 2026-11-24; the design is on issue #33, posted before it was built): **exact where the
reading is certain, the former rules where it is not.** The guard's reader knows only the part
of the shell language that bash (3.2 and later), zsh and sh read the same way, and stops at
anything else instead of guessing. The commands before that point are judged by their words;
from the command it stopped in to the end of the text, the guard reads the text as the former
permission rules did (all of them, kept in the guard as `NET_DENY` and `NET_ASK`) and by the
belt. A text the reader does not know is therefore stopped whenever those rules stopped it,
a commit whose message names a rule's words included, and a misreading can no longer pass a
command. That rest is read a second time by a reader that skips what it does not know, so
that what the words say still counts there; the belt is for a command it had to skip in. The
reading is checked against bash 3.2, zsh and dash themselves (`tools/fuzz_git_guard.py`:
random texts run with a `git` that logs its words; outside the test gate, it needs those
shells). A second independent review (2026-11-24) found no class this design does not close,
and texts the reader was wrongly certain of; since then `$'…'` is never certain (no two shells
decode it alike), nor zsh's `repeat` after `do` or `then`, a command after `]]`, `<->`, an
`alias`; an unquoted `$IFS` in a word is also read as a split; a substitution in a
here-document body without a quoted delimiter is judged by the rules and the belt; and the
second reading gives up, and the text is refused, once it has read `MAX_AGAIN` characters
again or `MAX_SECONDS` have passed (it took 38 s on 32,000 braces, where the hook has 10 s).
A here-document body stays data unless a shell or an interpreter reads it, or a command in the
text runs a text that is not in its own words (`eval "$(cat <<'EOF' … EOF)"`): then every
body is judged as a shell text. A body written to a file that is run later is not seen, as
before, though the former rules stopped it by its text: asked "Here-documents als data laten
(zoals de branch doet) en #33 pushen?", the maintainer answered "Ja, alles" (2026-11-24), so a
here-document body stays data. A third independent review (2026-11-24, the last findings
round by the maintainer's rule of three) again found no class the design does not close, and
four texts read wrongly: the word of `${@:-word}`, `${!x:-word}` and `${x/pattern/word}` is
now read as the value it may be and any other unknown form of `${…}` is uncertain;
`${IFS%x}` splits as `${IFS}` does; a `$'…'` inside a substitution of a here-document body;
`/dev/fd/0` as a shell's input. Those last fixes were not reviewed again. The hook also covers the
terminal tool. The installer removes
the rules it added that the policy dropped, and names the user's own such rules without
changing them; `tools/remove_reaching_rules.py` removes those for the user (a dry run unless
`--apply`, a backup first, and only once the installed guards plugin runs the guard with
`--claude`).
**Why:** such a `*` spans the rest of the command, so `git -C r commit -m "a clean step"` was
refused by `git -C * clean*` and a message saying "push" asked the user (six refused commits in
one day in another repository).
**Binds:** `plugins/guards/scripts/pre_tool_git_guard.py`, `plugins/guards/hooks/hooks.json`,
`tools/installer.py` (`REACHES_COMMIT`), `tools/remove_reaching_rules.py`, `tests/claude_git_rules.py` (against
`tests/claude_git_rules_former.json`), `tests/claude_permissions.py`, `tests/git_guard.py`.
**Detail:** issue #33.

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
