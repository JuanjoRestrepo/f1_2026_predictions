#!/usr/bin/env node
/**
 * Pull the published dashboard bundle from object storage into reports/<season>
 * before `next build` runs.
 *
 * Databricks owns orchestration and publishes the season's report artifacts to
 * S3-compatible storage (see src/f1_predictions/utils/dashboard_publish.py).
 * This script mirrors them back into the local reports/ layout that
 * dashboard/src/utils/fileReader.ts already reads — so the dashboard code is
 * unchanged and existing local/committed data keeps working.
 *
 * Opt-in and safe by default:
 *   - No-op unless F1_DASHBOARD_DATA_BASE_URL is set.
 *   - Never fails the build unless F1_DASHBOARD_DATA_STRICT=1.
 *
 * Environment:
 *   F1_DASHBOARD_DATA_BASE_URL  Base URL of the season bundle, e.g.
 *                               https://<project>.supabase.co/storage/v1/object/public/<bucket>/dashboard/2026
 *   F1_DASHBOARD_DATA_TOKEN     Optional bearer token for private buckets.
 *   F1_DASHBOARD_SEASON         Season to sync (default: 2026).
 *   F1_DASHBOARD_DATA_STRICT    "1" to fail the build on any sync error.
 */
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";

const BASE_URL = (process.env.F1_DASHBOARD_DATA_BASE_URL ?? "").replace(/\/+$/, "");
const TOKEN = process.env.F1_DASHBOARD_DATA_TOKEN;
const SEASON = process.env.F1_DASHBOARD_SEASON ?? "2026";
const STRICT = process.env.F1_DASHBOARD_DATA_STRICT === "1";

/** Resolve the reports/ root the same way fileReader.ts does. */
function reportsRoot() {
  const cwd = process.cwd();
  const fromDashboard = join(cwd, "..", "reports");
  const fromRoot = join(cwd, "reports");
  if (existsSync(fromDashboard)) return resolve(fromDashboard);
  if (existsSync(fromRoot)) return resolve(fromRoot);
  return resolve(fromDashboard);
}

function authHeaders() {
  return TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {};
}

async function fetchJson(url) {
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return res.json();
}

async function fetchBytes(url) {
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return Buffer.from(await res.arrayBuffer());
}

async function main() {
  if (!BASE_URL) {
    console.log(
      "[dashboard-data] F1_DASHBOARD_DATA_BASE_URL not set — using committed reports/."
    );
    return;
  }

  const manifest = await fetchJson(`${BASE_URL}/manifest.json`);
  const files = Array.isArray(manifest.files) ? manifest.files : [];
  const seasonDir = join(reportsRoot(), SEASON);
  const seasonDirResolved = resolve(seasonDir);

  let written = 0;
  for (const rel of files) {
    if (typeof rel !== "string" || rel.length === 0 || isAbsolute(rel)) {
      console.warn(`[dashboard-data] Skipping unsafe manifest entry: ${rel}`);
      continue;
    }
    const target = resolve(seasonDir, rel);
    // Guard against path traversal outside the season directory.
    if (target !== seasonDirResolved && !target.startsWith(seasonDirResolved + "/")) {
      console.warn(`[dashboard-data] Refusing to write outside season dir: ${rel}`);
      continue;
    }
    const bytes = await fetchBytes(`${BASE_URL}/${rel}`);
    await mkdir(dirname(target), { recursive: true });
    await writeFile(target, bytes);
    written += 1;
  }

  console.log(
    `[dashboard-data] Synced ${written}/${files.length} artifact(s) into ${seasonDir}`
  );
}

main().catch((err) => {
  const message = err instanceof Error ? err.message : String(err);
  if (STRICT) {
    console.error(`[dashboard-data] sync failed (strict): ${message}`);
    process.exit(1);
  }
  console.warn(
    `[dashboard-data] sync skipped (keeping committed reports/): ${message}`
  );
});
