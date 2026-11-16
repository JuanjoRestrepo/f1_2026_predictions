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
| Pause status | `UNPAUSED` — restored 2026-11-12 after the R19/R20 backfill and Gold verification (see §4.9) |
| Intended days | Friday, Saturday, Sunday, Monday at 06:00 UTC |
| Next scheduled windows | Las Vegas 2026-11-20 → 2026-11-23 |
| Latest verified run | `922153016042740` — 2026-11-14 06:00 UTC — `SUCCESS` (all five tasks, 4m24s) |
| Previous scheduled run | `452413799810251` — 2026-11-13 06:00 UTC — `SUCCESS` (all five tasks, 4m45s) |
| Latest manual backfill | 2026-11-12 — R19 `310152296089` (1,084 laps), R20 `234559857240873` (1,435 laps); full refresh `f4df2afb-b437-49c1-891f-093e870a45cd` |
| Missing run observed | 2026-10-24 → 2026-10-30 — no run records (compute `INACTIVE`); 2026-11-02 → 2026-11-12 — job intentionally `PAUSED` |
| Dashboard bundle | Supabase `f1-cache`, prefix `dashboard/2026`, manifest written last (project restored 2026-11-17, see §4.10) |
| Dashboard URL | `https://f1-2026-predictions-beta.vercel.app` |
| Public manifest | `https://wjwqjmecefgyypkqnabe.supabase.co/storage/v1/object/public/f1-cache/dashboard/2026/manifest.json` |

Current limitations:

1. **No cloud prediction yet.** The export task publishes `PROJECT_ROOT/reports`, which is produced locally. The Monday job cannot create a new round’s predictions.
2. **Gmail SMTP (fixed 2026-11-15).** The canonical secret `F1_GMAIL_APP_PASSWORD` held a stale app password while the legacy `gmail_app_password` key still worked. The canonical key was repaired in place and delivery is verified (`1/1 channels`). See §4.10.
3. **Oct 24–30 had no runs.** There is no failed run: the workspace compute was `INACTIVE` (see item 8 and §4.7).
4. **The dashboard may use committed reports.** `F1_DASHBOARD_DATA_BASE_URL` is not set in the repository; if it is also absent in Vercel, the build uses committed `reports/`.
5. **The Austin prediction is pre-race and local.** It was generated 2026-10-18 from local 2026 rounds 01–03. Do not claim it uses the full R1–17 Delta window.
6. **Race-day stub (fixed in `d6e0785`; `--all-completed` path fixed in `f12e354`).** Before the fix, the Sunday 06:00 UTC run treated a race whose calendar date was “today” as completed and ingested a pre-race stub. See §4.9 for the recovery procedure and for the 2026 Mexico incident record.
7. **Re-ingest duplicates (fixed in `d6e0785`).** Bronze is an append-only streaming table while the ingest overwrites the round’s Volume directory, so re-ingesting a round appended a second copy of every lap. `laps_silver` now dedupes on `(Season, RoundNumber, Driver, LapNumber)`, keeping the newest `_ingested_at`.
8. **Compute can go `INACTIVE`.** The workspace compute was `INACTIVE` for eight days (2026-10-23 → 2026-10-31) and only resumed after a user login. A scheduled run during that window cannot fire; see §4.7.
9. **FastF1 credentials are required for live sessions.** `F1_USERNAME` and `F1_PASSWORD` are read from the `f1_secrets` scope by `run_ingest()`. Without them FastF1 can return partial or empty timing data even when the race has finished.
10. **Dashboard object storage (restored 2026-11-17).** The Supabase project behind `SUPABASE_S3_*` was deleted and later restored from the dashboard. Publishing works again; see §4.10 for the symptom and the check that separates "deleted project" from "rotated key".

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

