# Git Versioning & Workflow Reference

Professional version control is not just about saving changes — it is a communication protocol
between developers, a traceability system for deployments, and an audit trail for every decision
made on a codebase. This reference covers the complete discipline: commit authorship, branching
strategy, pull request conventions, hooks, automated versioning, and repository governance.

---

## 1. Branching Strategy

Choose one strategy per project and enforce it consistently. Do not mix conventions.

### GitHub Flow (recommended for most web projects)

Simple, continuous-delivery-friendly. Works best when you deploy `main` frequently.

```
main ──────────────────────────────────────────────────────► production
         │                        │
         └── feature/user-auth ──►┘  (PR → squash merge → delete branch)
                   │                        │
                   └── fix/login-redirect ──┘
```

**Rules:**

- `main` is always deployable — every commit on `main` must pass CI
- All work happens on short-lived feature branches cut from `main`
- Branches are merged via Pull Request only — never push directly to `main`
- Delete branches immediately after merge
- Deploy to production from `main` after every merge (or on tag)

### Git Flow (for versioned releases with long support cycles)

More structured. Use for libraries, SDKs, or apps with scheduled release cycles.

```
main        ──────────────────────────────────────────► v1.0 ── v1.1
                                                          │
develop     ────────────────────────────────────────────►│
               │             │             │
               feature/x ───►│  release/1.0►│  hotfix/1.0.1
```

**Branches:**
| Branch | Purpose | Merges into |
|---|---|---|
| `main` | Production-ready code only | — |
| `develop` | Integration branch for features | `main` (via release) |
| `feature/*` | New features | `develop` |
| `release/*` | Release stabilization | `main` + `develop` |
| `hotfix/*` | Critical production fixes | `main` + `develop` |

### Trunk-Based Development (for large teams with strong CI)

Everyone commits to `main` (or very short-lived branches ≤ 1 day). Requires feature flags
to decouple deployment from release.

**When to use:** teams with >5 engineers, strong automated test coverage, feature flag infrastructure.

### Branch Naming Convention (apply to all strategies)

```
<type>/<ticket-id>-<short-description>

feature/AUTH-42-oauth-github-integration
fix/PROJ-108-null-pointer-payment-service
hotfix/PROJ-201-csrf-token-validation
chore/PROJ-55-upgrade-prisma-v5
docs/PROJ-60-update-api-reference
release/v2.1.0
```

**Rules:**

- Lowercase only
- Hyphens as word separators — no underscores, no spaces
- Include ticket/issue ID when applicable
- Keep description concise: 3–5 words maximum
- Prefix must match the commit type for the work being done

---

## 2. Conventional Commits Specification

Conventional Commits is the standard for structured commit messages. It enables automated
changelog generation, semantic version bumping, and readable Git history. Every commit must
follow this format exactly.

### Full Commit Format

```
<type>[optional scope][optional !]: <description>

[optional body]

[optional footer(s)]
```

### Type Reference

| Type       | Purpose                                  | Triggers semver bump |
| ---------- | ---------------------------------------- | -------------------- |
| `feat`     | New feature visible to users             | `MINOR`              |
| `fix`      | Bug fix visible to users                 | `PATCH`              |
| `perf`     | Performance improvement                  | `PATCH`              |
| `refactor` | Code change with no feature/fix          | none                 |
| `docs`     | Documentation only                       | none                 |
| `test`     | Adding or correcting tests               | none                 |
| `build`    | Build system or dependency changes       | none                 |
| `ci`       | CI/CD configuration changes              | none                 |
| `chore`    | Maintenance tasks, tooling               | none                 |
| `style`    | Formatting, whitespace (no logic change) | none                 |
| `revert`   | Reverts a previous commit                | depends              |

**Breaking change** (triggers `MAJOR` bump): add `!` after the type, or add `BREAKING CHANGE:` footer.

### Commit Message Examples

**Simple feature:**

```
feat(auth): add OAuth2 login with GitHub provider
```

**Bug fix with scope:**

