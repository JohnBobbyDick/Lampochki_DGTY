import { describe, expect, it } from 'vitest';
import { estimateN, formatFactor, growth, speedup } from './speedup';

describe('speedup', () => {
  const NB = '\u00a0';
  it('gives no number without the data size', () => {
    for (const [b, a] of [['O(n²)', 'O(n)'], ['O(n)', 'O(1)'], ['O(2^n)', 'O(n)']]) {
      expect(speedup(b, a)).toMatchObject({ factor: null, label: '' });
      expect(speedup(b, a, null).label).toBe('');
    }
  });

  it.each([
    ['O(n)', 'O(n)'], ['O(?) рекурсия', 'O(n)'], ['O(n)', 'O(?)'], ['', 'O(n)'],
  ])('nothing to compare: %s -> %s', (b, a) => {
    expect(speedup(b, a, 50).label).toBe('');
  });

  it('uses the data size of the run', () => {
    expect(speedup('O(n²)', 'O(n)', 11).label).toBe('~11× быстрее');
    expect(speedup('O(n²)', 'O(n)', 4).label).toBe('~4× быстрее');
    expect(speedup('O(n log n)', 'O(n)', 11).label).toBe('~3,5× быстрее');
    expect(speedup('O(n²)', 'O(n)', 1234).label).toBe('~1200× быстрее');
    expect(speedup('O(n³)', 'O(n)', 400).label).toBe(`~160${NB}000× быстрее`);
    expect(speedup('O(n²)', 'O(n)', 11).hint).toContain('n ≈ 11');
    expect(speedup('O(n²)', 'O(n)', 1).label).toBe('≈ без разницы');
    expect(speedup('O(n)', 'O(n²)', 7)).toMatchObject({ label: '~7× медленнее', worse: true });
    expect(speedup('O(2^n)', 'O(n)', 20).label).toBe(`~52${NB}000× быстрее`);
    expect(speedup('O(n)', 'O(2^n)', 10)).toMatchObject({ label: '~100× медленнее', worse: true });
  });

  it('estimates n from the work of the busiest line', () => {
    expect(estimateN('O(n²)', 121)).toBe(11);
    expect(estimateN('O(n)', 14)).toBe(14);
    expect(estimateN('O(n³)', 1000)).toBe(10);
    expect(estimateN('O(log n)', 10)).toBe(1024);
    expect(estimateN('O(n²)', 0.5)).toBe(1);
    expect(estimateN('O(1)', 50)).toBeNull();
    expect(estimateN('O(2^n)', 50)).toBeNull();
    expect(estimateN('O(?)', 50)).toBeNull();
    expect(estimateN('O(n)', 0)).toBeNull();
  });

  it('formats factors', () => {
    expect(formatFactor(3.32)).toBe('3,3');
    expect(formatFactor(11)).toBe('11');
    expect(formatFactor(123)).toBe('120');
    expect(formatFactor(1e6)).toBe(`1${NB}000${NB}000`);
  });

  it('parses growth classes', () => {
    expect(growth('O(1)')).toBe(1);
    expect(growth('O(n)')).toBe(1000);
    expect(growth('O(log² n)')).toBeCloseTo(Math.log2(1000) ** 2);
    expect(growth('O(log^6 n)')).toBeCloseTo(Math.log2(1000) ** 6);
    expect(growth('O(n⁴)')).toBe(1e12);
    expect(growth('O(n^6)')).toBeCloseTo(1e18);
    expect(growth('O(n, 10)')).toBeNull();
    expect(growth('O(?)')).toBeNull();
    expect(growth('O(?) рекурсия')).toBeNull();
    expect(growth('O(2^n)', 10)).toBe(1024);
    expect(growth('O(n)', 10)).toBe(10);
  });

});
