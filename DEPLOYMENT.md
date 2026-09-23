# AntimBench production deployment

This repository deploys the complete application to one load-balanced Elastic
Beanstalk environment in us-east-1.

~~~text
Cloudflare
  -> antimbench.sunitanepali.com.np
  -> ACM certificate and Application Load Balancer
  -> Elastic Beanstalk (Node.js 22 / Amazon Linux 2023)
  -> nginx
       /       -> Next.js standalone server
       /api/*  -> FastAPI on 127.0.0.1:8000
       /health -> FastAPI health endpoint
  -> private Amazon RDS PostgreSQL
~~~

The environment runs Next.js, FastAPI, the notification worker, and nginx on
each instance. Elastic Beanstalk manages the load balancer and Auto Scaling
Group with minimum 1, desired 1, and maximum 4 instances. Ports 3000, 8000,
and 5432 are never public.

## Security first

Never commit AWS keys, session tokens, database passwords, JWT secrets, SMTP
passwords, or GitHub tokens. Credentials pasted into chat, a terminal, or a
repository must be revoked and replaced immediately.

The deployment workflow uses the existing AWS Academy/VocLabs temporary session
credentials stored as GitHub `production` environment secrets. These credentials
expire when the lab session ends, so refresh all three secrets after starting a
new session. Do not use long-lived IAM user access keys.

## Provision the AWS foundation

infra/aws/antimbench-production.yml is the reproducible CloudFormation
foundation. It creates:

- the 10.0.0.0/16 VPC, two public subnets, and two private database subnets;
- the internet gateway and public/private route tables;
- ALB, application, and RDS security groups;
- encrypted, non-public PostgreSQL 15 RDS with a two-subnet DB subnet group;
- encrypted S3 buckets for deployment bundles and private profile media;
- Elastic Beanstalk application/environment roles and instance profile;
- the load-balanced AntimBench-Prod Node.js 22 environment;
- an optional GitHub Actions OIDC deployment role restricted to
  the `production` environment in `nabinphoenix/attendance_system`.

The template enables the HTTPS listener when CertificateArn is supplied. The
ACM certificate must be issued in us-east-1 for
antimbench.sunitanepali.com.np. If the account already has the GitHub OIDC
provider, pass its ARN as ExistingGitHubOidcProviderArn; otherwise the stack
creates it when `CreateGitHubOidcResources=true` is supplied by an
IAM-authorized bootstrap principal. The default is `false` because AWS Academy
roles generally cannot create IAM identity providers or roles.

This repository was created after GitHub introduced immutable OIDC subjects.
The deployment job also uses the `production` environment, so the role trust
policy must match this subject exactly:

~~~text
repo:nabinphoenix@159899712/attendance_system@1321622311:environment:production
~~~

Use a fresh, URL-safe database password and a unique JWT secret through the
CloudFormation console or a secrets-aware deployment process. Do not place
either value in a committed parameter file.

~~~bash
aws cloudformation deploy \
  --region us-east-1 \
  --stack-name AntimBench-Production \
  --template-file infra/aws/antimbench-production.yml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    CreateGitHubOidcResources=true \
    GitHubRepository=nabinphoenix/attendance_system \
    GitHubRepositoryOwnerId=159899712 \
    GitHubRepositoryId=1321622311 \
    GitHubEnvironment=production \
    DBPassword="$DB_PASSWORD" \
    JWTSecretKey="$JWT_SECRET_KEY" \
    CertificateArn="$ACM_CERTIFICATE_ARN"
~~~
If the stack already exists, run the same update from an IAM-authorized
principal and retain the existing secret parameter values. The OIDC provider
and deployment role are an optional authentication path; the current workflow
uses the existing AWS Academy session credentials described below.


The Node.js solution stack changes over time. Before creating or updating the
stack, confirm the current value:

~~~bash
aws elasticbeanstalk list-available-solution-stacks \
  --region us-east-1 \
  --query "SolutionStacks[?contains(@, 'Node.js 22') && contains(@, 'Amazon Linux 2023')]"
~~~

Pass the current result as SolutionStackName when it differs from the template
default.

## RDS migration

The stack creates a new private RDS instance and does not modify a local
database. Migrate the existing local PostgreSQL database explicitly:

~~~bash
pg_dump --format=custom --no-owner --no-acl "$LOCAL_DATABASE_URL" > antimbench.dump
pg_restore --clean --if-exists --no-owner --no-acl \
  --dbname "$RDS_DATABASE_URL" antimbench.dump
~~~

Confirm the row counts, application tables, and Alembic version on RDS. The
Elastic Beanstalk pre-deploy hook then runs:

~~~bash
python -m alembic upgrade head
~~~

It never creates a database, changes roles, or initializes local PostgreSQL.

## Elastic Beanstalk configuration

The CloudFormation environment supplies:

~~~text
DATABASE_URL
JWT_SECRET_KEY
AUTH_COOKIE_SECURE=true
FRONTEND_URL=https://antimbench.sunitanepali.com.np
CORS_ORIGINS=["https://antimbench.sunitanepali.com.np"]
PROFILE_MEDIA_BUCKET=<private S3 bucket>
PROFILE_MEDIA_PREFIX=profile-media
PROFILE_MEDIA_REGION=us-east-1
COLLEGE_NAME
SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL
~~~

SMTP values are optional, but account setup and notification delivery require a
working SMTP configuration. The instance role can only read, write, and delete
objects under the private profile-media/ prefix.

## ACM and Cloudflare

1. Request an ACM DNS-validated certificate in us-east-1 for
   antimbench.sunitanepali.com.np.
2. Add the ACM validation CNAME to Cloudflare with proxying disabled.
3. Wait for ACM status ISSUED.
4. Pass the certificate ARN to the CloudFormation stack.
5. Point the Cloudflare antimbench CNAME at the Elastic Beanstalk/ALB
   hostname. Keep the root and www records unchanged.
6. Configure the ALB port 80 listener to redirect to HTTPS 443 after the HTTPS
   listener is healthy. Use Cloudflare Full (strict) after the origin
   certificate is active.

The public application URL is:

~~~text
https://antimbench.sunitanepali.com.np
~~~

## GitHub Actions

The workflow .github/workflows/deploy.yml runs:

1. PostgreSQL-backed backend migrations and tests;
2. frontend TypeScript, lint, and production build;
3. a self-contained Elastic Beanstalk bundle with the Next.js standalone
   runtime, backend runtime packages, hooks, nginx configuration, and worker;
4. an S3 upload and Elastic Beanstalk application version;
5. a deployment to AntimBench-Prod;
6. a wait for Ready, Green, and the expected version label.

Configure these GitHub repository settings:

### Production environment secrets

~~~text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN
~~~

Add these under **Settings → Environments → production → Secrets** using the
current AWS Academy/VocLabs session values. The session token is required.
Refresh all three values whenever the lab session is restarted or expires.


### Variables

~~~text
AWS_REGION=us-east-1
EB_APPLICATION_NAME=AntimBench
EB_ENVIRONMENT_NAME=AntimBench-Prod
EB_S3_BUCKET=<DeploymentBucketName output>
~~~

`EB_S3_BUCKET` must be the exact `DeploymentBucketName` output from the
`AntimBench-Production` CloudFormation stack. Do not construct a bucket name
manually from the account ID or region. Retrieve the current value with:

~~~bash
aws cloudformation describe-stacks \
  --region us-east-1 \
  --stack-name AntimBench-Production \
  --query "Stacks[0].Outputs[?OutputKey=='DeploymentBucketName'].OutputValue" \
  --output text
~~~

Update the production environment variable with that value before rerunning a
deployment. The workflow performs an S3 preflight check after authenticating
with the AWS Academy session credentials, so a stale bucket variable fails with
an actionable error before the upload step.

There are no Vercel variables or deployment stages. The frontend and backend
are always delivered by the same Elastic Beanstalk version.

Push to main after the environment is provisioned. For a rollback, deploy a
previous healthy Elastic Beanstalk application version and confirm that its
database migrations remain compatible before replacing the current version.

## Local verification

For a local deployment-bundle check:

~~~bash
cd frontend
npm ci
npm run build

cd ../backend
uv sync --locked --no-dev
~~~

The GitHub workflow is the authoritative production packaging path. It rejects
environment files, Git metadata, local databases, certificates, caches, and
development build artifacts from the bundle.
