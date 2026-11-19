# Sign-in through Identity-Aware Proxy: what the repository must show

Read with [SKILL.md](SKILL.md). **Status, 2026-11-19: written from Google's documentation and
the library's source, not yet exercised in a live project.** The first project on this route
verifies every line, corrects this file in the same change and removes this paragraph. Sources
(read 2026-11-19): IAP's *Enable IAP for Cloud Run*, *Securing your app with signed headers*,
*Getting the user's identity*, *Manage access to IAP-secured resources*, *Use custom OAuth
clients with IAP* and *Using query parameters and headers*; Cloud Run's *Configure IAP for Cloud Run* (all on docs.cloud.google.com);
`src/auth/oauth2client.ts` of `googleapis/google-auth-library-nodejs` on GitHub.

IAP signs the user in with their Google account before a request reaches the service; with
Google's own OAuth client it admits only accounts of the project's organisation, which fits a
Workspace-only site. Whether the service can be reached around IAP is
[cloud-run.md](cloud-run.md) §Who can reach the service. This file is what the application
itself must do.

## The application verifies the signed header

Every request that reads or changes data verifies `x-goog-iap-jwt-assertion`, server side, in
the one module that tells who the user is (the proxy and the Data Access Layer use it; the
proxy is not the authorization, as in [vercel.md](vercel.md) §Proxy, Server Actions, runtime):

- **Signature**: ES256, with a key whose `kid` is in
  `https://www.gstatic.com/iap/verify/public_key` (or `public_key-jwk`). IAP rotates the keys:
  cache them and refresh the cache when a `kid` is unknown.
- **`aud`** equals the exact expected value, from configuration: for IAP on the Cloud Run
  service `/projects/<project number>/locations/<region>/services/<service name>`, for IAP on a
  load balancer `/projects/<project number>/global/backendServices/<backend service id>`.
- **`iss`** is `https://cloud.google.com/iap`.
- **`exp` and `iat`**: not expired, not issued in the future, within a short skew (Google's
  sample allows 30 seconds; a token lives about ten minutes).
- **The user** is the token's `email` and `sub`. Never `x-goog-authenticated-user-email` or
  `x-goog-authenticated-user-id` alone: those unsigned headers are forged by anyone who reaches
  the service around IAP. Trusting them is Critical.

**The trap in the Node sample.** Google's Node sample calls
`OAuth2Client.verifySignedJwtWithCertsAsync(jwt, keys, expectedAudience, ['https://cloud.google.com/iap'])`
and sets `expectedAudience` only for App Engine and backend services: for Cloud Run it stays
`null`. The library then skips the `aud` check, as it skips the `iss` check when no issuers are
passed, and by default allows 300 seconds of skew and a lifetime of a day. So a token IAP signed
for any other application is accepted. The expected shape: `expectedAudience` set to the Cloud
Run value above, the issuer list passed, and `maxExpiry` lowered. An `aud` check that is missing
or that can be `null` is High; with the service's ingress open around IAP, Critical.

## What the application decides itself

- **Who may do what** stays in the application: IAP decides who may enter, not which rows a user
  may read. Authorization per record, as in `review-security/checklist.md`, keyed on the
  verified `sub` or `email`.
- **No route that skips the check**: health checks and webhooks that must work without a user are
  named, return nothing personal, and are listed in the issue. A path excluded from the
  verification by a matcher or an early return is a finding of the severity of what it serves.
- **Sign-out**: `?gcp-iap-mode=CLEAR_LOGIN_COOKIE` clears IAP's cookies (*Using query parameters
  and headers*), but the user stays signed in to Google, so the next request enters again. On a
  shared device, signing out of Google is how one leaves: the site says so. Advice, not a
  finding.
- **Local development** does not fake the header in code that ships: a bypass is behind a
  development-only setting the production build cannot enable.
