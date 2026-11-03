# Race-Weekend Runbook

| Field | Value |
|---|---|
| Status | Current operational runbook; reflects the system as of 2026-11-01 |
| Applies to | Production job `849873932739477` and pipeline `ee5ef64c-e347-41db-9d2d-2c6be421aadc` |
| Plan | [PLAN_CLOUD_NATIVE_SERVING.md](PLAN_CLOUD_NATIVE_SERVING.md) |
| Scope | Pre-race checks, post-race checks, failure handling, rollback, evidence capture |
| Time basis | All times UTC unless stated otherwise |

> **Read this first.** The current scheduled job’s dashboard task **exports** the committed `reports/` tree; it does **not** generate a new prediction. The job still ingests, runs DLT, trains, and notifies. Until Phase 22 workstream A lands, a completed race will not automatically produce a new post-race dashboard page. Never describe the old bundle as a post-race result.

---

## 1. Schedule and current limitations

| Item | Current value |
|---|---|
| Job | `[prod] F1 2026 Race Weekend Predictions Workflow` |
| Job ID | `849873932739477` |
| Pipeline | `ee5ef64c-e347-41db-9d2d-2c6be421aadc` |
| Cron | `0 0 6 ? * FRI-MON` (UTC) |
| Pause status | `UNPAUSED` |
| Intended days | Friday, Saturday, Sunday, Monday at 06:00 UTC |
| Next scheduled windows | Monday 2026-11-02 06:00 UTC (post-race), then São Paulo 2026-11-06 → 2026-11-09 |
| Latest verified run | `957016537359610` — 2026-11-01 06:00 UTC — `SUCCESS` (all five tasks; ingested a race-day stub — see §4.9) |
| Missing run observed | 2026-10-24 → 2026-10-30 — no run records (compute `INACTIVE`) |
| Dashboard bundle | Supabase `f1-cache`, prefix `dashboard/2026`, manifest written last |
| Dashboard URL | `https://f1-2026-predictions-beta.vercel.app` |
| Public manifest | `https://wjwqjmecefgyypkqnabe.supabase.co/storage/v1/object/public/f1-cache/dashboard/2026/manifest.json` |

Current limitations:

1. **No cloud prediction yet.** The export task publishes `PROJECT_ROOT/reports`, which is produced locally. The Monday job cannot create a new round’s predictions.
2. **Gmail SMTP fails.** The notification task reports `0/1 channels`; no production email is delivered. The job remains green because notifications are non-fatal.
3. **Oct 24–30 had no runs.** There is no failed run: the workspace compute was `INACTIVE` (see item 8 and §4.7).
4. **The dashboard may use committed reports.** `F1_DASHBOARD_DATA_BASE_URL` is not set in the repository; if it is also absent in Vercel, the build uses committed `reports/`.
5. **The Austin prediction is pre-race and local.** It was generated 2026-10-18 from local 2026 rounds 01–03. Do not claim it uses the full R1–17 Delta window.
6. **Race-day stub (fixed in `d6e0785`).** Before the fix, the Sunday 06:00 UTC run treated a race whose calendar date was “today” as completed and ingested a pre-race stub. See §4.9 for the recovery procedure and for the 2026 Mexico incident record.
7. **Re-ingest duplicates (fixed in `d6e0785`).** Bronze is an append-only streaming table while the ingest overwrites the round’s Volume directory, so re-ingesting a round appended a second copy of every lap. `laps_silver` now dedupes on `(Season, RoundNumber, Driver, LapNumber)`, keeping the newest `_ingested_at`.
8. **Compute can go `INACTIVE`.** The workspace compute was `INACTIVE` for eight days (2026-10-23 → 2026-10-31) and only resumed after a user login. A scheduled run during that window cannot fire; see §4.7.
9. **FastF1 credentials are required for live sessions.** `F1_USERNAME` and `F1_PASSWORD` are read from the `f1_secrets` scope by `run_ingest()`. Without them FastF1 can return partial or empty timing data even when the race has finished.

---

## 2. Pre-race checklist

Run this at least 24 hours before the race and again on race morning. Record the outputs in the evidence template.

### 2.1 Scheduled runs

```bash
uv run --env-file .env -- databricks jobs list-runs \
  --job-id 849873932739477 --limit 10
```

Expected:
- The latest periodic run is `SUCCESS`.
- The run’s start time matches the intended 06:00 UTC window.
- If the latest expected window is missing, see §4.1.

Check one run in detail:

```bash
uv run --env-file .env -- databricks jobs get-run <run_id> -o json
```

