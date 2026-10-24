# From Codebase to Production: GitHub, CI/CD, Docker, and Operations

This guide explains how to take this repository, or a similar full-stack
application, from a local folder to a repeatable, secure, observable production
deployment. The current target is one Linux VM running Docker Compose with
PostgreSQL, Caddy, and GHCR-based delivery. The AWS sections remain an optional
future path, not a requirement.

The commands use PowerShell on Windows where possible and POSIX shell on the
server. Replace values such as `YOUR_GITHUB_USERNAME`, `YOUR_REPOSITORY`,
`YOUR_DOMAIN`, and `YOUR_AWS_REGION` with your own values.

> **Important:** [DEPLOYMENT.md](DEPLOYMENT.md) is the source of truth for this
> repository's first deploy, SQLite migration, environment variables, HTTPS,
> backups, restore, and CI/CD secrets. This guide explains the wider delivery
> and operations model.

## 1. The mental model

DevOps is the set of practices that makes software delivery:

1. **Reproducible** - another machine can build the same application.
2. **Automated** - tests, packaging, and deployment do not depend on manual
   steps.
3. **Safe** - changes are reviewed, secrets are protected, and deployments can
   be rolled back.
4. **Observable** - failures, performance, and security events can be found.
5. **Recoverable** - data is backed up and the service can be restored.

The usual path is:

```text
Local code
  -> Git history
  -> Pull request and review
  -> CI: lint, type-check, test, build, security checks
  -> Immutable artifact: container image or build package
  -> CD: deploy the exact artifact
  -> Health checks and smoke tests
  -> Monitoring, rollback, and backups
```

CI answers **“is this change safe to merge?”** CD answers **“can the merged
artifact be delivered safely?”**

## 2. Understand this repository before automating it

Before introducing infrastructure, identify:

| Area | This repository |
| --- | --- |
| Frontend | React 19, TypeScript, Vite |
| Backend | FastAPI, Uvicorn, SQLAlchemy, Alembic |
| Database | PostgreSQL 17 via Compose in production; SQLite for local development and tests |
| Tests | Pytest backend against SQLite and PostgreSQL; Vitest, ESLint, TypeScript, and Vite build frontend |
| Static delivery | FastAPI serves `frontend/dist` from one origin behind Caddy |
| External services | Open Food Facts and optional DeepSeek photo analysis |
| Existing CI | `.github/workflows/ci.yml` runs both backends, frontend checks, Docker build, and GHCR publish |
| Runtime constraint | One Uvicorn worker because rate limits, photo jobs, and the day-edit lock are process-local |
| Existing operations docs | [DEPLOYMENT.md](DEPLOYMENT.md) |

Do this inventory for any codebase:

```text
Language and runtime versions
Package manifests and lockfiles
Build commands
Test, lint, and type-check commands
Database and migration strategy
Required environment variables
File uploads and persistent storage
External APIs and queues
Ports and health endpoints
Background jobs and scheduled tasks
Logging and error reporting
Current deployment assumptions
```

Do not put generated or machine-local material in Git. In this repository that
means `.venv`, `node_modules`, `frontend/dist`, local SQLite databases, upload
directories, logs, caches, and `.env` files. Verify `.gitignore` before the
first push. A lockfile and seed data are source-controlled inputs; a database
created from them is not.

## 3. Prepare the repository for GitHub

### 3.1 Create a clean, reviewable baseline

First inspect the current state. Do not discard other people's or your own
uncommitted work:

```powershell
git status --short
git diff --stat
git diff -- .gitignore README.md DEPLOYMENT.md
```

Run the local checks from the repository root:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm ci
npm run check
```

If dependencies are not installed, create the environment and install from the
lockable manifests. Do not commit the environment itself:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Review the result, then create a focused commit. Avoid committing secrets,
database files, build output, or unrelated formatting changes.

```powershell
git add .gitignore README.md DEPLOYMENT.md backend frontend .github
git diff --cached --check
git diff --cached --stat
git commit -m "Prepare repository for GitHub"
```

If the working tree contains intentional changes that are not ready, commit
only the files that belong to the current change or leave them for a separate
branch. Never use `git add .` blindly on a project containing local data.

### 3.2 Create the GitHub repository and push it

Create an empty repository on GitHub. Do not initialize it with a README,
license, or `.gitignore` if this local repository already has those files.

```powershell
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPOSITORY.git
git remote -v
git push -u origin main
```

If a remote already exists:

```powershell
git remote set-url origin https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Use SSH instead if that is your standard:

