# Docker & Kubernetes Reference Templates

---

## Layer Caching & Build Optimization

Understanding Docker's layer model is the single most impactful optimization for build speed.

### The Layer Cache Mental Model

Every instruction in a Dockerfile creates an immutable layer. Docker caches each layer by its
instruction + the hash of all inputs (files, args). On rebuild, Docker reuses cached layers
from the top down — the moment any layer changes (or its inputs change), **all subsequent
layers are invalidated and rebuilt from scratch**.

```
Layer 1: FROM node:20-alpine          ← almost never changes → always cached
Layer 2: RUN apt-get install ...      ← rarely changes       → cached
Layer 3: COPY package*.json ./        ← changes when deps change
Layer 4: RUN npm ci                   ← rebuilt only when layer 3 changes
Layer 5: COPY . .                     ← changes on every code edit ← PUT LAST
Layer 6: RUN npm run build            ← rebuilt on every code change
```

**The core rule:** order instructions by ascending frequency of change — least volatile first,
most volatile last. Your source code changes on every commit; your base image and system
dependencies change rarely.

### The Classic Anti-Pattern vs The Correct Pattern

```dockerfile
# ❌ WRONG — cache-hostile ordering
FROM ubuntu
RUN apt-get update               # layer 2
WORKDIR /app                     # layer 3
COPY requirements.txt .          # layer 4
RUN pip3 install -r requirements.txt  # layer 5
COPY . .                         # layer 6 — PROBLEM: this should come AFTER install
CMD ["python", "app.py"]

# Every code change invalidates layer 6 — but also re-runs pip install
# because COPY . . came AFTER the install, meaning any file change in the
# context invalidates the install cache. Wait — actually the problem is
# different. See the correct pattern below.
```

```dockerfile
# ✅ CORRECT — cache-friendly ordering
FROM ubuntu                              # layer 1 — never changes
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
 && rm -rf /var/lib/apt/lists/*         # layer 2 — rarely changes; combined into one RUN
WORKDIR /app                             # layer 3 — never changes
COPY requirements.txt .                  # layer 4 — changes only when deps change
RUN pip3 install -r requirements.txt     # layer 5 — rebuilt only when layer 4 changes
COPY . .                                 # layer 6 — changes on every code edit → LAST
CMD ["python", "app.py"]                 # layer 7
```

**What changes in practice:**
- Edit `app.py` → only layers 6–7 rebuild. Layers 1–5 are fully cached. Fast.
- Edit `requirements.txt` → layers 4–7 rebuild. Layers 1–3 cached. Acceptable.
- Change base image → all layers rebuild. Rare.

### Combining RUN Instructions — Minimize Layer Count

Each `RUN` is a layer. Unrelated sequential `RUN` statements waste cache slots and inflate
image size when intermediate files aren't cleaned up in the same layer.

```dockerfile
# ❌ WRONG — 3 layers, apt cache left in image permanently
RUN apt-get update
RUN apt-get install -y curl git
RUN rm -rf /var/lib/apt/lists/*   # too late — previous layer already committed the cache

# ✅ CORRECT — 1 layer, cache cleaned in the same operation
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    curl \
    git \
 && rm -rf /var/lib/apt/lists/*
```

**Rule:** combine logically related `RUN` commands with `&&`. Clean up (package caches, temp
files, build artifacts) in the **same** `RUN` instruction that created them.

### .dockerignore — Cache Correctness and Context Size

`COPY . .` sends the entire build context to the Docker daemon. Without `.dockerignore`,
`node_modules/` (hundreds of MB), `.git/`, `.env`, and build artifacts are included —
inflating context size and invalidating the `COPY . .` layer on every trivial change.

```dockerignore
# .dockerignore — always commit this alongside your Dockerfile
node_modules/
.next/
dist/
build/
coverage/
.git/
.gitignore
.env
.env.*
*.log
README.md
.DS_Store
```

A proper `.dockerignore` means `COPY . .` only transfers what the application actually needs,
and the layer cache is not invalidated by files irrelevant to the build.

### BuildKit Cache Mounts — Advanced Package Manager Caching

BuildKit (enabled by default since Docker 23) supports persistent cache mounts that survive
across builds — far more efficient than relying on layer cache alone for package installs.

```dockerfile
# syntax=docker/dockerfile:1
# ↑ Required for BuildKit features

# Node.js — cache the npm/pnpm store across builds
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline

# Python — cache pip's download cache across builds
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# pnpm
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
```