Expected: all five tasks are `TERMINATED` / `SUCCESS`.

### 2.2 Pipeline state

```bash
uv run --env-file .env -- databricks pipelines get \
  ee5ef64c-e347-41db-9d2d-2c6be421aadc -o json
```

Expected:
- `state: IDLE`
- latest update `COMPLETED`
- no failed update newer than the latest successful one

### 2.3 Serving bundle

```bash
curl -fsS \
  https://wjwqjmecefgyypkqnabe.supabase.co/storage/v1/object/public/f1-cache/dashboard/2026/manifest.json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["generated_at"]); print(d["rounds"]); print(d["file_count"])'
```

Expected:
- `generated_at` is recent enough for the intended release.
- `rounds` includes the upcoming round.
- `file_count` is non-zero and consistent with the expected artifact count.

If the manifest is old, see §4.4.

### 2.4 Live page

```bash
curl -fsSI https://f1-2026-predictions-beta.vercel.app/race/<round>
```

Then inspect the page payload:

```bash
curl -fsS https://f1-2026-predictions-beta.vercel.app/race/<round> \
  | python3 -c 'import json,re,sys; h=sys.stdin.read(); m=re.search(r"<script id=\"__NEXT_DATA__\" type=\"application/json\">(.*?)</script>",h,re.S); d=json.loads(m.group(1)); p=d["props"]["pageProps"]; print(p["race"]); print("drivers",len(p["predictions"])); print("has_markdown",bool(p.get("markdownReport") or p.get("predictedMarkdownReport")))'
```

Expected:
- HTTP 200.
- Race name, round, and date are correct.
- 22 driver rows.
- If markdown is missing, record it as an optional artifact gap, not a page failure.

### 2.5 Calendar coverage

```bash
uv run python scripts/check_next_race_coverage.py --season 2026
```

Expected: exit 0 for the next race. A failure means the dashboard will show a greyed-out/“Awaiting Data” tile; do not hide it.

### 2.6 Notification channel

Before a race weekend, confirm the channel is configured without printing secrets:

```bash
uv run --env-file .env -- databricks secrets list-secrets f1_secrets
```

Expected: the configured keys exist (names only). Do **not** print values. If Gmail is the only channel, assume no email delivery until Phase 22 workstream D is complete.

---

## 3. Post-race checklist

The race is Sunday; the current post-race window is Monday 06:00 UTC. FastF1 data may not be available immediately.

### 3.1 Confirm the run exists

```bash
uv run --env-file .env -- databricks jobs list-runs \
  --job-id 849873932739477 --limit 10
```

Expected: a run started at the Monday 06:00 UTC window. If absent, go to §4.1.

### 3.2 Inspect the five tasks

```bash
uv run --env-file .env -- databricks jobs get-run <run_id> -o json
```

Expected tasks:
1. `ingest_race_telemetry`
2. `run_medallion_pipeline`
3. `train_and_register_champion`
4. `dispatch_notifications`
5. `export_dashboard_data`

For the ingest task, read the output:

```bash
uv run --env-file .env -- databricks jobs get-run-output <ingest_task_run_id> -o json
```

Expected: a log line showing the completed round was ingested.
Not acceptable as success: `No completed race to ingest for season 2026.` If you see that line, FastF1 data was not available; see §4.2.

### 3.3 Check the Delta tables

Use the SQL warehouse in the Databricks UI or SQL editor. Do not start a warehouse unnecessarily; stop it when finished. Example:

```sql
SELECT RoundNumber, EventName, COUNT(*) AS lap_rows
FROM main.f1_2026_prod.lap_features_gold
WHERE Season = 2026
GROUP BY RoundNumber, EventName
ORDER BY RoundNumber DESC
LIMIT 5;
```

Expected: the new round appears with a plausible row count. Also check:

```sql
SELECT COUNT(*) AS bronze_rows FROM main.f1_2026_prod.telemetry_bronze;
SELECT COUNT(*) AS silver_rows FROM main.f1_2026_prod.laps_silver;
SELECT COUNT(*) AS driver_rows FROM main.f1_2026_prod.driver_features_gold;
```

Record the counts; do not infer success from the job state alone.

### 3.4 Check the serving bundle

```bash
curl -fsS \
  https://wjwqjmecefgyypkqnabe.supabase.co/storage/v1/object/public/f1-cache/dashboard/2026/manifest.json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["generated_at"]); print(d["rounds"]); print(d["file_count"])'
```

Expected: the new round is in `rounds`, and `generated_at` advanced.

