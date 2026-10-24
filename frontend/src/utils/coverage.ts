export type ProbeKind = 'line' | 'method' | 'branch' | 'cond' | 'rel';
export interface Probe { id: number; kind: ProbeKind; line: number; method: string; label: string; outcomes: string[]; slot: number }
export interface Coverage { code: string; probes: Probe[]; hits: number[]; runs: number }
export interface Metric { covered: number; total: number }
export interface MethodCoverage { method: string; called: boolean; lines: Metric; branches: Metric; conditions: Metric; relational: Metric }
export interface Missing { line: number; kind: ProbeKind; label: string; outcome: string }
export interface CoverageSummary { lines: Metric; methods: Metric; branches: Metric; conditions: Metric; relational: Metric; perMethod: MethodCoverage[]; missing: Missing[] }
export interface LineState { state: 'hit' | 'miss' | 'partial'; count: number; missing: string[] }

export const mergeCoverage = (prev: Coverage | undefined, code: string, probes: Probe[], hits: number[]): Coverage => {
  if (prev && prev.code === code && prev.hits.length === hits.length) {
    return { code, probes, hits: prev.hits.map((h, i) => h + hits[i]), runs: prev.runs + 1 };
  }
  return { code, probes, hits, runs: 1 };
};

export const percent = (m: Metric): string =>
  m.total === 0 ? '—' : `${Math.round((m.covered / m.total) * 100)}%`;

const count = (c: Coverage, p: Probe, i: number): number => c.hits[p.slot + i] ?? 0;
const isOutcomeKind = (k: ProbeKind): boolean => k === 'branch' || k === 'cond' || k === 'rel';

const linesMetric = (c: Coverage, probes: Probe[]): Metric => {
  const byLine = new Map<number, boolean>();
  for (const p of probes) {
    if (p.kind !== 'line') continue;
    byLine.set(p.line, (byLine.get(p.line) ?? false) || count(c, p, 0) > 0);
  }
  return { covered: [...byLine.values()].filter(Boolean).length, total: byLine.size };
};

const outcomesMetric = (c: Coverage, probes: Probe[], kind: ProbeKind): Metric => {
  let covered = 0; let total = 0;
  for (const p of probes) {
    if (p.kind !== kind) continue;
    p.outcomes.forEach((_, i) => { total++; if (count(c, p, i) > 0) covered++; });
  }
  return { covered, total };
};

export const summarize = (c: Coverage): CoverageSummary => {
  const methodProbes = c.probes.filter((p) => p.kind === 'method');
  const perMethod: MethodCoverage[] = methodProbes.map((mp) => {
    const own = c.probes.filter((p) => p.method === mp.method);
    return {
      method: mp.method,
      called: count(c, mp, 0) > 0,
      lines: linesMetric(c, own),
      branches: outcomesMetric(c, own, 'branch'),
      conditions: outcomesMetric(c, own, 'cond'),
      relational: outcomesMetric(c, own, 'rel'),
    };
  });
  const missing: Missing[] = [];
  for (const p of [...c.probes].sort((a, b) => a.line - b.line || a.id - b.id)) {
    if (!isOutcomeKind(p.kind)) continue;
    p.outcomes.forEach((o, i) => {
      if (count(c, p, i) === 0) missing.push({ line: p.line, kind: p.kind, label: p.label, outcome: o });
    });
  }
  return {
    lines: linesMetric(c, c.probes),
    methods: { covered: perMethod.filter((m) => m.called).length, total: perMethod.length },
    branches: outcomesMetric(c, c.probes, 'branch'),
    conditions: outcomesMetric(c, c.probes, 'cond'),
    relational: outcomesMetric(c, c.probes, 'rel'),
    perMethod,
    missing,
  };
};

export const lineStates = (c: Coverage): Map<number, LineState> => {
  const maxCount = new Map<number, number>();
  for (const p of c.probes) {
    if (p.kind === 'line') maxCount.set(p.line, Math.max(maxCount.get(p.line) ?? 0, count(c, p, 0)));
  }
  const missingByLine = new Map<number, string[]>();
  for (const m of summarize(c).missing) {
    const list = missingByLine.get(m.line) ?? [];
    list.push(`${m.label} → ${m.outcome}`);
    missingByLine.set(m.line, list);
  }
  const result = new Map<number, LineState>();
  for (const [line, n] of maxCount) {
    const missing = n > 0 ? missingByLine.get(line) ?? [] : [];
    result.set(line, { state: n === 0 ? 'miss' : missing.length ? 'partial' : 'hit', count: n, missing });
  }
  return result;
};
