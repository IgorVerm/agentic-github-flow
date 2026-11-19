# Cloud Run and Secret Manager: what the repository must show

Read with [SKILL.md](SKILL.md). **Status, 2026-11-19: written from Google's documentation, not
yet exercised in a live project.** The first project on this route verifies every line against
what it sees, corrects this file in the same change and removes this paragraph. Sources, on
docs.cloud.google.com (read 2026-11-19): Cloud Run's *Deploy container images*, *Container
runtime contract*, *Configure environment variables*, *Configure secrets for services*,
*Restrict network endpoint ingress*, *Access control with IAM*, *Introduction to service
identity* and *Cloud Run locations*; Secret Manager's *Access control with IAM*, *Best
practices* and *Create rotation schedules*.

The deploy is reviewable only where it is written down: a `Dockerfile`, a service YAML
(`service.yaml`, `gcloud run services replace`), Terraform (`google_cloud_run_v2_service`), a
`cloudbuild.yaml`, a GitHub workflow or a deploy script. A service deployed by hand from the
console leaves nothing to read: say so as a Medium finding (the settings below cannot be
reviewed or restored) and move every line below to the dashboard list. Next.js on Cloud Run
keeps the application rules of [vercel.md](vercel.md) §Headers (set in `next.config.*`
`headers()`), §Proxy, Server Actions, runtime and §Repository hygiene; its Vercel-only lines
(scopes, Deployment Protection, `VERCEL_URL`) do not apply.

## The container

- **A non-root user.** The `Dockerfile`'s final stage sets `USER` to a user it creates (or the
  base image's, such as `node` or a distroless `nonroot`): Cloud Run runs the container as root
  when none is set, and as root as well when the named user does not exist. Missing: Medium.
- **Nothing secret in the image.** No `.env`, key file or `ARG`/`ENV` holding a secret in the
  `Dockerfile`; `.dockerignore` excludes `.env*`, `.git`, keys and local data. A secret in a
  build layer is in every copy of the image: Critical, and it goes to the user to rotate.
- **A pinned base image** (a version tag, better a digest) and a supported Node major, as in
  [vercel.md](vercel.md) §Proxy, Server Actions, runtime.

## Who can reach the service

Two routes are documented. **IAP directly on the Cloud Run service** (`--iap`, Terraform
`iap_enabled = true`) is Google's recommended one: it covers every ingress path, the default
`run.app` URL included. **IAP on an external Application Load Balancer** in front of the service
does not cover `run.app`: there the service needs ingress `internal-and-cloud-load-balancing`
(or `--no-default-url`), or IAP is bypassed. IAP cannot be on both.

- **Ingress**: `internal-and-cloud-load-balancing` behind a load balancer, `internal` for a
  service only other services call. `all` is acceptable only with IAP directly on the service.
  A service holding personal data with ingress `all` and no IAP on the service is Critical.
- **No public invoker.** None of `--allow-unauthenticated`, an `allUsers` or
  `allAuthenticatedUsers` binding of `roles/run.invoker`, or `--no-invoker-iam-check`
  (annotation `run.googleapis.com/invoker-iam-disabled`, Terraform `invoker_iam_disabled`) on a
  service behind IAP: Google documents them as the ways to make a service public. Present:
  Critical.
- **The IAP service agent's invoker binding.** With direct IAP set up by gcloud or Terraform,
  the IAP service agent (`service-<project number>` at `gcp-sa-iap.iam.gserviceaccount.com`)
  holds `roles/run.invoker` on the service, written in the same code (only the console grants
  it by itself). Who may sign in is the dashboard list's, not the repository's.
- **The default URL**: closed (`--no-default-url`, annotation
  `run.googleapis.com/default-url-disabled: true`, Terraform `default_uri_disabled = true`) when
  users come through a custom domain on a load balancer. Closing it breaks callers of
  `run.app` (Cloud Scheduler, Tasks, Pub/Sub push, uptime checks): name them first.
- The application still verifies who is signed in: [iap.md](iap.md).

## The service's own identity

- **A user-managed service account** per service (`--service-account`, Terraform
  `service_account`), never the Compute Engine default
  (`<project number>-compute` at `developer.gserviceaccount.com`), which may hold Editor.
- **Its roles**, where the repository grants them: `roles/cloudsql.client` for the database,
  `roles/secretmanager.secretAccessor` on each secret it reads, nothing project-wide beyond what
  a feature needs, never a basic role: `review-security/checklist.md` §Stack notes, *Google
  Cloud service accounts*. No service account key file anywhere: the attached account is the
  credential.

## Secrets: Secret Manager only

- **No secret value in configuration**: not in `--set-env-vars`, a service YAML `env.value`,
  Terraform variables with defaults, `cloudbuild.yaml` substitutions or a workflow file. A secret
  reaches the service as a Secret Manager reference (`--set-secrets`, `valueFrom.secretKeyRef`,
  Terraform `value_source.secret_key_ref`), as an environment variable or a mounted file.
  `.env.example` lists every variable with a placeholder and marks which are secrets.
- **Pinned versions.** Google advises referencing a version number, not `latest`. A secret as an
  environment variable is resolved once, at instance start; a mounted file always reads the
  latest version, which suits rotation but fails at run time when access breaks. In the gen2
  environment root owns the mounted secret files: the non-root user must still be able to
  read them (test it once).
- **Access per secret**: the runtime service account gets
  `roles/secretmanager.secretAccessor` on each secret
  (`google_secret_manager_secret_iam_member`), not on the project. A project-wide grant is a
  Medium finding.
- **Rotation** is the user's: Secret Manager only sends a `SECRET_ROTATE` message; the new
  version and the redeploy are someone's job, named in the project's documentation.

## Region

The service, the database and the secrets' replication are in the region the privacy notice
names: [privacy.md](privacy.md) §Function region. Cloud Run's EU regions are listed on *Cloud
Run locations*; the database sits in the same region as the service (Cloud SQL's *Connect from
Cloud Run*). Secret Manager's automatic replication may place copies outside the EU: for an EU
promise, user-managed replication in EU regions.
