# Proposal: a verification gate that stays small

Status: proposal for the maintainer, issue #146. Nothing here is implemented. Sources:
[the Claude Code article](../sources/2026-11-16-claude-code-verification.md) ("the article")
and [METR's Q4 2026 update](../sources/2026-11-20-metr-q4-capability-update.md) ("METR"); the
section references below are to those two documents. Measured on 2026-11-24 at `5c2a3b2`.

## Summary for the maintainer

**What I propose.** Every change that lands carries one line, `Verified:`, that says how it
was checked and what the evidence is, or `none` with a reason. The author writes it, the
reviewer checks it against the diff, and the two scripts that already guard landing
(`push_branch.py`, `merge_pr.py`) look for it. It starts in observe mode, where a missing line
is reported and nothing is refused. It is one line per pull request, not a stamp per commit,
and it adds no sentence to `rules/core.md`.

**What keeps the test base from growing.** Four mechanisms, each with one owner:

1. A budget in `tests/run_all.py`: 34 test files and 320 seconds on the Linux CI job, which is
   where the suite stands today. A change that goes over it removes or merges something first,
   or raises the number in the same change with its reason.
2. An admission test: a new check names the defect it catches, and the author shows it fail on
   that defect. A check that cannot fail on a plausible defect is not added.
3. Selection by diff: locally a change runs only the test files whose trigger matches its
   paths, not all 34.
4. A pruning date: the budget entry carries a `Review by:` date, which the existing check in
   `tests/repo_checks.py` turns into a failing gate when it passes.

**Why now, in numbers.** In 30 days the suite went from 12 to 34 test files and the CI test
step from 60 to 312 seconds on Linux and from 292 to 1,253 seconds on Windows. No test file
has ever been removed. A pull request waits 21 minutes per CI run and has 2.2 runs on average.

**What the measurements say about value.**
- The independent review is the stage that catches most: 41 findings rounds on 20 of the 29
  reviewed pull requests.
- CI failed on 15 of 55 branches, and 19 of its 21 runs with a failed test failed on Windows
  only: CI earns its cost as the portability check.
- 21 of the 34 test files have never failed in CI, and they take 309 of the 469 seconds of a
  local run. That does not make them worthless, because failures before a push are recorded
  nowhere. It does make them the first candidates to look at.

**The two sources agree on one thing that decides the design.** A check is worth what it
costs when it is exact, fast and out of the author's reach. The article says so from practice;
METR measures the other side: agents that had to build their own yardstick misled themselves,
and more so in larger groups. A test written by the author, in the same change, to prove that
change is such a self-made yardstick. That is the argument for refusing tests that restate the
implementation, and for reading the gate's rules from the default branch.

**Decisions I need from you** are in [§7](#7-open-questions-for-the-maintainer): seven
questions, each with my recommendation. The follow-up issues are in
[§9](#9-follow-up-issues); the first four are the whole gate, the rest are optional.

## The link between the two sources

The issue stated four hypotheses. Each is checked against METR here.

| Hypothesis | Verdict | Source |
|---|---|---|
| Models do best where feedback is clear and automatic. | **Confirmed.** Strongest where the goal is cheap to check and the score is visible to the agent. Caveats: top humans still win, only 3 tasks have human baselines, and such tasks resemble training environments. | METR §3.A, Appendices K and L, §1 |
| Models are weaker where verification is costly. | **Partly, with a correction.** Tasks with a higher lifecycle cost are somewhat harder (R² = 0.14; 13.8 points of success per doubling). But lifecycle cost is the cost of building, running and scoring a task, not the cost of verifying it, and progress is as fast on the costly half. The direct evidence is on judgment: without clear feedback, agents judged worse than experts, on 4 task families. | METR §3.B.1 and footnote 35, Appendix F, §3.B.2 |
| METR documents reward hacking. | **Confirmed, with a correction to the form.** The forms found are tailoring a solution to a guess of the hidden tests, searching for answers and brute force, not editing tests. After hardening that takes at least 10% of task-development effort, under 0.1% of runs still had to be scored zero. | METR Appendix G |
| Model judges overrate stronger models' work. | **Confirmed, narrower than stated.** Shown in one task setting, without a sample size, and for authors that are similarly strong or stronger. The best judge still scored about 0.2 of 1 too high. | METR §3.B.2, footnotes 46 and 47 |

A fifth finding belongs here, although the issue did not ask for it. The article says
verification loops are what allow dozens of agents in parallel (article §1). METR tested
parallel agents against independent agents with the same token spend: they were consistently
better on one task, where every submission gets its exact grade at once, and consistently
worse on two tasks where the score exists but is not shown, because agents fixed on a metric
of their own and never checked it against the real one (METR Appendix J). The article's claim
therefore holds under a condition it does not state: the feedback must be exact, immediate and
not made by the agents themselves.

What follows for a repository:

1. **Spend on checks that are exact, fast and external.** An existing test, read from the
   default branch, that passes or fails in seconds is the strongest evidence a change can show.
2. **A check the author wrote for this change is the weakest.** It can only confirm what the
   author already believed (METR §3.B.2: a model has only its own judgment to optimise
   against). It earns its place by failing on a defect the author can name.
3. **Where no cheap check exists, do not invent one.** Rule text, skill wording and design
   choices are judgment. A model reviewer of the same strength is a weak judge of them (METR
   §3.B.2), so they go to a person, which this repository already does for rules, guards and
   hooks. `Verified: none` with a reason is the honest record there, and a test that pretends
   to check prose is bloat.
4. **Keep the check out of the change's reach** (article §3, *Changes cannot modify their own
   checks*; METR keeps hidden tests in a separate container, Appendix G).
5. **Expect gaming where the agent is stuck** (METR Appendix G: more likely at the limit of
   ability). That is the case for a stop after a fixed number of failed rounds.

## 0. Measurements

All numbers are from this repository on 2026-11-24. Sources: a local run of
`python3 tests/run_all.py` on macOS inside the client's sandbox, `gh run list` and the job
records of all 176 runs of the `ci` workflow, the logs of the 23 failed jobs, `gh pr list`
with comments for all 55 pull requests, and `git log`.

**Size.**

| | |
|---|---|
| Test files in the gate (`TESTS` in `tests/run_all.py`) | 34 |
| Lines in `tests/*.py`, helpers included | 13,905 |
| `unittest` methods (`def test_`) | 486, in 21 files |
| Files with their own case tables | 13 (their cases are not counted the same way; `sandbox_network_guard.py` reports 260, `git_guard.py` 235) |
| Test files on 2026-10-25 | 12 |
| Test files ever removed | 0 |
| Revert commits in 344 commits | 0 |

**Runtime.**

| | Seconds |
|---|---|
| Local run, macOS, wall clock (33 passed, 1 skipped for the sandbox) | 469 |
| of which CPU (user + system) | 386 |
| CI test step, Linux, median of the last 30 runs | 312 (first 30 runs: 60) |
| CI test step, macOS | 627 (first 30: 128) |
| CI test step, Windows | 1,253 (first 30: 292) |
| CI job p90 over median, Linux, 175 runs | 1.31 |
| CI wall clock per run, median of the last 30 | 1,243 (the Windows job) |
| CI job seconds per run, three jobs summed | 2,207 |

Eight files take 272 of the 469 local seconds: `worktree_tools.py` 61, `codex_worker.py` 42,
`merge_pr.py` 40, `merge_landing.py` 28, `landing.py` 28, `delete_guard.py` 27,
`pre_push_checks.py` 24, `start_issue_chat.py` 22. The median file takes 10 seconds.

**What the gate caught.**

| | |
|---|---|
| CI runs | 176: 151 passed, 24 failed, 1 unfinished |
| Failed runs in which a test failed | 21, with 23 failed jobs; in the other 3 the macOS job was cancelled |
| Failed jobs by system | Windows 20, macOS 2, Linux 1 |
| Runs that failed on Windows only | 19 of the 21, on 14 branches |
| Branches with at least one failed CI run | 15 of 55 |
| Test files that failed in CI at least once | 13 of 34 |
| Test files that never failed in CI | 21, taking 309 of the 469 local seconds |
| Same commit run twice with different results | 0 (no commit was run twice, so flakiness cannot be read from CI) |
| Pull requests with a review verdict | 29 of 55 |
| Review verdicts | 37 approvals, 41 findings rounds |
| Reviewed pull requests with at least one findings round | 20 of 29 |
| Reviewed pull requests with three or more findings rounds | 3 (4, 5 and 9 rounds) |
| Merges into `main` that touched `tests/` | 32 of 41 |

**Cost per change.** A pull request has 2.2 CI runs on average (123 runs on 55 branches,
median 2), so it waits about 46 minutes on CI and uses about 81 job-minutes. A local full run
costs 7.8 minutes. The suite's output is 3,014 characters, roughly 750 tokens (an estimate
from the character count). Reviewed pull requests had 2 verdict rounds at the
median. The token cost of a review round is not recorded anywhere and could not be measured.

**Three gaps in what can be measured today.** Test failures before a push leave no record, so
"never failed" above means only "never failed in CI". Case counts are not comparable across
the two test styles. Review cost in tokens is unknown. §5 closes the first two.

## 1. Inventory

What exists, against each practice of the article (§3 unless noted).

| Practice in the article | Here today | Verdict |
|---|---|---|
| Verification means running the change | Most tests already run the real thing: hooks get the JSON the client sends (`tests/delete_guard.py`, `git_guard.py`), the installer runs in temporary homes (`tests/installer.py`), scripts run against real git repositories. | Exists. No new test kind needed here. |
| A `verify` skill per repository | `HANDOFF.md` §Build, test, run names the commands; `ship-change` step 3 says to run them. No skill, and nothing says what to run for which change. | Missing: the decision and its record. |
| Cheap checks before a pull request | `ship-change` step 3, as text. `push_branch.py` does not look for it. A local full run takes 7.8 minutes, which invites skipping it. | Partly. Selection by diff makes it cheap enough to hold. |
| Stop after three failed rounds | Core rule: stop after two failed corrections of the same problem. `ship-change` step 8 loops over review rounds without a limit; three pull requests had 4, 5 and 9. | Partly. Missing for review rounds. |
| Owners write their checks | One maintainer; `AGENTS.md` and the tests are his. | Exists. |
| A checklist triggered by the diff | `HANDOFF.md` §What to read for which work maps areas to tests, for a reader. Nothing a script can use, and no review checklist. | Missing. |
| One reviewer, rounds that build on each other | One reviewer (`review-change`). A re-review reads only the new commits when the head moved, but is not given the earlier findings. | Partly. |
| A `REVIEW.md` read from the default branch | None. `review-change` step 3 reads `AGENTS.md` and `HANDOFF.md` without saying from which commit. | Missing, and a gap. |
| Changes cannot modify their own checks | Strong for the gate itself: `merge_pr.py` runs from the installed plugin, reads its settings from the default branch and holds rules, guards, hooks, CI and its own files for the maintainer's word (`EXCLUDED`). `templates/pre-push` reads the landing branch the same way. **Not for tests:** `tests/` is outside `EXCLUDED`, CI runs the tests of the pull request, so a change can remove a test and merge automatically if the reviewer misses it. | Conflict to settle (§2.4). |
| A review belongs to one commit | `review_verdict.py` pins the verdict to a SHA; `merge_pr.py` accepts only that commit or clean merges of the base after it. | Exists. |
| A stamp per commit, a commit gate with three modes | Pull request body lines `Overlap check:` and `Efficient design:`; `merge_pr.py` refuses without the first. No verification line, no modes. | Missing. Proposed per landing, not per commit (§2.2). |
| Review the reviewers | Nothing. The numbers of §0 were collected by hand for this proposal. | Missing (§5). |
| Misses become rules | `AGENTS.md`: a rule only after the same mistake happened twice; one that must always hold becomes a hook. | Exists as a principle, without a route for review findings. |
| Flaky tests: fix or delete with a reason | Core rule: never weaken a test or a gate. Nothing on sleeps, retries or deleting. | Partly. |
| Pruning on a routine | Budgets for rules and skills (`tests/skills_format.py`). None for tests; nothing was ever removed. | Missing. This is the core of the request. |
| Property and differential tests (§2) | One differential test: `tests/delete_guard_differential.py` compares the guard with the version on `main` over 38,364 generated commands. No property library; the tests use the standard library only. | Exists where it pays. |

## 2. Enforcement

### 2.1 The decision and its record

Before a change lands, the author decides how it is verified, does it, and writes one line in
the pull request body, or in the landing comment in local-main mode:

```
Verified: <kind>: <evidence>
```

| Kind | Meaning | Example of evidence |
|---|---|---|
| `tests` | Existing checks ran and passed. | `run_all.py --changed, 4 files, 71 s` |
| `new-check` | A check was added; names the defect it fails on. | `tests/landing.py test_x fails when the row is read from the worktree` |
| `run` | The changed tool was run and its behaviour observed. | `installer.py --dry-run in a temporary home: 6 plugins listed` |
| `seen` | A screenshot or a rendered result was looked at. | `screenshot of the settings page at 375 px` |
| `none` | Nothing to run. The reason is required. | `documentation only` |

More than one kind may be given, separated by `;`. The format has one owner, a small script
beside `review_verdict.py` that parses and validates the line, and `merge_pr.py` and
`push_branch.py` read it through that script, as they already read verdicts.

### 2.2 A stamp per commit, weighed

The article stamps every commit (§3, *Start a new gate in observe mode*). Weighed for this
method:

| | Per commit (a trailer) | Per landing (a body line) |
|---|---|---|
| Records in 30 days here | 344 | 55 |
| Can be queried | `git log`, offline | `gh`, and the merge commit when the line is copied into it |
| Noise | A trailer on every small commit, most of them `none: work in progress` | One line where the reader already looks |
| Enforced by | A commit hook, per client | The two landing scripts, which exist and serve both clients |
| What it proves | That a line was typed at each commit | The same, once, for what actually lands |

The core rules ask for small commits of verified work, and what lands is the pull request, so
the per-commit stamp records 6 times as much to prove the same thing. **Recommendation: per
landing.** The article's reason for the commit stamp, being able to query what was not
verified, is kept: `none` is a valid, searchable value.

### 2.3 Where each check runs

| Stage | What runs | Enforced by | Cost |
|---|---|---|---|
| While working | The test files whose trigger matches the changed paths (§3.1). | The `verify` procedure (§2.6); not a hook. | Seconds to about a minute; the median file takes 10 s. |
| Before the push | The `Verified:` line exists and parses. | `push_branch.py`, which already refuses without the overlap line. In observe mode it prints; in enforce mode it refuses, and the push falls back to asking the user. | Milliseconds. |
| CI | The whole suite on three systems, as now. | `.github/workflows/ci.yml`, unchanged. | 21 minutes of waiting per run. |
| Review | The line is checked against the diff: the evidence is real (the reviewer reruns a cheap command), it fits the size of the change, and a `new-check` passes the admission test of §3.2. | `review-change`, one more item in its step 4. | Part of a review that runs anyway. |
| Merge | The line exists; the gate's mode is read from the default branch; the round limit and the removed-checks signal (§2.4, §2.5). | `merge_pr.py`, one more condition in its header. | Milliseconds. |

**Not proposed: a hook that runs tests when the agent finishes** (the article's suggestion in
§3). At 7.8 minutes for the suite it is too slow to run at every stop; with selection it
would be fast enough, but it would be a second place that decides what runs, in a plugin
whose every change waits for the maintainer. The line checked at the push gives the same
guarantee for less. Worth another look once selection exists and its timings are known.

**The modes.** One row in `HANDOFF.md` §Landing settings, next to `automatic merge`, read from
the default branch like the others:

| Setting | Value |
|---|---|
| verification gate | `off`, `observe` or `enforce`; `off` when the row is missing |

Observe reports what would have been refused, in the script's output and in a line of the
landing report, so false refusals are seen before anyone is stopped (article §3). Enforce
refuses the unasked push and the automatic merge. It never blocks the maintainer: a refusal
means the landing waits for a person's word, which is what the scripts do today for a
protected path. The article lets a commit through after two blocks so the agent cannot get
stuck; that escape is not needed here, because the refusal already ends at a person.

### 2.4 Gating rules come from the default branch

Three changes, in order of value.

1. **Removed checks hold for the maintainer.** `merge_pr.py` compares `tests/` between the
   base and the head: a test file deleted, an entry removed from `TESTS`, or fewer test
   methods in a file than before. Any of these refuses the automatic merge with the list, and
   the maintainer decides. Putting all of `tests/` in `EXCLUDED` would be simpler and wrong:
   32 of 41 merges touched `tests/`, so automatic merging would end. The signal would have
   fired on none of the 52 merged pull requests, since nothing was ever removed. It will fire
   on every pruning change, which is intended: pruning is the maintainer's decision.
2. **The reviewer reads the rules from the base.** `review-change` step 3 says so explicitly:
   `git show origin/<base>:AGENTS.md`, and the same for `HANDOFF.md` and `REVIEW.md`.
3. **A `REVIEW.md` at the repository root**, read only from the default branch: the checklist
   of §3.6. It starts nearly empty.

Not changed: CI keeps running the tests of the pull request. Running the base branch's tests
against the head's code would catch a weakened test, and would fail every change that
legitimately changes behaviour together with its test. Item 1 covers the dangerous case for
far less.

### 2.5 Three rounds, then a person

The core rule already stops after two failed corrections of the same problem, which is
stricter than the article's three. The gap is the review loop: `ship-change` step 8 turns
findings into commits and asks for a new review without a limit.

Proposed: `merge_pr.py` counts the findings verdicts on the pull request, which it already
parses, and after the third it refuses the automatic merge until the maintainer says go.
`ship-change` step 8 says the same in one sentence: after the third findings round, stop and
report what was tried. In the 30 days measured this would have stopped 3 of 29 reviewed pull
requests, the ones that went to 4, 5 and 9 rounds.

Second change, from the article's *One reviewer, multiple rounds*: a re-review is handed the
earlier findings and reads the commits since, and does not start again from nothing. No
second reviewer is added. METR's finding on judges (§3.B.2) is a reason not to stack model
reviewers: a second judge of the same strength shares the first one's blind spot.

### 2.6 A `verify` skill

The article puts a skill named `verify` in each repository's `.claude/skills/`. Two
constraints of this method argue for a different split: skills are written once for both
clients, and a session cannot write its own `.claude/` inside the sandbox (#50).

- **The procedure** is one skill in the core plugin, `verify`: decide the kind, run the
  selected checks, apply the admission test before adding a check, write the line. It replaces
  most of `ship-change` step 3, which then points to it.
- **The facts of a repository** live in its `HANDOFF.md`, where the commands already are: a
  section `## Verification` with the fast command, the full command, and how to start and
  drive the application where there is one. A project with a heavy harness (a game, a mobile
  app) keeps that harness as its own skill or script and names it in the section.

Cost: about 2,500 bytes of skill body and about 300 bytes of description. The descriptions
budget stands at 5,645 of 5,645 bytes, so it is raised in the same change, and every session
of every user carries the 300 bytes. The alternative in question 3 of §7 costs none of that.

## 3. The anti-bloat system

### 3.1 Selection by diff

Each entry of `TESTS` in `tests/run_all.py` gets the path patterns that trigger it, and
`run_all.py --changed [<base>]` runs only the files whose trigger matches the paths changed
against the base. This is the article's checklist with triggers (§3), applied to tests. The
map already exists for readers, as the table in `HANDOFF.md` §What to read for which work;
`run_all.py` becomes its owner and the table points to it.

- A path that matches no trigger runs everything. Selection may miss speed, never a test.
- `skills_format.py` and `repo_checks.py` always run: 0.8 seconds together.
- CI ignores selection and runs everything. Selection is the cheap local tier, not the gate.
- Does it fit? Yes: the tests are 34 independent scripts, already keyed by area.

### 3.2 The admission test

A check enters only when it fails on a plausible defect that nothing else catches. In
practice, for a `new-check`:

1. The author names the defect as a change to the code under test: a condition inverted, a
   branch removed, a setting read from the wrong place.
2. The author makes that change, runs the new check and sees it fail, then restores the code.
   For a bug fix this is free: the new test must fail on the commit before the fix.
3. The line records it: `new-check: <test> fails when <defect>`.
4. The reviewer repeats step 2 for one new check per pull request, chosen by the reviewer.

Refused at review:
- a test that restates the implementation: it asserts a constant equals itself, or checks a
  stub returns what the stub was told to return;
- a test of someone else's code: the standard library, git, the client;
- a second test that fails on the same defect as an existing one: it becomes a row in the
  existing test's table, or is dropped;
- a test for text that only a person can judge (§The link, point 3).

Why this and not a coverage number: coverage rewards the tests the admission test refuses.
Does it fit? Yes, at a cost of about a minute per new check, and it applies to every
repository that installs the method.

### 3.3 The budget and its owner

In the style of the rule budget: one file owns the numbers, and a change that goes over raises
them in the same diff, where the reviewer and the maintainer see it.

| Budget | Value | Starts from | Owner | Enforced |
|---|---|---|---|---|
| Test files in the gate | 34 | 34 today | `tests/run_all.py` | Fails when `TESTS` is longer. |
| Suite time, Linux CI | 320 s | 312 s median | `tests/run_all.py` | Printed on every run; fails in CI on Linux above 1.5 times the budget (480 s). |
| One test file, local | 60 s | The slowest is 61 s; the median 10 s | `tests/run_all.py` | Printed; over budget is named in the summary line. |
| `REVIEW.md` | 12 items, 4,000 bytes | The 6,162 bytes of the skill that reads it: the list must cost less than its reader | `tests/repo_checks.py` | Fails when larger. |

The factor of 1.5 comes from the measured spread: the Linux job's p90 is 1.31 times its
median, so a limit at 1.5 does not fail on a slow runner. A time limit without that margin
would be a flaky check, which §3.5 forbids.

The rule for what may enter: a change that adds a test file, or takes the suite over its time,
does one of three things in the same change. It merges the new cases into an existing file,
or removes a check and says why that check can no longer fail on anything, or raises the
number with one line of reason. Adding cases to an existing file stays free while the time
holds, which is where most new checks should go.

Case counts are left out of the budget on purpose: the two test styles count differently
(§0), and a count that cannot be compared cannot be owned.

### 3.4 Tiers

| Tier | What | When | Today |
|---|---|---|---|
| Fast | Selected files (§3.1) | While working, before every push | Does not exist; the only local option is 7.8 minutes. |
| Full | All 34 files, three systems | CI, on every push of a pull request | Exists. |
| Live | `tests/skill_triggers.py`, `tests/installer.py --real` | By hand, after a description or installer change | Exists; spends tokens or touches the real clients. |

The article puts heavy tests before the commit (§2). Here the heavy tier is CI, because its
value is the two systems a session does not have: 19 of 21 failed runs failed on Windows only.

One change to the full tier is worth a measurement: the local run uses 386 CPU seconds in 469
seconds of wall clock on one core at a time, and the test files are independent processes.
Running them in parallel should cut the wait roughly by the number of cores. That is an
estimate; the follow-up issue measures it before anything is promised.

### 3.5 Flaky tests

Adopted from the article as written (§3, *Turn misses into rules*): a flaky test is not
skipped, given a sleep, or retried until green. Its cause is fixed, or the test is deleted
with the reason written in the commit. It lives in `AGENTS.md` §Test gate for this repository
and in the `verify` skill for the others; the core rule against weakening a test already
covers the principle. Nothing in §0 shows a flaky test today, and nothing could: no commit
was run twice.

### 3.6 When a miss becomes a check

The article's threshold (§3) matches this repository's rule for rules: seen at least twice,
and recognisable from a diff. What it becomes depends on what it is:

| The miss is | It becomes | Lives in |
|---|---|---|
| Mechanical, and a test can fail on it | A row in an existing test, through the admission test | `tests/` |
| Something that must hold every time | A hook or a permission rule | The guards plugin (`AGENTS.md` §Rule budget) |
| A matter of attention at review | An item in `REVIEW.md`: trigger, question, the two pull requests behind it | `REVIEW.md` on the default branch |
| Seen once | Nothing yet | |

One item already meets the threshold on the evidence of §0: 19 Windows-only failures on 14
branches, recognisable from a diff that adds or changes a script or a test that handles
paths, symlinks or child processes. The 41 findings comments are the source for further
items; reading them for patterns is a follow-up issue, and `REVIEW.md` starts with what that
finds, not with a list written in advance.

### 3.7 Pruning

Two triggers, so that it happens without anyone remembering.

- **The budget.** A change that hits it prunes first (§3.3).
- **A date.** The `DESIGN_DECISIONS.md` entry that records the budget carries
  `**Review by:**` three months ahead. `tests/repo_checks.py` already fails once such a date
  has passed, so the gate itself asks for the pruning pass.

The pass, one session: for each test file, the time it takes, when it last failed (CI, and
the local record of §5), and the defect it would catch that no other file catches. A file for
which no such defect can be shown is merged or removed. "Never failed" alone is not a reason
to remove: a guard's test that never fails is doing its work if a plausible defect makes it
fail. The pass also reads `REVIEW.md` and the instruction files against their budgets.

First candidates, from §0: `worktree_tools.py` (61 s, over the file budget, never failed in
CI) and the other seven files above 20 seconds.

### 3.8 What does not fit

| Idea | Why not here |
|---|---|
| A reliability checklist of 39 items | It rests on a history of incidents. This repository has no reverts and one pattern that meets the threshold. Start from the evidence, capped at 12. |
| A commit gate that looks for a review or verify step in the session | It needs the session transcript, which differs per client. The landing scripts see the same thing for both. |
| A stamp on every commit | §2.2. |
| A property-testing library | It would be this repository's first test dependency. Where a round trip exists (the verdict format, the settings tables), a seeded generator from the standard library in an existing test does the same; the differential test shows the pattern. |
| Running the base branch's tests against the change | §2.4. |
| A coverage target | §3.2. |

## 4. Test kinds per project type

The method is installed in other repositories. The `verify` skill carries this table as a
reference file, read when a repository's `## Verification` section is first written.

| Project | Fast tier | End-to-end | Property tests | Differential tests |
|---|---|---|---|---|
| Rules, skills and scripts (this one) | Selected test scripts | Already the norm: hooks fed real input, installer in a temporary home | Seeded generators for parsers and formats, no library | Guards against their previous version |
| Rust, including Bevy | `cargo fmt --check`; `cargo clippy --all-targets -- -D warnings`; `cargo test` for the changed crate | The application run headless for a fixed number of frames from a fixed seed: no panic, and a state the test can compare. A screenshot for what only eyes can judge, recorded as `seen` | `proptest` on pure logic: save and load round trips, invariants of the simulation (a count never negative), idempotent systems | Old against new across a refactor of the simulation: same seed, same inputs, same state after N steps |
| Python service or tool | Linter, type checker, tests of the changed package | The service started locally and called through its real interface | Hypothesis on parsers, serialisers and anything with an inverse | Old against new for a rewrite or a migration, on sampled inputs |
| Web application | Linter, type check, unit tests of the changed module | A browser flow per user journey, with the trace kept on failure | fast-check on reducers, formatters and validation | A visual or response comparison across a framework migration |

- **Clippy with warnings denied is part of the Rust gate,** in the fast tier, because it is
  exact, fast and not written by the author: the kind of check §The link ranks first.
- **End-to-end pays most where there is a running product** (article §2); it is the one test
  kind to have if there is only one.
- **Property tests pay where a statement holds for all inputs** and the input space is large.
  They do not share the author's bias (article §2), which is the weakness METR measures in
  self-made checks. They do not pay for glue code and configuration.
- **Differential tests pay during a rewrite and are removed after it.** A differential test
  against a version nobody runs any more is a pruning candidate by definition.
- A dependency a project does not have yet (proptest, Hypothesis) is asked for first, as the
  core rules say.

## 5. Measuring the checks

The article's measures (§3, *Test your checks on what actually matters*), cut to what one
maintainer's repository can keep up.

| Measure | Read from | Today |
|---|---|---|
| Merged changes reverted | `git log` | 0 of 344 commits |
| Changes stopped before merging | Findings verdicts per pull request | 41 rounds on 20 of 29 |
| A control set of clean changes | Reviewed pull requests with no findings and no later fix | 9 of 29 had no findings |
| What each stage caught | CI failures by test file and system; findings by review; local failures | CI and review known; local unknown |
| Cost per change | CI seconds, runs per pull request, review rounds | §0 |
| Misses | A fix whose pull request names the change that introduced the defect | Not recorded |

Three additions make this repeatable:

1. **A report script,** `tools/gate_report.py`, that prints the tables of §0 from `gh` and
   `git`. The queries written for this proposal are its first version. Run at each pruning
   pass, not on a schedule.
2. **A local failure record.** `run_all.py` appends one line per failing run (date, branch,
   failed files) to a file in the git directory, shared by all worktrees and never committed.
   It answers "has this test ever caught anything before a push", which today nobody can.
3. **A line on a fix:** `Missed by: <stage>` in the pull request body of a change that fixes a
   defect which landed earlier. It gives recall per stage (article §3) without an evaluation
   harness. A formal evaluation with replayed incidents, as the article describes, needs
   incidents; with no reverts it would be built on nothing.

What would show the gate is wrong: a `none` on a change that later needed a fix; a rise in
findings rounds after the gate; a suite time above budget twice in a row.

## 6. Budgets and constraints of this repository

Every proposed piece, where it lives and what it costs.

| Piece | Lives in | Cost | Merges |
|---|---|---|---|
| The rule itself | No new sentence in `rules/core.md` (7,721 of 8,000 bytes). "Report what happened" and "never weaken a test or a gate" already state it; the line makes them checkable. | 0 bytes | |
| The line's format | A script beside `review_verdict.py` in the core plugin, with a test added to `tests/review_verdict.py` | About 80 lines; no new test file | Automatically |
| The gate and its modes | `merge_pr.py`, `push_branch.py`, the row in `HANDOFF.md` §Landing settings | Milliseconds per landing; cases added to `tests/merge_pr.py` and `tests/push_branch.py` | On the maintainer's word (gate scripts) |
| Removed-checks signal, round limit | `merge_pr.py` | The same | On the maintainer's word |
| Selection, budgets, failure record | `tests/run_all.py`, checked in `tests/maint_tools.py` | About 60 lines | Automatically |
| The procedure | A core skill `verify`, or `ship-change` step 3 (question 3) | 2,500 + 300 bytes, or about 600 bytes | Automatically; `BODY_BUDGET` and `DESCRIPTIONS_BUDGET` raised in the same change |
| The reviewer's part | `review-change` step 3 and step 4 | About 400 bytes; its budget raised | Automatically |
| Flaky rule, admission rule, budget | `AGENTS.md` §Test gate, and a `DESIGN_DECISIONS.md` entry with the maintainer's words and a review date | About 900 bytes | On the maintainer's word |
| The checklist | `REVIEW.md`, at most 4,000 bytes | Read once per review | Automatically, unless it joins `EXCLUDED` (question 6) |
| The report | `tools/gate_report.py` | Run by hand | Automatically |

Held throughout: skills written once for both clients (nothing above is client-specific); a
plugin version raised with `tools/bump_version.py` in every change that touches a plugin; one
owner per fact (the line's format, the budgets and the trigger map each have exactly one);
no hook added, because nothing here must hold without exception: a landing without the line
ends at the maintainer, which is the right place for an exception.

The gate adds no test file. Every new case goes into an existing one, so the proposal stays
inside the budget it sets.

## 7. Open questions for the maintainer

1. **Per landing or per commit?** Recommendation: per landing (§2.2). Per commit records six
   times as much to prove the same.
2. **Is the file budget frozen at 34?** Recommendation: yes, and the time budget at 320
   seconds on Linux. The alternative is to prune first and freeze lower, which delays the gate
   for a pass whose result is not known.
3. **A new `verify` skill, or a longer step 3 in `ship-change`?** Recommendation: the new
   skill. Verification happens during the work, and `ship-change` is read at the end; at
   13,770 bytes it is also the core plugin's largest skill already. The price is 300 bytes of description
   in every session.
4. **Should removed checks wait for your word, or is the reviewer's finding enough?**
   Recommendation: your word. It costs you a decision only on pruning changes, which are yours
   anyway, and it closes the one place where a change can still weaken its own gate.
5. **Three findings rounds, or two?** Recommendation: three, as in the article. The core rule's
   two is for the same problem failing twice; findings rounds usually raise different
   problems. Three would have stopped 3 of 29 pull requests; two would have stopped 9.
6. **Does `REVIEW.md` merge only on your word?** Recommendation: no. It is read from the
   default branch, so a change cannot use its own version; a change that weakens it is visible
   in the diff the reviewer reads from the base's rules.
7. **Keep Windows in every CI run?** It is the slowest job, four times the Linux one, and
   19 of the 21 failed runs failed there alone. Recommendation: keep it, and shorten the wait by running the test files in
   parallel, after measuring. Dropping it to merges only would save 21 minutes per run and
   move every portability failure to after the review.

## 8. Rollout

| Stage | What changes | Ends when |
|---|---|---|
| 0 | This proposal. | You answer §7. |
| 1, observe | The line, its format script, the reviewer's item, `verification gate` set to `observe`. Selection, budgets printed and not failing, the local failure record. Nobody is refused. | 20 pull requests have landed with the gate observing. |
| 2, decide | `gate_report.py` over those 20: how many lines were missing, how many `none`, how many the reviewer disputed, what the suite time did. | You decide to enforce, to change, or to drop it. |
| 3, enforce here | `verification gate` set to `enforce`; the file and time budgets fail; removed checks and the round limit refuse automatic merges. The first pruning pass. | The first `Review by:` date. |
| 4, elsewhere | The `## Verification` section and the project table of §4 in the other repositories, one at a time, each starting in observe. | Per repository. |

If stage 2 shows the line is written by rote, with the same evidence on every change and no
disputes from the reviewer, the gate stops at observe and only the anti-bloat half (§3)
goes on. The two halves do not depend on each other.

## 9. Follow-up issues

Each is one session and one pull request. The first four are the gate; the others stand
alone and can wait for the data of stage 2.

| # | Issue | Touches | Merge |
|---|---|---|---|
| 1 | `run_all.py`: triggers and `--changed`, the file and time budgets (printing only), per-file times in the summary, the local failure record. | `tests/run_all.py`, `tests/maint_tools.py`, `HANDOFF.md` | Automatic |
| 2 | The `Verified:` line: the format script, `ship-change` step 4, the item in `review-change` step 4, the rules read from the base in step 3. | Core plugin scripts and two skills, `tests/review_verdict.py`, `tests/skills_format.py` | Automatic |
| 3 | The gate in observe mode: the `verification gate` row, the condition in `merge_pr.py` and `push_branch.py`. | Both scripts and their tests, `landing.py`, `HANDOFF.md` §Landing settings | Maintainer |
| 4 | The rules in `AGENTS.md` §Test gate (admission, flaky, budget) and the `DESIGN_DECISIONS.md` entry with the review date. | `AGENTS.md`, `DESIGN_DECISIONS.md` | Maintainer |
| 5 | `merge_pr.py`: removed checks and the third findings round refuse the automatic merge; `ship-change` step 8 says when to stop and hands earlier findings to a re-review. | `merge_pr.py`, its test, `ship-change` | Maintainer |
| 6 | `tools/gate_report.py`, from the queries of §0. | `tools/`, `tests/maint_tools.py` | Automatic |
| 7 | Read the 41 findings comments for patterns seen in two or more pull requests; write `REVIEW.md` from them and its size check. | `REVIEW.md`, `tests/repo_checks.py`, `review-change` | Automatic |
| 8 | The `verify` skill and the `## Verification` section in the `repo-docs` layout, with the project table of §4 as its reference file. | Core plugin, `tests/skills_format.py` | Automatic |
| 9 | Measure running the test files in parallel, locally and on the three CI systems; adopt it if the wait drops and nothing becomes order-dependent. | `tests/run_all.py` | Automatic |
| 10 | The first pruning pass: the eight files above 20 seconds, then the 21 that never failed in CI. | `tests/` | Maintainer (removed checks) |
| 11 | Turn the budgets from printing to failing and set the gate to `enforce`, after stage 2. | `tests/run_all.py`, `HANDOFF.md` | Maintainer |
