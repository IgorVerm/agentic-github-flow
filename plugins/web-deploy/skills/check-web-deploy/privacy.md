# Privacy for a site with visitors in the EU

Read with [SKILL.md](SKILL.md). For a site run from the EU, or one that offers its service to
people in the EU, the GDPR applies and the data protection authority of the member state where
the site's operator is established supervises; the ePrivacy rules on cookies apply on top. This
is what a repository can show and what the user confirms, not legal advice. Sources: GDPR
Articles 5, 13, 17, 30 and 33, the cookie page of the Belgian authority
(Gegevensbeschermingsautoriteit, GBA) as one national authority's reading, Vercel's pages on
function regions and Web Analytics privacy, Supabase's regions page, and the DPAs of Supabase,
Vercel and Resend (read 2026-10-27). Findings use the severities of
`review-security/checklist.md` §Severity. Where the operator's own authority reads the cookie
rules differently, its reading applies and the report says so.

## In the repository

- **Consent before trackers.** Analytics, advertising and marketing tags, and embeds that set
  cookies or read the device (video, maps, social widgets) load only after an opt-in. A
  pre-ticked box or browsing on is no consent, refusing is as easy as accepting, a cookie wall
  is not allowed, and consent can be withdrawn as easily as it was given (GBA). Strictly
  necessary cookies (the Supabase session, a language choice, the consent choice itself) need
  no consent; analytics cookies in principle do (GBA). Vercel Web Analytics sets no cookies (it
  identifies a visit by a hash of the request, discarded after 24 hours), so it needs no banner.
  Check the code that loads each tag, not the banner text: a tag that loads before the opt-in
  is a Medium finding.
- **A privacy notice** is linked from every page's footer and from sign-up, and gives what
  Article 13 asks: who is responsible and how to reach them; purposes and legal basis;
  recipients (the processors on [dashboard.md](dashboard.md) §Privacy); transfers outside the
  EEA and their safeguard; retention periods; the rights of access, rectification, erasure,
  restriction, objection and portability, withdrawal of consent, and a complaint to the
  supervisory authority. None on a site with sign-up or a contact form is Medium. Google
  sign-in needs its URL too ([google-auth.md](google-auth.md)).
- **Deletion reaches every table.** Every table holding a user's data references
  `auth.users(id)` with `on delete cascade`, or one deletion function removes those rows and
  the user's storage objects; a row or object that survives the user's deletion is a finding
  (Article 17: erasure without undue delay). An export may be answered by hand on request; it
  needs no button.
- **Retention.** Data kept for a short purpose (unconfirmed sign-ups, logs with IP addresses,
  contact-form messages, abandoned uploads) has a deletion job (`pg_cron` in a migration, a
  scheduled function) or a period stated in the notice (Article 5(1)(e)). Logs hold no more
  personal data than the feature needs: `review-security/checklist.md` §6.
- **Function region.** Vercel runs functions in Washington, D.C. (`iad1`) for new projects
  unless `vercel.json` `regions` or the project settings say otherwise. Functions that handle
  personal data run next to the Supabase project (for Frankfurt, `fra1`), or the notice names
  the transfer to the United States; a notice that says the data stays in the EU while the
  functions run in `iad1` is a finding.
