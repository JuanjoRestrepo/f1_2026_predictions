import { task } from '@trigger.dev/sdk/v3';
import { python } from '@trigger.dev/python';
import * as path from 'path';

function pythonRunOptions() {
  const pythonPath = path.join(process.cwd(), 'src');
  const existingPythonPath = process.env.PYTHONPATH;

  return {
    env: {
      PYTHONPATH: existingPythonPath
        ? `${pythonPath}${path.delimiter}${existingPythonPath}`
        : pythonPath,
      // Ensure the Discord webhook is passed down to the Python script
      F1_DISCORD_WEBHOOK_URL: process.env.F1_DISCORD_WEBHOOK_URL || '',
    },
  };
}

/**
 * F1 Live Monitor - Manually Triggered
 *
 * Runs during an active race session to stream FastF1 live timing data via
 * SignalR sockets. Computes driver pace deltas against the ML model predictions
 * and emits Discord alerts in real-time if a pivot is detected.
 */
export const f1LiveMonitor = task({
  id: 'f1-live-monitor',
  maxDuration: 3600 * 3, // 3 hours (covers maximum race duration)
  run: async (payload: { year?: number; round: number; replay?: string }) => {
    console.log(`Starting Live Monitor for Round ${payload.round}`);

    const args = [
      '--year',
      (payload.year ?? 2026).toString(),
      '--round',
      payload.round.toString(),
    ];

    if (payload.replay) {
      args.push('--replay', payload.replay);
    }

    const scriptPath = path.join(process.cwd(), 'scripts', 'live_monitor.py');
    const result = await python.runScript(scriptPath, args, pythonRunOptions());

    if (result.exitCode !== 0) {
      throw new Error(`Live monitor failed: ${result.stderr}`);
    }

    return {
      success: true,
      stdout: result.stdout,
    };
  },
});
