import { defineConfig } from '@trigger.dev/sdk/v3';
import { pythonExtension } from '@trigger.dev/python/extension';

const devPythonBinaryPath =
  process.platform === 'win32'
    ? '.venv/Scripts/python.exe'
    : '.venv/bin/python3';

const pythonBuildFiles = [
  'scripts/**/*.py',
  'src/f1_predictions/**/*.py',
  'src/f1_predictions/templates/**/*',
  'data/external/**/*',
  'data/outputs/models/**/*',
];

export default defineConfig({
  project: 'proj_qikobyuvvlwjvmdaaqwk',
  runtime: 'node',
  logLevel: 'log',
  // The max compute seconds a task is allowed to run. If the task run exceeds this duration, it will be stopped.
  // You can override this on an individual task.
  // See https://trigger.dev/docs/runs/max-duration
  maxDuration: 3600,
  retries: {
    enabledInDev: true,
    default: {
      maxAttempts: 3,
      minTimeoutInMs: 1000,
      maxTimeoutInMs: 10000,
      factor: 2,
      randomize: true,
    },
  },
  dirs: ['./src/trigger'],
  build: {
    extensions: [
      pythonExtension({
        requirementsFile: 'trigger_requirements.txt',
        devPythonBinaryPath,
        scripts: pythonBuildFiles,
      }),
    ],
  },
});