The `--mount=type=cache` directory persists on the build host between runs. Even if the
`requirements.txt` changes, only the delta (new packages) is downloaded — previously cached
packages are reused from the mount.

**Note:** cache mounts are not included in the final image and are local to the build host.
In CI (GitHub Actions), pair with `cache-from: type=gha` at the workflow level for equivalent
cross-runner caching.

### Layer Optimization Checklist

- [ ] Base image pinned to a specific version (not `latest`)
- [ ] System dependencies installed in a single `RUN` with cache cleanup in the same layer
- [ ] Dependency manifest (`package.json`, `requirements.txt`) copied **before** `COPY . .`
- [ ] Package install runs **before** `COPY . .` so it only rebuilds when deps change
- [ ] Source code `COPY . .` is the last step before `CMD`/`ENTRYPOINT`
- [ ] `.dockerignore` excludes `node_modules`, `.git`, `.env`, build artifacts, logs
- [ ] Multi-stage build used to keep the runtime image free of build tools
- [ ] `RUN` commands combined with `&&`; intermediate files cleaned in the same layer
- [ ] BuildKit cache mounts used for package managers in CI-intensive projects

---



```dockerfile
# syntax=docker/dockerfile:1
FROM node:20-alpine AS base
WORKDIR /app
COPY package*.json ./

FROM base AS deps
RUN npm ci --only=production

FROM base AS builder
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs

COPY --from=deps /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json

USER nextjs
EXPOSE 3000
CMD ["node_modules/.bin/next", "start"]
```

---

## Python / FastAPI Dockerfile (multi-stage)

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

FROM python:3.12-slim AS runner
WORKDIR /app
RUN addgroup --system --gid 1001 appgroup && adduser --system --uid 1001 --ingroup appgroup appuser
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY . .
USER appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## docker-compose.yml (Full Stack: Next.js + Postgres + Redis)

```yaml
version: "3.9"

services:
  app:
    build:
      context: .
      target: runner
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgres://postgres:${POSTGRES_PASSWORD}@db:5432/mydb
      REDIS_URL: redis://redis:6379
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: mydb
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

---

## Docker Compose Secrets

**Source:** Docker official documentation — "Manage secrets securely in Docker Compose"
(docs.docker.com/compose/how-tos/use-secrets); Docker Compose Specification — secrets
top-level element (docs.docker.com/reference/compose-file/secrets); BetterStack,
"A Comprehensive Guide to Docker Secrets" (February 2025); OneUptime Engineering Blog,
"How to Use Docker Secrets in Swarm and Compose" (January 2026).

---

### Why Environment Variables Are Not Enough for Secrets

The instinctive approach — passing credentials as environment variables — has concrete
security weaknesses that Docker Compose secrets are specifically designed to eliminate:

```
❌ Environment variables are dangerous for secrets because:
  1. Visible to ALL processes in the container — not scoped to the application
  2. Printed in logs when debug-level logging is active — accidentally leaked
  3. Exposed in plain text via `docker inspect <container>` — readable by anyone
     with Docker daemon access on the host
  4. Easily committed to version control through .env files or compose.yaml
  5. Emitted in `docker compose config` output — leaked in CI/CD logs
```

Docker Compose secrets mount sensitive values as **read-only files** at
`/run/secrets/<secret_name>` inside the container — a tmpfs (in-memory) mount. They are
never stored in image layers, never visible in `docker inspect`, and access is granted
per-service, not globally to all processes.

**Official limitation:** secrets are supported on **Linux containers only**. Windows
containers support bind-mounting directories, not individual files.

### How It Works — The Two-Step Pattern

```
Step 1: Define the secret at the top level (where the value comes from)
Step 2: Grant access to specific services (which services can read it)
```

```yaml
# compose.yaml — minimal example (official Docker docs pattern)
services:
  myapp:
    image: myapp:latest
    secrets:
      - my_secret                              # Step 2: grant access to this service
    environment:
      # Point the app to the file path — never put the value here
      API_KEY_FILE: /run/secrets/my_secret

secrets:
  my_secret:                                   # Step 1: define the secret and its source
    file: ./my_secret.txt
```

Inside the container, Docker bind-mounts the file content to `/run/secrets/my_secret`.
No credential ever appears in an environment variable, image layer, or `docker inspect`.

### Three Secret Sources

**Source 1 — `file:` (standard for local development)**

```yaml
secrets:
  db_password:
    file: ./secrets/db_password.txt    # relative to compose.yaml; absolute path also valid
  ssl_cert:
    file: /etc/myapp/certs/server.crt
