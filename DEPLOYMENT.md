# AntimBench Elastic Beanstalk deployment

## Demo architecture and limitations

This repository targets **one Elastic Beanstalk instance** and an existing
Amazon RDS PostgreSQL instance in `us-east-1`:

```text
Internet -> nginx (public port 80)
               |- /api/* and /health -> FastAPI (127.0.0.1:8000)
               `- all other requests -> Next.js (internal EB Node.js listener)

PostgreSQL -> Amazon RDS (private endpoint)
```

Use the Node.js 22 Amazon Linux 2023 Elastic Beanstalk platform, application
`AntimBench`, environment `AntimBench-Prod`, and a single `t3.micro` instance.
The Node.js platform supervises the `web` command in the root `Procfile`; FastAPI
is a `systemd` service created by the post-deploy hook. The Node.js platform
supplies the internal listener port to Next.js (it defaults to port 3000 outside
Elastic Beanstalk). FastAPI explicitly binds to `127.0.0.1:8000`.

RDS owns the database lifecycle. Keep its deletion protection and backup
retention enabled, and do not expose port 5432 publicly. The Elastic Beanstalk
security group must be allowed to reach the RDS security group on port 5432.
Deployments never create, replace, delete, or alter ownership of the RDS
database; they only run Alembic upgrades against the configured database. S3 is
used only to hold Elastic Beanstalk application-version bundles. The instance
needs ordinary outbound HTTPS access to the Amazon Linux package repositories to
install Python; use a public subnet with an internet gateway or provide NAT when
placing it in a private subnet.

## Required Elastic Beanstalk environment properties

Set these through **Elastic Beanstalk -> Environment -> Configuration -> Updates,
monitoring, and logging -> Runtime environment variables**. Do not commit these
values or put them in the GitHub workflow.

| Property | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Yes | `postgresql://<user>:<URL_ENCODED_PASSWORD>@<rds-endpoint>:5432/antimbench` |
| `PROFILE_MEDIA_BUCKET` | No | Existing private S3 bucket used for durable profile-image storage. When unset, the single-instance service uses its managed local state directory. |
| `PROFILE_MEDIA_PREFIX` | No | Object prefix for profile images; defaults to `profile-media`. |
| `PROFILE_MEDIA_REGION` | No | Bucket region when it differs from the instance's region. |
| `JWT_SECRET_KEY` | Yes | Backend signing key; use a strong unique value. |
| `AUTH_COOKIE_SECURE` | Yes | Set `false` for plain HTTP; set `true` as soon as HTTPS is introduced. |
| `FRONTEND_URL` | Yes | For plain HTTP, `http://<elastic-beanstalk-cname>`. |
| `CORS_ORIGINS` | Yes | JSON array, for example `["http://<elastic-beanstalk-cname>"]`. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` | Optional | Needed only when notification email delivery is enabled. |
| `COLLEGE_NAME`, `ATTENDANCE_THRESHOLD_PERCENT`, `MINIMUM_OBSERVATIONS` | Optional | Branding and attendance-analysis behaviour. |

The backend Settings model also supports `JWT_ALGORITHM`,
`ACCESS_TOKEN_EXPIRE_MINUTES`, `AUTH_COOKIE_NAME`, QR/geofence limits,
notification-worker polling settings, and `INVITATION_EXPIRE_HOURS`; their safe
defaults are in `backend/app/core/config.py`.

The pre-deploy hook accepts a managed PostgreSQL URL and never performs local
PostgreSQL initialisation, role changes, database creation, or ownership
changes. It runs `python -m alembic upgrade head` using the deployment's
prebuilt package tree and never echoes the database URL or password.

Profile images are served through the authenticated application path. When
`PROFILE_MEDIA_BUCKET` is configured, they are stored privately in that bucket;
grant the environment instance profile only `s3:GetObject`, `s3:PutObject`, and
`s3:DeleteObject` for the configured prefix. Without a bucket, the single
Elastic Beanstalk instance stores them in its managed writable state directory.

The browser uses relative `/api/...` requests by default. nginx proxies those
requests to local FastAPI, so no `NEXT_PUBLIC_API_URL`, public backend URL, or
hard-coded Elastic Beanstalk hostname is required.

## GitHub Actions configuration

The workflow is [.github/workflows/deploy.yml](.github/workflows/deploy.yml),
named **AntimBench CI/CD**. It first runs backend migrations and tests against a
throwaway PostgreSQL 15 service container, then runs `npm ci`, TypeScript,
lint, and a production frontend build. After CI succeeds, it deploys the
self-contained Elastic Beanstalk bundle and, when Vercel credentials are
configured, deploys the production Vercel frontend too.

Add these **GitHub Secrets**:

| Name | Purpose |
| --- | --- |
| `AWS_ACCESS_KEY_ID` | Temporary AWS access-key ID. |
| `AWS_SECRET_ACCESS_KEY` | Matching temporary AWS secret access key. |
| `AWS_SESSION_TOKEN` | Matching temporary AWS session token. |
| `VERCEL_TOKEN` | Vercel account token with permission to deploy `antimbench-https-proxy`. |
| `VERCEL_ORG_ID` | Vercel team or personal-account ID that owns the project. |
| `VERCEL_PROJECT_ID` | Vercel project ID for `antimbench-https-proxy`. |

Add these **GitHub Variables**:

| Name | Purpose |
| --- | --- |
| `AWS_REGION` | `us-east-1` for this environment. |
| `EB_APPLICATION_NAME` | `AntimBench`. |
| `EB_ENVIRONMENT_NAME` | `AntimBench-Prod`. |
| `EB_S3_BUCKET` | Existing bucket for application-version bundles. |
| `VERCEL_DEPLOY_ENABLED` | Set to `true` after all three Vercel secrets are configured. |

AWS Academy credentials expire. Refresh all three AWS secrets together before
they expire; the workflow supports the required session token. The deployment
job validates its non-secret variables, uploads a uniquely named ZIP, waits for
Elastic Beanstalk to process the application version and for the environment to
be `Ready`, updates the existing environment, and then waits for `Ready` plus
`Green` health. It does not create infrastructure.

The Vercel job is skipped until all Vercel secrets are supplied. Create
`VERCEL_TOKEN` in **Vercel Account Settings → Tokens**, then copy the team and
project IDs from **Project Settings → General** into `VERCEL_ORG_ID` and
`VERCEL_PROJECT_ID`. The project keeps its existing production environment
variables, including `API_PROXY_TARGET`, when the workflow deploys it.

## Bundle and service behaviour

The generated ZIP includes `Procfile`, hidden `.platform` hooks and nginx
configuration, backend source/migrations/lockfile, a locked Linux Python
package tree, and the traced Next.js standalone runtime. The two bundled
production runtimes deliberately contain the Node and Python packages needed to
start the app; the instance does not run `npm ci`, download `uv`, or resolve
PyPI packages while Elastic Beanstalk is deploying. The workflow rejects other
`.env` files, Git metadata, virtual environments, local databases, certificates,
test caches, and development build diagnostics.

`01-start-api-service.sh` creates the existing unprivileged `DynamicUser`
FastAPI service with its working directory under `backend`, an internal
`127.0.0.1:8000` Uvicorn command, restart policy, and the Elastic Beanstalk
environment-property file. Secrets are not copied into a new world-readable
file. nginx proxies only `/api/` and `/health` to FastAPI; it never exposes
PostgreSQL or port 8000 publicly.

## Deploying and rollback

Push to `main` or manually run **AntimBench CI/CD** from the Actions tab after
configuring the existing Elastic Beanstalk application, environment, S3 bucket,
and GitHub settings. The security group does not need SSH for this workflow.

For rollback, select a previous healthy application version in Elastic
Beanstalk and deploy it to the same environment. Confirm database-migration
compatibility before rolling back code; a database backup is essential before
replacing the single instance.