**Current limitation:** before Phase 22 workstream A, the export only republishes the committed `reports/` tree. A new round will **not** appear just because the Delta tables advanced. If the manifest did not advance, record “Delta updated; dashboard not updated — expected until cloud inference lands.” Do not call this a successful end-to-end update.

### 3.5 Check the live page

```bash
curl -fsSI https://f1-2026-predictions-beta.vercel.app/race/<new-round>
```

Expected: HTTP 200 and the new round’s page. If the page is 404, the bundle/route is missing; see §4.5.

### 3.6 Check the notification

```bash
uv run --env-file .env -- databricks jobs get-run-output <notify_task_run_id> -o json
```

Expected: at least one channel reports success.
`0/1 channels succeeded` means no delivery; do not claim an email was sent. See §4.6.

---

## 4. Failure matrix

### 4.1 No run record after an expected window

1. Check the job schedule:
   ```bash
   uv run --env-file .env -- databricks jobs get 849873932739477 -o json
   ```
2. Confirm `pause_status: UNPAUSED` and the cron.
3. Check whether the workspace hit a Free Edition quota or was shut down for the day. Free Edition can stop compute when its fair-usage quota is exhausted.
4. Check the next window; a skipped run does not automatically mean the next one will skip.
5. If a manual run is required and the current job is known good:
   ```bash
   uv run --env-file .env -- databricks bundle run \
     --target prod f1_2026_race_predictions_job
   ```
   **Caveat:** the current job will ingest/DLT/train/export, but it still cannot create a new prediction. Do not describe a manual run as a dashboard update unless the manifest actually advances.
6. Record the incident; do not edit the cron in an emergency without approval.

### 4.2 Ingest says “No completed race to ingest”

This is expected when the last race is outside the 7-day lookback, FastF1 has not published the round yet, or the race is scheduled **today** (the detection window is `[today − days_back, today)`).

1. Confirm the race has actually finished and FastF1 has data.
2. Check the next scheduled window (or the planned post-race retry after Phase 22).
3. Do not fabricate lap times or duplicate an older round.
4. On race day, the run intentionally ingests nothing; the next window is Monday 06:00 UTC. If the round must land sooner, re-ingest it explicitly with `--round <n>` (see §4.9) once the session is complete.
5. If this is the Monday post-race run and the data is late, record “ingest deferred”; the next retry/manual run is required.

### 4.3 DLT pipeline failed

1. Read the latest pipeline update events and the failing table’s expectations.
2. Check the Volume contract: 12 columns, no `TIMESTAMP(NANOS)` raw files.
3. Do not drop production tables to “fix” a refresh without a backup/recreate plan.
4. Fix in dev/staging first; rerun production only after the same commit passes staging.

### 4.4 Export or manifest missing/old

1. Read the export task output for the S3/credential error.
2. Verify the Supabase bucket/credentials (names only; never log values).
3. Confirm the manifest is written last; a partial artifact set is not a valid release.
4. If the new manifest is missing, keep the old release; do not point Vercel at an incomplete prefix.
5. If credentials are the issue, rotate them with:
   ```bash
   uv run scripts/rotate_supabase_s3_keys.py --dry-run
   uv run scripts/rotate_supabase_s3_keys.py
   ```

### 4.5 Site shows the old round or 404s

1. Check the Vercel build environment:
   - `F1_DASHBOARD_DATA_BASE_URL`
   - `F1_DASHBOARD_DATA_STRICT`
2. If the base URL is unset, the build is using committed `reports/`; this is the likely cause of stale content.
3. Verify the public manifest and the specific artifact URL with `curl -I`.
4. If the bundle is valid but the site is old, trigger a rebuild from the Vercel deploy hook and verify the build logs.
5. Roll back to the previous release prefix if the new bundle is bad.

### 4.6 Notification failed (`0/N channels`)

1. Read the notify task output. `SMTPServerDisconnected` at login is not an authentication error.
2. On Databricks Free Edition, outbound internet is restricted; do not assume Gmail SMTP or port 587 will work.
3. Do not spend race weekend rotating the app password first; test egress before credentials.
4. Use the documented HTTPS relay once Phase 22 D2 is implemented.
5. If no channel works, record that no notification was delivered; the website remains the primary surface.

### 4.7 Free Edition quota / workspace shutdown

1. Check the workspace for a quota notice.
2. Do not add parallel tasks or start a second SQL warehouse.
3. Wait for the quota reset; use the next scheduled window.
4. If the race-weekend update is urgent, use the manual fallback only after confirming compute is available.

