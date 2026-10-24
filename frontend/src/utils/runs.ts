export type RunStatus = 'ok' | 'error' | 'timeout' | 'stopped' | 'limit';

export interface RunRecord {
  stdout: string;
  stderr: string;
  exitCode: number;
  durationMs: number;
  stdin: string;
  code: string;
  status: RunStatus;
  at: number;
}

/** how many runs of one file are kept for comparison (previous + last) */
export const RUN_HISTORY = 2;

/** Append a run to the file's history (immutably), keeping only the last RUN_HISTORY. */
export const pushRun = (
  history: Record<string, RunRecord[]>, fileId: string, r: RunRecord,
): Record<string, RunRecord[]> => ({
  ...history,
  [fileId]: [...(history[fileId] ?? []), r].slice(-RUN_HISTORY),
});

/** Markers come from backend/core/interactive.py. */
export const runStatus = (exitCode: number, stderr: string, stoppedByUser: boolean): RunStatus => {
  if (stoppedByUser) return 'stopped';
  if (stderr.includes('output limit reached')) return 'limit';
  if (stderr.includes('Timeout: сессия дольше')) return 'timeout';
  return exitCode !== 0 ? 'error' : 'ok';
};

/** same regex as backend/core/comparator.py */
const TIMESTAMP = /\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?/g;
const mask = (s: string) => s.replace(TIMESTAMP, '<TS>');

export const compareRuns = (prev: RunRecord, last: RunRecord): { same: boolean; stdinDiffers: boolean } => ({
  same: mask(prev.stdout) === mask(last.stdout) && prev.status === last.status,
  stdinDiffers: prev.stdin !== last.stdin,
});
