# Cloud SQL for PostgreSQL: what the repository must show

Read with [SKILL.md](SKILL.md). **Status, 2026-11-19: written from Google's documentation, not
yet exercised in a live project.** The first project on this route verifies every line,
corrects this file in the same change and removes this paragraph. Sources (read 2026-11-19):
Cloud SQL for PostgreSQL's *Connect from Cloud Run*, *Configure authorized networks*,
*IAM authentication*, *Connect using Cloud SQL Language Connectors*, *Configure SSL/TLS
certificates*, *Configure point-in-time recovery*, *Choose your backup option* and *Prevent
deletion of an instance* (docs.cloud.google.com); the README of
`GoogleCloudPlatform/cloud-sql-nodejs-connector` on GitHub.

The instance's settings are reviewable where Terraform (`google_sql_database_instance`) or a
script creates it; an instance made in the console goes to the dashboard list whole. Several
defaults differ between the console and code (below), so code is checked against the values,
not against "the default".

## Network and connection

- **No open authorized network.** `0.0.0.0/0` in `authorized_networks` is Critical; any
  authorized network on an instance reached only from Cloud Run is a Medium finding. A new
  instance gets a public IP by default; that is acceptable when no network is authorized and
  every client comes through the connector, which authenticates with IAM. Private IP (with
  Direct VPC egress) is stronger, not required.
- **The connector, not a raw address.** The application connects through the Cloud SQL Node.js
  Connector (`@google-cloud/cloud-sql-connector`), the Cloud Run Cloud SQL connection
  (`--add-cloudsql-instances`, a Unix socket) or the Auth Proxy; a connection string with the
  instance's IP address is a finding unless it is the private IP. The runtime service account
  holds `roles/cloudsql.client`.
- **SSL mode** `ENCRYPTED_ONLY` or `TRUSTED_CLIENT_CERTIFICATE_REQUIRED` (`--ssl-mode`,
  Terraform `ssl_mode`), never the default `ALLOW_UNENCRYPTED_AND_ENCRYPTED`; `requireSsl` is
  the legacy setting and must not contradict it. The connectors encrypt whatever the mode says;
  the mode closes the door for any other client. Missing: Medium.
- **Database user**: automatic IAM database authentication for the service account, which Google
  "strongly recommends" (the Node connector's `authType: 'IAM'`; the user is the service account's
  e-mail without `.gserviceaccount.com`). A password user instead takes its password from
  Secret Manager ([cloud-run.md](cloud-run.md) §Secrets). The `postgres` superuser is never the
  application's user.

## Data safety

- **Automated backups and point-in-time recovery on** in the code that creates the instance
  (Terraform `backup_configuration.enabled`, `point_in_time_recovery_enabled`,
  `transaction_log_retention_days`): only the console turns them on by itself on the Enterprise
  edition. Off for a database with users' data: High.
- **Retention** stated: backups keep 7 days by default (Enterprise; 15 on Enterprise Plus), logs
  for point-in-time recovery up to 7 (Enterprise) or 35 days. The project's documentation names
  the period it chose and how a restore was tested.
- **Deletion protection on**: Terraform has two flags, `deletion_protection` (Terraform's own)
  and `settings.deletion_protection_enabled` (Google's); set both. It does not protect backups
  or a deleted project.

## Schema and data

- **Migrations as files** in the repository (a migration tool's folder, in order, each one
  applied by the deploy or by a documented step), so the schema is reviewable; a schema changed
  by hand in a console has nothing to review: Medium.
- **Least privilege inside the database**: the application's user owns or is granted only its
  own schema; no `GRANT ALL` to `PUBLIC`. Where several tenants or users share tables, every
  query that returns user data filters on the verified user ([iap.md](iap.md)): PostgreSQL's
  row-level security is off unless the migrations enable it.
- **Deletion and retention** as in [privacy.md](privacy.md): rows that reference a user go with
  the user (`on delete cascade` to the users table, or one deletion function).