Observed 2026-10-23 → 2026-10-31: the workspace compute was `INACTIVE` for eight days and no scheduled run fired. Compute resumed only after a user login. A scheduled run does not wake an `INACTIVE` workspace by itself, so a silent gap in run history should be treated as this failure mode first — open the workspace and confirm the compute state before assuming a job or cron defect.

### 4.8 Unexpected or wrong data

1. Stop the release; do not publish a manifest over the last good one.
2. Compare the new round’s row counts and driver list with the previous round.
3. Check the feature contract version and model provenance.
4. If a model or feature change caused it, restore the previous release/model alias and open an incident.
5. Do not “fix” published numbers by hand.

### 4.9 Race-day stub ingested (race had not finished)

**Symptom.** The Sunday 06:00 UTC run is green, but the new round has a suspiciously small row count: a few dozen laps, every row at the same `LapNumber`, and placeholder driver IDs. Gold shows the new event with a handful of “drivers” and a tiny `total_laps`.

**Cause.** Before `d6e0785`, `find_last_completed_race` used `EventDate <= today`, so a race scheduled later the same day counted as completed. FastF1 returned a pre-race session snapshot; the ingest wrote it and DLT propagated it. The same defect made `notify` report a verdict for an unrun race.

**Do not** retry the ingest immediately. FastF1 caches the stub on the workspace, so a naive re-run reloads the same partial snapshot. Wait until the race has actually finished and FastF1 has published timing data.

**Do not** use `--all-completed` on race day either. `completed_round_numbers` still compares `EventDate` (midnight UTC in the FastF1 schedule) against the reference time, so on race morning it includes the unrun round. The scheduled job never passes that flag, but a manual backfill would reproduce the stub. Until this path is fixed, backfill with explicit `--round` values or wait for the next day.

**Recovery (approved per incident; no training, no promotion, no republish):**

1. Confirm the race is over and timing data is available. A quick probe with a throwaway cache is safe:
   ```bash
   uv run python - <<'PY'
   import tempfile, fastf1
   fastf1.Cache.enable_cache(tempfile.mkdtemp())
   s = fastf1.get_session(2026, 19, "R")
   s.load(laps=True, telemetry=False, weather=False, messages=False)
   print(len(s.laps), s.laps["Driver"].nunique(), int(s.laps["LapNumber"].max()))
   PY
   ```
   Expect ~1,000+ laps, ~20 drivers and a max lap near the race distance. If it still reports 0 laps or a stub, the session is not published yet; wait and retry.
2. Delete the FastF1 cache for that event so the workspace cannot serve the stub:
   ```bash
   databricks workspace delete --recursive \
     '/Workspace/Users/<user>/.bundle/f1_2026_predictions/prod/files/.cache/fastf1/2026/<date>_<Event_Name>'
   databricks workspace delete \
     '/Workspace/Users/<user>/.bundle/f1_2026_predictions/prod/files/.cache/fastf1/fastf1_http_cache.sqlite'
   ```
3. Re-ingest that round explicitly. Same-day auto-detection intentionally returns nothing, so pass `--round`:
   ```bash
   databricks jobs run-now --json '{
     "job_id": 849873932739477,
     "only": ["ingest_race_telemetry"],
     "notebook_params": {},
     "python_params": ["--season","2026","--run-mode","ingest","--round","19",
                       "--catalog","main","--schema","f1_2026_prod","--force"]
   }'
   ```
   Verify the log says `Landed <n> laps for 2026 R19` with a full-race count.
4. Confirm the Volume:
   ```sql
   SELECT COUNT(*) AS rows, COUNT(DISTINCT Driver) AS drivers,
          MIN(LapNumber) AS min_lap, MAX(LapNumber) AS max_lap
   FROM read_files('/Volumes/main/f1_2026_prod/raw_telemetry/season=2026/round=19',
                   format => 'parquet');
   ```
5. Full-refresh the pipeline to purge the stub from Bronze/Silver/Gold. Bronze is streaming, so a normal update keeps the stale rows:
   ```bash
   databricks pipelines start-update ee5ef64c-e347-41db-9d2d-2c6be421aadc --full-refresh
   ```
6. Verify 2026 Gold has both rounds correct and no duplicated laps:
   ```sql
   SELECT EventName, COUNT(*) AS drivers, SUM(total_laps) AS laps
   FROM main.f1_2026_prod.driver_features_gold
   WHERE Season = 2026 GROUP BY EventName ORDER BY EventName;
   ```
   Compare against Bronze per-round counts; a round whose Gold `total_laps` is roughly double Bronze is a dedupe failure.
7. Do **not** train, promote a model, or republish the dashboard as part of this recovery. The candidate trained on the stub must not become `@champion`.