```
fix(api): resolve null pointer exception in payment processing

The charge endpoint was not handling undefined customer IDs when
the webhook fired before the user record was fully persisted.

Closes #108
```

**Breaking change — method 1 (exclamation mark):**

```
feat(api)!: replace REST endpoints with tRPC router

BREAKING CHANGE: All /api/v1/* endpoints are removed.
Clients must migrate to the tRPC client. See MIGRATION.md.
```

**Breaking change — method 2 (footer):**

```
refactor(db): migrate from Sequelize to Prisma ORM

BREAKING CHANGE: Database schema has been regenerated.
Run `prisma migrate deploy` before starting the application.
```

**Multiple footers:**

```
fix(auth): invalidate all sessions on password change

Ensures that changing a password terminates all active sessions
across devices, preventing session fixation attacks.

Closes #201
Reviewed-by: @teammate
```

### Commit Message Rules (enforce via commitlint)

- **Subject line:** imperative mood ("add", "fix", "remove" — not "added", "fixes", "removed")
- **Subject line:** 72 characters maximum — no period at the end
- **Subject line:** lowercase after the colon
- **Body:** wrap at 100 characters per line; explain _what_ and _why_, not _how_
- **Blank line** mandatory between subject and body
- **Scope:** optional, lowercase, refers to the module/domain affected (`auth`, `api`, `db`, `ui`)
- **Never** use vague messages: `wip`, `fix`, `update`, `changes`, `stuff` — these are rejected by commitlint

---

## 3. Full Toolchain Setup

### commitlint — enforce commit message format in CI and locally

```bash
pnpm add -D @commitlint/cli @commitlint/config-conventional
```

```javascript
// commitlint.config.js
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'subject-case': [2, 'always', 'lower-case'],
    'subject-max-length': [2, 'always', 72],
    'body-max-line-length': [2, 'always', 100],
    'scope-case': [2, 'always', 'lower-case'],
    // Enforce only allowed types
    'type-enum': [
      2,
      'always',
      [
        'feat',
        'fix',
        'perf',
        'refactor',
        'docs',
        'test',
        'build',
        'ci',
        'chore',
        'style',
        'revert',
      ],
    ],
  },
};
```

### husky + lint-staged — enforce quality on every commit

```bash
pnpm add -D husky lint-staged
pnpm exec husky init
```

```bash
# .husky/commit-msg  — validates commit message format
pnpm exec commitlint --edit "$1"
```

```bash
# .husky/pre-commit  — runs linters on staged files only
pnpm exec lint-staged
```

```javascript
// lint-staged.config.js
export default {
  '*.{ts,tsx,js,jsx}': ['eslint --fix', 'prettier --write'],
  '*.{json,md,yaml,yml}': ['prettier --write'],
  '*.py': ['ruff check --fix', 'ruff format'],
};
```

```json
// package.json — wire husky install to postinstall
{
  "scripts": {
    "prepare": "husky"
  }
}
```

### GitHub Actions — enforce commitlint on every PR

```yaml
# .github/workflows/commitlint.yml
name: Lint Commits

on:
  pull_request:
    types: [opened, synchronize, reopened, edited]

jobs:
  commitlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm exec commitlint --from ${{ github.event.pull_request.base.sha }} --to HEAD --verbose
```

---

## 4. Semantic Versioning In Depth

Version numbers are a contract with your users. Increment them with intention.

```
MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
  2   . 4  .  1  -   rc.1
```

| Segment | Increment when...                                   | Example          |
| ------- | --------------------------------------------------- | ---------------- |
| `MAJOR` | Breaking change — existing API consumers must adapt | `1.9.2 → 2.0.0`  |
| `MINOR` | New feature, fully backward-compatible              | `1.9.2 → 1.10.0` |
| `PATCH` | Bug fix, backward-compatible                        | `1.9.2 → 1.9.3`  |

**Pre-release identifiers (in order of maturity):**

