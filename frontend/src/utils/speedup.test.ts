import { describe, expect, it } from 'vitest';
import { estimateN, formatFactor, growth, speedup } from './speedup';

describe('speedup', () => {
  const NB = '\u00a0';
  const range: [string, string, string, boolean][] = [
    ['O(n²)', 'O(n)', '~10–1000× быстрее', false],
    ['O(n)', 'O(log n)', '~3–100× быстрее', false],
    ['O(n²)', 'O(n log n)', '~3–100× быстрее', false],
    ['O(n log n)', 'O(n)', '~3,3–10× быстрее', false],
    ['O(n)', 'O(1)', '~10–1000× быстрее', false],
    ['O(n)', 'O(n²)', '~10–1000× медленнее', true],
    ['O(n)', 'O(n)', '', false],
    ['O(?) рекурсия', 'O(n)', '', false],
    ['O(n)', 'O(?)', '', false],
    ['', 'O(n)', '', false],
    ['O(2^n)', 'O(n)', '≥100× быстрее', false],
    ['O(n)', 'O(2^n)', '≥100× медленнее', true],
    ['O(n³)', 'O(n)', `~100–1${NB}000${NB}000× быстрее`, false],
    ['O(n^6)', 'O(n^5)', '~10–1000× быстрее', false],
    ['O(n² log n)', 'O(n²)', '~3,3–10× быстрее', false],
  ];
  it.each(range)('without a run: %s -> %s = %s', (b: string, a: string, label: string, worse: boolean) => {
    const s = speedup(b, a);
    expect(s.label).toBe(label);
    expect(s.worse).toBe(worse);
    expect(s.factor === null).toBe(label === '');
    if (label) expect(s.hint).toContain('при n от 10 до 1000');
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
    expect(growth('O(2^n)')).toBe(Infinity);
    expect(growth('O(n)', 10)).toBe(10);
  });

});
