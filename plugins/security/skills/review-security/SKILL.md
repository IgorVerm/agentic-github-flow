---
name: review-security
description: Review a change or a whole repository for security defects, committed secrets and vulnerable dependencies. Use when a change touches authentication, authorization, access policies, secrets or environment configuration, dependencies, deployment configuration or input handling of a public service; when reviewing such a change for another agent; or when the user asks for a security review or audit.
---

# Security review of a change or a repository

A review finds and reports; it changes code only when the task asked for fixes. It never rotates
or creates a key, changes a live system, installs a tool, pushes, or weakens a gate or a test to
get a pass. A real secret found stops everything else: tell the user the file and the commit;
the secret is revoked first, and history is cleaned up only on the user's word (it needs a
force-push).

`<plugin>` below is the folder two levels above this skill's folder. The checks are in
[checklist.md](checklist.md), each with the source it rests on.

1. **Scope and context.** A change: the diff of the branch against the default branch and the
   files it touches. An audit: the whole repository. Read the repository's `AGENTS.md`,
   `HANDOFF.md` and any security document they name first, and the company overlay's data
   classes if one is installed; note what the repository already enforces, so the review judges
   the change against it instead of restating it.
2. **Secrets.** `python3 <plugin>/scripts/scan_secrets.py <repo>` for the tree, with
   `--history` for an audit or when the change touches configuration. It prints the pattern,
   the file, the line and the commit, never the value. History can take minutes on a large
   repository: run it in the background. A finding on a test fixture or a regular expression is
   dismissed with one line saying why; anything else goes to the user as above.
3. **Dependencies.** `python3 <plugin>/scripts/audit_dependencies.py <repo>` checks every
   lockfile (npm, pnpm, Cargo, poetry, uv, composer, pinned requirements) against the OSV
   database, with `npm audit` as a cross-check where npm is present. It sends package names and
   versions to osv.dev, to the public npm registry (`npm audit`, always registry.npmjs.org;
   `--no-npm` leaves it out) and, with `--upgrades`, to the npm and PyPI registries and
   endoflife.date: ask the user before the first run in a repository, naming those
   destinations, and skip it where the company overlay forbids it. Default threshold `high`; `--level moderate` before a deploy.
   `--upgrades` adds the latest release of each direct dependency and the support status of
   frameworks and runtimes: a cycle past its end of support is a finding, a major behind is
   advice. A transitive finding is fixed through the direct dependency that pulls it in; a
   finding with no fix is suppressed only per advisory id, with the reason on the issue.
4. **The client's own review.** In Claude Code, `/security-review` on the branch. In Codex,
   `/review` with the focus text in `checklist.md` §Focus for a client review. Their findings
   are input: check each against the code before it becomes yours, and keep the ones they
   missed.
5. **The checks** of `checklist.md`, area by area, for the files in scope, plus the stack notes
   that match the repository. Trace each user input to where it is used; the diff alone does not
   show the sink.
6. **Report** on the owning issue or pull request, signed `🤖 <agent> (reviewer):`, in the
   format of `checklist.md` §Report, severity first; then the areas confirmed clean, one line
   each; then what was not checked. No secret value, no personal data, environment variables by
   name only. A finding that blocks the merge says so (`checklist.md` §Severity).

Optional cross-checks, never requirements: Gitleaks and osv-scanner for the two scripts, and the
vendors' own deep-scan tools when the user installs them.
