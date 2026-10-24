import { describe, it, expect } from 'vitest';
import { changedMethods, isBigoChange } from './bigoChange';

describe('bigoChange', () => {
  it('ignores missing, same and unknown labels', () => {
    expect(isBigoChange('O(n²)', undefined)).toBe(false);
    expect(isBigoChange('O(n)', 'O(n)')).toBe(false);
    expect(isBigoChange('O(n)', 'O(?)')).toBe(false);
    expect(isBigoChange('O(?)', 'O(n)')).toBe(false);
    expect(isBigoChange('O(n²)', 'O(n)')).toBe(true);
  });
  it('lists only changed methods', () => {
    expect(changedMethods({ 'A.f': 'O(n²)', 'A.g': 'O(n)' }, { 'A.f': 'O(n)', 'A.g': 'O(n)' }))
      .toEqual([['A.f', 'O(n²)', 'O(n)']]);
  });
});