1. Read the notify task output. `SMTPServerDisconnected` raised inside `server.login()` happens **after** the TLS handshake, so it is an authentication failure, not an egress failure. Measured on 2026-11-15: the same host, port and network authenticated successfully with the other credential in the scope.
2. Egress to `smtp.gmail.com` works on both 465 (implicit TLS) and 587 (STARTTLS) from the job's serverless compute. Do not assume Free Edition blocks SMTP; test before blaming the network.
3. Test the credentials without printing them: read every Gmail key in `f1_secrets`, log only `len()` and `has_space`, and attempt a login with each. See §4.10 for the exact procedure.
4. Repair the canonical key rather than adding a code fallback to a legacy key. Then verify end to end by running only the notify task and looking for `Email sent successfully` and `1/1 channels`.
5. If no channel works, record that no notification was delivered; the website remains the primary surface.

### 4.7 Free Edition quota / workspace shutdown

1. Check the workspace for a quota notice.
2. Do not add parallel tasks or start a second SQL warehouse.
3. Wait for the quota reset; use the next scheduled window.
4. If the race-weekend update is urgent, use the manual fallback only after confirming compute is available.

Observed 2026-10-23 → 2026-10-31: the workspace compute was `INACTIVE` for eight days and no scheduled run fired. Compute resumed only after a user login. A scheduled run does not wake an `INACTIVE` workspace by itself, so a silent gap in run history should be treated as this failure mode first — open the workspace and confirm the compute state before assuming a job or cron defect.

Observed 2026-11-12: the Jobs API rejected every trigger with:

```text
Error: Triggering new runs for organization <org-id> is currently disabled temporarily.
```

Read and write APIs (`jobs get`, `workspace list/delete`) kept working; only new run triggering was blocked. This is an organization-level restriction, not a job, credential or bundle problem. Do not rebuild the bundle or rotate secrets.

Databricks confirms this is the **Free Edition compute-time quota per organization**. There is **no quota visibility** in Free Edition: no dashboard, CLI or API reports the remaining budget, and a rejected trigger consumes no compute. The practical rules are:

1. Retry at most once per hour. Polling faster adds nothing and makes the incident harder to read.
2. Consolidate work into one window: ingest every missing round, then refresh once. Do not spread backfills across days.
3. Budget the normal load: the scheduled job is ~7 minutes per run, four days a week. Manual retries are what exhaust the quota — thirteen manual runs between 2026-11-03 and 2026-11-05 triggered the block.
4. Wait for the next-day reset. If the block lasts more than 48 hours, open a case in **Databricks Free Edition Help** with the first-failure timestamp; creating a second Free Edition workspace is a last resort because it fragments the catalog.

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

**Do not** use `--all-completed` on race day either. `completed_round_numbers` now uses the same half-open calendar-day rule as `find_last_completed_race`: a round counts only once its UTC race day is over (`EventDate.date() < now.date()`), and rounds with a TBC (`NaT`) date are excluded. This was fixed after the 2026 Mexico incident — before it, the comparison was `<= now`, so a 20:00 UTC race looked completed at 06:00. The scheduled job never passes that flag; when backfilling, `--round` remains the most explicit option and is still preferred for a single known round.

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

**Resolution — 2026-11-12:**

