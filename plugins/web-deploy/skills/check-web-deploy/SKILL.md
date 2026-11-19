---
name: check-web-deploy
description: Hardening check of a website on Vercel with Supabase (optionally Google sign-in) or on Google Cloud (Cloud Run, Cloud SQL, IAP, Secret Manager), before its first production deploy, before a deploy that changes authentication, access rules, environment or secrets, headers or redirects, or when the user asks whether a site is safe to go live. Checks the repository only, then gives the user a dashboard list to confirm and a ready or not-ready verdict; it deploys nothing.
---

# Is this site safe to go live?

The check reads the repository: migrations, configuration, environment names, headers, the auth
flow, dependencies, the `Dockerfile` and the deploy code. State that lives only in a dashboard
(Supabase auth settings and Security Advisor, Vercel environment variables and Deployment
Protection, the Google OAuth client, the Google Cloud console) is not read by the agent: it
becomes a list the user confirms. The agent never logs in to Supabase, Vercel or Google, runs no
`vercel`, `supabase`, `gcloud` or `cloud-sql-proxy` command and no database client against a
deployed database, changes no environment variable or secret, rotates no key, deploys nothing
and pushes nothing. The user deploys.
Besides the dependency audit of step 2, its only network reads are two public, read-only
lookups: the sending domain's DNS records ([mail.md](mail.md)) and the response headers of the
public production URL ([dashboard.md](dashboard.md) §Vercel, §Google Cloud).

Two routes, picked in step 1: **Vercel + Supabase** ([vercel.md](vercel.md),
[supabase.md](supabase.md), [google-auth.md](google-auth.md)) and **Google Cloud**
([cloud-run.md](cloud-run.md), [iap.md](iap.md), [cloud-sql.md](cloud-sql.md)); a project that
mixes them takes the file of each part it uses. [mail.md](mail.md) and [privacy.md](privacy.md)
apply to both; the list for the user is [dashboard.md](dashboard.md). Each file names its sources
and their read date; google-auth.md and the Google Cloud files are written from the vendors'
documentation and not yet exercised in a live project. This skill uses the security plugin's
scripts: `<security plugin>/scripts/` is a sibling plugin of this one, installed with it.

1. **Map the project and pick the route.** Framework and version (`package.json`: Next.js 16
   uses `proxy.ts`, earlier versions `middleware.ts`; Vite exposes `VITE_*`), `next.config.*`,
   the auth routes; for Vercel + Supabase `supabase/` (migrations, `config.toml`, functions),
   `vercel.json` and the modules that hold the Supabase clients; for Google Cloud the
   `Dockerfile`, Terraform, service YAML, `cloudbuild.yaml` or deploy scripts, the migrations
   and the module that verifies the IAP header. Read `HANDOFF.md` and any security document it names: what
   the repository already proves is not re-proven here.
2. **Secrets and dependencies** as `review-security` steps 2 and 3: `scan_secrets.py` with
   `--history`, and `audit_dependencies.py --level moderate --upgrades` (ask before its first
   network call in the repository, naming osv.dev, the npm registry, PyPI and endoflife.date).
   A secret found stops the check and goes to the user first.
3. **Database.** Supabase: [supabase.md](supabase.md); row-level security on every exposed
   table with a policy per operation, grants, security definer functions, views, storage
   buckets, where each key is used, and `config.toml` as the reviewable home of the auth
   settings. Cloud SQL: [cloud-sql.md](cloud-sql.md); network, connector, SSL mode, database
   user, backups and recovery, migrations.
4. **Auth flow and mail.** Supabase Auth: [supabase.md](supabase.md) §Auth flow and, when
   Google sign-in is on, [google-auth.md](google-auth.md). IAP: [iap.md](iap.md), the signed
   header verified with its exact audience. Callback and confirm routes, redirect sanitizing, the
   site URL, the redirect allow list, server-side authorization behind the proxy. When the site
   sends mail, [mail.md](mail.md): custom SMTP for auth mail and the sending domain's SPF, DKIM
   and DMARC records.
5. **Hosting and Next.js.** Vercel: [vercel.md](vercel.md); environment names and scopes, the
   public prefix, Deployment Protection for previews, the security headers and the CSP route,
   the proxy, `.gitignore`, the runtime version against the vendor's supported list. Cloud Run:
   [cloud-run.md](cloud-run.md); the container, who can reach the service, its service account,
   secrets in Secret Manager, the region, with vercel.md's Next.js sections.
6. **Privacy (EU)**: [privacy.md](privacy.md). Consent before analytics and other trackers,
   the privacy notice, deletion that reaches every table, retention, the region.
7. **Findings** on the owning issue, signed, in the format and severities of the
   `review-security` skill's `checklist.md` §Report and §Severity.
8. **The dashboard list** for the user: [dashboard.md](dashboard.md) filled in for this
   project, only the lines that apply, in the user's language, as one comment on the issue after
   the findings. Each line names where to look and what the correct state is; the user ticks or
   answers.
9. **Verdict**, as the last line of that comment: *ready* only when no Critical or High
   finding is open without a current acceptance by the user, including one that already stood
   on the default branch and has its own tracking issue (the `review-security` skill's
   `checklist.md` §Severity), and the user has confirmed every line of the dashboard list;
   otherwise *not ready*, with the items that block. A verdict is a recommendation; the deploy
   is the user's.

When the site is already live, the same steps apply to the change at hand; the dashboard list
then holds only the lines the change touches.
