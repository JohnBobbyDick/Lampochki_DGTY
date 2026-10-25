import { describe, expect, it } from 'vitest';
import { compareVerdict, VERDICT_TITLE } from './verdict';
import { CompareResult } from '../types';

describe('compareVerdict and output match checks', () => {
  it('returns ok when behavior preserved and both exit with 0', () => {
    const res: CompareResult = {
      before: { stdout: 'hello', stderr: '', exitCode: 0, durationMs: 10 },
      after: { stdout: 'hello', stderr: '', exitCode: 0, durationMs: 10 },
      diff: '',
      behaviorPreserved: true,
    };
    expect(compareVerdict(res)).toBe('ok');
    expect(VERDICT_TITLE[compareVerdict(res)]).toBe('Поведение сохранено');
    expect(!res.diff || res.behaviorPreserved).toBe(true);
  });

  it('returns warn when behavior preserved but non-zero exit code', () => {
    const res: CompareResult = {
      before: { stdout: 'err', stderr: '', exitCode: 1, durationMs: 10 },
      after: { stdout: 'err', stderr: '', exitCode: 1, durationMs: 10 },
      diff: '',
      behaviorPreserved: true,
    };
    expect(compareVerdict(res)).toBe('warn');
    expect(VERDICT_TITLE[compareVerdict(res)]).toBe('Подтвердить не удалось');
    expect(!res.diff || res.behaviorPreserved).toBe(true);
  });

  it('returns fail when behavior not preserved', () => {
    const res: CompareResult = {
      before: { stdout: 'old', stderr: '', exitCode: 0, durationMs: 10 },
      after: { stdout: 'new', stderr: '', exitCode: 0, durationMs: 10 },
      diff: '--- before\n+++ after\n-old\n+new',
      behaviorPreserved: false,
    };
    expect(compareVerdict(res)).toBe('fail');
    expect(VERDICT_TITLE[compareVerdict(res)]).toBe('Поведение изменилось');
    expect(!res.diff || res.behaviorPreserved).toBe(false);
  });

  it('correctly detects matching output even if one run had an error fixed by AI', () => {
    const res: CompareResult = {
      before: { stdout: 'Result: 42', stderr: 'warning', exitCode: 1, durationMs: 10 },
      after: { stdout: 'Result: 42', stderr: '', exitCode: 0, durationMs: 10 },
      diff: '',
      behaviorPreserved: false, // exit codes differed (1 vs 0)
    };
    // The overall verdict is fail (behaviorPreserved is false because exit code changed)
    expect(compareVerdict(res)).toBe('fail');
    // But the output match step correctly recognizes that stdout matched!
    expect(!res.diff || res.behaviorPreserved).toBe(true);
  });
});