```

```bash
# Create secret files outside git tracking
mkdir -p ./secrets
echo "supersecretpassword" > ./secrets/db_password.txt
chmod 600 ./secrets/db_password.txt

# .gitignore — mandatory
echo "secrets/" >> .gitignore
echo "*.txt" >> secrets/.gitignore
```

**Source 2 — `environment:` (Compose v2.23+, CI/CD pipelines)**

Reads from an environment variable on the **host** — not inside the container. The host
env var is injected as a file at `/run/secrets/<name>` inside the container. Ideal for
CI/CD where credentials already exist as pipeline environment variables.

```yaml
secrets:
  api_key:
    environment: API_KEY        # reads $API_KEY from the host shell / CI runner
  db_password:
    environment: DB_PASSWORD
```

```bash
# GitHub Actions usage — host env vars supplied by CI secrets
API_KEY=${{ secrets.API_KEY }} DB_PASSWORD=${{ secrets.DB_PASSWORD }} docker compose up -d
```

**Source 3 — `external: true` (Docker Swarm only)**

Secret already exists in Docker Swarm's encrypted store; only its name is referenced.

```yaml
secrets:
  db_password:
    external: true    # created separately: echo "password" | docker secret create db_password -
```

### Full Production Example — PostgreSQL + API + Worker

```yaml
# compose.yaml

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: myapp
      POSTGRES_DB: myappdb
      # The _FILE suffix is a convention in official Docker images (postgres, mysql, redis):
      # the entrypoint reads the file at this path and uses its content as the credential value
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U myapp"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build: .
    environment:
      DATABASE_URL_FILE: /run/secrets/db_url
      JWT_SECRET_FILE: /run/secrets/jwt_secret
      STRIPE_KEY_FILE: /run/secrets/stripe_key
    secrets:
      - db_url
      - jwt_secret
      - stripe_key      # api needs stripe; worker does not
    depends_on:
      db:
        condition: service_healthy

  worker:
    build: .
    command: ["celery", "-A", "app.celery", "worker"]
    environment:
      DATABASE_URL_FILE: /run/secrets/db_url
    secrets:
      - db_url          # worker gets db_url only — stripe_key never mounted here
    depends_on:
      db:
        condition: service_healthy

secrets:
  db_password:
    file: ./secrets/db_password.txt
  db_url:
    file: ./secrets/db_url.txt
  jwt_secret:
    file: ./secrets/jwt_secret.txt
  stripe_key:
    file: ./secrets/stripe_key.txt

volumes:
  postgres_data:
```

**Per-service access control is the key advantage.** The `worker` receives `db_url` but
not `stripe_key` or `jwt_secret`. Even if the worker container is compromised, those secrets
are not mounted and cannot be read from `/run/secrets/`. Environment variables cannot
provide this granularity.

### Reading Secrets in Application Code

Two standard patterns for applications to consume secrets from `/run/secrets/`:

**Pattern A — `_FILE` convention (official images: postgres, mysql, redis, mariadb)**

The image entrypoint reads the `_FILE` env var and loads the file content automatically.
No code change required — it works out of the box.

```bash
# What the official postgres image does internally:
if [ -n "$POSTGRES_PASSWORD_FILE" ]; then
    POSTGRES_PASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"
fi
```

**Pattern B — Read file in application code (custom apps)**

```typescript
// TypeScript — read at startup with local dev fallback
import fs from "fs";

function readSecret(name: string): string {
  const filePath = `/run/secrets/${name}`;
  try {
    return fs.readFileSync(filePath, "utf8").trim();
  } catch {
    // Fallback to env var for local dev without Docker secrets
    const envValue = process.env[name.toUpperCase()];
    if (!envValue) throw new Error(`Secret '${name}' not found at ${filePath} or in env`);
    return envValue;
  }
}

// Read ONCE at startup — not on every request
const DB_PASSWORD = readSecret("db_password");
const JWT_SECRET  = readSecret("jwt_secret");
```

```python
# Python — read at startup with local dev fallback
import os
from pathlib import Path