```
v2.0.0-alpha.1   → internal, unstable, not for public use
v2.0.0-beta.1    → public testing, API may still change
v2.0.0-rc.1      → release candidate, API frozen, final testing
v2.0.0            → stable release
```

**Rules:**

- `MAJOR` resets `MINOR` and `PATCH` to zero: `1.9.2 → 2.0.0`
- `MINOR` resets `PATCH` to zero: `1.9.2 → 1.10.0`
- `0.y.z` signals initial development — anything may change at any time
- `1.0.0` is the first stable, public API

---

## 5. Tagging

Tags mark permanent points in history. Always annotate release tags — lightweight tags
(without `-a`) carry no metadata and should only be used for temporary personal reference.

```bash
# Annotated tag — required for releases
git tag -a v1.4.2 -m "Release v1.4.2: fix payment null pointer, add OAuth GitHub"
git push origin v1.4.2

# Tag a specific past commit
git tag -a v1.4.1 -m "Release v1.4.1" <commit-sha>
git push origin v1.4.1

# List tags sorted by version
git tag --sort=-version:refname

# Delete a tag (use with caution — never delete a tag that's been released)
git tag -d v1.4.2
git push origin --delete v1.4.2
```

### GPG Tag Signing (for hardened pipelines)

Sign tags cryptographically to prove they were created by a trusted key.

```bash
# Configure Git to use your GPG key
git config --global user.signingkey <YOUR_GPG_KEY_ID>
git config --global tag.gpgsign true

# Create a signed tag
git tag -s v1.4.2 -m "Release v1.4.2"

# Verify a signed tag
git tag -v v1.4.2
```

In GitHub: add your GPG public key under Settings → SSH and GPG keys. Signed tags display
a "Verified" badge on the release page.

---

## 6. Automated Versioning & Changelog Generation

Manual versioning is error-prone. Automate it using commit history.

### Option A: `semantic-release` (fully automated — recommended for CI/CD-first teams)

Reads commit messages since the last release, determines the next version automatically,
generates a changelog, creates a GitHub Release, and publishes to npm/PyPI if configured.

```bash
pnpm add -D semantic-release \
  @semantic-release/commit-analyzer \
  @semantic-release/release-notes-generator \
  @semantic-release/changelog \
  @semantic-release/github \
  @semantic-release/git
```

```javascript
// release.config.js
export default {
  branches: ['main'],
  plugins: [
    '@semantic-release/commit-analyzer', // determines version bump from commits
    '@semantic-release/release-notes-generator', // generates changelog content
    ['@semantic-release/changelog', { changelogFile: 'CHANGELOG.md' }],
    '@semantic-release/github', // creates GitHub Release
    [
      '@semantic-release/git',
      {
        assets: ['CHANGELOG.md', 'package.json'],
        message: 'chore(release): ${nextRelease.version} [skip ci]',
      },
    ],
  ],
};
```

```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    branches: [main]

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      issues: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm exec semantic-release
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**How it works:** push to `main` → `semantic-release` reads commits since last tag →
determines bump (`feat` → minor, `fix` → patch, `BREAKING CHANGE` → major) → tags, publishes,
creates release automatically. No manual `git tag` needed.

### Option B: `release-please` (Google's approach — PR-based)

Creates and updates a "Release PR" automatically. The release only happens when you merge
that PR — giving you manual control over timing while keeping versioning automated.

```yaml
# .github/workflows/release-please.yml
name: Release Please
on:
  push:
    branches: [main]

jobs:
  release-please:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: googleapis/release-please-action@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          release-type: node # or: python, go, rust, etc.
```

**How it works:** every push to `main` → `release-please` updates a "Release PR" with the
cumulative changelog and proposed version. Merge the PR when ready to release.

### Option C: Changesets (for monorepos)

The standard for monorepos with multiple independently versioned packages.

```bash
pnpm add -D @changesets/cli
pnpm exec changeset init
```

**Developer workflow:**

```bash
# After making changes to one or more packages:
pnpm exec changeset
# → Interactive prompt: which packages changed? major/minor/patch? summary?
# → Creates a .changeset/<random-name>.md file — commit this with your PR

