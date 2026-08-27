# AntimBench Elastic Beanstalk deployment

## Scope and target design

This repository is prepared for deployment to a **single-instance Elastic Beanstalk Node.js 22 Amazon Linux 2023 environment**. The environment, VPC, instance profile, PostgreSQL installation, and all other AWS infrastructure are intentionally outside this repository.

The application version runs three local-only processes:

```text
Internet -> Elastic Beanstalk nginx (port 80/443)
                   |- /api/* and /health -> FastAPI (127.0.0.1:8000)
                   `- all other paths -> Next.js (EB Node.js port)
```

The root `Procfile` makes Elastic Beanstalk supervise the Next.js process. `.platform/hooks/prebuild/01-install-runtime-dependencies.sh` installs the frontend's production dependencies and uses `uv` to provision Python 3.12 and sync the backend's production dependencies. `.platform/hooks/postdeploy/01-start-api-service.sh` creates an unprivileged systemd service for Uvicorn. `.platform/nginx/conf.d/elasticbeanstalk/antimbench.conf` extends the default EB nginx server block to proxy only the API and health-check routes to the loopback-only FastAPI listener.

Docker is not used: the existing source bundle is enough when the Elastic Beanstalk environment uses the Node.js 22 AL2023 platform, whose Node runtime satisfies Next.js 16's Node 20.9+ requirement.

## GitHub Actions workflow

Workflow file: `.github/workflows/deploy.yml`
Workflow name: **AntimBench CI/CD**

It runs on pushes to `main` and on manual `workflow_dispatch`; it does not deploy pull requests. The concurrency group `antimbench-production-deploy` serializes deployments and does not cancel one already updating Elastic Beanstalk.

The workflow stages are:

1. Check out the commit.
2. Set up Python 3.12 and uv 0.8.15.
3. Run `uv sync --locked --all-groups` and `uv run --locked pytest` in `backend`.
4. Set up Node.js 22, run `npm ci`, `npx tsc --noEmit`, `npm run lint`, and `npm run build` in `frontend`.
5. Create a minimal source ZIP containing only the runtime bundle, migration files, lockfile, process files, nginx configuration, and platform hooks. The workflow rejects archives containing `.env` files, Git metadata, virtual environments, `node_modules`, caches, local databases, or certificates.
6. Upload the ZIP to the explicitly configured S3 bucket, create a version named `antimbench-<short-sha>-<run-number>`, update the target Elastic Beanstalk environment, and poll for `Ready` + `Green` health for up to 30 minutes.

The workflow prints the commit, version label, target application, target environment, and region. It never prints credentials.

## GitHub configuration

Before the first deployment, open **Repository -> Settings -> Secrets and variables -> Actions**.

Add these under **Secrets**:

| Name | Purpose |
| --- | --- |
| `AWS_ACCESS_KEY_ID` | Temporary AWS access-key ID used only by the deployment run. |
| `AWS_SECRET_ACCESS_KEY` | Matching temporary AWS secret access key. |
| `AWS_SESSION_TOKEN` | Matching temporary AWS session token. |

Add these under **Variables**:

| Name | Purpose |
| --- | --- |
| `AWS_REGION` | Target AWS Region, normally `us-east-1`. A secret with this name is also accepted if your policy requires it. |
| `EB_APPLICATION_NAME` | Existing Elastic Beanstalk application name. |
| `EB_ENVIRONMENT_NAME` | Existing Elastic Beanstalk environment name. |
| `EB_S3_BUCKET` | Existing bucket permitted to store Elastic Beanstalk application-version ZIPs. |
| `NEXT_PUBLIC_API_URL` | Optional public API origin used only at frontend build time. Leave unset for the recommended same-origin `/api` proxy. |

Create **Repository -> Settings -> Environments -> New environment -> `production`** before the first run. The workflow targets this environment, so you can later add required reviewers or branch/deployment protection rules. This repository does not create the GitHub Environment through the API.

## Elastic Beanstalk prerequisites

Create these separately before enabling deployment:

- An Elastic Beanstalk application and a **single-instance** environment with no load balancer.
- The current Node.js 22 Amazon Linux 2023 platform branch.
- The custom VPC, subnet, security groups, instance profile, and local PostgreSQL installation that your architecture requires.
- An existing `EB_S3_BUCKET` with permissions for the deployment credentials to upload application versions.
- Least-privilege AWS permissions to upload the version ZIP and call `elasticbeanstalk:create-application-version`, `elasticbeanstalk:update-environment`, `elasticbeanstalk:describe-environments`, and `elasticbeanstalk:describe-events` on the intended resources.
- An EB health check path of `/health`; nginx proxies that path to FastAPI without opening port 8000 publicly.

Set application settings through **Elastic Beanstalk -> Environment -> Configuration -> Updates, monitoring, and logging -> Runtime environment variables**. Keep secrets out of this repository and GitHub workflow source. At minimum configure:

| Setting | Notes |
| --- | --- |
| `DATABASE_URL` | Required. PostgreSQL URL reachable from the EC2 instance, commonly via `127.0.0.1:5432`. Store it as a secret value. |
| `JWT_SECRET_KEY` | Required by the backend; use a strong, rotated secret. |
| `AUTH_COOKIE_SECURE` | Set to `true` when the public site uses HTTPS. |
| `FRONTEND_URL` | Public canonical frontend URL. |
| `CORS_ORIGINS` | JSON array containing the public frontend origin, for example `["https://app.example.edu"]`. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` | Configure only when email delivery is required; treat `SMTP_PASSWORD` as secret. |

