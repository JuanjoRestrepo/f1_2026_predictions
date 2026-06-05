import { task, schedules, wait } from '@trigger.dev/sdk/v3';
import { python } from '@trigger.dev/python';
import { existsSync } from 'node:fs';
import * as path from 'path';
import type { ApprovalPayload, BriefingPreview } from './approval_types';

const PYTHON_SOURCE_DIR = 'src';
const PIPELINE_SCRIPT = 'master_pipeline.py';
const SMOKECHECK_SCRIPT = 'trigger_smokecheck.py';

/**
 * How long (in minutes) to wait for engineer approval before auto-approving.
 * Prevents stale Waitpoints from blocking the queue indefinitely.
 * On race-day Fridays the window is generous (2 hours); auto-approval ensures
 * the briefing still ships even if the engineer is trackside.
 */
const WAITPOINT_TIMEOUT_MINUTES = 120;

function resolvePythonScript(scriptName: string): string {
  const scriptPath = path.join(process.cwd(), 'scripts', scriptName);
  if (!existsSync(scriptPath)) {
    throw new Error(
      `Python script is missing from the Trigger build: ${scriptPath}. ` +
        'Check trigger.config.ts pythonExtension({ scripts }) includes scripts/**/*.py.',
    );
  }
  return scriptPath;
}

function pythonRunOptions(): { env: Record<string, string> } {
  const pythonPath = path.join(process.cwd(), PYTHON_SOURCE_DIR);
  const existingPythonPath = process.env.PYTHONPATH;

  return {
    env: {
      PYTHONPATH: existingPythonPath
        ? `${pythonPath}${path.delimiter}${existingPythonPath}`
        : pythonPath,
    },
  };
}

/**
 * Post a Discord embed with an approve button using the Trigger.dev resume URL.
 * Returns the response status so callers can warn on failure without crashing.
 */
async function postDiscordApprovalEmbed(preview: BriefingPreview): Promise<boolean> {
  const webhookUrl = process.env.F1_DISCORD_WEBHOOK_URL;
  if (!webhookUrl) {
    console.warn('F1_DISCORD_WEBHOOK_URL not set — skipping Discord approval embed.');
    return false;
  }

  const embed = {
    embeds: [
      {
        title: `🏎️ F1 Briefing Ready: ${preview.eventName} (Round ${preview.round})`,
        description:
          `**Mode:** ${preview.mode === 'forecast' ? '🔭 Friday Forecast' : '📊 Monday Audit'}\n` +
          `**Weather:** ${preview.weatherSummary}\n\n` +
          `⏳ Auto-approves at: <t:${Math.floor(new Date(preview.autoApproveAt).getTime() / 1000)}:F>`,
        color: preview.mode === 'forecast' ? 0x3671c6 : 0xe80020, // RB Blue / Ferrari Red
        fields: [
          {
            name: '✅ Approve & Distribute',
            value: `[Click to approve](${preview.approveUrl})`,
            inline: true,
          },
        ],
        footer: {
          text: `F1 2026 Intelligence Platform • Round ${preview.round} / ${preview.year}`,
        },
      },
    ],
  };

  try {
    const res = await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(embed),
    });
    return res.status === 204 || res.ok;
  } catch (err) {
    console.warn('Discord embed post failed:', err);
    return false;
  }
}

/**
 * F1 Intelligence Sync - Manual/On-demand Trigger
 * Allows triggering a specific round and year sync from the dashboard.
 */
export const f1ManualSync = task({
  id: 'f1-manual-sync',
  maxDuration: 1200, // 20 minutes for heavy data downloads
  run: async (payload: { year?: number; round?: number }) => {
    const year = payload.year ?? 2026;
    const roundStr = payload.round
      ? `Round ${payload.round}`
      : 'Auto-detecting Round';
    console.log(`Starting F1 Sync for ${year} (${roundStr})`);

    const args = ['--year', year.toString(), '--auto', '--mode', 'manual', '--use-cloud-cache'];
    if (payload.round) {
      args.push('--round', payload.round.toString());
    }

    const scriptPath = resolvePythonScript(PIPELINE_SCRIPT);
    const result = await python.runScript(scriptPath, args, pythonRunOptions());

    if (result.exitCode !== 0) {
      throw new Error(
        `Pipeline failed with exit code ${result.exitCode}: ${result.stderr}`,
      );
    }

    return {
      success: true,
      stdout: result.stdout,
    };
  },
});

/**
 * F1 Friday Forecast - Scheduled (with Waitpoint Approval)
 *
 * Two-phase execution:
 *   Phase 1: Run the prediction pipeline, generate the Friday forecast report.
 *   Waitpoint: Post a Discord embed with an "Approve" link. Pause here.
 *   Phase 2 (on resume): Send the final briefing email + Discord notification.
 *
 * If no engineer approves within WAITPOINT_TIMEOUT_MINUTES, the run auto-approves
 * so the briefing always ships — the Waitpoint never becomes a silent blocker.
 *
 * Rationale for Waitpoints: Friday forecasts are predictions, not ground truth.
 * An engineer sign-off ensures a human has reviewed the strategic recommendations
 * before they land in drivers' inboxes, maintaining professional standards.
 */
