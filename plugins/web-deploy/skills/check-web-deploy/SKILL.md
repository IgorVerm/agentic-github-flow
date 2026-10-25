---
name: check-web-deploy
description: Hardening check of a public website on Vercel with Supabase, optionally Google sign-in through Supabase Auth, before its first production deploy, before a deploy that changes authentication, row-level security, environment configuration, headers or redirects, or when the user asks whether a site is safe to go live. Checks the repository only, then gives the user a dashboard list to confirm and a ready or not-ready verdict; it deploys nothing.
---

# Is this site safe to go live?

The check reads the repository: migrations, configuration, environment names, headers, the auth
flow, dependencies. State that lives only in a dashboard (Supabase auth settings and Security
Advisor, Vercel environment variables and Deployment Protection, the Google OAuth client) is not
read by the agent: it becomes a list the user confirms. The agent never logs in to Supabase,
Vercel or Google, runs no `vercel`, `supabase` or `gcloud` command that writes, changes no
environment variable, rotates no key, deploys nothing and pushes nothing. The user deploys.

The checks per area, each with its source, are in [supabase.md](supabase.md),
[vercel.md](vercel.md) and [google-auth.md](google-auth.md) (the last one written from the
vendors' documentation and not yet exercised in a live project); the list for the user is
[dashboard.md](dashboard.md). This skill uses the security plugin's scripts:
`<security plugin>/scripts/` is a sibling plugin of this one, installed with it.

1. **Map the project.** Framework and version (`package.json`: Next.js 16 uses `proxy.ts`,
   earlier versions `middleware.ts`; Vite exposes `VITE_*`), `supabase/` (migrations,
   `config.toml`, functions), `vercel.json`, `next.config.*`, the auth routes and the modules
   that hold the Supabase clients. Read `HANDOFF.md` and any security document it names: what
   the repository already proves is not re-proven here.
2. **Secrets and dependencies** as `review-security` steps 2 and 3: `scan_secrets.py` with
   `--history`, and `audit_dependencies.py --level moderate --upgrades` (ask before its first
   network call in the repository). A secret found stops the check and goes to the user first.
3. **Supabase**: [supabase.md](supabase.md). Row-level security on every exposed table with a
   policy per operation, grants, security definer functions, views, storage buckets, where each
   key is used, and `config.toml` as the reviewable home of the auth settings.
4. **Auth flow**: [supabase.md](supabase.md) §Auth flow and, when Google sign-in is on,
   [google-auth.md](google-auth.md). Callback and confirm routes, redirect sanitizing, the site
   URL, the redirect allow list, server-side authorization behind the proxy.
5. **Vercel and Next.js**: [vercel.md](vercel.md). Environment names and scopes, the public
   prefix, Deployment Protection for previews, the security headers and the CSP route, the
   proxy, `.gitignore`, the runtime version against the vendor's supported list.
6. **Findings** on the owning issue, signed, in the format and severities of the
   `review-security` skill's `checklist.md` §Report and §Severity.
7. **The dashboard list** for the user: [dashboard.md](dashboard.md) filled in for this
   project, only the lines that apply, in the user's language, as one comment on the issue after
   the findings. Each line names where to look and what the correct state is; the user ticks or
   answers.
8. **Verdict**, as the last line of that comment: *ready* only when no Critical or High finding
   is open and the user has confirmed every line of the dashboard list; otherwise *not ready*,
   with the items that block. A verdict is a recommendation; the deploy is the user's.

When the site is already live, the same steps apply to the change at hand; the dashboard list
then holds only the lines the change touches.
