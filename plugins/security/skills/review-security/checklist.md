# The checks, by area

Read with [SKILL.md](SKILL.md). Each check names its source in a few words (OWASP Top 10 2025,
OWASP ASVS 5.0, the OWASP cheat sheets, the OWASP Top 10 for LLM applications, and the vendors'
documentation); the links and the dates they were read are in [sources.md](sources.md). A check
that does not apply is skipped, not reported as clean. The stack notes at the end apply only
where the repository uses that stack.

## 1. Access control and ownership (OWASP A01, ASVS V8, Authorization cheat sheet)

- Every server entry point authorizes on its own: route handlers, API endpoints, RPC functions,
  jobs that act for a user. A check in a layout, a page or a proxy does not protect the action
  behind it.
- Object-level checks: a request that names an id proves the caller may act on that object; a
  random identifier is no protection, and an organisation or tenant id the request carries is
  checked against the caller's membership on the server.
- Deny by default; role checks in the client are presentation only. Admin paths check a
  server-side claim or table, never a flag the client sent.
- Cross-site requests: no state change on `GET` or during rendering. An endpoint authenticated by
  a cookie that changes state checks `Origin` against the site, uses the framework's CSRF
  protection, or requires a credential that is not a cookie; `SameSite` is defence in depth, not
  CSRF protection (Session Management cheat sheet; the stack notes say which frameworks check
  for you).
- Webhooks (payments, mail, auth hooks) verify the provider's signature over the raw body with a
  constant-time comparison, reject a timestamp outside the tolerance (Stripe's libraries: 5
  minutes; never 0) and skip an event id already processed. A provider that sends only an id
  (Mollie's classic webhooks) is answered by fetching the object from its API, never by trusting
  the request (Stripe and Mollie webhook guides).
- Prices, discounts and amounts are computed on the server from the product or plan id; an amount
  the client sends is input, not a fact (ASVS V2).
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
- Tokens live in the cookies the auth library sets; refresh tokens rotate; no token in a URL, in
  local storage by hand, or in a log. A cookie the application sets itself carries `Secure`,
  `HttpOnly` unless browser code must read it, `SameSite=Lax` or `Strict`, and no `Domain`
  attribute (Session Management cheat sheet).
- Sign-out goes through the library, which ends the session on the server, never a cookie
  deletion alone. Access tokens already issued stay valid until they expire, so a decision that
  must take effect at once (a deleted or banned user, a revoked role) asks the auth server or a
  table, not the token's claims; a password or e-mail change ends the other sessions (Session
  Management cheat sheet).
- Passwords are stored by the auth provider. Code that hashes or compares passwords itself is a
  finding unless it uses Argon2id (at least 19 MiB, 2 iterations), scrypt (N at least 2^17, r=8,
  p=1), PBKDF2-HMAC-SHA256 with at least 600,000 iterations where FIPS-140 is required, or for
  legacy code bcrypt with work factor 10 or more and a 72-byte limit; MD5, SHA-1 or SHA-256 on a
  password is High (Password Storage cheat sheet).

## 3. Input, injection and output (OWASP A05, ASVS V1, V2, V5; API4:2023)

- Input at every server entry point (route handler, API endpoint, RPC, worker job) is parsed with
  a schema that bounds every string, array and number (`z.string().max(…)` in zod,
  `Field(max_length=…)` in pydantic), and the code uses the parsed value, never the raw body or a
  type assertion on it; path segments, query parameters and headers are input too (ASVS V2;
  API4:2023: a maximum size on every parameter).
- Abuse limits: an endpoint that sends mail or SMS, calls a paid API or does expensive work has a
  rate limit per user and per address, and the paid provider has a spending limit or a billing
  alert (API4:2023).
- Mail: the sender and reply-to addresses are constants or configuration, never input; a
  recipient, subject or name from input is validated (an e-mail schema, no line breaks) before it
  reaches the mail API; an endpoint that mails an address the visitor typed is rate-limited, or
  it is a spam relay (API4:2023).
