import { describe, expect, it } from 'vitest';
import { languageOf } from './language';

describe('languageOf', () => {
  it('detects by extension', () => {
    expect(languageOf('x.py')).toBe('python');
    expect(languageOf('X.java')).toBe('java');
    expect(languageOf('README')).toBe('java');
  });
});
