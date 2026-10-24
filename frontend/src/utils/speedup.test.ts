import { describe, expect, it } from 'vitest';
import { growth, speedup } from './speedup';

describe('speedup', () => {
  const rows: [string, string, string, boolean][] = [
    ['O(n²)', 'O(n)', '~1000× быстрее', false],
    ['O(n)', 'O(log n)', '~100× быстрее', false],
    ['O(n²)', 'O(n log n)', '~100× быстрее', false],
    ['O(n log n)', 'O(n)', '~10× быстрее', false],
    ['O(n)', 'O(1)', '~1000× быстрее', false],
    ['O(n)', 'O(n²)', '~1000× медленнее', true],
    ['O(n)', 'O(n)', '', false],
    ['O(?) рекурсия', 'O(n)', '', false],
    ['O(n)', 'O(?)', '', false],
    ['', 'O(n)', '', false],
    ['O(2^n)', 'O(n)', '>1000000× быстрее', false],
    ['O(n)', 'O(2^n)', '>1000000× медленнее', true],
    ['O(n³)', 'O(n²)', '~1000× быстрее', false],
    ['O(n⁴)', 'O(n³)', '~1000× быстрее', false],
    ['O(n^6)', 'O(n^5)', '~1000× быстрее', false],
    ['O(n⁵)', 'O(n^6)', '~1000× медленнее', true],
    ['O(n² log n)', 'O(n²)', '~10× быстрее', false],
  ];
  it.each(rows)('%s -> %s = %s', (b: string, a: string, label: string, worse: boolean) => {
    const s = speedup(b, a);
    expect(s.label).toBe(label);
    expect(s.worse).toBe(worse);
    expect(s.factor === null).toBe(label === '');
    if (s.factor !== null) expect(Number.isFinite(s.factor)).toBe(true);
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

  it('rounds to nearest by logarithm', () => {
    expect(speedup('O(n)', 'O(1)', 30).label).toBe('~10× быстрее');
    expect(speedup('O(n)', 'O(1)', 3).label).toBe('~2× быстрее');
  });
});
