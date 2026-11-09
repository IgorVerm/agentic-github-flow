# Security sources: what the checks stand on

The sources behind [SKILL.md](SKILL.md), [checklist.md](checklist.md) and the two scripts of this
plugin, and behind the `check-web-deploy` skill of the web-deploy plugin. A check names its
source in a few words; the link, the date it was read and the version on the page are here. All
pages were read on **2026-10-25** with plain fetches, except the rows marked *read 2026-10-27*
(input, sessions, uploads, webhooks, mail and EU privacy), *read 2026-10-28* (Python web
backends, Google sign-in without Supabase, service accounts) and *read 2026-11-08* (osv-scanner).
Re-read a source before changing a check that rests on it, and update the date; a page that
moved is noted at the end.

Columns: *Source* (linked), *Version or date on the page* (none shown: "n/d"), *Backs*: the
checks that rest on it, named as the skill files name them.

## OWASP

| Source | Version | Backs |
|---|---|---|
| [ASVS 5.0.0](https://asvs.owasp.org/) (chapters at [github.com/OWASP/ASVS v5.0.0](https://github.com/OWASP/ASVS/tree/v5.0.0/5.0/en)) | 30 May 2025, stable | The areas of `checklist.md`: V1 Encoding and Sanitization, V2 Validation and Business Logic (input schemas, server-side prices; chapter list re-read 2026-10-27), V5 File Handling, V6 Authentication, V7 Session Management, V8 Authorization, V10 OAuth and OIDC, V13 Configuration (secrets live here), V16 Logging and Error Handling |
| [OWASP Top 10:2025](https://top10.owasp.org/2025/) | 2025 release | Area names and order: A01 Broken Access Control, A02 Security Misconfiguration, A03 Software Supply Chain Failures, A05 Injection, A07 Authentication Failures, A09 Logging and Alerting, A10 Mishandling of Exceptional Conditions |
| [Secrets Management cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) | n/d | Secrets never in source or images; detection in pre-commit hooks (`scan_secrets.py --staged`); separate production and development stores; rotate, prefer short-lived; CI treated as production |
| [Authorization cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) | n/d | Deny by default; enforce on the server, client checks are UX only; object-level checks (a random id is no protection); least privilege; fail closed; log authorization events |
| [OAuth 2.0 cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html) | n/d, cites RFC 9700 | Redirect URIs never an open redirector, no `http` outside loopback; PKCE for public clients; `state` or `nonce` against CSRF; implicit grant gone; audience-restricted tokens; refresh tokens rotated |
| [HTTP Headers cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html) | n/d | The header values in `check-web-deploy` (`vercel.md`): HSTS `max-age=63072000; includeSubDomains; preload`, `X-Frame-Options: DENY` or CSP `frame-ancestors`, `nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, the Cross-Origin-* trio |
| [Vulnerable Dependency Management cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Vulnerable_Dependency_Management_Cheat_Sheet.html) | n/d | Fix a transitive finding through its direct dependency; suppress per advisory id, after a verified fix, never by editing a version string; several vulnerability sources (`audit_dependencies.py` compares OSV with npm audit) |
| [Node.js Security cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Nodejs_Security_Cheat_Sheet.html) | n/d (`NPM_Security_Cheat_Sheet` is gone) | Lockfile committed, `npm ci`, `ignore-scripts=true` in `.npmrc`, check a package's name, downloads and age before adding it (typosquatting and model-invented names), granular short-lived registry tokens never in a committed `.npmrc` |
| [Session Management cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) | n/d, read 2026-10-27 | Cookies the application sets: `Secure`, `HttpOnly`, `SameSite=Strict` or `Lax` (defence in depth, not a CSRF control), no `Domain`; the server invalidates the session at sign-out, a cookie deletion alone does not; renew or end sessions after a password or privilege change |
| [Password Storage cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) | n/d, read 2026-10-27 | Own password hashing: Argon2id (19 MiB, t=2, p=1), else scrypt (N=2^17, r=8, p=1), bcrypt for legacy only (work factor 10+, 72-byte limit), PBKDF2 for FIPS (HMAC-SHA256 600,000 iterations); fast hashes (MD5, SHA-1, SHA-256) unsuitable |
| [File Upload cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) | n/d, read 2026-10-27 | Uploads: extension allow list, the client's `Content-Type` not trusted, generated file names, size limits, storage outside the webroot or on a separate host |
| [DOM-based XSS Prevention cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html) | n/d, read 2026-10-27 | DOM sinks `innerHTML`, `outerHTML`, `document.write`; `textContent` or DOMPurify instead |
| [API Security Top 10 2023, API4 Unrestricted Resource Consumption](https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption) | 2023 edition, read 2026-10-27 | A maximum size on every parameter, string and array; rate limits, stricter on sensitive operations; spending limits or billing alerts for paid providers (mail, SMS); the abuse-limit and mail lines of `checklist.md` §3 |
| [SSRF Prevention cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) | n/d, read 2026-10-28 | Allow-list target hosts; else refuse loopback, RFC 1918, link-local (169.254.169.254), `fc00::/7`, `fe80::/10`; validate the resolved addresses and connect to the checked one (DNS rebinding); no redirects |
| [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/llm-top-10/): [LLM01](https://genai.owasp.org/llmrisk/llm01-prompt-injection/), [LLM05](https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/), [LLM06](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/) | 2025 edition | The agent area of `checklist.md`: external content segregated and labelled, model output treated as untrusted input, least privilege and human approval for high-impact tool actions, complete mediation downstream of the model |

## Supabase

| Source | Version | Backs |
|---|---|---|
| [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security) | n/d | RLS enabled in a migration on every exposed table; one policy per operation, `to authenticated`; `(select auth.uid())` with a null guard; policies do not remove default grants; security definer functions with `search_path = ''` outside exposed schemas; a secret key bypasses RLS only without a user token |
| [API keys](https://supabase.com/docs/guides/getting-started/api-keys) | n/d | Publishable (`sb_publishable_`, legacy `anon`) for anything shipped; secret (`sb_secret_`, legacy `service_role`) only for servers, functions and jobs, "never put one in a browser, a shipped application, or source control"; rotation steps; legacy `anon`/`service_role` deprecated by the end of 2026 |
| [Redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls) | n/d | Site URL as default; `redirectTo` must match the allow list; glob rules; wildcards for local and preview only, exact paths in production; the Vercel preview pattern `https://*-<slug>.vercel.app/**` |
| [Login with Google](https://supabase.com/docs/guides/auth/social-sign-in/auth-google) | n/d | `check-web-deploy` (`google-auth.md`): Google Auth Platform setup (Audience, Data Access with `openid`, Branding, Verification), authorized JavaScript origins without localhost in production, the Supabase callback as the only redirect URI, the client secret through `env()` in `config.toml`, nonce validation on by default |
| [Going into production](https://supabase.com/docs/guides/deployment/going-into-prod) | n/d | The dashboard list: RLS on all tables, SSL enforcement, network restrictions, MFA on the account, several organisation owners, e-mail confirmations, OTP expiry at most 3600 s, custom SMTP, Security Advisor, CAPTCHA on sign-up, sign-in and reset |
| [Database linter and Security Advisor](https://supabase.com/docs/guides/observability/advisors) | n/d | Lint numbers on the dashboard list: errors 0002 `auth_users_exposed`, 0010 `security_definer_view`, 0013 `rls_disabled_in_public`, 0015 `rls_references_user_metadata`, 0023 `sensitive_columns_exposed`; warnings 0003 `auth_rls_initplan`, 0006 `multiple_permissive_policies`, 0011 `function_search_path_mutable`, 0014 `extension_in_public`, 0024 `permissive_rls_policy`, 0025 `public_bucket_allows_listing`; info 0007, 0008, 0012 |
| [Hardening the Data API](https://supabase.com/docs/guides/api/securing-your-api) | n/d | A dedicated exposed schema; revoke default privileges from `anon`, `authenticated`, `service_role`; review every security definer function |
| [User sessions](https://supabase.com/docs/guides/auth/sessions) | n/d, read 2026-10-27 | A refresh token is used once, reuse after the 10 s interval revokes the session; JWT expiry 1 hour by default, not below 5 minutes; time-boxed sessions and inactivity timeout on Pro and up; HttpOnly cookies are not feasible when browser code reads the session |
| [Signing out](https://supabase.com/docs/guides/auth/signout) | n/d, read 2026-10-27 | `signOut()` defaults to the global scope in JavaScript and destroys the sessions' refresh tokens; access tokens already issued stay valid until they expire |
| [Postgres Changes](https://supabase.com/docs/guides/realtime/postgres-changes) | n/d, read 2026-10-27 | Tables join the `supabase_realtime` publication to stream; every event is authorized per subscriber; RLS is not applied to `DELETE` events |
| [Realtime Authorization](https://supabase.com/docs/guides/realtime/authorization) | n/d, read 2026-10-27 | Private channels (`private: true`); `select` and `insert` policies on `realtime.messages` per extension (Broadcast, Presence); turning off "Allow public access" enforces private channels |
| [Custom SMTP](https://supabase.com/docs/guides/auth/auth-smtp) | n/d, read 2026-10-27 | The default sender delivers only to the project team's addresses, about 2 messages an hour, no SLA; custom SMTP for production; configure SPF, DKIM and DMARC with the sending service |
| [Storage access control](https://supabase.com/docs/guides/storage/security/access-control) | n/d | Policies on `storage.objects` by `bucket_id` and folder; a public bucket is readable regardless of policies; secret keys bypass all of them |

## Vercel and Next.js

| Source | Version | Backs |
|---|---|---|
| [Config and Secret environment variables](https://vercel.com/docs/environment-variables/sensitive-environment-variables); [overview](https://vercel.com/docs/environment-variables) | 2026-08-28; 2026-09-17 | Secret type for passwords, keys and tokens; scopes Production, Preview (per branch), Development; changes apply to new deployments only; build logs redact Secret values of 32+ characters; the team policy for separate production values |
| [Framework env vars](https://vercel.com/docs/environment-variables/framework-environment-variables); [system env vars](https://vercel.com/docs/environment-variables/system-environment-variables) | 2026-09-16; 2026-07-15 | A framework prefix (`NEXT_PUBLIC_`, `VITE_`, `PUBLIC_`) exposes the value to the browser; `VERCEL_URL` is unusable behind Standard Protection, `VERCEL_PROJECT_PRODUCTION_URL` always set |
| [Next.js environment variables](https://nextjs.org/docs/app/guides/environment-variables) | 2026-08-25 | Server-only by default; `NEXT_PUBLIC_` inlined at build; `.env*` files not committed |
| [Deployment Protection](https://vercel.com/docs/deployment-protection); [Vercel Authentication](https://vercel.com/docs/deployment-protection/methods-to-protect-deployments/vercel-authentication); [Protection Bypass for Automation](https://vercel.com/docs/deployment-protection/methods-to-bypass-deployment-protection/protection-bypass-automation) | 2026-09-15; 2026-09-15; 2026-09-16 | Vercel Authentication on all plans, the recommended method; Standard Protection covers everything but production domains; Password Protection is Pro and paid; disabling leaves every deployment open; the bypass header and its secret |
| [Security headers](https://vercel.com/docs/cdn-security/security-headers) | 2026-03-05 | Start with `Content-Security-Policy-Report-Only`; no `unsafe-inline`, `unsafe-eval` or wildcard sources; CSP is a second line of defence |
| [Vercel WAF](https://vercel.com/docs/vercel-firewall/vercel-waf); [Attack Mode](https://vercel.com/docs/vercel-firewall/attack-mode); [security overview](https://vercel.com/docs/security) | 2026-07-29; 2026-08-11; 2026-08-11 | Dashboard options for the site's owner: custom rules on all plans, Attack Mode free but temporary and hostile to standalone APIs, HTTPS everywhere, shared responsibility |
| [Vercel OIDC: Google Cloud](https://vercel.com/docs/oidc/gcp) | 2026-09-01, read 2026-10-28 | A Vercel deployment reaches Google APIs through Workload Identity Federation with Vercel's OIDC token, impersonating a service account without a key; all plans |
| [Next.js CSP guide](https://nextjs.org/docs/app/guides/content-security-policy) | 2026-03-20 | The nonce route in `proxy.ts` with `strict-dynamic`, dynamic rendering, no PPR; the policy template; static `headers()` when nonces are not used |
| [Next.js data security](https://nextjs.org/docs/app/guides/data-security); [blog, 2023](https://nextjs.org/blog/security-nextjs-server-components-actions) | 2026-10-06, re-read 2026-10-27 | Server Actions are POST only and compare `Origin` with the host (route handlers get no such check); rate-limit expensive operations such as sending mail; A server-only Data Access Layer that authorizes and returns minimal DTOs; `import 'server-only'`; every Server Action re-checks authentication, authorization and ownership and treats its arguments as hostile; validate `searchParams`, headers, form data; `allowedOrigins` behind proxies; the audit list for `proxy.ts` and `route.ts` |
| [`serverActions` reference](https://nextjs.org/docs/app/api-reference/config/next-config-js/serverActions) | 2026-08-26, read 2026-10-27 | `allowedOrigins`: only the same origin by default, a request without `Origin` passes with a warning; `bodySizeLimit` 1 MB by default |
| [`public` folder](https://nextjs.org/docs/app/api-reference/file-conventions/public-folder) | 2025-06-16, read 2026-10-27 | Every file in `public/` is served from the base URL |
| [`proxy.js` reference](https://nextjs.org/docs/app/api-reference/file-conventions/proxy) | 2026-09-04 | `middleware.ts` renamed `proxy.ts` in 16.0; never the sole authorization; a matcher gap also skips Server Function calls |
| [CVE-2025-29927 postmortem](https://vercel.com/blog/postmortem-on-next-js-middleware-bypass) | March 2025 | Why middleware or proxy is never the only gate; fixed in 14.2.25 and 15.2.3; self-hosted `next start` affected |

## Google

| Source | Version | Backs |
|---|---|---|
| [OAuth 2.0 for Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server) | n/d | Exact-match redirect URIs (scheme, case, trailing slash), HTTPS except localhost, no wildcards or fragments; random `state` verified on return; client secret outside the source tree; incremental authorization; Cross-Account Protection |
| [OAuth for native apps](https://developers.google.com/identity/protocols/oauth2/native-app) | 2026-10-16 | PKCE: verifier 43 to 128 characters, `S256` |
| [OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect) | 2026-06-15 | ID token validation: signature, `iss`, `aud`, `exp`; the `hd` claim "must" be checked server-side when restricting to a domain, the `hd` parameter is UI only; `sub` as identifier, not e-mail; `nonce` |
| [App configuration and verification](https://support.google.com/cloud/answer/15549945); [brand verification](https://support.google.com/cloud/answer/13464321) | n/d | Testing status: 100 test users, authorizations expire after seven days; unverified apps with sensitive scopes capped at 100 users for the project's lifetime; authorized domains verified in Search Console; narrowest scopes |
| [OAuth best practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices) | 2026-05-20 | Credentials in a secret manager, never committed; tokens encrypted and revoked when done; verify `state`; remove unused OAuth clients (deleted after six months idle) |
| [Verify the Google ID token on your server side](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token) | 2025-12-22, read 2026-10-28 | `checklist.md`, stack notes, Google sign-in without Supabase: signature, `aud` equal to a client ID, `iss` `accounts.google.com` or `https://accounts.google.com`, `exp`; Python `id_token.verify_oauth2_token(token, requests.Request(), CLIENT_ID)`, Node `verifyIdToken({ idToken, audience })`; `hd` checked by the caller; `sub` as the key, `email` trusted with `email_verified`; the `g_csrf_token` cookie against the body field |
| [Best practices for managing service account keys](https://docs.cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys) | 2026-10-26, read 2026-10-28 | Prefer attached service accounts and Workload Identity Federation; key creation as the exception; *Disable service account key creation* and *upload* constraints (enforced by default for organisations created since 3 May 2024); *Service Account Key Exposure Response* `DISABLE_KEY`; never in source control, a committed key is deleted in IAM at once; rotate |
| [Best practices for using service accounts securely](https://docs.cloud.google.com/iam/docs/best-practices-service-accounts) | 2026-10-26, read 2026-10-28 | One dedicated service account per application, no default accounts (which may hold Editor); least privilege; no project-level access to service accounts (Token Creator or Service Account User there impersonates them all); disable unused accounts before deleting |
| [Cross-Account Protection (RISC)](https://developers.google.com/identity/protocols/risc) | 2026-03-22 | Named as an option on the dashboard list: security event tokens to a registered HTTPS receiver |

## Python web backends

| Source | Version | Backs |
|---|---|---|
| [Django deployment checklist](https://docs.djangoproject.com/en/stable/howto/deployment/checklist/) | Django 6.1, read 2026-10-28 | `check --deploy` against the production settings; never `DEBUG` in production (source excerpts, local variables, settings); `SECRET_KEY` large, random, secret, from the environment, used nowhere else; `ALLOWED_HOSTS` required, a wildcard needs own Host validation; `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` |
| [Django CSRF reference](https://docs.djangoproject.com/en/stable/ref/csrf/) | Django 6.1, read 2026-10-28 | `@csrf_exempt` removes the middleware's protection from a view; the middleware checks `Origin` against the host and `CSRF_TRUSTED_ORIGINS`, which widens what it accepts |
| [Flask: debugging application errors](https://flask.palletsprojects.com/en/stable/debugging/) | Flask 3.1, read 2026-10-28 | Never the development server or the debugger in production: it executes arbitrary Python from the browser, its PIN is not to be relied on; `app.run(debug=True)` enables it |
| [Flask: templates](https://flask.palletsprojects.com/en/stable/templating/) | Flask 3.1, read 2026-10-28 | Autoescaping on for `.html`, `.htm`, `.xml`, `.xhtml`, `.svg` with `render_template()`; `Markup`, the `safe` filter and `{% autoescape false %}` turn it off |
| [Jinja API: autoescaping](https://jinja.palletsprojects.com/en/stable/api/#autoescaping) | Jinja 3.1, read 2026-10-28 | Off unless configured (`autoescape=False` in the signature); `select_autoescape()` is the recommended configuration; `Markup` and the `safe` filter skip escaping |
| [FastAPI: CORS](https://fastapi.tiangolo.com/tutorial/cors/) | n/d, read 2026-10-28 | With `allow_credentials=True`, none of `allow_origins`, `allow_methods`, `allow_headers` may be `['*']`; list the origins explicitly |
| [Starlette `middleware/cors.py`](https://github.com/encode/starlette/blob/1.10.0/starlette/middleware/cors.py) | 1.10.0 and 1.0.0, read 2026-10-28 | With `allow_origins=["*"]` and `allow_credentials=True` the middleware sends back the request's own `Origin` and allows credentials, on preflight and on the response: any origin is trusted (what the FastAPI docs do not say) |
| [Flask: security considerations](https://flask.palletsprojects.com/en/stable/web-security/) | Flask 3.1, read 2026-10-28 | No built-in CSRF protection ("Why does Flask not do that for you?"); autoescaping in Jinja, but not for `Markup` on user data |
| [Django: automatic HTML escaping](https://docs.djangoproject.com/en/stable/ref/templates/language/#automatic-html-escaping) | Django 6.1, read 2026-10-28 | Every variable escaped by default; the `safe` filter and `{% autoescape off %}` turn it off |
| [Requests: advanced usage](https://requests.readthedocs.io/en/latest/user/advanced/) | latest, read 2026-10-28 | `verify=False` accepts any certificate and hostname: man in the middle; requests do not time out unless a timeout is set |

## Mail and payments

| Source | Version | Backs |
|---|---|---|
| [Resend: domains](https://resend.com/docs/dashboard/domains/introduction); [add a domain](https://resend.com/docs/add-a-domain); [API keys](https://resend.com/docs/dashboard/api-keys/introduction) | n/d, read 2026-10-27 | `check-web-deploy` (its mail checks): a verified domain before sending; send from subdomains; DKIM and SPF records (`TXT`, `MX` or `CNAME`) exactly as generated, return path `send.<domain>` by default; a key's permission and optional domain restriction |
| [Resend: DMARC](https://resend.com/docs/dashboard/domains/dmarc) | n/d, read 2026-10-27 | A TXT record at `_dmarc`; start with `p=none`, then `quarantine` or `reject` once legitimate mail passes; `rua` for reports; SPF or DKIM passing is enough |
| [RFC 7208, SPF](https://www.rfc-editor.org/rfc/rfc7208.html) | April 2014, read 2026-10-27 | One SPF record per name (more is a permerror, §3.2, §4.5); the default qualifier is `+`, so a bare `all` passes every sender |
| [Stripe: webhooks](https://docs.stripe.com/webhooks) | n/d, read 2026-10-27 | Verify `Stripe-Signature` over the raw body, constant-time comparison, timestamp tolerance 5 minutes by default and never 0 (replay), deduplicate by event id |
| [Mollie: webhooks](https://docs.mollie.com/reference/webhooks) | n/d, read 2026-10-27 | Classic webhooks send only an `id`; the receiver fetches the object's status from the API |

## Privacy (EU)

| Source | Version | Backs |
|---|---|---|
| [GDPR, Regulation (EU) 2016/679](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng) (read through [gdpr-info.eu](https://gdpr-info.eu/), since EUR-Lex returned no text to a fetch) | 2016, read 2026-10-27 | `check-web-deploy` (its privacy checks): Art. 5(1)(e) storage limitation; Art. 13 the notice's contents; Art. 17 erasure without undue delay; Art. 30 record of processing, the 30(5) exemption not for processing that is not occasional; Art. 33 breach to the authority within 72 hours |
| [GBA: cookies](https://www.gegevensbeschermingsautoriteit.be/burger/thema-s/internet/cookies) | n/d, read 2026-10-27 | Consent before cookies that are not strictly necessary; no pre-ticked box, browsing on is no consent, no cookie wall, withdrawal as easy as consent; analytics cookies in principle not exempt; session and language cookies exempt |
| [Vercel: function regions](https://vercel.com/docs/functions/configuring-functions/region) | 2026-08-11, read 2026-10-27 | New projects run functions in `iad1` (Washington, D.C.) unless `vercel.json` `regions` or the project settings choose another |
| [Vercel Web Analytics: privacy](https://vercel.com/docs/analytics/privacy-policy) | 2026-06-26, read 2026-10-27 | No third-party cookies; a visit is a hash of the request, discarded after 24 hours |
| [Supabase: regions](https://supabase.com/docs/guides/platform/regions) | n/d, read 2026-10-27 | EU regions Frankfurt, Ireland, Paris, Stockholm; London and Zurich are not EU; region choice is "a data-location control, not proof of regulatory compliance" |
| [Supabase DPA](https://supabase.com/legal/dpa); [Vercel DPA](https://vercel.com/legal/dpa); [Resend DPA](https://resend.com/legal/dpa) | n/d, read 2026-10-27 | Each is part of the provider's terms and binding on accepting them; transfers under the 2021 EU standard contractual clauses (Resend also names the EU-U.S. Data Privacy Framework and processes primarily in the United States) |

## Anthropic (Claude Code)

| Source | Version | Backs |
|---|---|---|
| [Security](https://code.claude.com/docs/en/security) | n/d | Agent area: deny `curl`/`wget` and use sandbox network isolation when enforcement must not depend on command text; WebFetch returns a separate model's summary; never pipe untrusted content into a session; verify changes to critical files; MCP servers only from trusted authors |
| [Permissions](https://code.claude.com/docs/en/permissions) | n/d | `Read` deny rules for secret files (they cover `cat`, `head`, `sed`, `tee`, not `grep -r` or scripts); deny beats allow; a PreToolUse hook block beats allow; Bash rule limits (`sh -c`, a binary by path) |
| [Sandboxing](https://code.claude.com/docs/en/sandboxing) | n/d | The sandbox wraps shell commands only; reads of `~/.ssh` and `~/.aws` are allowed unless `denyRead`; env vars inherited unless masked; network through a proxy with an empty allow list; not a complete boundary |
| [Automated security reviews](https://support.claude.com/en/articles/11932705-automated-security-reviews-in-claude-code) | 16 March 2026 | `/security-review`: on-demand pass over the branch (injection, XSS, auth flaws, insecure data handling, dependency vulnerabilities), "should complement, not replace" other practices; step 4 of [SKILL.md](SKILL.md) |
| [security-guidance plugin](https://code.claude.com/docs/en/security-guidance) | n/d | Not used by this skill: hooks on every edit and an end-of-turn review by a separate model call; "none of the layers block writes or commits" |
| [claude-security plugin](https://code.claude.com/docs/en/claude-security) | n/d | The opt-in one-time deep scan: multi-agent, writes `CLAUDE-SECURITY-<timestamp>/` with Markdown, JSONL and SARIF, patches never applied automatically, reads source and "not a running site or deployed service" |

## OpenAI (Codex)

| Source | Version | Backs |
|---|---|---|
| [Agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security) | n/d (Codex 0.114+) | Sandbox modes (`read-only`, `workspace-write`, `danger-full-access`), network off by default, `--yolo` not recommended; "treat web results as untrusted", cached web search against live-content injection; Codex Cloud strips secrets before the agent phase |
| [Sandboxing](https://learn.chatgpt.com/docs/sandboxing) | n/d | Seatbelt on macOS, bubblewrap on Linux; applies to spawned commands |
| [Safety in building agents](https://developers.openai.com/api/docs/guides/agent-builder-safety) | n/d | Prompt injection defined as untrusted text entering the system to exfiltrate data through downstream tool calls; untrusted input never drives behaviour directly; keep tool approvals on; agents "can still make mistakes or be tricked" |

## Scanners and GitHub

| Source | Version | Backs |
|---|---|---|
| [npm audit](https://docs.npmjs.com/cli/v11/commands/npm-audit/) | npm 11.21.1 | `--audit-level`, `--omit dev`, `npm audit signatures`; the cross-check in `audit_dependencies.py` |
| [pnpm audit](https://pnpm.io/cli/audit); [pip-audit](https://pypi.org/project/pip-audit/); [cargo-audit](https://github.com/rustsec/rustsec/blob/main/cargo-audit/README.md) | v12; 2.10.1 (June 2026); n/d | What `audit_dependencies.py` replaces and may be cross-checked against; all query OSV or its mirrors (RustSec, PyPI advisory database) |
| [osv-scanner](https://google.github.io/osv-scanner/): [output](https://google.github.io/osv-scanner/output/), [scan source and call analysis](https://google.github.io/osv-scanner/usage/scan-source), [offline mode](https://google.github.io/osv-scanner/usage/offline-mode/); source at [v2.7.0](https://github.com/google/osv-scanner/tree/v2.7.0) (`pkg/models/results.go`, `internal/sourceanalysis/rust.go`, `pkg/osvscanner/scan.go`) | v2.7.0 (released 2026-10-12); read 2026-11-08 | The second opinion in `audit_dependencies.py`: the JSON shape (`results[].packages[].groups` with `ids`, `aliases`, `max_severity`, `experimental_analysis.called`); exit 0, 1 with vulnerabilities, 128 no packages; transitive resolution of manifests through deps.dev is on unless `--no-resolve`; the default `directory` plugins send file hashes of vendored folders to api.osv.dev (`/v1experimental/determineversion`; measured 2026-11-08) unless `--x-disable-plugins=directory`; Rust call analysis runs `cargo build --workspace --all-targets --release` with its own RUSTFLAGS in the project's `target/release`, runs build scripts, and reads ELF only (measured on macOS: "bad magic number", no analysis) |
| [OSV API](https://google.github.io/osv.dev/api/) and [ecosystems](https://osv-vulnerabilities.storage.googleapis.com/ecosystems.txt) | measured 2026-10-25 | `POST /v1/querybatch` returns ids per package, `GET /v1/vulns/<id>` the record; ecosystems used: npm, PyPI, crates.io, Packagist; no ecosystem for Node, PHP or Homebrew runtimes |
| [endoflife.date API](https://endoflife.date/docs/api) ([all.json](https://endoflife.date/api/all.json), `<product>.json`); [npm registry](https://registry.npmjs.org/next) `dist-tags.latest`; [PyPI JSON](https://pypi.org/pypi/requests/json) `info.version` | measured 2026-10-25: 485 products, among them nextjs, react, nodejs, python, eslint, django, express, vue, angular, nuxt, svelte, php, postgresql, rust | `audit_dependencies.py --upgrades`: support windows per release cycle and the latest release of each direct dependency; crates.io is not queried (its crawler policy asks for contact details in the User-Agent, which is personal data) |
| [gitleaks](https://github.com/gitleaks/gitleaks); [trufflehog](https://github.com/trufflesecurity/trufflehog) | v8.30.1 (feature complete); v3.99.7 | Optional cross-checks of `scan_secrets.py`: `gitleaks git -v <repo>`, `trufflehog git file://. --results=verified` |
| [GitHub secret scanning](https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning); [push protection](https://docs.github.com/en/code-security/concepts/secret-security/push-protection); [plans](https://docs.github.com/en/get-started/learning-about-github/githubs-plans) | n/d | Free only on public repositories; private repositories need Secret Protection on Team or Enterprise; on a private repository without it, the local scanner is the only control |

## Installing osv-scanner (optional)

`audit_dependencies.py` asks osv-scanner for a second opinion when it is on PATH and works as
before without it. The script pins the release (`OSV_SCANNER_PIN`, 2.7.0) and says when the
installed version differs. The user installs it; a review never does. Take the asset for the
machine from the [v2.7.0 release](https://github.com/google/osv-scanner/releases/tag/v2.7.0),
check it, and put it on PATH as `osv-scanner`. Two checksums are recorded here; they matched the
release's `osv-scanner_SHA256SUMS` and GitHub's own asset digest on 2026-11-08:

| Asset of v2.7.0 | SHA-256 |
|---|---|
| `osv-scanner_darwin_arm64` (55,336,530 bytes) | `d4926ef8da134332543be276dff157e4c170f99ad91fc48e89448a8816bdf70b` |
| `osv-scanner_linux_arm64` (53,870,752 bytes) | `4061ef4c021ed3c47f203b818f337e351336cc5cd67c0274fc36bd1dfc728dd7` |

Every other asset (Linux on amd64, Windows, Intel Macs) has no checksum recorded here. For those,
checking against the release's own `osv-scanner_SHA256SUMS` catches a corrupted download, not a
replaced release, since both come from the same place.

```bash
gh release download v2.7.0 -R google/osv-scanner -p osv-scanner_darwin_arm64 -D <new empty folder>
echo "d4926ef8da134332543be276dff157e4c170f99ad91fc48e89448a8816bdf70b  osv-scanner_darwin_arm64" | (cd <folder> && shasum -a 256 -c)
install -m 0755 <folder>/osv-scanner_darwin_arm64 ~/.local/bin/osv-scanner
osv-scanner --version
```

On Linux on arm64 the same with the `linux_arm64` asset and `sha256sum -c`. The release also
carries SLSA provenance (`multiple.intoto.jsonl`); checking it needs `slsa-verifier`, so the
checksum is the check here. `--reachability` (Rust call analysis) works on Linux only: the row
above says why. Inside Claude Code's sandbox, osv-scanner needs `api.osv.dev` in
`sandbox.network.allowedDomains`, the one host it shares with the script. On macOS it also
verifies certificates through the system's trust service, which the sandbox closes: without
`sandbox.enableWeakerNetworkIsolation: true` it fails (`x509: OSStatus -26276`, exit 127) and the
audit reports it as skipped (measured 2026-11-08). That setting weakens network isolation for
every sandboxed command, not only this one, so it is the user's decision; a review never changes
it, and runs without the second opinion instead. A newer release is a change for this plugin's maintainers: read its notes,
change the pin in the script and this section together, and run the repository's
`tests/audit_dependencies.py`.

## Moved or unreachable on 2026-10-25

The Supabase and GitHub links above are the final locations after redirects (API keys, Login
with Google, Advisors, Securing your API; secret scanning and push protection moved under
`concepts/secret-security`). OWASP, Anthropic and Google pages answer 403 to a plain Python
client and 200 to a browser user agent: a link checker needs the latter.
`owasp.org/asvs` → `asvs.owasp.org`; `owasp.org/Top10/2025` → `top10.owasp.org/2025`;
`nextjs.org/blog/cve-2025-29927` → the Vercel postmortem above; `vercel.com/docs/headers/security-headers`
→ `/docs/cdn-security/security-headers`; `…/attack-challenge-mode` → `/docs/vercel-firewall/attack-mode`;
`developers.openai.com/codex/…` → `learn.chatgpt.com/docs/…`; `code.claude.com/docs/en/iam` now
serves authentication, permissions are at `/docs/en/permissions`. Gone: OWASP
`NPM_Security_Cheat_Sheet.html`. Not obtainable: a GitHub page stating Secret Protection's price.
Gaps in the sources themselves: Google's web-server OAuth page does not describe PKCE (the
native-app page does); only the OpenID Connect page mentions `hd`; the Supabase Google page does
not mention `hd` at all, so the domain-restriction check in `google-auth.md` combines the two.