def read_secret(name: str) -> str:
    """Read from /run/secrets/<name> (Docker) or environment variable (local dev)."""
    secret_path = Path(f"/run/secrets/{name}")
    if secret_path.exists():
        return secret_path.read_text().strip()
    env_value = os.environ.get(name.upper())
    if not env_value:
        raise RuntimeError(f"Secret '{name}' not found at {secret_path} or in env")
    return env_value

# Read ONCE at module import — fails fast if misconfigured
DB_PASSWORD = read_secret("db_password")
JWT_SECRET  = read_secret("jwt_secret")
```

### Secret File Attributes — Permissions and Ownership

```yaml
services:
  api:
    secrets:
      - source: db_password
        target: db_password    # filename in /run/secrets/ (defaults to secret name)
        uid: "1000"            # UID that owns the file inside the container
        gid: "1000"            # GID — match the non-root app user
        mode: 0400             # octal: 0400 = read-only for owner only (default: 0444)
```

Default mode `0444` is world-readable inside the container. For high-sensitivity secrets
(signing keys, payment credentials), restrict to `0400` and pair `uid`/`gid` with the
non-root user the container runs as — consistent with the non-root user pattern in the
Dockerfile section above.

### Build Secrets — Keep Credentials Out of Image Layers

For credentials needed only at build time (npm tokens, pip index auth, SSH keys), use
BuildKit's `--mount=type=secret`. The credential is available during the `RUN` command
but never written to any image layer.

```dockerfile
# syntax=docker/dockerfile:1
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./

# Secret available only during this RUN — not baked into the image
RUN --mount=type=secret,id=npm_token \
    npm config set //registry.npmjs.org/:_authToken=$(cat /run/secrets/npm_token) && \
    npm ci --only=production && \
    npm config delete //registry.npmjs.org/:_authToken
```

```yaml
# compose.yaml — supply build secret from host environment variable
services:
  api:
    build:
      context: .
      secrets:
        - npm_token

secrets:
  npm_token:
    environment: NPM_TOKEN    # $NPM_TOKEN on host → /run/secrets/npm_token at build time
```

Verify the secret is absent from the image:
```bash
docker history my-api:latest       # npm_token must not appear in any layer command
docker inspect my-api:latest       # no npm_token in image config or metadata
```

### Security Comparison

| Approach | In `docker inspect`? | In image layers? | Per-service control | Recommended for |
|---|---|---|---|---|
| `-e SECRET=value` | ✅ Exposed | No | No — all processes | Never in production |
| `.env` + `env_file:` | ✅ Exposed | No | No | Local dev only; gitignore mandatory |
| Compose `secrets:` + `file:` | No | No | ✅ Yes | Dev + single-host production |
| Compose `secrets:` + `environment:` | No | No | ✅ Yes | CI/CD pipelines |
| Docker Swarm `external: true` | No | No | ✅ Yes | Multi-node Swarm |
| External manager (Vault, AWS SM) | No | No | ✅ Yes | Enterprise / multi-cloud |
| BuildKit `--mount=type=secret` | No | No | Build-time only | Build credentials |

### Checklist

```
- [ ] Secret files created outside the repo, or in a gitignored ./secrets/ directory
- [ ] ./secrets/ entry in .gitignore — verified with git status
- [ ] No raw secret values in compose.yaml environment: blocks — only _FILE pointers
- [ ] Secret files chmod 600 on the host
- [ ] mode: 0400 set inside container for high-sensitivity secrets
- [ ] Application reads /run/secrets/<name> at startup, not on every request
- [ ] Per-service access: each service lists only the secrets it actually needs
- [ ] Build secrets use --mount=type=secret, not ARG (ARG values visible in docker history)
- [ ] CI/CD uses environment: source — no secret files left on CI runners
- [ ] docker compose config output never logged in CI — it prints resolved secret values
```

---

## Kubernetes Deployment (baseline)

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  namespace: production
spec:
  replicas: 2
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
        - name: my-app
          image: ghcr.io/org/my-app:latest
          ports:
            - containerPort: 3000
          envFrom:
            - configMapRef:
                name: my-app-config
            - secretRef:
                name: my-app-secrets
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          readinessProbe:
            httpGet:
              path: /health
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 3000
            initialDelaySeconds: 15
            periodSeconds: 30
---
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: my-app
  namespace: production
spec:
  selector:
    app: my-app
  ports:
    - protocol: TCP
      port: 80
      targetPort: 3000
---
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app
  namespace: production
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - myapp.example.com
      secretName: my-app-tls
  rules:
    - host: myapp.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-app
                port:
                  number: 80
```
