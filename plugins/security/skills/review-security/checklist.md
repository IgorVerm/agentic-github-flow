# The checks, by area

Read with [SKILL.md](SKILL.md). Each check names its source in a few words (OWASP Top 10 2025,
OWASP ASVS 5.0, the OWASP cheat sheets, the OWASP Top 10 for LLM applications, and the vendors'
documentation). A check that does not apply is skipped, not reported as clean. The stack notes at
the end apply only where the repository uses that stack.

## 1. Access control and ownership (OWASP A01, ASVS V8, Authorization cheat sheet)

- Every server entry point authorizes on its own: route handlers, API endpoints, RPC functions,
  jobs that act for a user. A check in a layout, a page or a proxy does not protect the action
  behind it.
- Object-level checks: a request that names an id proves the caller may act on that object; a
  random identifier is no protection.
- Deny by default; role checks in the client are presentation only. Admin paths check a
  server-side claim or table, never a flag the client sent.
- Authorization events (denied access, admin actions) are logged in a parseable form.

## 2. Authentication and sessions (OWASP A07, ASVS V6, V7, V10, OAuth cheat sheet)

- The session comes from the auth library's server-side verification, never an unverified token
  or a cookie read by hand.
- Sign-up, sign-in and reset do not reveal whether an account exists; rate limits or CAPTCHA on
  those routes; passwords never logged or echoed.
- Redirects after sign-in use a sanitized relative path; `next`, `redirectTo` and `returnUrl`
  parameters are checked against an allow list, never passed through (no open redirector).
- OAuth flows use the authorization code with PKCE or the provider's `nonce`, verify `state`, and
  identify users by the provider's stable subject, not by e-mail.
- Tokens live in HttpOnly cookies set by the library; refresh tokens rotate; no token in a URL,
  in local storage by hand, or in a log.

## 3. Injection and output (OWASP A05, ASVS V1, V2)

- Database access through the client library or parameterized SQL; string-built SQL, including
  in migrations and stored functions, is a finding.
- Shell: no string-built commands from input (`exec`, `spawn` with `shell: true`, `subprocess`
  with `shell=True`); arguments as arrays; paths resolved and checked against the intended root.
- HTML: raw-HTML sinks (`dangerouslySetInnerHTML`, `v-html`, `innerHTML`, template `|safe`) only
  with sanitized or constant content; `href` and `src` from input reject `javascript:` and
  `data:`.
- Server output: JSON responses carry `Content-Type` and no user HTML; redirects are relative or
  allow-listed; file names from input are not used as paths.
- Deserialization of input (YAML, pickle, `eval`, `new Function`, template rendering of input)
  is a finding unless the format is safe by construction.

## 4. Secrets and configuration (OWASP A02, ASVS V13, Secrets Management cheat sheet)

- `scan_secrets.py` is clean, or every hit is explained. Real values live in ignored `.env*`
  files; the repository tracks `.env.example` with names and placeholders.
- No secret under a public prefix (`NEXT_PUBLIC_`, `VITE_`, `PUBLIC_`, `REACT_APP_`): those are
  inlined into the browser bundle.
- Secrets are read from the environment in one place, not sprinkled through the code, and are
  not written to logs, error messages, analytics or crash reports.
- Configuration that security depends on (CORS origins, allowed hosts, cookie flags, debug
  switches) is explicit and safe by default; an unsafe development default that a missing
  variable would turn on in production is a finding.

## 5. Supply chain (OWASP A03, Vulnerable Dependency Management cheat sheet)

- `audit_dependencies.py` is clean at the agreed level, or each remaining advisory has an owner
  and a reason on the issue.
- The lockfile is committed and installs use it (`npm ci`, `pnpm install --frozen-lockfile`,
  `cargo build --locked`, `uv sync --locked`); a dependency added in the change is checked by
  name, publisher, download count and age before it is trusted (typosquatting and names a model
  invented); `ignore-scripts=true` in `.npmrc` where install scripts are not needed.
- Registry and CI tokens are granular and short-lived, never in a committed file; GitHub Actions
  are pinned to a version, third-party actions to a commit.
