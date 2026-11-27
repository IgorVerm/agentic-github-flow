# Writing a repository's Verification section

Read when a repository's `## Verification` section is first written. Its rows and their defaults:
the `repo-docs` skill's `skeleton.md`. Every repository that installs the method gets the
section; one without CI runs `full` before every landing.

## Test kinds per project type

| Project | Fast | End to end (`drive`) | Property tests | Differential tests |
|---|---|---|---|---|
| Rust, including Bevy | `cargo fmt --check`; `cargo clippy --all-targets -- -D warnings`; `cargo test` for the changed crates | The application run headless for a fixed number of frames from a fixed seed: no panic, and a state the test can compare. A screenshot for what only eyes can judge, recorded as `seen` | `proptest` on pure logic: save and load round trips, invariants of the simulation, idempotent systems | Old against new across a refactor of the simulation: same seed, same inputs, same state after N steps |
| Python service or tool | Linter, type checker, tests of the changed package | The service started locally and called through its real interface | Hypothesis on parsers, serialisers, anything with an inverse | Old against new for a rewrite or migration, on sampled inputs |
| Web application | Linter, type check, unit tests of the changed module | A browser flow per user journey, with the trace kept on failure | fast-check on reducers, formatters, validation | A visual or response comparison across a framework migration |
| Rules, skills and scripts | The test scripts whose trigger matches | Hooks fed the input the client sends; the installer in a temporary home | Seeded generators from the standard library | A guard against its previous version |

- **Clippy with warnings denied belongs in the Rust fast check:** exact, fast, and not written
  by the author.
- **End to end pays most where there is a running product,** and is the one kind to have if
  there is only one.
- **Property tests pay where a statement holds for all inputs;** their inputs do not share the
  author's bias.
- **Differential tests pay during a rewrite** and are pruned after it.
- A dependency the project does not have yet is asked for first.
- `fast` selects by the changed paths (the changed crate or package, the test files whose
  trigger matches); a path the selection does not know runs everything, so selection costs
  speed, never a check.
- A project with a heavy harness (a game, a mobile app) keeps it as its own skill or script and
  names it under `drive`.

## The list of critical paths

An audit agent writes it: a session with a fresh context that reads the repository, not the
history of one change. For each part of the code it asks: if this broke unnoticed, what would be
lost that cannot be taken back or would stop the work (data, money, security, a release, the
method's own gates)? It writes the `critical paths` row with one line of reason per entry under
the table, as an audit change: a landing that changes those lines and nothing else, for an issue
of its own, approved by an independent reviewer. It runs when the section is first written and
again at each `Review by:` date of the repository's `DESIGN_DECISIONS.md` entry for its
verification settings.

The reviewer of an audit change checks that it belongs to an audit issue and its session has no
other change open or in hand that the list bears on; that every entry names the loss; that every
removed entry says what changed in the code since it was listed; that no part with an
irreversible loss is missing (naming any it finds); and that the change holds nothing else.
Otherwise it is refused.

Then the first pruning pass applies the pruning rule (`SKILL.md`) to the checks that exist.
