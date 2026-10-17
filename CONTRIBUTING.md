# Contributing

## Branch model

This repository uses **trunk-based development**: `master` is the single
long-lived branch and is expected to be deployable at all times. Work happens on
short-lived branches that are deleted as soon as they merge.

| Branch | Purpose |
| --- | --- |
| `master` | The only long-lived branch. Protected. |
| `feat/<slug>` | New capability |
| `fix/<slug>` | Bug fix |
| `chore/<slug>` | Tooling, CI, dependencies, cleanup |
| `docs/<slug>` | Documentation only |
| `dependabot/<...>` | Automated dependency bumps |

There is deliberately **no `develop` branch**. A second integration branch buys
nothing here because every change already passes CI before it lands, and it would
only add a merge step and a second place for history to drift.

## Rules on `master`

Enforced by the **Master Protection & CI Gates** ruleset:

- Every change lands through a pull request.
- **Linear history** — merge commits are rejected.
- Force-pushes and branch deletion are blocked.

Reinforced by repository settings:

- **Squash merge only** — the PR title becomes the commit subject and the commit
  messages become the body.
- **Head branches are deleted automatically** on merge, so no merged branch ever
  lingers.

## Pull request flow

```bash
git switch -c feat/my-change origin/master   # always branch off master
# ...commit in small, reviewable steps...
git push -u origin feat/my-change
gh pr create --base master
```

Then wait for CI, and squash-merge. The branch deletes itself.

Keep PRs focused: one concern per PR. If you notice an unrelated problem, open a
second PR rather than widening the first.

## Pre-push checklist

Run locally what CI runs remotely:

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src/ --strict
uv run pytest --cov=src          # coverage gate: 80%
databricks bundle validate --target dev
```

Dashboard (`dashboard/`) changes additionally:

```bash
corepack pnpm typecheck
corepack pnpm build
```

## Secrets

- Never commit credentials. Runtime secrets live in a gitignored `.env` locally
  and in the Databricks `f1_secrets` scope in the cloud.
- If a key is ever exposed, rotate it at the provider (for Gemini, Google AI
  Studio) — the repository history is not the place to fix it.
- Log neither credential values nor credential names. CodeQL's
  `py/clear-text-logging-sensitive-data` query runs on every PR and will fail the
  build for both.

## Dependency updates

Dependabot opens `dependabot/github_actions/...` PRs. Treat them like any other
PR: they must pass CI before merging, and their branches are deleted on merge.