# On release:
pnpm exec changeset version   # bumps package.json files and updates CHANGELOG.md
pnpm exec changeset publish   # publishes to npm
```

**Comparison:**

| Tool               | Best for                  | Versioning trigger             | Manual control         |
| ------------------ | ------------------------- | ------------------------------ | ---------------------- |
| `semantic-release` | Single packages, CI-first | Automatic on push              | None — fully automated |
| `release-please`   | Single packages, PR-based | Automatic, release on PR merge | When to merge          |
| `changesets`       | Monorepos                 | Manual changeset files         | Full                   |

---

## 7. Pull Request Conventions

A PR is a unit of review, not a dump of work. It should be small, focused, and self-explanatory.

### PR Title Format

PR titles must follow Conventional Commits format — they become the squash commit message:

```
feat(auth): add OAuth2 login with GitHub provider
fix(api): resolve null pointer in payment processing
chore(deps): upgrade Prisma to v5.14
```

Enforce this with a GitHub Actions step using `amannn/action-semantic-pull-request`:

```yaml
# .github/workflows/pr-title.yml
name: Validate PR Title
on:
  pull_request:
    types: [opened, edited, synchronize, reopened]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: amannn/action-semantic-pull-request@v5
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### PR Description Template

```markdown
<!-- .github/pull_request_template.md -->

## What does this PR do?

<!-- One paragraph: what problem does it solve, what was changed, and why. -->

## Type of change

- [ ] `feat` — new feature
- [ ] `fix` — bug fix
- [ ] `refactor` — code restructure, no behavior change
- [ ] `chore` — maintenance, dependencies
- [ ] `docs` — documentation only
- [ ] `perf` — performance improvement
- [ ] `test` — test coverage improvement
- [ ] Breaking change (mark with `!` in the PR title)

## How to test

<!-- Steps to reproduce the scenario and verify the fix/feature works. -->

## Checklist

- [ ] Tests written and passing locally
- [ ] No secrets or credentials included
- [ ] `.env.example` updated if new env vars were added
- [ ] Documentation updated if public API changed
- [ ] Self-reviewed: read every line of the diff before opening the PR
```

### PR Size Guidelines

| Lines changed | Assessment                                                |
| ------------- | --------------------------------------------------------- |
| < 200         | Ideal — fast to review, easy to reason about              |
| 200–500       | Acceptable with clear scope                               |
| 500–1000      | Requires strong justification (e.g., migration, scaffold) |
| > 1000        | Split into smaller PRs unless physically impossible       |

Large PRs accumulate more bugs, take longer to review, and are harder to revert.

---

## 8. Git Workflow Techniques

### Interactive Rebase — cleaning history before merging

Use to squash WIP commits, reorder, reword, or split commits before a PR is merged.

```bash
# Rebase the last 4 commits interactively
git rebase -i HEAD~4

# Rebase against main (all commits not in main)
git rebase -i origin/main
```

In the editor:

```
pick abc1234 feat(auth): scaffold OAuth module
squash def5678 wip: OAuth almost working
squash ghi9012 fix typo
reword jkl3456 add token refresh logic
```

| Command  | Effect                                           |
| -------- | ------------------------------------------------ |
| `pick`   | Keep commit as-is                                |
| `reword` | Keep commit, edit the message                    |
| `squash` | Merge into previous commit, combine messages     |
| `fixup`  | Merge into previous commit, discard this message |
| `drop`   | Remove the commit entirely                       |

**Rule:** never rebase commits that have been pushed to a shared remote branch. Rebase is for
local cleanup before the PR is opened.

### Amending the Last Commit

```bash
# Fix the last commit message
git commit --amend -m "feat(auth): add OAuth2 GitHub login"

# Add a forgotten file to the last commit (no message change)
git add forgotten-file.ts
git commit --amend --no-edit
```

### Reverting (safe undo for shared history)

