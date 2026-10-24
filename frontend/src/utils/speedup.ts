export interface Speedup {
  factor: number | null;
  label: string;
  worse: boolean;
}

const STEPS = [2, 5, 10, 100, 1000, 10000, 100000, 1000000];
const SUP: Record<string, number> = { '²': 2, '³': 3, '⁴': 4, '⁵': 5 };

const exp = (sup?: string, caret?: string): number =>
  caret ? Number(caret) : sup ? SUP[sup] : 1;

const SHAPE = /^(?:(n)(?:([²³⁴⁵])|\^(\d+))?)?\s*(?:(log)(?:([²³⁴⁵])|\^(\d+))?\s*n)?$/;

/** f(n) for a Big O label of bigo_analyzer; Infinity for O(2^n); null when unknown. */
export const growth = (bigo: string, n = 1000): number | null => {
  const m = /^O\((.*)\)$/.exec(bigo.trim());
  if (!m) return null;
  const body = m[1].trim();
  if (body === '1') return 1;
  if (body === '2^n') return Infinity;
  const g = SHAPE.exec(body);
  if (!body || !g || (!g[1] && !g[4])) return null;
  const p = g[1] ? exp(g[2], g[3]) : 0;
  const l = g[4] ? exp(g[5], g[6]) : 0;
  return n ** p * Math.log2(n) ** l;
};

/** Expected speedup from `before` to `after` at size n, rounded to a "nice" factor. */
export const speedup = (before: string, after: string, n = 1000): Speedup => {
  const none: Speedup = { factor: null, label: '', worse: false };
  const fb = growth(before, n);
  const fa = growth(after, n);
  if (fb === null || fa === null || fb === fa) return none;
  const worse = fa > fb;
  const ratio = worse ? fa / fb : fb / fa; // Infinity-safe: Infinity/finite
  if (!(ratio > 1 + 1e-9)) return none;
  const word = worse ? 'медленнее' : 'быстрее';
  if (ratio > STEPS[STEPS.length - 1]) {
    return { factor: STEPS[STEPS.length - 1], label: `>1000000× ${word}`, worse };
  }
  const lr = Math.log(ratio);
  const nice = STEPS.reduce((best, s) =>
    Math.abs(Math.log(s) - lr) < Math.abs(Math.log(best) - lr) ? s : best);
  return { factor: nice, label: `~${nice}× ${word}`, worse };
};