- Uploads: the type is checked on the server against an allow list (the storage bucket's or the
  handler's), never by the `accept` attribute or the `Content-Type` the client sent; a size limit
  holds; the stored name is generated, not the visitor's file name; the file lands in private
  storage, never in a folder the site serves as is (File Upload cheat sheet; ASVS V5).
- Database access through the client library or parameterized SQL; string-built SQL, including
  in migrations and stored functions, is a finding.
- Shell: no string-built commands from input (`exec`, `spawn` with `shell: true`, `subprocess`
  with `shell=True`); arguments as arrays; paths resolved and checked against the intended root.
- HTML: raw-HTML sinks (`dangerouslySetInnerHTML`, `v-html`, `innerHTML`, `outerHTML`,
  `document.write`, a template's `|safe`, `Markup()` or autoescaping switched off) only with
  sanitized or constant content (`textContent` or a sanitizer such as DOMPurify instead; DOM-based
  XSS cheat sheet); `href` and `src` from input reject `javascript:` and `data:`.
- Server output: JSON responses carry `Content-Type` and no user HTML; redirects are relative or
  allow-listed; file names from input are not used as paths.
- A server that fetches a URL the visitor supplied (a link preview, an import, a webhook target)
  allows only listed hosts, or resolves the name and refuses loopback, private, link-local (the
  cloud metadata address 169.254.169.254) and unique-local addresses, connects to the address it
  checked, and does not follow redirects (SSRF Prevention cheat sheet).
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
  switches) is explicit and safe by default; an unsafe development default (a localhost fallback
  for a redirect base, `debug=true`, an authentication bypass or mock user kept for local work or
  tests) is a finding when a missing variable would turn it on in production.
- Outgoing HTTPS calls keep certificate verification (`verify=False` in Python's `requests` or
  `httpx` accepts any certificate: a man-in-the-middle path) and carry a timeout, which
  `requests` does not set by default (Requests advanced guide).

## 5. Supply chain (OWASP A03, Vulnerable Dependency Management cheat sheet)

- `audit_dependencies.py` is clean at the agreed level, or each remaining advisory has an owner
  and a reason on the issue.
- The lockfile is committed and installs use it (`npm ci`, `pnpm install --frozen-lockfile`,
  `cargo build --locked`, `uv sync --locked`); a dependency added in the change is checked by
  name, publisher, download count and age before it is trusted (typosquatting and names a model
  invented); `ignore-scripts=true` in `.npmrc` where install scripts are not needed.
- A Python service's dependencies are locked: `uv.lock`, `poetry.lock`, or every line of
  `requirements*.txt` pinned with `==`. `audit_dependencies.py` audits only `==` pins and lists
  every other requirement (`flask>=3`, a bare name, a URL, `-e`) as `unaudited`, ranked
  moderate: the pre-deploy run at `--level moderate` fails on it.
- Registry and CI tokens are granular and short-lived, never in a committed file; GitHub Actions
  are pinned to a version, third-party actions to a commit.
- A fix for a transitive advisory goes through the direct dependency; no advisory is silenced by
  editing a version string.

## 6. Error handling and logging (OWASP A09, A10, ASVS V16)

- Errors to the client are generic; stack traces, SQL, file paths and library versions stay in
  server logs, and so does a database error's text, which names tables, columns and constraints.
  Unhandled rejections and exceptions fail the request, not the process's safety.
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
  appears only in server-only code; the server reads the user with `getUser()`, which also
  answers a decision that must take effect at once, since an access token stays valid until it
  expires (1 hour by default). The SSR client keeps the session cookies readable by its browser
  client, so XSS defences and the CSP carry that weight. `signOut()` in the JavaScript client
  ends every session of the user by default. A Supabase error's `message`, `details` and `hint`
  stay out of the response. The `check-web-deploy` skill (web-deploy plugin) has the full list.
- **Next.js:** a proxy or middleware is never the only gate (CVE-2025-29927); Server Actions
  validate their arguments and check ownership (they are reachable by direct POST); a Data
  Access Layer with `import 'server-only'`; a client component never receives a whole row or a
  secret. Server Actions compare `Origin` with the host themselves (a request without `Origin`
  passes with a warning); route handlers do not, so a cookie-authenticated route handler that
  changes state checks `Origin` itself. Every file in `public/` is served (Next.js data security
  guide and `serverActions` reference).
- **Python services:** `subprocess` with argument lists, no `pickle` or `yaml.load` on input,
  `defusedxml` for untrusted XML. A plain Jinja `Environment` does not escape;
  `select_autoescape()` turns it on, and Flask does for `.html` templates (Jinja API, Flask
  template guide).
- **Python web backends** (Django deployment checklist and CSRF reference; Flask debugging and
  security guides; FastAPI CORS guide):
  - Django runs with `DEBUG = False` (debug pages leak source excerpts, local variables and
    settings), `SECRET_KEY` from the environment and used nowhere else, exact `ALLOWED_HOSTS` (a
    wildcard needs its own Host validation), and `SESSION_COOKIE_SECURE` and
    `CSRF_COOKIE_SECURE` on; `python manage.py check --deploy` against the production settings
    reports the rest. `@csrf_exempt` sits only on an endpoint that authenticates another way (a
    webhook signature, a bearer token), never on a view behind the session cookie, and
    `CSRF_TRUSTED_ORIGINS` lists only origins the site controls.
  - Flask never runs the development server or `debug=True` in production: the Werkzeug
    debugger executes Python from the browser and its PIN is no protection. Reachable, it is
    Critical. `SECRET_KEY` comes from the environment. Flask and FastAPI have no CSRF protection
    of their own unless an extension adds it.
  - FastAPI and Starlette CORS: with `allow_credentials=True`, `allow_origins=["*"]` does not
    fail safe. Starlette's middleware then echoes each caller's own `Origin` with credentials
    allowed, so any website can make credentialed requests and read the answers: High, and
    Critical when a cookie authenticates. With credentials, the origins, methods and headers are
    listed explicitly (Starlette `middleware/cors.py`).
- **Google sign-in without Supabase** (Google Identity Services, or an OAuth flow the server runs
  itself): the server verifies the ID token with Google's library, which checks the signature,
  `aud` and `exp` (`id_token.verify_oauth2_token(token, requests.Request(), CLIENT_ID)` in
  Python, `verifyIdToken({ idToken, audience })` in Node's `google-auth-library`); `iss` is
  `accounts.google.com` or `https://accounts.google.com`. A token that is only decoded, or
  verified without the audience, is High. The account is keyed on `sub`; `email` counts only
  with `email_verified`; a domain restriction checks the `hd` claim on the server; in the
  redirect mode the `g_csrf_token` cookie equals the field of the same name in the body (Google:
  verify the ID token on the server).
- **Google Cloud service accounts:** no JSON key where a keyless route exists: code on Google
  Cloud uses the attached service account, and code elsewhere uses Workload Identity Federation
  (on Vercel, through Vercel's OIDC token). A key that must exist lives only in the secret store
  (`scan_secrets.py` names `service-account*.json` files and private-key blocks). A committed
  key is Critical and goes to the user, who deletes it in IAM first: removing it from git does
  not revoke it. One service account per application, with the narrowest role on the resource it
  needs; never a basic role (Owner, Editor) and never a project-wide Service Account User or
  Token Creator grant, which lets its holder impersonate every service account in the project
  (Google Cloud service-account and key best practices; Vercel OIDC for Google Cloud).
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

The effect on the merge applies to findings the change introduces or touches: a dependency it
adds or upgrades, code it changes that reaches a vulnerable path. A finding that already stands
on the default branch (the same advisory id on the same package, or the same code) does not block
an unrelated pull request. It gets exactly one tracking issue with an owner (search for an open
one first; the `open-issue` skill), and the report names that issue. A Critical finding and a
secret stop everything, already on the default branch or not.

**Deadlines.** The tracking issue of a Critical gets the label `priority: critical` and is due in
3 days; of a High, `priority: high` and 14 days; a Medium is due at the next planned update; Low
and Info have none. The issue says `due: YYYY-MM-DD`. The user, or a maintainer the repository
names, accepts a finding on its issue with `accepted until YYYY-MM-DD`; after that date the
acceptance has lapsed and the finding is open again. A release or a deploy blocks on every open
Critical or High that is not under a current acceptance; the due date says when its owner must
have fixed it, not when it starts to block. A merge that deploys (a production deploy on merge)
counts as a deploy: an existing Critical or High blocks only what deploys, while for a Critical
the review stops and tells the user at once; an unrelated merge that deploys nothing does not
block on them.

**Continuous scanning.** A repository with a lockfile has GitHub's Dependabot alerts on (a
repository setting its owner turns on; a review never changes it). Whoever keeps the overview of
the repository's issues reads `gh api repos/<owner>/<repo>/dependabot/alerts?state=open` and
opens one tracking issue per new alert as above, named by its advisory id.

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
