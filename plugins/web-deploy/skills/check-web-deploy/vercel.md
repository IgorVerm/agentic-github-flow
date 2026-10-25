# Vercel and Next.js: what the repository must show

Read with [SKILL.md](SKILL.md). Sources: Vercel's documentation on environment variables,
Deployment Protection, security headers, the firewall and Attack Mode; Next.js's guides on
environment variables, Content Security Policy and data security, the `proxy` reference and
the CVE-2025-29927 postmortem; the OWASP HTTP Headers cheat sheet (read 2026-10-25). A Vite site on Vercel follows the same rules with `VITE_` for
the public prefix and `vercel.json` for the headers.

## Environment variables

- **Names and scopes** are reviewable in the repository: `.env.example` lists every variable
  with a placeholder, grouped by scope (Production, Preview, Development) and marked Secret or
  Config as Vercel types them. A variable the code reads that `.env.example` lacks is a finding.
- **Nothing sensitive under a public prefix.** `NEXT_PUBLIC_*` and `VITE_*` are inlined into the
  browser bundle at build time (Next.js env guide; Vercel framework env vars). The publishable
  Supabase key and the site URL are the expected public values; a secret-shaped value under a
  public name is Critical, and a build-time guard against it is the expected shape.
- **Preview deployments never carry production secrets.** The Supabase secret key, payment and
  mail keys for production exist in the Production scope only; previews use a separate project
  or test keys. This is a dashboard line for the user (the repository cannot show it) unless the
  project's documentation records the scopes; Vercel's "Separate Production Secret Values"
  team policy is the mechanism to recommend.
- **Secrets are read in one place** (a server-only config module or the Data Access Layer) and
  `VERCEL_URL` is not used for self-fetches when Standard Protection is on (it is protected);
  `VERCEL_PROJECT_PRODUCTION_URL` or a relative path instead.

## Deployment Protection

- Previews are behind **Vercel Authentication** with **Standard Protection** (all plans; the
  recommended method), so a preview URL does not expose a half-finished site, test data or an
  unreviewed change to the public. Password Protection costs extra on Pro; Hobby has only Vercel
  Authentication.
- Automation that must reach a protected preview uses the **Protection Bypass for Automation**
  header with its secret (never a query string in a committed URL); the secret is a Vercel
  Secret variable, and regenerating it invalidates earlier deployments.
- Disabling protection "renders all existing deployments unprotected": a dashboard line.

## Headers (OWASP values; Vercel and Next.js guides)

Set in `next.config.*` `headers()` (or `vercel.json` `headers` for a static site), on `/(.*)`:

| Header | Expected | Note |
|---|---|---|
| `Content-Security-Policy` | `default-src 'self'`; `script-src` without `'unsafe-inline'` and `'unsafe-eval'`; `object-src 'none'`; `base-uri 'self'`; `form-action 'self'`; `frame-ancestors 'none'`; `upgrade-insecure-requests` | Two routes to drop `'unsafe-inline'`: a per-request nonce set in `proxy.ts` with `'strict-dynamic'` (Next.js CSP guide: pages render dynamically, no PPR), or hashes for a static export. Start with `Content-Security-Policy-Report-Only` and read the reports (Vercel). `'unsafe-inline'` in `script-src` on a site with sign-in is High. |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | Vercel sends HSTS on its own domains; a custom domain needs the header from the app, and `preload` only after the preload requirements are read. Missing on a site with sign-in: Medium. |
| `X-Frame-Options` | `DENY` | Redundant with `frame-ancestors` for current browsers; keep both. |
| `X-Content-Type-Options` | `nosniff` | |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | |
| `Permissions-Policy` | at least `geolocation=(), camera=(), microphone=()` | Name the features the site does use. |
| `Cross-Origin-Opener-Policy` | `same-origin` | OWASP recommends the trio; `Cross-Origin-Embedder-Policy: require-corp` only when every embedded resource allows it. |

`Cache-Control` on authenticated responses: `private, no-store`. A static Vite site with no
sign-in still sets CSP, HSTS, `nosniff`, `Referrer-Policy` and `frame-ancestors`: a site that
loads analytics or fonts names those origins in the CSP instead of widening it.

## Proxy, Server Actions, runtime

- Next.js 16 renamed `middleware.ts` to `proxy.ts`; a project on 13, 14 or 15 must be on a
  version with the CVE-2025-29927 fix (14.2.25, 15.2.3) or later, which
  `audit_dependencies.py` reports. Either way the proxy is not the authorization: every
  Server Action, route handler and page that shows user data re-checks the user (Next.js data
  security guide; `proxy` reference: a matcher gap also skips Server Function calls).
- Server Actions are "reachable via direct POST requests": arguments validated with a schema,
  ownership checked, `serverActions.allowedOrigins` set when a proxy or custom domain sits in
  front.
- A Data Access Layer with `import 'server-only'` is the shape to expect; a component marked
  `"use client"` never receives a whole database row or a secret as a prop.
- **Runtime and framework versions**: `audit_dependencies.py --upgrades` reports, for
  the direct dependencies and the Node version in `package.json` `engines.node` or `.nvmrc`
  (Vercel picks the runtime from them), the latest release and the support window from
  endoflife.date; a cycle past its end of support (no more security fixes) is High, a major
  behind is advice. A runtime the repository does not pin is a Medium finding: pin it.
- The Vercel **WAF** (custom rules on all plans) and **Attack Mode** (free, temporary, blocks
  standalone API clients) are the user's dashboard options for an attack, not something the
  repository configures.

## Repository hygiene

- `.gitignore` carries the secrets block of `templates/gitignore-secrets` of agentic-github-flow (every
  `.env*` except the examples, keys, certificates); `.vercel/` is ignored; `vercel.json` holds no
  secret.
- `scan_secrets.py --history` is clean or explained; `audit_dependencies.py` at
  `--level moderate` is clean or every advisory has an owner on the issue, with the framework's
  own advisories first.
- No CI is required by these rules; where a workflow exists, its secrets are repository secrets
  and its actions are pinned (`review-security/checklist.md` §5).