```bash
# Revert a specific commit — creates a new commit that undoes the change
git revert <commit-sha>

# Revert a merge commit
git revert -m 1 <merge-commit-sha>
```

Use `revert` on `main` — never `reset --hard` on shared branches.

---

## 9. Repository Governance (.github/)

A well-configured `.github/` directory communicates standards to contributors and automates
governance without manual effort.

### CODEOWNERS

Automatically requests review from the right team when specific files are changed.

```
# .github/CODEOWNERS

# Global fallback — all files require review from the core team
*                   @org/core-team

# Infrastructure files require DevOps review
*.yml               @org/devops
Dockerfile          @org/devops
docker-compose*.yml @org/devops

# Security-sensitive files require security team review
src/server/auth.ts  @org/security-team
references/security.md @org/security-team

# Frontend components
src/components/     @org/frontend-team
```

### Issue Templates

```yaml
# .github/ISSUE_TEMPLATE/bug_report.yml
name: Bug Report
description: Report a reproducible bug
labels: ['bug', 'triage']
body:
  - type: textarea
    id: description
    attributes:
      label: What happened?
      description: Clear description of the bug.
    validations:
      required: true
  - type: textarea
    id: reproduction
    attributes:
      label: Steps to reproduce
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: Expected behavior
    validations:
      required: true
  - type: dropdown
    id: severity
    attributes:
      label: Severity
      options: [Critical, High, Medium, Low]
    validations:
      required: true
```

### Branch Protection Rules (enforce via GitHub Settings)

For `main` (and `develop` in Git Flow), configure:

```
✅ Require a pull request before merging
  ✅ Require at least 1 approval
  ✅ Dismiss stale reviews when new commits are pushed
  ✅ Require review from Code Owners

✅ Require status checks to pass before merging
  ✅ Require branches to be up to date before merging
  Required checks: lint, test, build (your CI job names)

✅ Require conversation resolution before merging
✅ Require linear history (enforces squash or rebase merge)
✅ Do not allow bypassing the above settings (applies to admins too)
✅ Restrict who can push to matching branches
```

---

## 10. Git Configuration Files

### .gitignore (universal additions beyond framework defaults)

```gitignore
# Environment
.env
.env.local
.env.*.local

# OS
.DS_Store
Thumbs.db

# Editor
.idea/
.vscode/
*.swp
*.swo

# Logs
*.log
logs/

# Build outputs
dist/
build/
.next/
out/

# Dependencies
node_modules/
.venv/
__pycache__/
*.pyc

# Test coverage
coverage/
.nyc_output/

# Temporary
tmp/
temp/
```

### .gitattributes (normalize line endings across OS)

```gitattributes
# Normalize line endings to LF on commit (prevents Windows/Mac diff noise)
* text=auto eol=lf

# Explicitly declare binary files — never modify
*.png binary
*.jpg binary
*.gif binary
*.pdf binary
*.ico binary

# Lock files — show diffs but don't merge automatically
package-lock.json merge=ours
pnpm-lock.yaml merge=ours
yarn.lock merge=ours
```

---

## 11. Quick Reference: Common Git Commands

```bash
# Start a new feature
git checkout -b feature/AUTH-42-oauth-github

# Stage only what's relevant (never use git add .)
git add src/server/auth.ts src/server/api/routers/auth.ts

# Commit with conventional message
git commit -m "feat(auth): add OAuth2 GitHub login"

# Keep your branch up to date with main (prefer rebase over merge)
git fetch origin
git rebase origin/main

# Push and open a PR
git push -u origin feature/AUTH-42-oauth-github

# After PR is merged: clean up locally
git checkout main
git pull origin main
git branch -d feature/AUTH-42-oauth-github

# Create a release tag
git tag -a v1.5.0 -m "Release v1.5.0"
git push origin v1.5.0

# Find the commit that introduced a bug
git bisect start
git bisect bad HEAD
git bisect good v1.4.0
# → Git checks out midpoints; run your test, mark good/bad until commit found
git bisect reset
```
