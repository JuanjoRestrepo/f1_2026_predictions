import { task, schedules } from "@trigger.dev/sdk/v3";
import { python } from "@trigger.dev/python";

/**
 * F1 Intelligence Sync - Manual/On-demand Trigger
 * Allows triggering a specific round and year sync from the dashboard.
 */
export const f1ManualSync = task({
  id: "f1-manual-sync",
  run: async (payload: { year?: number; round: number }) => {
    const year = payload.year ?? 2026;
    console.log(`Starting F1 Sync for ${year} Round ${payload.round}`);

    const result = await python.runScript("scripts/master_pipeline.py", [
      "--year",
      year.toString(),
      "--round",
      payload.round.toString(),
      "--auto",
    ]);

    if (result.exitCode !== 0) {
      throw new Error(`Pipeline failed with exit code ${result.exitCode}: ${result.stderr}`);
    }

    return {
      success: true,
      stdout: result.stdout,
    };
  },
});

/**
 * F1 Friday Forecast - Scheduled
 * Automatically runs the predictive pipeline for the upcoming race.
 */
export const f1FridayForecast = schedules.task({
  id: "f1-friday-forecast",
  cron: "0 10 * * 5", // Fridays at 10:00 AM
  run: async (payload) => {
    // Note: We need a way to determine the "next" round automatically.
    // For now, we can add logic to master_pipeline.py to auto-detect if no round is passed,
    // or use a helper task here.
    console.log("Friday Forecast Triggered. Syncing upcoming race...");
    
    // In a real scenario, we'd fetch the current round number here.
    // For this demo, let's assume master_pipeline handles 'next' if round=0
    const result = await python.runScript("scripts/master_pipeline.py", [
      "--auto",
    ]);

    return { success: result.exitCode === 0 };
  },
});

/**
 * F1 Monday Audit - Scheduled
 * Automatically runs the post-race auditing and narrative synthesis.
 */
export const f1MondayAudit = schedules.task({
  id: "f1-monday-audit",
  cron: "0 10 * * 1", // Mondays at 10:00 AM
  run: async (payload) => {
    console.log("Monday Audit Triggered. Processing race results...");
    
    const result = await python.runScript("scripts/master_pipeline.py", [
      "--auto",
    ]);

    return { success: result.exitCode === 0 };
  },
});
