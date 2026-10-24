import { describe, it, expect } from 'vitest';
import { fragmentPresent } from './fragment';

describe('fragmentPresent', () => {
  const code = 'class A {\n    void f() {\n        int x = 1;\n\n        x++;\n    }\n}';
  it('ignores indentation and blank lines', () => expect(fragmentPresent(code, 'int x = 1;\n  x++;')).toBe(true));
  it('false when edited', () => expect(fragmentPresent(code.replace('x++', 'x--'), 'int x = 1;\nx++;')).toBe(false));
  it('false for empty', () => expect(fragmentPresent(code, '  \n')).toBe(false));
});
