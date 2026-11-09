# Mail: what the sending domain must show

Read with [SKILL.md](SKILL.md). This applies when the site sends mail: Supabase Auth's
confirmation and reset mail, or the application's own through Resend or another provider.
Sources: Supabase's Auth SMTP guide, Resend's pages on domains, adding a domain and DMARC, and
RFC 7208 for SPF (read 2026-10-27).

## In the repository

The checks are owned elsewhere: custom SMTP for auth mail in [supabase.md](supabase.md) §Auth
flow; the provider key server-side only in `review-security/checklist.md` §4
(`scan_secrets.py` recognises Resend keys); a constant sender, validated recipients and a rate
limit on every endpoint that sends mail in `review-security/checklist.md` §3.

## The domain's DNS records

DNS is public: the agent reads the records with `dig +short TXT <name>` (and `MX` for the
return-path name; on Windows `Resolve-DnsName -Type TXT <name>` or `nslookup -type=TXT <name>`,
and `MX` likewise), as it may read the live headers on [dashboard.md](dashboard.md); a lookup of
a public record carries no personal data. The report names each record and whether it passes,
not its reporting address.

- **Sending domain**: mail goes from a subdomain where the project allows it (Resend recommends
  one or more subdomains, so the main domain's reputation stays apart).
- **SPF**: the name the provider gives (Resend: the return-path subdomain, `send.<domain>` by
  default, with its MX record) has exactly one `v=spf1` record; a second one makes SPF fail with
  a permerror (RFC 7208). It includes the provider and ends in `~all` or `-all`, never `+all` or
  a bare `all`, which authorizes every server.
- **DKIM**: the records the provider generated are present and match it exactly, and the
  provider shows the domain verified (Resend: the domain's Records tab).
- **DMARC**: a TXT record at `_dmarc.<domain>` with `v=DMARC1`. Start with `p=none` and a `rua`
  address for the reports, then move to `p=quarantine` or `p=reject` once the reports show the
  legitimate mail passing SPF or DKIM (Resend DMARC guide). No DMARC record on a domain that
  sends is a Medium finding (anyone can send in its name unchallenged); `p=none` kept after the
  launch is Low.

## On the providers' side: the lines for the user

The custom SMTP setting, the provider's domain status, the key's permission and the sending
quota are read only in the Supabase and mail provider's dashboards and go on
[dashboard.md](dashboard.md) §Mail.