`NEXT_PUBLIC_API_URL` is different: Next.js embeds it into browser code during `npm run build`. It must never contain a secret. The current application defaults to an empty value and therefore makes same-origin `/api` calls, which is the intended Elastic Beanstalk configuration; no build-time value is needed in that case.

## Alembic migration behavior

`.platform/hooks/predeploy/01-run-migrations.sh` runs `uv run --locked alembic upgrade head` on the Elastic Beanstalk instance before the Next.js process is started. It receives `DATABASE_URL` from Elastic Beanstalk environment properties and fails the deployment if that setting is absent. GitHub Actions never connects to the private/local PostgreSQL database and never receives `DATABASE_URL`.

## Deploying and troubleshooting

After configuring the values above, either push a commit to `main` or open **Repository -> Actions -> AntimBench CI/CD -> Run workflow** and select `main`.

If a run fails:

1. Open the failed GitHub Actions step. Validation, tests, TypeScript, frontend build, package checks, AWS upload, and EB health polling fail independently with a useful step name.
2. For Elastic Beanstalk failures, the workflow prints the 20 most recent EB events. Then inspect **Elastic Beanstalk -> Environment -> Events** and request instance logs, especially `eb-engine`, nginx, and `antimbench-api.service` logs.
3. Check the required variables and secrets are set, the bucket and EB resources are in the same configured region, and the target environment is on the Node.js 22 AL2023 platform.
4. Confirm the EC2 instance can reach PostgreSQL at the configured `DATABASE_URL` and that `/health` returns successfully through nginx.

## Rollback

No automated rollback is performed. To roll back safely, identify the previous healthy application version in **Elastic Beanstalk -> Application versions**, then deploy it to the same environment using the console or:

```bash
aws elasticbeanstalk update-environment \
  --application-name "$EB_APPLICATION_NAME" \
  --environment-name "$EB_ENVIRONMENT_NAME" \
  --version-label "$PREVIOUS_HEALTHY_VERSION"
```

Wait for the environment to become `Ready` and `Green`. Review whether the database migration is backward-compatible before rolling back application code.

## Credential rotation

Use short-lived AWS credentials, rotate the three GitHub AWS secrets together before they expire, and rerun a manual deployment to verify access. Do not place AWS credentials, database passwords, JWT secrets, or SMTP passwords in `.env` files committed to Git or in GitHub repository variables.
