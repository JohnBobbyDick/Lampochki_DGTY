export interface Speedup {
  factor: number | null;
  label: string;
  worse: boolean;
  /** what the number is based on (tooltip) */
  hint: string;
}

const SUP: Record<string, number> = { '²': 2, '³': 3, '⁴': 4, '⁵': 5 };

const exp = (sup?: string, caret?: string): number =>
  caret ? Number(caret) : sup ? SUP[sup] : 1;

const SHAPE = /^(?:(n)(?:([²³⁴⁵])|\^(\d+))?)?\s*(?:(log)(?:([²³⁴⁵])|\^(\d+))?\s*n)?$/;

const isExp = (bigo: string): boolean => /^O\(\s*2\^n\s*\)$/.test(bigo.trim());

/** f(n) for a Big O label of bigo_analyzer; null when unknown. */
export const growth = (bigo: string, n = 1000): number | null => {
  const m = /^O\((.*)\)$/.exec(bigo.trim());
  if (!m) return null;
  const body = m[1].trim();
  if (body === '1') return 1;
  if (body === '2^n') return 2 ** n;
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
 * Speedup from `before` to `after` at the data size `n` measured by a run; the ratio of two growth classes depends
 * on n only (O(n²) → O(n) is «n times»), so without n there is no number.
 */
export const speedup = (before: string, after: string, n?: number | null): Speedup => {
  const none: Speedup = { factor: null, label: '', worse: false, hint: '' };
  if (!n || growth(before, n) === null || growth(after, n) === null || before === after) return none;
  const hint = `при n ≈ ${n} — размер данных при запуске программы`;
  const at = ratio(before, after, n);
  if (!at || at.r < 1.5) return { factor: 1, label: '≈ без разницы', worse: false, hint };
  return { factor: at.r, label: `~${formatFactor(at.r)}× ${at.worse ? 'медленнее' : 'быстрее'}`, worse: at.worse, hint };
};