- The job was held `PAUSED` from 2026-11-02 to 2026-11-12 so no scheduled run could train on the stub. No run fired on 2026-11-06/08/09, so São Paulo (R20) was not ingested either.
- R19 was re-ingested as run `310152296089` → `Landed 1084 laps for 2026 R19`. R20 was ingested in the same window as run `234559857240873` → `Landed 1435 laps for 2026 R20`.
- Volume check: R19 = 1,084 rows, 22 drivers, laps 1–56 (red-flag shortened race); R20 = 1,435 rows, 21 drivers, laps 1–71. Zero numeric/placeholder driver IDs in both.
- Full refresh `f4df2afb-b437-49c1-891f-093e870a45cd` completed in ~1m30s. The Mexico stub is gone from all three layers.
- Bronze and Silver now agree per round: R1 1,000 · R2 904 · R3 1,086 · R4 203 · R18 1,163 · R19 1,084 · R20 1,435. Gold 2026: Australia 20/1,000 · China 18/904 · Japan 22/1,086 · USA 22/1,163 · Mexico 22/1,084 · São Paulo 21/1,435.
- `laps_silver` has **0** duplicate `(Season, RoundNumber, Driver, LapNumber)` keys for 2026, so the `d6e0785` dedupe guard works on real re-ingested data.
- Job restored to `UNPAUSED` with all five tasks intact; next window Friday 2026-11-13 06:00 UTC, then Las Vegas.
- Not done, by design: no training, no model promotion, no dashboard republish. `@challenger` v4 is still stub-tainted and must not be promoted; the published manifest stays at rounds 1–18.
- Two platform-level blockers were hit during recovery and are documented in §4.7: FastF1 published no R19 timing data until ~2026-11-12, and Databricks temporarily rejected all run triggers for the organization (Free Edition compute quota).
- Side note: the 1,164-lap R18 reading seen on 2026-11-03 was transient. A forced re-ingest on 2026-11-15 landed 1,163 laps again, so the Volume was always correct; the extra lap came from a partially refreshed FastF1 cache, not an upstream revision.

### 4.10 Notification and publishing outages

Both tasks fail non-fatally, so a green run does **not** mean the email was delivered or the bundle was published. Always read the task log.

**Gmail SMTP — `SMTPServerDisconnected` during `login` (fixed 2026-11-15).**

Symptom in `dispatch_notifications`:

```text
smtplib.SMTPServerDisconnected: Connection unexpectedly closed
Notification dispatch complete: 0/1 channels succeeded.
```

The failure happens inside `server.login()`, after the TLS handshake, so it is an authentication problem — not DNS, not egress, not the message body. The scope had two keys: `F1_GMAIL_APP_PASSWORD` (canonical, read by the code) and `gmail_app_password` (legacy). The canonical value was stale; the legacy value authenticated on both 465 and 587.

Diagnosis that never prints a secret: read both keys inside a Databricks notebook, log only `len()` and `has_space`, and attempt a login with each. The repair copies the working value into the canonical key through the Secrets REST API (`dbutils.secrets.put` is not available in this runtime) and re-verifies the login.

Do not "fix" this by adding a fallback to the legacy key in code — that cements a duplicate credential. Repair the canonical key and delete the legacy one once the GitHub Actions secrets are confirmed to be independent.

**Dashboard publishing — `Could not connect to the endpoint URL` (resolved 2026-11-17).**

Symptom in `export_dashboard_data`:

```text
Dashboard publish skipped for season 2026 (Could not connect to the endpoint URL:
"[REDACTED]/[REDACTED]/dashboard/2026/Australian_Grand_Prix/results/predictions.csv")
```

The Supabase project in `SUPABASE_S3_ENDPOINT_URL` had stopped resolving:

```bash
host wjwqjmecefgyypkqnabe.supabase.co   # NXDOMAIN on 2026-11-14
```

That is a deleted project, not a credential rotation: DNS never reached the storage API, so the keys were never exercised. The bundle stayed frozen at the last successful upload (2026-11-01, rounds 1–18) and `/race/19` returned 404.

**Recovery.** The project was restored from the Supabase dashboard under the same ref, so the endpoint, bucket and access keys all stayed valid — no secret rotation was needed. Verify in this order:

1. `host <ref>.supabase.co` resolves.
2. The public manifest returns `200` and lists the expected rounds.
3. `list_objects_v2` with the stored keys succeeds — this proves the keys survived the restore.
4. `put_object` + public `GET` + `delete_object` on a throwaway key under `dashboard/2026/.publish-check.json`.

All four passed on 2026-11-17. Do not "repair" a publishing outage by committing the bundle to git — that reintroduces the coupling the cloud-native plan removes. If a future project is deleted rather than paused, point `SUPABASE_S3_*` at a live S3-compatible bucket (R2 needs `SUPABASE_S3_REGION=auto`) and update `F1_DASHBOARD_DATA_BASE_URL` in Vercel.

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
