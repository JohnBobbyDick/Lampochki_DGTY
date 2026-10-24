import { CompareResult } from '../types';

export type Verdict = 'ok' | 'warn' | 'fail';

/**
 * Verdict for a before/after comparison. Matching output only counts as proof when both
 * versions actually ran: two identical crashes (e.g. no JDK installed) prove nothing.
 */
export const compareVerdict = (c: CompareResult): Verdict => {
  if (!c.behaviorPreserved) return 'fail';
  const bothRan = [c.before, c.after].every((r) => r.exitCode === 0 && !r.compileErrors?.length);
  return bothRan ? 'ok' : 'warn';
};

export const VERDICT_TITLE: Record<Verdict, string> = {
  ok: 'Поведение сохранено',
  warn: 'Подтвердить не удалось',
  fail: 'Поведение изменилось',
};

/** Verdict for "previous run vs last run" of one file. */
export const RUN_VERDICT_TITLE = { same: 'Вывод не изменился', changed: 'Вывод изменился' } as const;
