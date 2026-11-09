# The dashboard list for the user

Read with [SKILL.md](SKILL.md). This is the template for step 8: copy the lines that apply to
the project, fill in the project's names, drop the rest, translate it into the user's language,
and post it as one signed comment on the owning issue after the findings. Each line says where
to look and what the correct state is; the user ticks it or writes what they see. An agent never
opens these dashboards itself. The sources behind each line are the same as in
[supabase.md](supabase.md), [vercel.md](vercel.md), [mail.md](mail.md), [privacy.md](privacy.md)
and [google-auth.md](google-auth.md).

## Supabase (Dashboard → project)

- [ ] **Authentication → URL Configuration**: Site URL is `https://<production domain>`; the
      Redirect URLs are exactly the production callback path(s) plus, for previews only,
      `https://*-<team-slug>.vercel.app/**`; no `http://localhost` entry in a production project.
- [ ] **Authentication → Providers → Email**: confirm e-mail on; OTP expiry at most 3600 s;
      *Prevent use of leaked passwords* on; minimum password length as the project documents.
- [ ] **Authentication → Providers → Google** (when used): enabled, Client ID matches the Google
      Cloud client, the secret is set; *Skip nonce check* off.
- [ ] **Authentication → Rate Limits and Attack Protection**: default rate limits on; CAPTCHA
      enabled for sign-up, sign-in and password reset on a public site.
- [ ] **Authentication → Sessions**: refresh token reuse detection on, its interval at the
      default 10 s; JWT expiry at the default 3600 s unless the issue says otherwise (never
      below 300 s).
- [ ] **Authentication → Emails → SMTP Settings** (when the site sends auth mail): custom SMTP
      on, the sender on the project's own domain ([mail.md](mail.md)).
- [ ] **Realtime → Settings** (when Realtime is used): public channel access off unless the
      issue names a public channel.
- [ ] **Advisors → Security Advisor**: zero errors (0002, 0010, 0013, 0015, 0019, 0023); each
      warning (0003, 0006, 0011, 0014, 0016, 0024, 0025, 0028, 0029) either fixed or named on the
      issue with its reason. Paste the counts, not the table.
- [ ] **Settings → API Keys**: the application uses the publishable and secret keys (or the
      legacy keys with a rotation date noted); no key has been exposed; legacy keys disabled once
      the rotation is done.
- [ ] **Settings → Database**: SSL enforcement on; network restrictions set when the database is
      reached from fixed addresses only.
- [ ] **Organization → Team**: MFA enforced for the account(s); at least two owners.
- [ ] **Storage**: every bucket's public flag matches [supabase.md](supabase.md) §Tables; size
      and MIME limits set on upload buckets.

## Vercel (Project → Settings)

- [ ] **Environment Variables**: every secret is of type Secret; production values exist in
      Production only; Preview and Development hold test or separate-project values; nothing
      secret-shaped under `NEXT_PUBLIC_` or `VITE_`; the names match `.env.example`.
- [ ] **Deployment Protection**: Vercel Authentication on, Standard Protection; Protection
      Bypass for Automation only if an automation needs it, its secret stored as a Secret
      variable.
- [ ] **Domains**: the production domain is assigned; HTTPS redirect on; the `*.vercel.app`
      production URL redirects to the custom domain (or is protected under Standard Protection).
- [ ] **Git**: production branch is `main`; previews only from this repository's branches;
      deploy hooks, if any, have their URLs stored as secrets.
- [ ] **Firewall**: no rule needed at launch; know where Attack Mode is for an incident.
- [ ] **Headers in the live response**: `curl -sI https://<production domain>` shows the headers
      of [vercel.md](vercel.md) §Headers (the user runs it, or an agent runs it against the public
      production URL only: a read of a public page carries no personal data).

## Mail (when the site sends mail)

- [ ] **Resend → Domains** (or the provider in use): the sending domain is verified; the DNS
      results of [mail.md](mail.md) are pasted as pass or fail per record.
- [ ] **Resend → API Keys**: the application's key has the narrowest permission that sends,
      with the domain restriction set to the sending domain; unused keys deleted.
- [ ] **Quota**: the plan's sending limit is known and a usage alert is set where the provider
      offers one (a mail endpoint without a limit spends it).

## Privacy (EU)

- [ ] **Supabase → Project Settings**: the project's region is in the EU (Frankfurt, Ireland,
      Paris, Stockholm; London and Zurich are not EU), and the privacy notice says so.
- [ ] **Processors**: Supabase, Vercel, the mail provider and any analytics or embed provider
      are named in the privacy notice and in the record of processing; their DPAs are part of
      their terms (no signature needed) and cover transfers with the EU standard clauses.
- [ ] **Record of processing** (GDPR Art. 30) exists: the under-250-employees exemption does not
      apply to processing that is not occasional, such as user accounts.
- [ ] **Breach**: it is written down who notifies the supervisory authority within 72 hours of
      learning of a personal-data breach (Art. 33), and where the contact details are.

## Google Cloud Console (when Google sign-in is used)

- [ ] **APIs & Services → Credentials → the OAuth client**: type Web application; Authorized
      redirect URIs: exactly `https://<project-ref>.supabase.co/auth/v1/callback`; Authorized
      JavaScript origins: the production origin, no localhost.
- [ ] **Google Auth Platform → Audience**: publishing status In production (not Testing); user
      type as intended (External or Internal).
- [ ] **Google Auth Platform → Branding**: app name, home page and privacy policy URLs resolve;
      authorized domains verified.
- [ ] **Google Auth Platform → Data Access**: scopes are `openid`, `email`, `profile` only,
      unless the issue says otherwise.
- [ ] **Credentials**: unused OAuth clients deleted; the client secret rotated if it ever left
      the two places it belongs (Supabase's provider setting and the local ignored `.env`).

## Google Cloud service accounts (when the code calls Google APIs)

- [ ] **IAM & Admin → Service Accounts**: one per application; unused ones disabled; no
      user-managed key on an account whose code runs on Vercel (Workload Identity Federation)
      or on Google Cloud (the attached account).
- [ ] **IAM & Admin → IAM**: no service account holds Owner or Editor; no project-wide Service
      Account User or Service Account Token Creator grant.
- [ ] **IAM & Admin → Organization Policies**: *Disable service account key creation* and
      *Disable service account key upload* enforced (the default for organisations created
      since 3 May 2024); *Service Account Key Exposure Response* set to `DISABLE_KEY`.

## Verdict line

`Verdict: ready` when every applicable box above is confirmed and no Critical or High finding is
open without a current acceptance ([SKILL.md](SKILL.md) step 9); otherwise
`Verdict: not ready — <what blocks>`. The user deploys.
