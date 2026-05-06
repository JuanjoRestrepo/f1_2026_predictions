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
version: '3.9'

services:
  app:
    build:
      context: .
      target: runner
    ports:
      - '3000:3000'
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
      test: ['CMD-SHELL', 'pg_isready -U postgres']
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
              cpu: '100m'
              memory: '128Mi'
            limits:
              cpu: '500m'
              memory: '512Mi'
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
