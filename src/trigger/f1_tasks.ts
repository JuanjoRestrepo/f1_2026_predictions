import { task, schedules } from "@trigger.dev/sdk/v3";
import { python } from "@trigger.dev/python";

/**
 * F1 Intelligence Sync - Manual/On-demand Trigger
 * Allows triggering a specific round and year sync from the dashboard.
 */
export const f1ManualSync = task({
  id: "f1-manual-sync",
  maxDuration: 1200, // 20 minutes for heavy data downloads
  run: async (payload: { year?: number; round?: number }) => {
    const year = payload.year ?? 2026;
    const roundStr = payload.round ? `Round ${payload.round}` : "Auto-detecting Round";
    console.log(`Starting F1 Sync for ${year} (${roundStr})`);

    const args = ["--year", year.toString(), "--auto"];
    if (payload.round) {
      args.push("--round", payload.round.toString());
    }

    const result = await python.runScript("scripts/master_pipeline.py", args);

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
  maxDuration: 1200,
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
  maxDuration: 1200,
  cron: "0 10 * * 1", // Mondays at 10:00 AM
  run: async (payload) => {
    console.log("Monday Audit Triggered. Processing race results...");
    
    const result = await python.runScript("scripts/master_pipeline.py", [
      "--auto",
    ]);

    return { success: result.exitCode === 0 };
  },
});
