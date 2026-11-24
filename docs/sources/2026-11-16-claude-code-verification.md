# Source note: How the Claude Code team thinks about verification

| | |
|---|---|
| Title | How the Claude Code team thinks about verification |
| Author | Addy Osmani (claude.dev blog, category Engineering) |
| Published | 2026-11-16 |
| URL | https://claude.dev/blog/how-the-claude-code-team-thinks-about-verification/ |
| Read | 2026-11-24, for issue #146 |
| How | Downloaded with `curl` (106,150 characters of HTML, SHA-256 starting `66c9a29cc8b7cffa`), converted to plain text locally (15,412 characters, 193 lines). |
| Ranges read | Characters 0 to 15,412 of the converted text: everything, including the page chrome and the list of related posts. |
| Passes | One, by the session that wrote this note, without a subagent. The two figures are images; their alt text was read, the pictures were not. |

This note paraphrases. The article is not copied here; read it at the URL. Section names below
are the article's own headings, shortened to §1 (the introduction), §2 (three test kinds) and
§3 (the team's practice, with its nine subsections).

## What the article claims

**§1 Introduction.**
- About 90% of the team's code is written and reviewed by the model, so how an agent proves its
  work decides how much can be delegated. Without a verification loop a person can supervise one
  or two agents, because everything is checked by hand; with one, many can run in parallel.
- One measured result: in internal tests on structured file generation, a separate grader
  checking against a rubric raised task success by up to 10 points over a plain prompting
  loop, most on the hardest problems. No sample size or task count is given.
- Checks are cheap to ask an agent for, and once written they run as software, without many
  further tokens.
- A check that keeps failing for the same reason is turned into a hook or a more explicit rule,
  which stops most repeats, not all.

**§2 Three test kinds worth the investment.**
- Two failure modes before any kind: a flaky test teaches the agent to rerun, not to fix; a
  slow test gets run less often, which makes a failure harder to place. Heavy tests belong
  before the commit.
- **End-to-end** is the one to pick if only one is affordable: a whole user flow either works
  or does not, so it is hard to fool, and its failure can show the step that broke. A unit test
  is faster and steadier, but it can pass while the feature is broken, because neither the
  agent nor the test sees the whole task. The agent needs a way to start, drive and inspect the
  running system; a feature map written from the user's side can serve as the rubric.
- **Property tests** state something that must always hold (round trip, invariant, idempotency,
  equivalence with a naive version) and let a library generate thousands of inputs against it:
  fast-check, Hypothesis, proptest. Their value against agents: the inputs do not share the
  bias of the agent that wrote the code. Also useful for rewrites where the specification no
  longer matches production.
- **Differential tests** run the old and the new system on the same generated or sampled
  inputs; the old system is the oracle. They need normalisation of irrelevant differences and a
  list of approved differences.

**§3 The team's practice.**
- *Verification means running the change.* Running the application end to end counts for more
  than tests. A repository holds one or more skills named `verify`, close to the code they
  cover, that say how to start and drive the application; the agent uses them before
  committing. The skill is a smoke-test harness and is itself made fast and reliable.
- *Failing tests require human attention.* The agent runs the checks and tries to fix failures;
  a check still failing after three rounds stops the agent and brings in a person. Failures are
  one way to choose what a person reads.
- *Code owners write their own checks,* and tune them until they flag what the owner would. A
  check that pulls in a reviewer says why.
- *Reliability checks trigger on the diff.* A checklist of 39 items, each with a trigger that
  can be read from a diff, the check itself, and the incidents or pull requests behind it. The
  agent reads the diff and runs only the matching items, usually 3 to 10.
- *One reviewer, multiple rounds.* A second, more expensive reviewer on top is often worse than
  tuning the first. A `REVIEW.md` says what the reviewer attends to for this code. Later rounds
  get the context of earlier rounds and past failures and do not start from nothing.
- *Changes cannot modify their own checks.* "If a change can modify the check that judges it,
  the check is broken." The review reads `REVIEW.md` from the base or default branch, never
  from the pull request. A review belongs to one commit: a pass on a commit that is no longer
  the head means nothing. Cheap checks run first: tests, build and linter before a pull request
  is opened, enforced by a hook that runs when the agent finishes, or by a goal of a passing
  suite.
- *Start a new gate in observe mode.* Each commit is stamped with how it was verified,
  including the value "none", so unverified commits can be queried. A commit gate can block a
  commit made in a session that ran neither the code review nor the verify step. It has three
  modes: off, observe (logs what it would have blocked, so false positives are seen before
  anyone is stopped) and enforce. In enforce mode a commit may explain in its message why it
  was not verified, and after two blocks in one session the next commit is let through, so the
  agent cannot get stuck.
- *Test your checks on what matters.* The team tracks merged changes that were reverted,
  changes a maintainer rejected before merging, and a size-matched set of changes that stayed
  clean. The code review product has a formal evaluation built from past incidents and reverts:
  the repository as it was at review time, a one-sentence answer key, points only for findings
  that describe that bug, clean merged changes as a control against over-flagging, a tuning set
  kept apart from a fixed test set. Recall is measured separately for raw findings, after
  verification and in the final review, to see where a found bug gets lost. Findings carry
  importance (important, nit, pre-existing). Recall is tuned only up to the point where more
  would fit the evaluation and not real bugs.
- *Turn misses into rules.* Two routes. Patterns from human review comments and reverts become
  candidate rules only when they occurred in at least two pull requests and can be recognised
  from a diff; three agents try to disprove a candidate and a person approves it in a pull
  request. Or three bug finders are replayed on a pull request tied to a known incident: found
  by at least two, the bug counts as detectable, and a detectable bug missed on a small diff
  becomes a rule. Flaky tests: no skipping, no added sleeps, no retrying until green; without a
  root cause the test is deleted and the reason written down. Test suites, verification steps
  and instruction files only grow unless they are tidied on a routine.

**Closing section.** Keep the verification layer out of reach of the changes it judges, grade
it against the bugs that mattered, write down a lesson at each miss and prune the lessons, so
that the person's work moves from reading diffs to defining "done" and reviewing evidence.

## What the article does not say

Read for what the proposal may not lean on it for:

- **No numbers on cost.** No runtime of the checks, no size of the test suite, no token cost of
  the review rounds, no false-positive rate of the commit gate.
- **No rule against adding tests.** The article says suites only grow unless pruned (§3, *Turn
  misses into rules*) and that agents can cheaply generate tests (§1). It gives no budget, no
  admission test for a new check and no pruning criterion. The anti-bloat system in the
  proposal is this repository's own design, not the article's.
- **The 10-point figure** is one internal result on one kind of task, with a grader and a
  rubric; it is not evidence about test suites.
- **The setting** is a team shipping an application with a user interface. The `verify` skill,
  the end-to-end advice and the reliability checklist assume a running product and a history of
  incidents. A repository of rules, skills and scripts has neither in that form.
- **The stamp and the commit gate** are described for the team's own repositories; the article
  does not say how the stamp is stored or what it costs.
