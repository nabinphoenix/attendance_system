# AntimBench Elastic Beanstalk deployment

## Demo architecture and limitations

This repository targets **one Elastic Beanstalk instance** in `us-east-1`:

```text
Internet -> nginx (public port 80)
               |- /api/* and /health -> FastAPI (127.0.0.1:8000)
               `- all other requests -> Next.js (internal EB Node.js listener)

PostgreSQL 15 -> 127.0.0.1:5432 only
```

Use the Node.js 22 Amazon Linux 2023 Elastic Beanstalk platform, application
`AntimBench`, environment `AntimBench-Prod`, and a single `t3.micro` instance.
The Node.js platform supervises the `web` command in the root `Procfile`; FastAPI
is a `systemd` service created by the post-deploy hook. The Node.js platform
supplies the internal listener port to Next.js (it defaults to port 3000 outside
Elastic Beanstalk). FastAPI explicitly binds to `127.0.0.1:8000`.

PostgreSQL runs on that same EC2 instance for this demonstration. It is **not** a
highly available production database: terminating or replacing the instance can
remove its data. Back up the database before an environment replacement. Do not
open port 5432 in the security group; nginx is the only public application entry
point. This design uses no RDS, Load Balancer, NAT Gateway, or Docker. S3 is used
only to hold Elastic Beanstalk application-version bundles.

## Required Elastic Beanstalk environment properties

Set these through **Elastic Beanstalk -> Environment -> Configuration -> Updates,
monitoring, and logging -> Runtime environment variables**. Do not commit these
values or put them in the GitHub workflow.

| Property | Required | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Yes | `postgresql://antimbench_app:<URL_ENCODED_PASSWORD>@127.0.0.1:5432/antimbench` |
| `POSTGRES_PASSWORD` | Yes | Password applied to the local `antimbench_app` PostgreSQL role. |
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

The pre-deploy hook initializes PostgreSQL 15 only once, sets
`listen_addresses = '127.0.0.1'`, changes only the IPv4 and IPv6 loopback
`pg_hba.conf` host rules to `scram-sha-256`, enables the service, waits for
`pg_isready`, creates or updates `antimbench_app`, creates `antimbench` when
needed, and runs `uv run --locked alembic upgrade head`. It never echoes the
database URL or password.

The browser uses relative `/api/...` requests by default. nginx proxies those
requests to local FastAPI, so no `NEXT_PUBLIC_API_URL`, public backend URL, or
hard-coded Elastic Beanstalk hostname is required.

## GitHub Actions configuration

The workflow is [.github/workflows/deploy.yml](.github/workflows/deploy.yml),
named **AntimBench CI/CD**. It first runs backend migrations and tests against a
throwaway PostgreSQL 15 service container, then runs `npm ci`, TypeScript,
lint, and a production frontend build. Only after CI succeeds does the deploy
job build a minimal Elastic Beanstalk ZIP and update the environment.

Add these **GitHub Secrets**:

| Name | Purpose |
| --- | --- |
| `AWS_ACCESS_KEY_ID` | Temporary AWS access-key ID. |
| `AWS_SECRET_ACCESS_KEY` | Matching temporary AWS secret access key. |
| `AWS_SESSION_TOKEN` | Matching temporary AWS session token. |

Add these **GitHub Variables**:

| Name | Purpose |
| --- | --- |
| `AWS_REGION` | `us-east-1` for this environment. |
| `EB_APPLICATION_NAME` | `AntimBench`. |
| `EB_ENVIRONMENT_NAME` | `AntimBench-Prod`. |
| `EB_S3_BUCKET` | Existing bucket for application-version bundles. |

AWS Academy credentials expire. Refresh all three AWS secrets together before
they expire; the workflow supports the required session token. The deployment
job validates its non-secret variables, uploads a uniquely named ZIP, creates
an application version, updates the existing environment, and waits for
`Ready` plus `Green` health. It does not create infrastructure.

## Bundle and service behaviour

The generated ZIP includes `Procfile`, hidden `.platform` hooks and nginx
configuration, backend source/migrations/lockfile, and the built Next.js output.
It rejects `.env` files, `.git`, `node_modules`, virtual environments, local
databases, certificates, test caches, and development build diagnostics.

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
