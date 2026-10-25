# Google sign-in through Supabase Auth: what the repository must show

Read with [SKILL.md](SKILL.md). **Status, 2026-10-25: written from the vendors' documentation,
not yet exercised in a live project**. The first project that adopts Google
sign-in verifies every line here against what it sees, corrects this file in the same change
and removes this paragraph. Sources: Supabase's Login with Google guide, Google's OAuth 2.0 for
Web Server Applications, OpenID Connect, app configuration and verification, OAuth best
practices and Cross-Account Protection pages, the OWASP OAuth cheat sheet
(read 2026-10-25).

## The flow, in one paragraph

The browser calls `supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo } })`;
Supabase Auth sends the user to Google with Supabase's own callback
(`https://<project-ref>.supabase.co/auth/v1/callback`) as the OAuth redirect URI; Google returns
to Supabase, which validates the ID token and then redirects to `redirectTo`, which must be on
the project's redirect allow list; the app's `/auth/callback` route exchanges the code for a
session (`exchangeCodeForSession`) and redirects to a sanitized `next` path. The application
never sees Google's client secret, and Google never sees the application's callback.

## In the repository

- **Provider configuration** in `supabase/config.toml`: `[auth.external.google]` with
  `enabled = true`, `client_id`, and `secret = "env(SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_SECRET)"`;
  the secret's value only in an ignored `.env`, its name in `.env.example`. Nonce validation
  stays on (`skip_nonce_check = false`, the default).
- **The callback route** exchanges the code server-side and treats `next` as untrusted
  ([supabase.md](supabase.md) §Auth flow). A PKCE flow is what the Supabase SSR client uses by
  default; a project that switched to the implicit flow gets a High finding (implicit grant is
  removed in OAuth 2.1; OWASP OAuth cheat sheet).
- **Identity**: the application keys its own tables on `auth.users.id` (Supabase's `sub`), never
  on the e-mail address, which can change and can be re-assigned (Google OIDC: use `sub`).
- **Domain restriction** (a site for one organisation, Google Workspace): Supabase passes the
  `hd` hint when `[auth.external.google]` sets `url` or query params for it, but Google's own
  words are that the `hd` parameter is a UI optimisation and "you must check this claim" server
  side. In a Supabase project that means an auth hook or a database trigger on `auth.users` that
  rejects or deletes a user whose identity's `hd` claim (in `raw_user_meta_data` or the
  identity data) is not the accepted domain, or an RLS policy that grants nothing to such a
  user; an e-mail suffix check (`like '%@domain'`) is not the same check and is a High finding
  when it is the only one. A general public site has no domain restriction and skips this.
- **Scopes**: `openid`, `email`, `profile` and nothing more unless a feature needs it (Google
  brand verification: narrowest scopes); a sensitive or restricted scope changes the
  verification requirements and the 100-user cap of an unverified app.
- **Local development** uses the local callback `http://127.0.0.1:54321/auth/v1/callback` and a
  separate OAuth client or the same client with that URI added; production configuration must
  not keep localhost origins (Supabase Google guide).

## On Google's side: the lines for the user

These are read only in Google Cloud Console and go on [dashboard.md](dashboard.md):

- The OAuth client is a **Web application** client; **Authorized redirect URIs** contain exactly
  the Supabase callback (scheme, host, path, no trailing slash difference: Google matches
  exactly) and nothing else for production; **Authorized JavaScript origins** contain the
  production origin and no localhost.
- The **consent screen** (Google Auth Platform: Branding, Audience, Data Access): user type
  External for a public site, Internal for one Workspace; publishing status **In production**
  (Testing caps the app at 100 test users whose grants expire after seven days); the app's
  home page and privacy policy URLs resolve; every **authorized domain** is verified in Search
  Console.
- The client secret was created once and lives only in the Supabase secret and the local
  `.env`; it has not been pasted into an issue, a chat or a document (`scan_secrets.py`
  recognises the `GOCSPX-` prefix). Rotate it if in doubt: a second secret, switch, delete the
  first.
- **Unused OAuth clients** are deleted (Google deletes inactive ones after six months and the
  app then breaks silently); **Cross-Account Protection** (RISC) is an option for a site that
  wants Google's sign-out and compromise events.
