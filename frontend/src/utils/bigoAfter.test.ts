import { describe, it, expect } from 'vitest';
import { applicablePatches, bestSingle, bigoAfter, staticBigoAfter } from './bigoAfter';
import type { Defect } from '../types';
import type { AiAnswer, AiPatch } from '../store/useStore';

const patch = (old: string, nw: string, after: Record<string, string>, valid = true): AiPatch => ({
  oldCode: old, newCode: nw, imports: [], startLine: 1, endLine: 1, valid, problems: [], warnings: [],
  bigoBefore: {}, bigoAfter: after,
});
const ans = (p: Partial<AiAnswer>): AiAnswer => ({ title: '', text: '', source: 'x', ...p });
const code = 'int a = 1;\nint b = 2;\n';

describe('applicablePatches', () => {
  it('drops invalid and stale patches', () => {
    const ok = patch('int a = 1;', 'int a = 2;', {});
    const bad = patch('int b = 2;', 'x', {}, false);
    const stale = patch('int zzz = 9;', 'x', {});
    const res = applicablePatches(code, [ans({ patch: ok }), ans({ items: [bad, stale].map(p => ({ line: 1, title: '', detail: '', example: '', patch: p })) })]);
    expect(res).toEqual([ok]);
  });
  it('counts the same patch once across ai and aiReview', () => {
    const p = patch('int a = 1;', 'int a = 2;', {});
    const dup = { ...p };
    const res = applicablePatches(code, [ans({ patch: p }), ans({ items: [{ line: 1, title: '', detail: '', example: '', patch: dup }] }), null]);
    expect(res).toHaveLength(1);
  });
});

describe('bigoAfter', () => {
  const p1 = patch('a', 'b', { 'A.f': 'O(n)', 'A.main': 'O(n²)' });
  const p2 = patch('c', 'd', { 'A.g': 'O(log n)', 'A.main': 'O(n)' });
  it('0 patches -> {}', () => expect(bigoAfter([], { 'A.f': 'O(1)' })).toEqual({}));
  it('1 patch -> its bigoAfter', () => expect(bigoAfter([p1], null)).toEqual(p1.bigoAfter));
  it('2 patches with combined -> combined', () => {
    const c = { 'A.f': 'O(n)', 'A.g': 'O(log n)', 'A.main': 'O(n)' };
    expect(bigoAfter([p1, p2], c)).toBe(c);
  });
  it('2 patches without combined -> best per method', () => {
    expect(bigoAfter([p1, p2], null)).toEqual({ 'A.f': 'O(n)', 'A.g': 'O(log n)', 'A.main': 'O(n)' });
  });
  it('unknown recursion does not beat a known complexity', () => {
    const a = patch('a', 'b', { 'A.f': 'O(?) рекурсия' });
    const b = patch('c', 'd', { 'A.f': 'O(n²)' });
    expect(bestSingle([a, b])).toEqual({ 'A.f': 'O(n²)' });
    expect(bestSingle([b, a])).toEqual({ 'A.f': 'O(n²)' });
  });
});

describe('staticBigoAfter', () => {
  const d = (method: string, bigO: string, bigOAfter?: string): Defect =>
    ({ lineStart: 1, lineEnd: 1, nodeId: '', severity: 'warning', message: '', recommendation: '', method, bigO, bigOAfter });

  it('uses the expected effect of the defect that sets the method label', () => {
    expect(staticBigoAfter({ 'A.f': 'O(n²)' }, [d('A.f', 'O(n²)', 'O(n)')])).toEqual({ 'A.f': 'O(n)' });
  });
  it('ignores defects below the method label and methods without a rule', () => {
    expect(staticBigoAfter({ 'A.f': 'O(n³)', 'A.g': 'O(n)' }, [d('A.f', 'O(n²)', 'O(n)')])).toEqual({});
  });
  it('takes the worst estimate of several dominant defects, none if one is unknown', () => {
    expect(staticBigoAfter({ 'A.f': 'O(n²)' }, [d('A.f', 'O(n²)', 'O(n)'), d('A.f', 'O(n²)', 'O(n log n)')]))
      .toEqual({ 'A.f': 'O(n log n)' });
    expect(staticBigoAfter({ 'A.f': 'O(n²)' }, [d('A.f', 'O(n²)', 'O(n)'), d('A.f', 'O(n²)')])).toEqual({});
  });
});
