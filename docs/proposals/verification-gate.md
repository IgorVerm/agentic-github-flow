# Proposal: verification as part of the method, for every repository

Status: proposal for the maintainer, issue #146, third version. Nothing here is implemented.
The first version was written around this repository's own test suite; the maintainer sent it
back twice (rulings below). This version describes one way of working for every repository that
installs the method, and treats this repository as its first case, in
[Part C](#part-c-this-repository-as-the-first-case).

Sources: [the Claude Code article](../sources/2026-11-16-claude-code-verification.md) ("the
article") and [METR's Q4 2026 update](../sources/2026-11-20-metr-q4-capability-update.md)
("METR"). Section references are to those two documents. Measured on 2026-11-24 at `5c2a3b2`.

## Summary for the maintainer

**The method in one sentence.** Work starts from a goal that can be tested, the agent proves
the goal was met with a check it did not write for the occasion, and one line on the landing
records how.

**Why this shape.** METR finds agents strongest where the goal is clearly defined, cheap to
check and visible to the agent while it works, and weaker where they must judge without that
feedback or build their own yardstick (METR §3.A, §3.B.2, Appendix J). The article reaches the
same place from practice: the person's work becomes defining what done means and reviewing
the evidence (article, closing section). So the largest gain is not more tests. It is a
testable goal on every piece of work, set before the work starts.

**Five parts, the same in every repository.**

1. **A testable goal on the issue,** written before the work: the check that proves it done.
   Where no cheap check exists, the issue says so and names who judges.
2. **A `verify` skill** that holds the procedure, and a `## Verification` section in each
   repository's `HANDOFF.md` that holds that repository's facts: its fast command, its full
   command, how to run the product, and its critical systems, which an audit agent lists.
3. **One line per landing,** `Verified:`, naming the kind of evidence, or `none` with a
   reason. Checked by the reviewer and by the two landing scripts, starting in observe mode.
4. **A check made for an issue stays with that issue.** It proves the goal and is left
   behind. It joins the checks that run on every change only when it protects a critical
   system.
5. **No budget, in tests or in seconds.** What decides whether a check is kept is what it
   protects, not how many there are or how long they take. Time is measured and reported.

**What changed after your answers.** After the first round: one method for every
repository, with this repository moved to Part C. After the second round: the time limits are
gone as well, an audit agent lists the critical systems, checks written for an issue are not
carried forward unless they protect one, and this repository is pruned now, not on a date.

**Four questions are left,** in [§B.6](#b6-open-questions). Three of them are places where I
read more into your words than they say; each is marked where it occurs.

## The maintainer's rulings on the first version, 2026-11-24

Recorded here with his words; they move into `DESIGN_DECISIONS.md` with the first change that
implements them.

| Question | Ruling |
|---|---|
| 1. The line per landing or per commit | Per landing: "landing". |
| 2. A file budget frozen at 34 | **No.** "dit is niet logisch bij een groeiende codebase het systeem moet voor elk van onze repos werken niet puur gericht op deze repo deze repo legt onze algemene werkwijze vast" (this is not logical for a growing codebase; the system must work for each of our repositories, not only this one; this repository records our general way of working). |
| 3. A new `verify` skill | Agreed. |
| 4. Removed checks wait for the maintainer | Agreed: "testen die nooit falen en geen kritiek onderdeel beschermen zijn nutteloze fluf" (tests that never fail and protect no critical part are useless fluff). |
| 5. Stop after three findings rounds | Agreed. |
| 6. `REVIEW.md` merges without the maintainer's word | Agreed. |
| 7. Windows stays in every CI run of this repository | Agreed. |
| The proposal as a whole | "dit voorstel is te gericht op deze repo ik wil een algemene werkwijze gebaseerd op anthropics document en de vaststelling van METR dat agents beter scoren als ze duidelijke testbare doelen krijgen" (too focused on this repository; I want a general way of working based on Anthropic's document and METR's finding that agents score better when they get clear, testable goals). |

## The maintainer's rulings on the second version, 2026-11-24

His answers to the four questions of the second version, relayed word for word by the
overview chat: "1 time limit is geen goed criteria een vast amount of max tests ook niet 2 een
audit agent 3 nu snoeien en duurzaam systeem die zorgt dat we een een toetsbaar doel op de
issue vóór het werk begint maar dit hoeft niet mee genomen te worden naar volgende issues die
mogen achtergelaten worden tenzij ze kritische systemen beschermen 4 ja elke repo werkt op
deze manier."

| Question | Ruling, as read here |
|---|---|
| 1. Is 120 seconds the right limit for the fast check? | A time limit is not a good criterion, and neither is a fixed or maximum number of tests. Both are dropped (§B.4). |
| 2. Who lists a repository's critical paths? | An audit agent (§B.2). |
| 3. How long between pruning passes? | Prune now, and build a lasting system: a testable goal on the issue before the work starts; what was made to prove it need not be carried to later issues and may be left behind, unless it protects critical systems (§B.4). |
| 4. Does a repository without CI get the gate? | Yes: every repository works this way. |

# Part A. What the two sources establish

The issue stated one hypothesis about the article and four about METR. Each is checked here.

| Hypothesis | Verdict | Source |
|---|---|---|
| The article says verification loops make delegation and parallel agents safe: cheap checks first, end-to-end checks that are hard to fool, checks the change cannot modify, a person after three failed rounds. | **Confirmed,** all four. The article gives one measured result (up to 10 points from a separate grader) and no cost figures. | Article §1, §2 (*E2E tests*), §3 (*Changes cannot modify their own checks*, *Failing tests require human attention*) |
| Models do best where feedback is clear and automatic. | **Confirmed.** Strongest where the goal is clearly defined and cheap to check, and often visible to the agent. Caveats: top humans still win, only 3 tasks have human baselines, and such tasks resemble training environments. | METR §3.A, Appendices K and L, §1 |
| Models are weaker where verification is costly. | **Partly, with a correction.** Tasks with a higher lifecycle cost are somewhat harder (R² = 0.14; 13.8 points of success per doubling). But lifecycle cost is the cost of building, running and scoring a task, not the cost of verifying it, and progress is as fast on the costly half. The direct evidence is on judgment: without clear feedback, agents judged worse than experts, on 4 task families. | METR §3.B.1 and footnote 35, Appendix F, §3.B.2 |
| METR documents reward hacking. | **Confirmed, with a correction to the form.** The forms found are tailoring a solution to a guess of the hidden tests, searching for answers and brute force, not editing tests. After hardening that takes at least 10% of task-development effort, under 0.1% of runs still had to be scored zero. | METR Appendix G |
| Model judges overrate stronger models' work. | **Confirmed, narrower than stated.** Shown in one task setting, without a sample size, and for authors that are similarly strong or stronger. The best judge still scored about 0.2 of 1 too high. | METR §3.B.2, footnotes 46 and 47 |

One more finding belongs here. The article says verification loops are what allow dozens of
agents in parallel (article §1). METR tested groups of agents against independent agents with
the same token spend: fairly consistently better on one task, where every submission gets its
exact grade at once, and fairly consistently worse on two tasks where the score exists but is
not shown, because agents fixed on a metric of their own and never checked it against the
real one (METR Appendix J; small experiments, no effect sizes in the text).

**Six principles the method is built on.** Each is used in Part B.

| # | Principle | Rests on |
|---|---|---|
| P1 | **Give the agent a goal it can test.** Defined before the work, cheap to check, and visible while working. | METR §3.A; article, closing section |
| P2 | **The check comes from outside the change.** A yardstick the author makes for the occasion can only confirm what the author already believed, and agents tailor their work to the check they expect. | METR Appendix J, Appendix G (tailoring to guessed tests); article §3 (*Changes cannot modify their own checks*) |
| P3 | **Prefer checks that are hard to fool:** the running product end to end, a property over generated inputs, the old system as oracle. | Article §2 |
| P4 | **Where no cheap check exists, say so and send it to a person.** Do not invent a metric. A model judge of the same strength is a weak judge. | METR §3.B.2 (one task setting), Appendix J |
| P5 | **Stop at a fixed number of failed rounds.** Gaming is more likely when the agent is at the limit of its ability. | Article §3 (*Failing tests require human attention*); METR Appendix G |
| P6 | **Checks only grow unless they are pruned, and a slow or flaky check gets run less or rerun, not fixed.** | Article §2, §3 (*Turn misses into rules*) |

What the sources do not give: any number for what a check costs, or any rule for which
checks to keep and which to remove. That part of the method (§B.4) follows the maintainer's
rulings, argued from the measurements in Part C.

# Part B. The method, for every repository

## B.1 A testable goal before the work

The method already asks for this in three places, as text: the core rule on long work (write
down the end state and the command that proves it), the `open-issue` skill (an issue body
holds the check that proves it fixed) and `spec-first` (the end-to-end check that proves the
whole). The proposal makes it the first step of verification and gives it a form.

Every issue an agent picks up has a `Check:` that is one of three kinds:

| Kind of goal | The issue's check says | What the agent does first |
|---|---|---|
| **Testable now** | A command and the result that counts as done, or a user flow and what must be observed. | Makes the check fail for the right reason before changing the code: the failing test for a bug, the flow that does not work yet for a feature. Then works until it passes. |
| **Testable with a harness** | What must be observable, and that the harness to observe it is part of the work. | Builds or extends the harness first (P3: end to end, property, differential), has it fail, then works. |
| **A matter of judgment** | That no cheap check exists, and who judges: the maintainer, or a named reader. | Does the work and hands over the evidence a person needs: a screenshot, a rendered page, the text itself. Does not write a test to stand in for the judgment (P4). |

- The check is written by whoever writes the issue, not by the agent that does the work (P2).
  When the agent finds the check wrong or untestable, it says so on the issue and waits or
  continues under a stated assumption, as the core rules already say.
- An issue without a usable check is not ready: `open-issue` and `requirements` already carry
  the field, and the ready label means it is filled in.
- This is where METR's finding pays most. The agent gets what METR's strong tasks have: a
  defined goal, a cheap check, a score it can see while working.

## B.2 The `verify` skill and the `## Verification` section

**The skill** (core plugin, written once for both clients) holds the procedure:

1. Read the issue's check and the repository's `## Verification` section, from the default
   branch.
2. Decide the kind of evidence this change needs (§B.3). Proportion is the rule: a
   documentation change needs none, a change to a critical system needs the full check.
3. Run the fast check while working and before every push. Fix what fails; after two failed
   corrections of the same problem, stop (the existing core rule).
4. Decide what happens to a check made for this issue: left behind, or kept as a standing
   check because it protects a critical system (§B.4).
5. Write the `Verified:` line.

**The section** in each repository's `HANDOFF.md` holds the facts, in the same table form as
`## Landing settings`. The landing scripts read it from the default branch, so a change
cannot rewrite the rules it is judged by (P2). It joins the sections `merge_pr.py` guards
(today `Standing permissions` and `Landing settings`): a change to it never merges
automatically, or one change could narrow `critical paths` or switch the gate off and the
next remove checks unseen.

| Setting | Meaning | Example: Rust and Bevy | Example: this repository |
|---|---|---|---|
| `fast` | The command for the cheap check. It takes the changed paths or selects by itself. | `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test -p <changed crates>` | `python3 tests/run_all.py --changed` |
| `full` | The command for everything. | `cargo test --workspace` and the headless run | `python3 tests/run_all.py` |
| `drive` | How to start the product and look at it, or the project skill or script that does. | The game run headless for N frames from a fixed seed; a screenshot command | none: the tests already run the real hooks, installer and scripts |
| `check paths` | Where checks live, as patterns. | `**/tests/**`, `**/*_test.rs` | `tests/**` |
| `critical paths` | The critical systems, as path patterns: the parts whose checks are kept. Listed by an audit agent. | Save-game format, the simulation core | a first guess until the audit: the guards, the merge and push gates, the pre-push hook, the installer (Part C) |
| `verification gate` | `off`, `observe` or `enforce`; `off` when missing. | `observe` | `observe` |

A project with a heavy harness (a game, a mobile app) keeps it as its own skill or script and
names it under `drive`; the article's advice to put a `verify` skill next to the code (§3)
is kept in that form. Every repository that installs the method gets the section (ruling 4
of the second round); one without CI runs `full` before the landing, as `ship-change`
already requires in local-main mode.

**The audit agent** lists the critical systems. It is a session with a fresh context that
reads the repository, not the history of one change, and answers one question per part of
the code: if this broke unnoticed, what would be lost that cannot be taken back or would
stop the work (data, money, security, a release, the method's own gates)? It writes the
list with one line of reason per entry as a change to the section. It runs when the section
is first written, and again at each `Review by:` date. An agent that is working on a change
never edits the list for that change (P2).

**One script, `verify.py`, in the core plugin,** is the instrument that makes this the same
everywhere: `verify.py fast` and `verify.py full` read the section from the default branch,
run the command, time it, and append one line to a record in the git
directory (date, branch, command, seconds, passed or what failed). The record is local,
shared by all worktrees, never committed. It gives every repository the two measurements
this repository lacked: how long the checks take per change, and which checks ever caught
something before a push.

## B.3 One line per landing, and the gate

```
Verified: <kind>: <evidence>
```

| Kind | Meaning | Example of evidence |
|---|---|---|
| `goal` | The issue's check was run and met. | `the check of #212: cargo test -p sim save_roundtrip, passes; failed before the fix` |
| `tests` | Existing checks ran and passed. | `verify.py fast, 71 s` |
| `standing-check` | A check was added to those that run on every change, for a critical system; names the defect it fails on. | `save_roundtrip fails when the version field is dropped` |
| `run` | The product or tool was run and its behaviour observed. | `headless run, 600 frames, seed 7, no panic` |
| `seen` | A screenshot or rendered result was looked at; a person may need to judge. | `screenshot of the settings page at 375 px` |
| `none` | Nothing to run. The reason is required. | `documentation only` |

More than one kind may be given, separated by `;`. The line goes in the pull request body, or
in the landing comment in local-main mode. Its format has one owner, a small script beside
`review_verdict.py`.

**Per landing, not per commit** (ruling 1). In this repository that is 55 records in 30 days
against 344, proving the same thing. The article's reason for a stamp, being able to find
what was not verified, is kept: `none` is a valid, searchable value.

**Where each check runs.**

| Stage | What | Enforced by |
|---|---|---|
| Before the work | The issue has a check of one of the three kinds. | `open-issue`, `requirements`; the ready label. |
| While working | `verify.py fast`. | The `verify` skill. |
| Before the push | The line exists and parses. | `push_branch.py`, next to its overlap condition. |
| CI, where the repository has it | The `full` command. | The repository's own workflow. |
| Review | The line against the diff: the evidence is real (a cheap command is rerun), it fits the size of the change, the issue's check is the one that was met, a `standing-check` protects a critical system and passes the admission test. | `review-change`. |
| Merge | The line exists; the round limit; removed checks (below). | `merge_pr.py`. |

**The modes** (article §3, *Start a new gate in observe mode*). Observe reports what would
have been refused and refuses nothing, so false refusals are seen first. Enforce refuses the
unasked push and the automatic merge; the landing then waits for a person, as it does today
for a protected path. It never blocks the maintainer, so the article's escape after two
blocks is not needed.

**Three rounds, then a person** (ruling 5, P5). `merge_pr.py` counts the findings verdicts it
already parses and refuses the automatic merge after the third; `ship-change` says to stop
there and report. A re-review is handed the earlier findings and reads the commits since
(article §3, *One reviewer, multiple rounds*). No second model reviewer is stacked on the
first (P4).

**Rules come from the default branch** (P2). The reviewer reads `AGENTS.md`, `HANDOFF.md` and
`REVIEW.md` with `git show origin/<base>:<file>`. `REVIEW.md` is the repository's checklist
for the reviewer: items with a trigger readable from a diff, a question, and the two pull
requests behind it. An item enters only when the pattern was seen in at least two pull
requests and can be recognised from a diff (article §3, *Turn misses into rules*), which is
also this repository's rule for rules. It merges without the maintainer's word (ruling 6).

**Removed checks wait for the maintainer** (ruling 4). `merge_pr.py` refuses the automatic
merge when a change deletes a file under `check paths`, or removes more test definitions
from any one file than it adds there (a default pattern covers `def test_`, `#[test]`, `it(` and `test(`; a
repository may set its own). The maintainer then decides, which is right for pruning and
costs a minute for the rare change that only moves a check.

**Not proposed: a hook that runs the checks when the agent finishes** (the article's
suggestion, §3). It would be a second place that decides what runs, per client, in a plugin
whose every change waits for the maintainer. The line checked at the push gives the same
guarantee. Worth another look once `fast` is quick everywhere.

## B.4 Which checks are kept

The request was a system that decides which checks run, how many exist and when they go. The
first version answered with a fixed count and the second with time limits. The maintainer
rejected both: neither a number of tests nor a number of seconds says whether a check is
worth having. The criterion is what a check protects.

Issue #146 asked for concrete budgets with an owner each. These rulings replace that
requirement: the measured numbers stay in Part C as what is reported, and no number is a
gate.

**1. Two kinds of check, with different lifetimes.**

| | A task check | A standing check |
|---|---|---|
| Made for | One issue: it shows that issue's goal was met (§B.1). | A critical system: it shows that system still works after any change. |
| Lives | Until the issue lands. It is left behind: not added to the `full` command, which is all "left behind" means. Until the landing the reviewer must be able to rerun it: its command is in the pull request body, or its script is committed with the change in a folder the section names outside `check paths`. The `Verified:` line records what was run and what it showed. | In the repository, under `check paths`, run by `fast` when its trigger matches and by `full` always. |
| May be | Quick and specific: a script, a one-off command, a failing-then-passing test, a screenshot. | Only what passes the admission test below. |
| Count and time | Not limited. | Not limited. They are measured and reported (§B.5), never a reason by themselves to refuse or to remove a check. |

This is what keeps the method lasting. The agent always works against a testable goal, which
is where METR finds agents strongest (P1), and the set of checks that every later change
must pay for grows only when a critical system gains protection.

**2. Which checks run on a change: only what the change touches.** The `fast` command
selects by changed paths: the changed crate, the changed package, the test files whose
trigger matches. A path the selection does not know runs everything, so selection can cost
speed and never a check. This is the article's checklist with triggers (§3) applied to
tests, and the core rule *Work grows with what changed* applied to the gate itself.

**3. What may become a standing check: the admission test.** Two conditions.

- It protects a path under `critical paths`.
- It fails on a plausible defect that nothing else catches, and the author shows it: names
  the defect as a change to the code (a condition inverted, a branch removed, a value read
  from the wrong place), makes that change, sees the check fail, restores the code. For a
  bug fix this is free: the check must fail on the commit before the fix. The line records
  it, `standing-check: <test> fails when <defect>`, and the reviewer repeats it for one new
  check per pull request, of the reviewer's choice.

Refused at review: a check outside the critical systems offered as a standing check (my
reading of "may be left behind" as "is left behind"; question 2 of §B.6); a test
that restates the implementation (it asserts a constant equals itself, or that a stub
returns what it was told to return); a test of someone else's code; a second test that fails
on the same defect as an existing one (it becomes a case of that one); a test that stands in
for a judgment (P4). No coverage target: coverage rewards exactly the tests this refuses.

**4. Which standing checks go: the pruning rule.** From the two rulings together; the second
bullet is my reading, since the second ruling alone would drop such a check (question 3 of
§B.6). A standing
check is kept when either holds:

- it protects a path under `critical paths`, and a named defect still makes it fail; or
- it has failed on record, in CI or in the local record of `verify.py`: it has caught
  something, so it is not the "useless fluff" of the first ruling.

Every other standing check is removed. A removed check is recorded with its reason in the
commit, and the change waits for the maintainer (§B.3).

**5. When pruning happens.** Now, as the first step in every repository that adopts the
method: the audit agent lists the critical systems, and one pruning pass applies the rule
to the checks that exist. After that the system holds by construction, because new checks
enter only through the admission test. The audit is repeated at a `**Review by:**` date,
which the maintainer sets when the section merges, on
the repository's `DESIGN_DECISIONS.md` entry for its verification settings, because what is
critical changes as a product grows; a pruning pass follows only if the list changed.

**6. Flaky checks** (article §3). Not skipped, not given a sleep, not retried until green.
The cause is fixed, or the check is deleted with the reason written down.

**7. When a miss becomes a check.** Seen at least twice and recognisable from a diff:

| The miss is | It becomes |
|---|---|
| Mechanical, in a critical system, and a test can fail on it | A case in an existing standing check, through the admission test |
| Mechanical, elsewhere | An item in `REVIEW.md`; no standing check (question 2 of §B.6) |
| Something that must hold every time | A hook or a permission rule, not a sentence |
| A matter of attention at review | An item in `REVIEW.md` |
| Seen once | Nothing yet |

**What does not fit, and why.**

| From the article | Why not in the method |
|---|---|
| A reliability checklist of 39 items | It rests on a history of incidents. A repository starts `REVIEW.md` from its own evidence, however short. |
| A commit gate that looks for a review or verify step in the session | It needs the session transcript, which differs per client. The landing scripts see the same thing for both. |
| A stamp on every commit | Ruling 1. |
| A formal evaluation with replayed incidents | It needs incidents. `Missed by:` (§B.5) is the cheap version until a repository has them. |

## B.5 Test kinds per project type, and measuring

The `verify` skill carries this table as a reference file, read when a repository's
`## Verification` section is first written.

| Project | Fast | End to end (`drive`) | Property tests | Differential tests |
|---|---|---|---|---|
| Rust, including Bevy | `cargo fmt --check`; `cargo clippy --all-targets -- -D warnings`; `cargo test` for the changed crates | The application run headless for a fixed number of frames from a fixed seed: no panic, and a state the test can compare. A screenshot for what only eyes can judge, recorded as `seen` | `proptest` on pure logic: save and load round trips, invariants of the simulation, idempotent systems | Old against new across a refactor of the simulation: same seed, same inputs, same state after N steps |
| Python service or tool | Linter, type checker, tests of the changed package | The service started locally and called through its real interface | Hypothesis on parsers, serialisers, anything with an inverse | Old against new for a rewrite or migration, on sampled inputs |
| Web application | Linter, type check, unit tests of the changed module | A browser flow per user journey, with the trace kept on failure | fast-check on reducers, formatters, validation | A visual or response comparison across a framework migration |
| Rules, skills and scripts | The test scripts whose trigger matches | Hooks fed the input the client sends; the installer in a temporary home | Seeded generators from the standard library | A guard against its previous version |

- **Clippy with warnings denied is in the Rust fast check:** exact, fast and not written by
  the author, the kind of check P1 and P2 rank first.
- **End to end pays most where there is a running product,** and is the one kind to have if
  there is only one (article §2).
- **Property tests pay where a statement holds for all inputs.** Their inputs do not share
  the author's bias (article §2), the weakness METR observes in self-made checks.
- **Differential tests pay during a rewrite and are pruned after it.**
- A dependency a project does not have yet is asked for first, as the core rules say.

**Measuring the checks** (article §3, *Test your checks on what actually matters*), cut to
what a small team can keep up. One report script in the core plugin reads `git`, `gh` and
the local record, and prints for any repository:

| Measure | Read from |
|---|---|
| Merged changes reverted | `git log` |
| Changes stopped before merging | Findings verdicts per pull request |
| A control set | Reviewed pull requests with no findings and no later fix |
| What each stage caught | The local record, CI failures by check, findings |
| Cost per change | Fast and full seconds, CI runs per pull request, review rounds: reported, not limited |
| Misses, per stage | A line `Missed by: <stage>` in the body of a change that fixes a defect which landed earlier |
| The `Verified:` kinds | How many `goal`, `tests`, `none`; how many the reviewer disputed |

What would show the method is wrong: a `none` on a change that later needed a fix; findings
rounds rising after the gate; issues whose check was rewritten by the agent that did the
work; the same evidence text on every landing.

## B.6 Open questions

1. **Does the audit agent's list take effect without the maintainer's word?** The section is
   guarded (§B.2), so today a change to it waits for the maintainer at the merge. That keeps
   a working agent from narrowing the list for its own change, and the maintainer sees the
   audit's result once per repository and at each review date, without compiling it.
   Recommendation: keep the guard.
2. **"May be left behind", or "is left behind"?** Your words say a check made for an issue
   need not be carried along and may be left behind unless it protects critical systems. The
   proposal reads that strictly: a check outside the critical systems does not become a
   standing check at all. The looser reading lets the author keep one when it seems useful.
   Recommendation: the strict reading, because "when it seems useful" is how this
   repository went from 12 to 34 test files in a month.
3. **Does a check that once caught something stay, although it protects nothing critical?**
   Your first ruling called useless the tests that never fail and protect no critical part;
   your second lets everything outside the critical systems go. The proposal keeps a
   standing check that has failed on record. That is uneven with question 2: an old check of
   that kind stays, a new one cannot enter. Recommendation: keep them at this first pruning
   pass, since the record shows they did work, and let the next audit decide whether what
   they protect is critical after all.
4. **Where does a task check live until the landing?** The reviewer must be able to rerun it
   (§B.3), so it cannot exist only in the author's session. The proposal offers the command
   in the pull request body, or a script committed with the change outside `check paths`.
   Your words say nothing about committing. Recommendation: the body for a command, a
   committed script only when a command does not fit; such scripts are never run by `full`.

# Part C. This repository as the first case

The measurements that led to the method, and the values this repository would start with.
All numbers are from 2026-11-24: a local run of `python3 tests/run_all.py` on macOS inside
the client's sandbox, `gh run list` and the job records of all 176 runs of the `ci`
workflow, the logs of the 23 failed jobs, `gh pr list` with comments for all 55 pull
requests, and `git log`. The token figure is the usage the client reported for the reviewing
subagent.

## C.1 Measurements

**Size.**

| | |
|---|---|
| Test files in the gate (`TESTS` in `tests/run_all.py`) | 34 |
| Lines in `tests/*.py`, helpers included | 13,905 |
| `unittest` methods (`def test_`) | 486, in 20 files |
| Files with their own case tables | 14 (their cases are not counted the same way; `sandbox_network_guard.py` reports 260, `git_guard.py` 235) |
| Test files on 2026-10-25 | 12 |
| Test files ever removed | 0 |
| Revert commits in 344 commits | 0 |

**Runtime.**

| | Seconds |
|---|---|
| Local run, macOS, wall clock (33 passed, 1 skipped for the sandbox) | 469 |
| of which CPU (user + system) | 386 |
| CI test step, Linux, median of the last 30 runs in which it passed | 312 (first 30 runs: 60) |
| CI test step, macOS | 627 (first 30: 128) |
| CI test step, Windows | 1,253 (first 30: 292) |
| CI job p90 over median, Linux, 175 runs | 1.31 |
| CI wall clock per run, median of the last 30 runs of any outcome | 1,243 (the Windows job) |
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
| Test files that failed in CI at least once | 13 of 34: `archive_guard.py` (5 jobs), `audit_dependencies.py` (5), `codex_tools.py` (4), `skills_format.py` (3), and once each `codex_worker.py`, `delete_guard.py`, `git_guard.py`, `landing.py`, `merge_guard.py`, `personal_data_guard.py`, `question_label.py`, `repo_checks.py`, `sandbox_network_guard.py` |
| Test files that never failed in CI | The other 21, taking 309 of the 469 local seconds |
| Same commit run twice with different results | 0 (no commit was run twice, so flakiness cannot be read from CI) |
| Pull requests with a review verdict | 29 of 55 |
| Review verdicts | 37 approvals, 41 findings rounds |
| Reviewed pull requests with at least one findings round | 20 of 29 |
| Reviewed pull requests with three or more findings rounds | 3 (4, 5 and 9 rounds); with two or more, 9 |
| Merged pull requests that touched `tests/` | 42 of 52 |

**Cost per change.** A pull request has 2.2 CI runs on average (123 runs on 55 branches,
median 2), so it waits about 46 minutes on CI and uses about 81 job-minutes. A local full run
costs 7.8 minutes. The suite's output is 3,014 characters, roughly 750 tokens (an estimate
from the character count). One review round was measured: the first review of this
proposal's pull request, 184,566 tokens in 7 minutes.

**What the numbers say.**
- The review is the stage that catches most: findings on 20 of 29 reviewed pull requests.
- CI earns its cost as the portability check: 19 of 21 failed runs failed on Windows only.
- The suite grew fivefold in time in 30 days and nothing was ever removed. That is P6,
  measured.
- 21 files never failed in CI and take two thirds of the time. By the pruning rule a file
  among them stays only if it protects a critical system; the 13 that failed in CI stay as
  checks that have caught something. Failures before a push leave no record yet, so "never
  failed" here means never in CI; the audit and the pruning pass (Part D) settle each file.

## C.2 Inventory against the article

| Practice in the article (§3 unless noted) | Here today | Under the method |
|---|---|---|
| A goal defined before the work (closing section) | The core rule on long work, `open-issue`, `spec-first`: as text. | §B.1: three kinds of check on the issue. |
| Verification means running the change | Most tests already run the real thing: hooks get the JSON the client sends, the installer runs in temporary homes, scripts run against real git repositories. | No new test kind needed here. |
| A `verify` skill per repository | `HANDOFF.md` §Build, test, run names commands; `ship-change` step 3 says to run them. | §B.2. |
| Cheap checks before a pull request | Text in `ship-change` step 3; the only local option takes 7.8 minutes. | `fast`, with selection. |
| Stop after three failed rounds | Core rule: two failed corrections of the same problem. Review rounds have no limit; three pull requests had 4, 5 and 9. | §B.3. |
| A checklist triggered by the diff | A table for readers in `HANDOFF.md` §What to read for which work. | Triggers in `tests/run_all.py`; `REVIEW.md`. |
| Rounds that build on each other | A re-review reads only the new commits when the head moved, without the earlier findings. | §B.3. |
| Rules read from the default branch | `merge_pr.py` and `templates/pre-push` read their settings from the default branch. `review-change` step 3 does not say from which commit it reads. | §B.3. |
| Changes cannot modify their own checks | Strong for the gate itself: `merge_pr.py` runs from the installed plugin and holds rules, guards, hooks, CI and its own files for the maintainer (`EXCLUDED`), including the gate scripts' tests by name. Not for the other tests: CI runs the pull request's tests, so a change can remove one and merge automatically if the reviewer misses it. | Removed checks wait for the maintainer. |
| A review belongs to one commit | `review_verdict.py` pins the verdict to a SHA. | Exists. |
| A stamp and a gate with three modes | Body lines `Overlap check:` and `Efficient design:`; `merge_pr.py` refuses without the first. | The `Verified:` line and the gate row. |
| Review the reviewers | Nothing; C.1 was collected by hand. | The report script. |
| Flaky tests: fix or delete | Core rule against weakening a test; nothing on sleeps, retries, deleting. | §B.4. |
| Pruning on a routine | Budgets for rules and skills; nothing for tests. | §B.4: pruned now, then kept small by the admission test. |
| Property and differential tests (§2) | One differential test, `tests/delete_guard_differential.py`, over 38,364 generated commands. Standard library only. | Enough; no library added. |

## C.3 This repository's values

| Setting | Value | From |
|---|---|---|
| `fast` | `python3 tests/run_all.py --changed`: each entry of `TESTS` gets the path patterns that trigger it; `skills_format.py` and `repo_checks.py` always run (0.8 s together) | The reader's table in `HANDOFF.md`, made usable by a script |
| `full` | `python3 tests/run_all.py`, in CI on three systems | Today |
| `critical paths` | For the audit agent to decide. A first guess, from the paths `merge_pr.py` already holds for the maintainer's word: `plugins/guards/**`, `plugins/core/scripts/merge_pr.py`, `push_branch.py`, `push_paths.py`, `landing.py`, `review_verdict.py`, `templates/pre-push`, `tools/installer.py`, `install.sh`, `install.ps1` | `EXCLUDED` in `merge_pr.py` |
| Windows in every CI run | Kept (ruling 7) | 19 of 21 failed runs |
| First `REVIEW.md` item | A script or test that handles paths, symlinks or child processes: does it hold on Windows? | 19 Windows-only failures on 14 branches |
| The pruning pass, now | By the rule of §B.4, after the audit. On the first guess above, the test files outside the critical paths that never failed in CI are the ones to go or to shrink; the eight files above 20 seconds are looked at first | C.1 |

Time is no longer a criterion, and it is still worth knowing: the local run uses 386 CPU
seconds in 469 seconds of wall clock, one file at a time, and the files are independent
processes. Running them in parallel may shorten the 21-minute wait; how much is not known
until it is tried, and the pruning pass may make it unnecessary.

## C.4 Constraints of this repository

| Piece | Lives in | Cost | Merges |
|---|---|---|---|
| The rule itself | No new sentence in `rules/core.md` (7,721 of 8,000 bytes); the rules on long work, on reporting and on not weakening a test already state it | 0 bytes | |
| The procedure | The core skill `verify`, with the project table as a reference file | About 2,500 bytes of body and 300 of description, the latter in every session; `DESCRIPTIONS_BUDGET` stands at 5,645 of 5,645 and is raised in the same change | Automatically |
| The goal on the issue | `open-issue`, `requirements`, `spec-first`: the three kinds of check | About 300 bytes each; budgets raised | Automatically |
| The section | `repo-docs` (layout and skeleton), each repository's `HANDOFF.md` | One table | The layout automatically; a repository's own section on the maintainer's word, as a guarded section |
| `verify.py`, the line's format, the report | Core plugin `scripts/`, with tests | Three scripts | Automatically, except a test added to `tests/review_verdict.py`, which `EXCLUDED` matches |
| The gate, removed checks, the round limit | `merge_pr.py`, `push_branch.py`, `landing.py` | Milliseconds per landing | On the maintainer's word |
| The reviewer's part | `review-change` steps 3 and 4, `ship-change` steps 3, 4 and 8 | About 400 bytes each; budgets raised | Automatically |
| The two kinds of check, admission, pruning, flaky rule | The `verify` skill for every repository; `AGENTS.md` §Test gate and a `DESIGN_DECISIONS.md` entry here | About 900 bytes | On the maintainer's word |

Held throughout: skills written once for both clients; a plugin version raised with
`tools/bump_version.py` in every change that touches a plugin; one owner per fact (the
line's format, the section's settings and the trigger map each have one); no hook added,
because a landing without the line ends at the maintainer, which is the right place for an
exception.

# Part D. Rollout and follow-up issues

| Stage | What changes | Ends when |
|---|---|---|
| 0 | This proposal. | The maintainer approves it. |
| 1, the method | The `verify` skill, the section, `verify.py`, the line, the goal on the issue. No gate yet. | Merged. |
| 2, audit and prune here | The audit agent lists this repository's critical systems; the section is written; one pruning pass applies the rule. | The maintainer has merged both. |
| 3, observe here | `verification gate` set to `observe` in this repository. Nobody is refused. | 20 pull requests have landed. |
| 4, decide | The report over those 20: lines missing, how many `none`, how many disputed, how many standing checks were added and for what. | The maintainer decides to enforce, change or drop. |
| 5, enforce here | Removed checks and the round limit refuse automatic merges. | The first `Review by:` date. |
| 6, every other repository | The same order in each: the audit, the section, a pruning pass, observe. The Rust and Bevy repositories first, since clippy gives them a fast check from the first day. | Per repository. |

If stage 4 shows the line is written by rote, the gate stops at observe and the rest goes
on: the testable goal (§B.1) and the rule for which checks are kept (§B.4) do not depend on
it.

Each issue below is one session and one pull request.

| # | Issue | Touches | Merge |
|---|---|---|---|
| 1 | The `verify` skill with its project table, and the `## Verification` section in the `repo-docs` layout and skeleton. | Core plugin, `tests/skills_format.py` | Automatic |
| 2 | The goal on the issue: the three kinds of check in `open-issue`, `requirements` and `spec-first`. | Three skills | Automatic |
| 3 | `verify.py`: read the section from the default branch, run `fast` or `full`, time it, write the local record. | Core plugin `scripts/`, a test | Automatic |
| 4 | The `Verified:` line: the format script, `ship-change` step 4, `review-change` steps 3 and 4 (rules read from the base, the line checked, a standing check held to the admission test). | Core plugin, `tests/review_verdict.py` | Maintainer (`EXCLUDED` matches that test) |
| 5 | The gate in observe mode: the row, the condition in `merge_pr.py` and `push_branch.py`, and `Verification` added to the guarded sections. | Both scripts, `landing.py`, their tests | Maintainer |
| 6 | Removed checks and the third findings round refuse the automatic merge; `ship-change` step 8 stops there and hands earlier findings to a re-review. | `merge_pr.py`, its test, `ship-change` | Maintainer |
| 7 | The audit of this repository: an audit agent lists the critical systems with a reason each; the section is written with them, with triggers and `--changed` in `tests/run_all.py`, `AGENTS.md` §Test gate, and the `DESIGN_DECISIONS.md` entry with both rounds of rulings and a review date. | `tests/run_all.py`, `HANDOFF.md`, `AGENTS.md`, `DESIGN_DECISIONS.md` | Maintainer |
| 8 | The report script. | Core plugin `scripts/`, a test | Automatic |
| 9 | Read the 41 findings comments for patterns seen in two or more pull requests; write this repository's `REVIEW.md`. | `REVIEW.md`, `review-change` | Automatic |
| 10 | The pruning pass here, now: the rule of §B.4 applied to the 34 test files, each removal with its reason. Right after issue 7. | `tests/` | Maintainer |
| 11 | After stage 4 and the maintainer's decision: the gate set to `enforce` here. Optional, if the wait still matters after pruning: measure running the test files in parallel. | `HANDOFF.md`, `tests/run_all.py` | Maintainer |
| 12 | The first Rust and Bevy repository: the audit, the section, a pruning pass, observe mode. | That repository | Its own landing mode |