```powershell
git remote set-url origin git@github.com:YOUR_GITHUB_USERNAME/YOUR_REPOSITORY.git
```

### 3.3 Configure repository protection

In GitHub, configure:

- A protected `main` branch.
- Pull requests required for changes to `main`.
- At least one approval for production repositories.
- Required status checks from the CI workflow.
- Branches up to date before merge when the team needs strict validation.
- Conversation resolution before merge.
- No force pushes or branch deletion for `main`.
- Dependabot updates for npm, pip, GitHub Actions, and Docker where applicable.
- Secret scanning, push protection, and code scanning if available.

Use short-lived feature branches:

```powershell
git switch -c feature/meal-photo-improvements
```

## 4. The pull request lifecycle

Use this lifecycle for every production change:

1. Create an issue or task with acceptance criteria.
2. Create a branch from the latest `main`.
3. Make one coherent change.
4. Add or update tests and documentation.
5. Run the same checks CI will run.
6. Commit with a meaningful message.
7. Push the branch and open a pull request.
8. Explain what changed, why, how it was tested, deployment impact, migration
   impact, and rollback steps.
9. Let CI finish. Fix failures in the branch; do not bypass required checks.
10. Obtain review. Treat review comments as correctness and maintainability
    feedback, not as a formality.
11. Update the branch if `main` moved:

```powershell
git fetch origin
git rebase origin/main
git push --force-with-lease
```

