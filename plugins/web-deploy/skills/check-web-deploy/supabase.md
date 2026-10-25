# Supabase: what the repository must show

Read with [SKILL.md](SKILL.md). Sources: the Supabase guides on row-level security, API keys,
redirect URLs, going into production, the database linter, hardening the Data API and storage
access control (read 2026-10-25). Everything
here is checked in migrations, `supabase/config.toml` and the application code; the live
project's state is on [dashboard.md](dashboard.md).

## Tables, policies, grants

- **Every table in an exposed schema** (`public` unless `config.toml` or the dashboard exposes
  another) has `enable row level security` in a migration. "A table in an exposed schema without
  RLS is readable and writable by any role with a grant on it" (RLS guide). A table kept without
  RLS and protected by revoked grants alone is a High finding: a later `grant` or a default
  privilege re-exposes it silently (a common finding).
- **One policy per operation** (`select`, `insert`, `update`, `delete`), each `to authenticated`
  (or the role that needs it), using `(select auth.uid())` and a null guard
  (`auth.uid() is not null and auth.uid() = user_id`): an unauthenticated request has a null
  `auth.uid()`, and `null = null` is not true but a careless policy can still pass. A table with
  RLS on and no policy is locked, which may be intended (writes through RPC only): say so.
- **Policies do not remove default grants.** Migrations revoke what `anon` and `authenticated`
  should not have, and `alter default privileges … revoke all on tables from anon,
  authenticated, service_role` where the project uses a dedicated schema (Hardening the Data
  API). Grants to `service_role` are a smell in policy-protected tables: the secret key bypasses
  RLS anyway.
- **Security definer functions** that write or read across users: `set search_path = ''` (or a
  fixed schema list), schema-qualified names, defined outside the exposed schema or with
  `execute` revoked from `anon` and `public`; each one re-checks the caller (`auth.uid()`) inside
  its body. Linter 0011 `function_search_path_mutable` and 0028/0029 `*_security_definer_function_executable`.
- **Views and materialized views** in the exposed schema run as their owner unless
  `security_invoker = true`; a view over `auth.users` or over a protected table is a finding
  (linter 0002 `auth_users_exposed`, 0010 `security_definer_view`, 0016 `materialized_view_in_api`).
- **Policies that read `user_metadata`** are a finding: users can edit it (linter 0015); use
  `app_metadata` or a table.
- **Storage**: policies on `storage.objects` by `bucket_id` and folder (`(storage.foldername(name))[1]`);
  no bucket public unless the content is public; size and MIME limits on upload buckets; downloads
  of private objects through signed URLs with a short expiry (Storage access control; linter 0025
  `public_bucket_allows_listing`).
- **Realtime and queues**: a channel or queue exposed through the API has its own policies
  (linter 0019 `insecure_queue_exposed_in_api`).

## Keys: which key where (API keys guide)

- The **publishable key** (`sb_publishable_…`, legacy `anon` JWT) is the only key in browser
  code, in `NEXT_PUBLIC_*` or `VITE_*` variables and in anything shipped. It is designed to be
  public; it protects nothing by itself, the policies do.
- The **secret key** (`sb_secret_…`, legacy `service_role` JWT) "bypasses every Row Level
  Security policy": it appears only in modules marked `import 'server-only'`, in workers and
  functions, and in `.env.example` as a name. Grep the client bundle's sources and every file
  under `app/`, `components/` and `pages/` for it; a build-time guard that refuses a
  secret-shaped public variable is a Clean line worth naming.
- `scan_secrets.py` names a service-role JWT or `sb_secret_` value wherever it is written
  down; a real one in the repository is Critical.
- Legacy `anon` and `service_role` keys are being deprecated by the end of 2026: a project still
  on them gets a Low finding with the rotation steps (create new, replace, confirm, retire).

## Auth flow

- The server reads the session with `getUser()` (verified against the Auth server), never
  `getSession()` alone, for any decision; the browser client is for UI state.
- **Callback and confirm routes** (`/auth/callback`, `/auth/confirm`): the `next`, `redirectTo`
  or `returnUrl` parameter is reduced to a relative path on the same origin, with protocol-relative
  (`//evil`) and backslash forms rejected, before any redirect. A sanitizer module with tests is
  the expected shape.
- **The site URL** used for `emailRedirectTo`, OAuth redirects and links in mail comes from
  configuration (`NEXT_PUBLIC_SITE_URL` or the framework's production URL); a fallback to
  `http://localhost:3000` is a Medium finding when a missing variable would send users there
  from production.
- **The redirect allow list** lives in `config.toml` (`auth.site_url`,
  `auth.additional_redirect_urls`) so it can be reviewed: the production entries are exact paths;
  wildcards (`https://*-<slug>.vercel.app/**`, `http://localhost:3000/**`) only for previews and
  local work (Redirect URLs guide). A project without `config.toml` has its auth settings only
  in the dashboard: a Medium finding with the request to commit the file.
- **Anti-enumeration**: sign-up and reset answer the same way whether the address exists; the
  sign-in error does not say which part was wrong.
- **Confirmations and limits**: e-mail confirmation on, OTP and magic-link expiry at most
  3600 s, CAPTCHA on sign-up, sign-in and password reset for a public site (Going into
  production); these are `config.toml` keys where the project tracks the file, dashboard lines
  otherwise.
- **Server Actions and route handlers** re-check the user and the object they act on
  (`review-security/checklist.md` §1); the proxy's redirect to the sign-in page is convenience,
  not the gate.

## Leaving the repository: the lines for the user

Auth settings that `config.toml` does not carry, the Security Advisor's lint results, SSL
enforcement, network restrictions, MFA on the Supabase account and the number of organisation
owners are on [dashboard.md](dashboard.md). An agent asks; it does not look.