**Incident record — 2026 Mexico City GP (R19), 2026-11-01:**

- `957016537359610` fired at 06:00 UTC; the race started at 20:00 UTC.
- Ingest logged `Landed 21 laps for 2026 R19`; the Volume had 21 rows, 21 drivers, all `LapNumber=2`.
- DLT propagated it: `telemetry_bronze` R19 = 21 rows; `driver_features_gold` Mexico = 21 drivers / 21 laps.
- R18 was unaffected: 1,163 laps and 22 drivers in Bronze and Gold.
- Training kept `@champion` (candidate CV RMSE 1.7439 vs incumbent 1.6566) and registered v4 as `@challenger`. The challenger is tainted by the stub and must not be promoted.
- Export republished 194 files, manifest `2026-11-01T06:07:18Z`, rounds 1–18. `/race/19` stayed 404, so no false post-race page was published.
- Notification failed again: `SMTPServerDisconnected`, `0/1 channels`.
- The race was interrupted by a red flag; a same-day re-ingest before the chequered flag would only have refreshed the stub.

---

## 5. Rollback

### 5.1 Dashboard bundle rollback

Target layout after Phase 22:

```text
dashboard/2026/releases/<UTC timestamp>-<short sha>/manifest.json
dashboard/2026/releases/<UTC timestamp>-<short sha>/<artifacts>
```

> **Current limitation:** the existing publisher writes to `dashboard/2026` and does not create versioned prefixes. Until P22-A5 lands, preserve the last known-good bundle before any republish; do not assume a prefix rollback is available.

1. Identify the last known-good release prefix.
2. Set `F1_DASHBOARD_DATA_BASE_URL` to that prefix in Vercel.
3. Trigger a rebuild.
4. Verify `/race/<expected-round>` returns 200 and 22 drivers.
5. Record the rollback in the evidence template.

Do not delete the bad or good release prefix during the incident; retention is decided later.

### 5.2 Model rollback

- Do not promote a candidate to cover a serving failure.
- The previous `@champion` alias and previous bundle remain the source of truth.
- If a model change caused the issue, stop export, restore the alias, and rerun the validation gate.
- R18 is frozen unless a separate approval explicitly changes it.

### 5.3 Schedule and notification rollback

- Restore the previous cron if the explicit-day or retry change causes failures.
- Disable the failing notification channel; keep the site as the primary surface.
- Do not claim a notification was delivered if the channel result is 0/N.

---

## 6. Evidence template

Copy this into the incident/issue/release record:

```text
Date/time (UTC):
Environment: prod
Trigger: scheduled | manual
Job run ID:
Pipeline update ID:
Expected round:
Ingest result: ingested | no completed race | failed
Bronze rows:
Silver rows:
Lap Gold rows:
Driver Gold rows:
Latest round in Delta:
Serving bundle generated_at:
Manifest rounds:
Manifest file_count:
Release prefix:
Site URL and status:
Notification result: 1/1 | 0/1 | not configured
What was verified:
What was NOT verified:
Rollback used: yes/no — prefix/alias:
Operator:
```

---

## 7. Do not do

- Do not edit `reports/` by hand to make a page appear.
- Do not write `manifest.json` before the artifacts are complete.
- Do not claim the dashboard updated because the Databricks job is green.
- Do not claim an email was delivered when the result is `0/N channels`.
- Do not promote a model or regenerate R18 without explicit approval.
- Do not print secret values, tokens, or connection strings.
- Do not run a local simulation as a production release without the plan/approval.
- Do not delete previous release prefixes during an incident.
- Do not add paid serving resources to work around a free-tier limit.
- Do not treat “no completed race” as an ingest failure when the data is simply not available yet.

---

## 8. References

- [PLAN_CLOUD_NATIVE_SERVING.md](PLAN_CLOUD_NATIVE_SERVING.md) — Phase 22 plan, ADR, tasks, risks, acceptance.
- [ARCHITECTURE.md](ARCHITECTURE.md) §3.4 and §4.4 — current model lanes and serving path.
- [README.md](../README.md) — deployment and dashboard environment variables.
- [CONTRIBUTING.md](../CONTRIBUTING.md) — branch, PR, and pre-push checks.
- Production job: `849873932739477`.
- Production pipeline: `ee5ef64c-e347-41db-9d2d-2c6be421aadc`.
- Public manifest: `https://wjwqjmecefgyypkqnabe.supabase.co/storage/v1/object/public/f1-cache/dashboard/2026/manifest.json`.
- Live dashboard: `https://f1-2026-predictions-beta.vercel.app`.