12. Squash-merge (or use the team's chosen merge strategy) into `main`.
13. Delete the feature branch.
14. Confirm CD deployed the expected commit and run a smoke test.

Do not make direct production edits on a server. If an urgent change is made,
turn it into a commit immediately so Git remains the source of truth.

### Pull request checklist

- [ ] Scope and acceptance criteria are clear.
- [ ] Tests cover the changed behavior and important failure paths.
- [ ] No secrets, credentials, local databases, or generated files are included.
- [ ] API, schema, environment, and operational documentation is updated.
- [ ] Backward compatibility and migration order were considered.
- [ ] Logs do not expose passwords, tokens, cookies, or personal data.
- [ ] CI passes from a clean checkout.
- [ ] Rollback is understood.

## 5. Continuous Integration with GitHub Actions

### 5.1 What CI should validate

A good CI pipeline runs on pull requests and pushes to protected branches:

1. Checkout source.
2. Install the exact dependency versions from lockfiles.
3. Lint.
4. Type-check.
5. Run unit and integration tests.
6. Build production assets.
7. Validate migrations and container builds.
8. Run dependency and secret/security checks.
9. Upload useful reports and artifacts.

Keep fast checks early and expensive checks later. Pin major action versions,
use least-privileged permissions, and avoid printing environment variables.

This repository's `.github/workflows/ci.yml` runs:

- `backend`: Python 3.12, SQLite tests.
- `backend-postgres`: Python 3.12, PostgreSQL 17 service, same suite.
- `frontend`: Node 22, `npm ci`, and `npm run check` (ESLint, Vitest, TypeScript,
  production build).
- `docker`: full production image build after all tests pass.
- `publish`: on `main` and `v*` tags, pushes immutable `sha-` tags and `latest`
  to GHCR.

`backend/tests/conftest.py` refuses to reset a PostgreSQL database unless its name
ends in `_test`. Test runs drop and recreate the `public` schema, so never point a
test run at production.

### 5.2 Deployment workflow shape

`.github/workflows/deploy.yml` listens for a successful `CI` run on `main`. It is
gated by the repository variable `DEPLOY_ENABLED` so an unconfigured server does
not break every merge. When enabled, it:

1. Updates the server checkout.
2. Backs up PostgreSQL if the database is running.
3. Pulls the exact `sha-<commit>` image from GHCR.
4. Runs `docker compose up -d --no-build`.
5. Checks `/api/health` and prints logs on failure.

It uses SSH secrets and repository variables instead of storing a deploy key in
the image. See [DEPLOYMENT.md](DEPLOYMENT.md) for the exact list.

### 5.3 CI failure diagnosis

Read the first meaningful error, not the final summary. Reproduce it locally
with the same runtime and command. Common causes are:

- `npm install` instead of `npm ci`, causing a lockfile mismatch.
- Different Python or Node versions.
- A missing test environment variable.
- Tests depending on local files or time zones.
- Tests sharing mutable state.
- A migration not included in the image.
- A frontend API URL baked incorrectly at build time.

Fix the application or workflow; do not make CI permissive merely to turn it
green.

## 6. Dockerizing a full-stack application

### 6.1 Why containers help

A container packages the runtime, dependencies, and startup command into an
immutable image. The same image can be tested in CI and promoted through
staging to production. Configuration and secrets remain outside the image.

Build-time values such as a Vite API base URL are different from runtime
values. Never bake secrets into a frontend bundle: frontend code is public.

### 6.2 Current production shape for this repository

`docker-compose.yml` defines three services:

- **caddy**: the only published port (80 today, 443 later); reverse proxy and
  optional automatic TLS.
- **app**: one Uvicorn worker, non-root, serves the API and the built frontend.
- **db**: PostgreSQL 17 on the private Compose network, with a persistent volume.

PostgreSQL data, uploads, and Caddy state are named volumes. The app image is
built multi-stage from `Dockerfile` and used unchanged in CI and production.

The image includes the frontend build, Alembic migrations, seed CSVs, and scripts.
It excludes local databases, virtual environments, uploads, logs, and `.env`.

### 6.3 Build and smoke test containers

The actual `Dockerfile` builds `frontend/dist`, installs Python requirements, runs
as UID 10001, and starts one worker with proxy headers trust limited to the
Compose network. Build it with:

```powershell
docker build -t calorie-tracker:local .
```

For a full local stack, create `.env` from `.env.production.example`, adjust
`APP_IMAGE` to `calorie-tracker:local`, then:

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://127.0.0.1/api/health
```

Do not test production with SQLite. The Compose environment sets `DATABASE_URL`
to PostgreSQL, and Alembic runs at app startup.

For local application development, SQLite plus the Vite dev server is faster and
is still supported.

### 6.4 Container security and reliability

- Use a small pinned base image and rebuild regularly.
- Prefer a non-root runtime user.
- Do not copy `.env`, credentials, `.venv`, `node_modules`, or local databases.
- Use a read-only root filesystem where the application supports it.
- Mount only required writable paths.
- Add a `HEALTHCHECK` or platform health check.
- Handle SIGTERM and shut down gracefully.
- Log to stdout/stderr; let the platform collect logs.
- Scan images with Trivy, Docker Scout, or the organization's approved tool.
- Pin dependencies and review Dependabot updates.
- Never use `latest` as the production rollback reference; use an immutable
  image tag such as the Git commit SHA.

## 7. Continuous Delivery: build once, promote the same artifact

The safest CD process is:

```text
main merge
  -> CI passes
  -> build image tagged with commit SHA
  -> push image to registry
  -> deploy to staging
  -> smoke test
  -> manual approval (for production)
  -> deploy the same image digest to production
```

Do not rebuild separately for staging and production: the two images can differ.
Store the image digest and deployment commit in the deployment record.

### Environments

Use at least:

- **Development** - local machines; disposable data.
- **Staging** - production-like configuration; safe test data.
- **Production** - real users and data; approvals and backups required.

Keep separate:

- Staging and production hosts, databases, and credentials.
- GitHub Environments and environment secrets.
- Domains and monitoring alerts.

### Deployment strategies

- **Restart in place:** `docker compose up -d --no-build` with a new immutable
  image; a short downtime, acceptable for a few users.
- **Blue/green:** run a second stack and switch the proxy after validation.
- **Canary:** send a small percentage of traffic to the new version first.

For the current single-VM deployment, a restart with a health check and a tested
rollback tag is sufficient. Add blue/green when downtime cost justifies it.

### Database migration rules

1. Write backward-compatible application changes first.
2. Add nullable columns or new tables before code requires them.
3. Deploy the migration before or with the compatible application.
4. Backfill separately and observe it.
5. Remove old columns only after all old application versions are gone.
6. Back up before production migrations.
7. Never edit production schema manually without recording the equivalent
   migration.

For this project, Alembic migrations live under `backend/migrations/` and run at
app startup. Production uses PostgreSQL. SQLite remains for local development and
the primary CI test job. Never treat an application image rollback as a database
rollback.

## 8. AWS: an optional future path

### 8.1 AWS foundations

Create an AWS account with:

- MFA on the root user.
- No access keys for the root user.
- A billing alarm and budget.
- A non-root administrative identity using IAM Identity Center.
- Separate users/roles for humans and workloads.
- Least-privilege policies.
- CloudTrail enabled.
- A chosen region close to users and compliant with data requirements.

Use the AWS CLI locally only with a named profile:

```powershell
aws configure sso
aws sts get-caller-identity --profile YOUR_PROFILE
```

Never put AWS access keys in GitHub source, Docker images, `.env` files
committed to Git, or application logs.

### 8.2 Option A: EC2 for the first simple deployment

EC2 is understandable for learning and for a small single-instance application:

```text
Internet
  -> Route 53 DNS
  -> security group: 80/443 only
  -> Docker Compose with Caddy for TLS
  -> backend container on localhost:8000
  -> persistent EBS volume for PostgreSQL, uploads, and backups
```

Steps:

1. Create a VPC, public subnet, route table, and security group.
2. Launch a current Amazon Linux or Ubuntu instance with an IAM instance role.
3. Allow SSH only from a controlled administrator IP, or use Systems Manager
   Session Manager instead of opening port 22.
4. Install Docker and a TLS reverse proxy.
5. Pull the image tagged with the approved commit SHA.
6. Store environment values in AWS Systems Manager Parameter Store or Secrets
   Manager, not in the image.
7. Mount persistent encrypted EBS storage for PostgreSQL data and uploads.
8. Configure daily backups to an encrypted S3 bucket and test restoration.
9. Attach a domain and configure HTTPS.
10. Add CloudWatch logs, disk alarms, CPU alarms, and an uptime check.

EC2 has a larger operational burden: patching, instance replacement, disk
capacity, process supervision, and recovery are yours.

### 8.3 Option B: ECS Fargate for a managed container

For the recommended container path:

```text
Route 53
  -> ACM certificate
  -> Application Load Balancer
  -> ECS service on Fargate
  -> ECR image
  -> RDS PostgreSQL and S3
  -> CloudWatch logs and alarms
```

Create:

- An ECR repository for the image.
- An ECS cluster and task definition.
- Private subnets for tasks and RDS.
- An Application Load Balancer in public subnets.
- A security group allowing ALB -> task and task -> RDS only.
- An execution role for pulling images and writing logs.
- A task role for only the AWS APIs the application needs.
- Secrets Manager references for database credentials and API keys.
- A target-group health check.
- An autoscaling policy only after the application supports shared state.

Use RDS PostgreSQL instead of a container database for multiple tasks. Use S3 for user
uploads and CloudFront for static frontend delivery when splitting services.
Use SQS plus a worker service for photo analysis or other long-running jobs.

### 8.4 Alternative managed services

- **AWS App Runner:** simplest managed container entry point; fewer knobs.
- **Elastic Beanstalk:** convenient VM-oriented deployment, but still carries
  platform configuration and operational complexity.
- **Lambda/API Gateway:** useful for stateless request handlers, but a poor
  direct fit for a long-running FastAPI process with file/background behavior
  unless deliberately adapted.
- **S3 + CloudFront:** excellent for the Vite frontend as static assets.

Choose the least complex service that satisfies reliability, scale, compliance,
and operational requirements. “More AWS services” is not automatically better.

## 9. GitHub Actions to AWS authentication (optional)

Prefer GitHub Actions OpenID Connect (OIDC) over long-lived AWS access keys:

1. Create an AWS IAM OIDC identity provider for GitHub.
2. Create a deploy role trusted only for the exact GitHub organization,
   repository, branch, and environment.
3. Give the role only ECR push and the deployment actions it needs.
4. Require the production GitHub Environment for production jobs.
5. Add a deployment approval rule.
6. Use the role with `aws-actions/configure-aws-credentials`.

A typical image publish job is:

```yaml
permissions:
  contents: read
  id-token: write

steps:
  - uses: actions/checkout@v4
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
      aws-region: ${{ vars.AWS_REGION }}
  - uses: aws-actions/amazon-ecr-login@v2
  - name: Build and push immutable image
    env:
      IMAGE_TAG: ${{ github.sha }}
    run: |
      docker build -t "$ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG" .
      docker push "$ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG"
```

Use the exact AWS action syntax and task-definition deployment action for the
chosen platform. Keep deployment permissions out of the PR workflow; a forked
pull request must never receive production credentials.

## 10. Secrets, configuration, and data

Classify every configuration value:

| Type | Example | Storage |
| --- | --- | --- |
| Public build setting | frontend API path | Repository variable or build config |
| Non-secret runtime setting | region, log level | Task definition/environment |
| Secret | API key, DB password, admin password | Server `.env` mode 600, GitHub Actions secrets |
| Persistent data | database, uploads | Compose volumes with backups (S3 for offsite copies) |

For this application, carefully handle `DEEPSEEK_API_KEY`,
`ADMIN_CONFIRM_PASSWORD`, `COOKIE_SECURE`, database paths, upload storage, and
allowed origins. Production should use HTTPS, `COOKIE_SECURE=true`, narrowly
scoped `CORS_ORIGINS`, and a deliberate registration policy.

If a secret is exposed:

1. Revoke or rotate it immediately.
2. Remove it from the current source and history as appropriate.
3. Check logs, CI output, and artifact layers.
4. Audit access using the provider's logs.
5. Document the incident and prevention.

Changing a secret in the current file is not enough if it was pushed to Git.

## 11. Observability and operations

### Health checks

Provide separate checks where possible:

- **Liveness:** the process is running and can respond.
- **Readiness:** dependencies and migrations permit serving traffic.
- **Synthetic smoke test:** login or a safe end-to-end request works.

A health endpoint must not expose credentials, internal stack traces, or
unnecessary database details.

### Logs

Emit structured logs to stdout/stderr with:

- timestamp and severity;
- request or correlation ID;
- route and status;
- duration;
- deployment version/commit;
- useful error context without secrets or sensitive user data.

Docker's `json-file` driver keeps a bounded local history; ship logs off the VM
when you need search or long retention. Set retention and alerting intentionally.

### Metrics and alerts

At minimum monitor:

- request rate, latency, and 4xx/5xx rate;
- container restarts and deployment failures;
- CPU, memory, disk, and database connections;
- queue depth and job age;
- backup success and restore test status;
- certificate expiry;
- provider billing and unusual spend, if using cloud services.

Alert on symptoms users experience, not every log line. Every alert should
have an owner and a runbook.

### Incident response

When production breaks:

1. Confirm impact and establish an incident owner.
2. Check the latest deployment, health checks, logs, and dependencies.
3. Stop the blast radius: rollback, disable a feature, or scale safely.
4. Preserve evidence and communicate status.
5. Restore service before performing non-urgent cleanup.
6. Write a blameless post-incident review with prevention actions.

## 12. Backups, disaster recovery, and rollback

Backups are not complete until restoration has been tested.

Define:

- **RPO:** maximum acceptable data loss.
- **RTO:** maximum acceptable recovery time.
- retention period;
- encryption and access controls;
- off-instance/off-account copies;
- restore owner and documented procedure.

The current deployment uses `deploy/backup_postgres.sh`, which runs `pg_dump`
inside the database container, keeps the newest 14 dumps, and writes them to
`backups/`. The deploy workflow takes a backup before replacing the app. For
production:

- back up before migrations and before each deploy;
- run and verify daily backups;
- copy backups off the VM regularly;
- test restoring to a separate database or instance;
- keep PostgreSQL and uploads on persistent volumes;
- document how uploads and database records remain consistent;
- never treat an image rollback as a database rollback.

Rollback an application by redeploying the previous known-good image digest.
If a migration is destructive, application rollback alone may not work; this is
why migrations must be backward compatible and destructive changes delayed.

## 13. Security baseline

- Enforce HTTPS and secure, appropriately scoped cookies.
- Use CSRF protection where cookie-authenticated state-changing requests need it.
- Validate file type, size, and content; store uploads outside executable paths.
- Apply authentication, authorization, and rate limits at the API boundary.
- Restrict CORS to known origins.
- Use parameterized queries and ORM safeguards.
- Do not return stack traces to clients.
- Patch OS and dependencies.
- Scan dependencies, images, and infrastructure.
- Encrypt data in transit and at rest.
- Keep production data out of development and CI.
- Review IAM policies and security groups periodically.
- Record audit events for administrative data changes.

For a real production launch, perform a focused security review and an
application-specific threat model. A CI pipeline is not a security assessment.

## 14. A staged implementation plan for this project

### Stage 1: source control

- [ ] Review the full tracked file list and `.gitignore`.
- [ ] Remove or rotate any accidentally exposed secret.
- [ ] Run backend and frontend checks locally.
- [ ] Push the clean baseline to GitHub.
- [ ] Protect `main`.

### Stage 2: dependable CI

- [x] Run backend tests against SQLite and PostgreSQL.
- [x] Run frontend lint, tests, type-check, and production build.
- [x] Validate the production Docker build.
- [x] Publish immutable image tags to GHCR on `main` and version tags.
- [ ] Add dependency update automation and secret scanning if desired.

### Stage 3: first deployment

- [ ] Create one Linux VM and install Docker Engine plus the Compose plugin.
- [ ] Clone the repository and create `.env` from `.env.production.example`.
- [ ] For a fresh install, start the stack and verify `/api/health`.
- [ ] For an existing database, create the schema without starting the app, run
  the SQLite migration script, verify it, then start the stack.
- [ ] Confirm the curated food catalog is present (fresh installs seed it when
  `SEED_FOODS_IF_EMPTY=true`).
- [ ] Create and promote the first admin; then set `ALLOW_REGISTRATION=false`.
- [ ] Configure daily backups and copy them off the VM.
- [ ] Enable HTTPS once a domain exists and set `COOKIE_SECURE=true`.

### Stage 4: automated CD

- [ ] Publish the first image to GHCR.
- [ ] Add SSH and GHCR read secrets plus `DEPLOY_ENABLED` and `DEPLOY_PATH`.
- [ ] Confirm the deploy workflow backs up, pulls the exact `sha-` image, and
  passes its health check.
- [ ] Document and test rollback to a previous `sha-` tag.

### Stage 5: scale and harden

- [ ] Move photo work to a queue and worker before scaling the app.
- [ ] Add shared rate limiting and a database-backed day lock.
- [ ] Move uploads to object storage.
- [ ] Split frontend delivery only if it solves a measured problem.
- [ ] Add blue/green or canary deployment when risk justifies it.
- [ ] Run restore drills and incident exercises.

## 15. Everyday command reference

```powershell
# Start from the latest protected branch
git switch main
git pull --ff-only origin main

# Make a focused change
git switch -c fix/short-description

# Validate locally
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run check
cd ..

# Inspect exactly what will be committed
git status --short
git diff --check
git diff --stat
git add path\to\intentional\files
git diff --cached --check
git commit -m "Describe the user-visible change"
git push -u origin fix/short-description

# Keep a branch current
git fetch origin
git rebase origin/main
git push --force-with-lease
```

Server operations:

```bash
cd /opt/calorie-tracker
docker compose ps
docker compose logs -f --tail=100 app
docker compose pull app
docker compose up -d --no-build
sh ./deploy/backup_postgres.sh
curl -fsS http://127.0.0.1/api/health
```

The goal is not to memorize every AWS or GitHub command. The goal is to make
the path from a change to a tested, observable, reversible production release
boring and repeatable.