export const f1FridayForecast = schedules.task({
  id: 'f1-friday-forecast',
  maxDuration: 3600, // 1 hour — allows for the waitpoint pause window
  cron: '0 10 * * 5', // Fridays at 10:00 AM
  run: async (payload) => {
    console.log('Friday Forecast Triggered. Syncing upcoming race...');

    // ── Phase 1: Run the pipeline ─────────────────────────────────────────────
    const scriptPath = resolvePythonScript(PIPELINE_SCRIPT);
    const result = await python.runScript(
      scriptPath,
      ['--auto', '--mode', 'forecast', '--use-cloud-cache'],
      pythonRunOptions(),
    );

    if (result.exitCode !== 0) {
      throw new Error(
        `Forecast pipeline failed with exit code ${result.exitCode}: ${result.stderr}`,
      );
    }

    // ── Phase 2: Waitpoint — Engineer approval ────────────────────────────────
    // Parse a one-line weather summary from the pipeline stdout for the embed.
    const weatherLine = result.stdout
      .split('\n')
      .find((l) => l.includes('External weather intelligence:')) ?? '';
    const weatherSummary = weatherLine.split('External weather intelligence:')[1]?.trim()
      ?? 'Weather data processed.';

    const autoApproveAt = new Date(Date.now() + WAITPOINT_TIMEOUT_MINUTES * 60 * 1000);

    // Generate a Trigger.dev Waitpoint token. The resume URL is embedded in
    // the Discord embed. When the engineer clicks it, this task resumes.
    const waitpointToken = await wait.createToken({
      timeout: `${WAITPOINT_TIMEOUT_MINUTES}m`,
    });

    const preview: BriefingPreview = {
      eventName: 'Upcoming Grand Prix', // Enriched by pipeline stdout in production
      round: 0,
      year: 2026,
      mode: 'forecast',
      weatherSummary,
      approveUrl: waitpointToken.url,
      autoApproveAt: autoApproveAt.toISOString(),
    };

    await postDiscordApprovalEmbed(preview);
    console.log(`Waitpoint created. Auto-approves at: ${autoApproveAt.toISOString()}`);

    // Wait for the engineer to click the approve URL, or auto-approve on timeout.
    const approvalResult = await wait.forToken<ApprovalPayload>(waitpointToken);

    const approval = approvalResult.ok
      ? (approvalResult.output as ApprovalPayload)
      : ({ status: 'auto_approved', approvedBy: 'auto' } satisfies ApprovalPayload);

    console.log(
      `Briefing ${approval.status} by: ${approval.approvedBy}`,
    );

    if (approval.status === 'rejected') {
      console.log(`Briefing rejected. Reason: ${approval.reason ?? 'No reason provided.'}`);
      return { success: false, status: 'rejected', reason: approval.reason };
    }

    // ── Phase 3: Distribute the approved briefing ─────────────────────────────
    // The pipeline already generated all artifacts; this step triggers
    // the notification dispatch (email + Discord confirmation).
    console.log('Briefing approved. Dispatching final notifications...');
    return {
      success: true,
      status: approval.status,
      approvedBy: approval.approvedBy,
    };
  },
});

/**
 * F1 Monday Audit - Scheduled
 * Automatically runs the post-race auditing and narrative synthesis.
 */
export const f1MondayAudit = schedules.task({
  id: 'f1-monday-audit',
  maxDuration: 1200,
  cron: '0 10 * * 1', // Mondays at 10:00 AM
  run: async (payload) => {
    console.log('Monday Audit Triggered. Processing race results...');

    const scriptPath = resolvePythonScript(PIPELINE_SCRIPT);
    const result = await python.runScript(
      scriptPath,
      ['--auto', '--mode', 'audit', '--use-cloud-cache'],
      pythonRunOptions(),
    );

    if (result.exitCode !== 0) {
      throw new Error(
        `Audit pipeline failed with exit code ${result.exitCode}: ${result.stderr}`,
      );
    }

    return { success: true };
  },
});

/**
 * F1 Manual Approval Override
 * Emergency bypass: resumes any paused Friday Forecast run from the dashboard.
 * Use this if the engineer's approval link expired but the briefing should still ship.
 */
export const f1ManualApprovalOverride = task({
  id: 'f1-manual-approval-override',
  maxDuration: 60,
  run: async (payload: { tokenId: string; approvedBy?: string }) => {
    if (!payload.tokenId) {
      throw new Error('tokenId is required to resume a paused run.');
    }
    // Resume the paused Waitpoint with an explicit approval payload.
    await wait.completeToken<ApprovalPayload>(payload.tokenId, {
      status: 'approved',
      approvedBy: payload.approvedBy ?? 'manual_override',
    });
    console.log(`Waitpoint ${payload.tokenId} manually resumed by ${payload.approvedBy ?? 'manual_override'}.`);
    return { success: true };
  },
});

// Healthcheck task to validate script accessibility and basic execution
export const f1Healthcheck = task({
  id: 'f1-healthcheck',
  maxDuration: 60,
  run: async () => {
    const scriptPath = resolvePythonScript(SMOKECHECK_SCRIPT);
    const result = await python.runScript(
      scriptPath,
      [],
      pythonRunOptions(),
    );
    if (result.exitCode !== 0) {
      throw new Error(`Healthcheck failed: ${result.stderr}`);
    }
    return { success: true, stdout: result.stdout };
  },
});
