import { describe, expect, it } from 'vitest';
import { compareRuns, pushRun, RunRecord, runStatus } from './runs';

const rec = (stdout: string, stdin = ''): RunRecord => ({
  stdout, stderr: '', exitCode: 0, durationMs: 1, stdin, code: '', status: 'ok', at: 0,
});

describe('runs', () => {
  it('keeps last two runs per file id', () => {
    let h = {}; for (const out of ['1', '2', '3']) h = pushRun(h, 'src/Demo.java', rec(out));
    expect((h as Record<string, RunRecord[]>)['src/Demo.java'].map((r) => r.stdout)).toEqual(['2', '3']);
  });
  it('does not mix files with the same name in different folders', () => {
    let h = pushRun({}, 'src/Demo.java', rec('12')); h = pushRun(h, 'examples/Demo.java', rec('7'));
    expect(h['src/Demo.java'].map((r) => r.stdout)).toEqual(['12']);
    expect(h['examples/Demo.java'].map((r) => r.stdout)).toEqual(['7']);
  });
  it('does not mutate the previous history', () => {
    const h = pushRun({}, 'a', rec('1'));
    pushRun(h, 'a', rec('2'));
    expect(h['a']).toHaveLength(1);
  });
  it('status: stop / limit / timeout / error / ok', () => {
    expect(runStatus(137, '', true)).toBe('stopped');
    expect(runStatus(137, '…[output limit reached, process killed]', false)).toBe('limit');
    expect(runStatus(137, '\nTimeout: сессия дольше 30 с\n', false)).toBe('timeout');
    expect(runStatus(1, 'Exception in thread "main"', false)).toBe('error');
    expect(runStatus(0, '', false)).toBe('ok');
  });
  it('compare masks timestamps and flags stdin change', () => {
    const a = rec('at 2026-10-24 10:00:00 sum=12', 'x'), b = rec('at 2026-10-24 11:30:05 sum=12', 'y');
    expect(compareRuns(a, b)).toEqual({ same: true, stdinDiffers: true });
  });
  it('compare: different output or status is not the same', () => {
    expect(compareRuns(rec('12'), rec('25')).same).toBe(false);
    expect(compareRuns(rec('1'), { ...rec('1'), status: 'error' }).same).toBe(false);
  });
});
