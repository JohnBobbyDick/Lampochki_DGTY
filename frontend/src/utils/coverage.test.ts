import { describe, expect, it } from 'vitest';
import { lineStates, mergeCoverage, percent, Probe, summarize } from './coverage';

const probes: Probe[] = [
  { id: 0, kind: 'method', line: 2, method: 'Demo.f', label: 'Demo.f', outcomes: ['выполнено'], slot: 0 },
  { id: 1, kind: 'line', line: 3, method: 'Demo.f', label: '', outcomes: ['выполнено'], slot: 1 },
  { id: 2, kind: 'line', line: 4, method: 'Demo.f', label: '', outcomes: ['выполнено'], slot: 2 },
  { id: 3, kind: 'line', line: 5, method: 'Demo.f', label: '', outcomes: ['выполнено'], slot: 3 },
  { id: 4, kind: 'branch', line: 4, method: 'Demo.f', label: 'if (x > 0 && x < 9)', outcomes: ['истина', 'ложь'], slot: 4 },
  { id: 5, kind: 'cond', line: 4, method: 'Demo.f', label: 'x > 0', outcomes: ['истина', 'ложь'], slot: 6 },
  { id: 6, kind: 'rel', line: 4, method: 'Demo.f', label: 'x < 9', outcomes: ['<', '==', '>'], slot: 8 },
  { id: 7, kind: 'method', line: 8, method: 'Demo.g', label: 'Demo.g', outcomes: ['выполнено'], slot: 11 },
  { id: 8, kind: 'line', line: 9, method: 'Demo.g', label: '', outcomes: ['выполнено'], slot: 12 },
];
//          m0 l3 l4 l5 br  cond  rel     m1 l9
const hits = [1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 0, 0, 0];

describe('coverage', () => {
  it('sums hits of the same code and counts runs', () => {
    const a = mergeCoverage(undefined, 'A', probes, hits);
    expect(a.runs).toBe(1);
    const b = mergeCoverage(a, 'A', probes, hits);
    expect(b.runs).toBe(2);
    expect(b.hits[0]).toBe(2);
    expect(b.hits).toHaveLength(hits.length);
  });
  it('starts over for different code or hits length', () => {
    const a = mergeCoverage(undefined, 'A', probes, hits);
    const b = mergeCoverage(a, 'B', probes, hits);
    expect(b).toEqual({ code: 'B', probes, hits, runs: 1 });
    expect(mergeCoverage(a, 'A', probes, [1, 2]).runs).toBe(1);
  });
  it('formats percent', () => {
    expect(percent({ covered: 0, total: 0 })).toBe('—');
    expect(percent({ covered: 3, total: 4 })).toBe('75%');
  });
  it('summarizes metrics', () => {
    const s = summarize(mergeCoverage(undefined, 'A', probes, hits));
    expect(s.lines).toEqual({ covered: 3, total: 4 });
    expect(s.methods).toEqual({ covered: 1, total: 2 });
    expect(s.branches).toEqual({ covered: 1, total: 2 });
    expect(s.conditions).toEqual({ covered: 1, total: 2 });
    expect(s.relational).toEqual({ covered: 1, total: 3 });
  });
  it('reports per method coverage and uncalled methods', () => {
    const s = summarize(mergeCoverage(undefined, 'A', probes, hits));
    const f = s.perMethod.find((m) => m.method === 'Demo.f')!;
    const g = s.perMethod.find((m) => m.method === 'Demo.g')!;
    expect(f.called).toBe(true);
    expect(f.lines).toEqual({ covered: 3, total: 3 });
    expect(f.branches).toEqual({ covered: 1, total: 2 });
    expect(g.called).toBe(false);
    expect(g.lines).toEqual({ covered: 0, total: 1 });
  });
  it('lists missing outcomes ordered by line then id', () => {
    const s = summarize(mergeCoverage(undefined, 'A', probes, hits));
    expect(s.missing.map((m) => [m.line, m.kind, m.outcome])).toEqual([
      [4, 'branch', 'ложь'], [4, 'cond', 'ложь'], [4, 'rel', '=='], [4, 'rel', '>'],
    ]);
  });
  it('computes line states', () => {
    const st = lineStates(mergeCoverage(undefined, 'A', probes, hits));
    expect(st.get(3)).toEqual({ state: 'hit', count: 1, missing: [] });
    expect(st.get(4)!.state).toBe('partial');
    expect(st.get(4)!.missing).toContain('x > 0 → ложь');
    expect(st.get(9)).toEqual({ state: 'miss', count: 0, missing: [] });
  });
});
