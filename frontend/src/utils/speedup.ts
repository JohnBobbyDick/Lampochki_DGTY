export interface Speedup {
  factor: number | null;
  label: string;
  worse: boolean;
  /** what the number is based on (tooltip) */
  hint: string;
}

/** Data sizes of the range shown before the program has been run. */
export const N_LOW = 10;
export const N_HIGH = 1000;

const SUP: Record<string, number> = { '²': 2, '³': 3, '⁴': 4, '⁵': 5 };

const exp = (sup?: string, caret?: string): number =>
  caret ? Number(caret) : sup ? SUP[sup] : 1;

const SHAPE = /^(?:(n)(?:([²³⁴⁵])|\^(\d+))?)?\s*(?:(log)(?:([²³⁴⁵])|\^(\d+))?\s*n)?$/;

const isExp = (bigo: string): boolean => /^O\(\s*2\^n\s*\)$/.test(bigo.trim());

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

/**
 * Data size n at which `bigo` does `work` steps, e.g. O(n²) with 121 executions of the busiest line → 11.
 * null for O(1), O(2^n) and unknown labels: the run tells nothing about n there.
 */
export const estimateN = (bigo: string, work: number): number | null => {
  const g = (n: number) => growth(bigo, n);
  const small = g(2);
  if (!(work > 0) || small === null || isExp(bigo) || g(1e6) === small) return null;
  if (work <= 1) return 1;
  let lo = 1;
  let hi = 1e9;
  for (let i = 0; i < 100; i++) {
    const mid = (lo + hi) / 2;
    if (g(mid)! < work) lo = mid; else hi = mid;
  }
  return Math.max(1, Math.round(hi));
};

/** «3,3», «11», «120», «1200», «1 000 000»: two significant digits, Russian number format. */
export const formatFactor = (x: number): string => {
  if (x < 10) return String(Math.round(x * 10) / 10).replace('.', ',');
  const s = String(Math.round(Number(x.toPrecision(2))));
  return s.length > 4 ? s.replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0') : s;
};

const ratio = (before: string, after: string, n: number): { r: number; worse: boolean } | null => {
  const fb = growth(before, n);
  const fa = growth(after, n);
  if (fb === null || fa === null || fb === fa) return null;
  const worse = fa > fb;
  const r = worse ? fa / fb : fb / fa;
  return r > 1 + 1e-9 ? { r, worse } : null;
};

/**
 * Expected speedup from `before` to `after`. With `n` (the data size of the last run) it is one number for
 * that size; without it — the range for n from N_LOW to N_HIGH, since the ratio of two growth classes depends
 * on n only (O(n²) → O(n) is «n times»).
 */
export const speedup = (before: string, after: string, n?: number | null): Speedup => {
  const none: Speedup = { factor: null, label: '', worse: false, hint: '' };
  const word = (worse: boolean) => (worse ? 'медленнее' : 'быстрее');

  if (n) {
    const hint = `при n ≈ ${n} — размер данных в последнем запуске`;
    const same: Speedup = { factor: 1, label: '≈ без разницы', worse: false, hint };
    if (growth(before, n) === null || growth(after, n) === null || before === after) return none;
    const at = ratio(before, after, n);
    if (!at || at.r < 1.5) return same;
    return { factor: at.r, label: `~${formatFactor(at.r)}× ${word(at.worse)}`, worse: at.worse, hint };
  }

  const hint = `при n от ${N_LOW} до ${N_HIGH}; запустите программу, чтобы оценить на своих данных`;
  if (isExp(before) !== isExp(after)) {
    // 2^n against a polynomial: the gap explodes with n, only the lower bound is meaningful
    const worse = isExp(after);
    const poly = growth(worse ? before : after, N_LOW);
    if (poly === null) return none;
    const at = 2 ** N_LOW / poly;
    return { factor: at, label: `≥${formatFactor(at)}× ${word(worse)}`, worse, hint };
  }
  const low = ratio(before, after, N_LOW);
  const high = ratio(before, after, N_HIGH);
  if (!low || !high) return none;
  const [a, b] = [formatFactor(Math.min(low.r, high.r)), formatFactor(Math.max(low.r, high.r))];
  const label = a === b ? `~${a}× ${word(high.worse)}` : `~${a}–${b}× ${word(high.worse)}`;
  return { factor: high.r, label, worse: high.worse, hint };
};
