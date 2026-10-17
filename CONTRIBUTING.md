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

Before you touch `reports/**`, or whenever the calendar has moved on, also check
that the next race is still servable by the dashboard:

```bash
uv run python scripts/check_next_race_coverage.py
```

It exits non-zero when the calendar's next race — or a race that has already run
— has no artifacts, which shows up in the UI only as a greyed-out "Awaiting
Data" tile. `scripts/simulate_race.py --year <season> --round <n> --event "<name>"`
generates the missing prediction.

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

### Rotating the Supabase S3 keys

The S3 pair that backs both the FastF1 cache and the dashboard bundle has exactly
two live copies — `.env` and the `f1_secrets` scope — so rotate both with the
script rather than by hand:

```bash
uv run scripts/rotate_supabase_s3_keys.py --dry-run   # show the plan, change nothing
uv run scripts/rotate_supabase_s3_keys.py             # prompt for the new pair
```

Mint the replacement pair in the Supabase dashboard first (`Storage → S3 Access
Keys → Create new access key`) — the Storage S3 API cannot create keys. The
script backs up `.env` to a mode-600 `.env.bak.<utc>` file, updates both
locations, and proves the new pair against the bucket before reporting success.
Delete the previous access key afterwards; Databricks reads secrets at task
runtime, so no job edit or redeploy is needed.

GitHub Actions does **not** consume these credentials — no workflow references
`SUPABASE_S3_*` — so the pair must never be mirrored into repository secrets. The
four copies created in June 2026 predate the move to Databricks and are dead;
remove them with:

```bash
gh secret list | grep SUPABASE_S3           # expect no output
for s in SUPABASE_S3_ACCESS_KEY SUPABASE_S3_SECRET_KEY \
         SUPABASE_S3_ENDPOINT_URL SUPABASE_S3_BUCKET_NAME; do
  gh secret delete "$s"                     # takes one name; already-absent is a harmless 404
done
```

The same scope holds `F1_VERCEL_DEPLOY_HOOK_URL` (see `.env.example`), which the
export task posts to after publishing so Vercel rebuilds and a newly published
round becomes reachable. Store it via stdin, never `--string-value` (which would
put it in the process list):

```bash
databricks secrets put-secret f1_secrets F1_VERCEL_DEPLOY_HOOK_URL   # prompts, or pipe it in
```

## Dependency updates

Dependabot opens `dependabot/github_actions/...` PRs. Treat them like any other
PR: they must pass CI before merging, and their branches are deleted on merge.

Note that the `github-actions` ecosystem is capped at `open-pull-requests-limit:
10`, so when that many are open Dependabot silently stops proposing more — check
the workflow files for stale action versions if no PRs have appeared for a while.

### Action pins

Workflows normally reference an action's floating major tag (for example
`actions/checkout@v7`), which keeps patch and minor fixes flowing automatically.

An action that does not publish floating major tags must instead be pinned to a
full version. `astral-sh/setup-uv` is the current example: upstream stopped
publishing floating majors after `v7`, so `@v10` does not resolve and the pin is
written as `astral-sh/setup-uv@v10.3.0`. Verify a ref actually exists before
using it — an unresolvable action fails the job in seconds with
`Unable to resolve action ... unable to find version ...`.

```bash
git ls-remote --tags https://github.com/astral-sh/setup-uv.git | grep -oE 'refs/tags/v[0-9]+$'
```