- A fix for a transitive advisory goes through the direct dependency; no advisory is silenced by
  editing a version string.

## 6. Error handling and logging (OWASP A09, A10, ASVS V16)

- Errors to the client are generic; stack traces, SQL, file paths and library versions stay in
  server logs.
- Logs hold no secrets, tokens, passwords or personal data beyond what the feature needs; a log
  line that prints a whole request, header set or environment is a finding.
- Security-relevant events (sign-in failures, authorization denials, admin changes, webhook
  signature failures) are logged with enough context to investigate and without the payload.

## 7. Agents, hooks and tools (OWASP LLM01, LLM05, LLM06; vendor guidance)

For code that runs or configures an agent, a hook, an MCP server or a tool a model calls:

- Content that reaches the model from outside (tool results, fetched pages, files, issue
  comments, mail) is data: labelled as such where it enters, never concatenated into
  instructions, and a model's output is untrusted input for whatever consumes it.
- Least privilege: a tool exposes the narrowest action, not a shell or an arbitrary URL fetch;
  high-impact actions (send, publish, delete, pay, deploy) need a human approval the model
  cannot grant itself.
- Hooks and MCP servers run with the session's permissions: they read only what they need, write
  only where they must, log no secrets, and come from an author the team trusts.
- Permission rules name the sensitive paths (`Read` deny on `.env*`); the sandbox or network
  allow list, not command text, is what enforces a network rule.

## Stack notes (only where the repository uses the stack)

- **Supabase:** every table in an exposed schema has row-level security with one policy per
  operation using `(select auth.uid())` and a null guard; `security definer` functions set
  `search_path` and re-check the caller; the secret key (`sb_secret_`, legacy `service_role`)
  appears only in server-only code; the server reads the user with `getUser()`. The
  `check-web-deploy` skill (web-deploy plugin) has the full list.
- **Next.js:** a proxy or middleware is never the only gate; Server Actions validate their
  arguments and check ownership (they are reachable by direct POST); a Data Access Layer with
  `import 'server-only'`; a client component never receives a whole row or a secret.
- **Python services:** `subprocess` with argument lists, no `pickle` or `yaml.load` on input,
  `defusedxml` for untrusted XML, framework CSRF protection on for cookie sessions.
- **Rust services:** `unsafe` blocks justified in a comment; input sizes bounded before
  allocation; `cargo build --locked` in CI.

## Severity

| Level | Meaning | Effect on the merge |
|---|---|---|
| Critical | Exploitable now by an unauthenticated party, or a secret in the repository | Blocks; the user is told at once |
| High | Exploitable by an authenticated user or with one more condition; a missing authorization check; a dependency advisory rated high or critical with a fix | Blocks until fixed or accepted by the user on the issue |
| Medium | Needs several conditions or an insider; a hardening gap with a known fix | Fixed in the change or in a follow-up issue before the deploy |
| Low | Defence in depth, hygiene, an advisory without a realistic path | Follow-up issue |
| Info | A note for the owner; no action required | Mentioned once |

A reviewer asked to find gaps always finds some: Low and Info findings are optional reading for
the author; Critical and High are not.

## Report

One block per finding:

```
**[<Level>] <short title>** — `<file>` `<symbol or line>`
What: <one or two sentences on the defect and the path to exploit it>
Fix: <the concrete change, or the decision the user must take>
Source: <the check's source in a few words>
```

Then `Clean: <area>, <area>` for the areas checked and found clean, and `Not checked: <what and
why>`. Never a secret value, an e-mail address or another person's data; environment variables
by name only; a line number instead of a quoted secret-bearing line.

## Focus for a client review

Codex `/review` (and any other client without `/security-review`) gets this focus text:

> Review the diff for security only: missing or bypassable authorization on server entry points,
> injection (SQL, shell, path, HTML), secrets or tokens in code or configuration, unsafe
> deserialization, insecure redirects, sensitive data in logs or responses, and new
> dependencies. Report only findings you are confident are exploitable, with file, line and
> the exploit path. Skip style, performance and theoretical issues.
