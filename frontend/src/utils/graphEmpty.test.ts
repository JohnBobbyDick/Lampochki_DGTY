import { describe, expect, it } from 'vitest';
import { graphEmptyText, methodAfterParse } from './graphEmpty';

describe('graphEmptyText', () => {
  it('names the current language', () => {
    expect(graphEmptyText('java', null)).toBe('Откройте файл слева или вставьте код на Java');
    expect(graphEmptyText('python', null)).toBe('Откройте файл слева или вставьте код на Python');
  });

  it('shows the server error instead of the hint', () => {
    expect(graphEmptyText('python', 'В коде нет методов')).toBe('Не удалось построить граф: В коде нет методов');
    expect(graphEmptyText('java', 'Метод не найден: Demo.sumPairs')).toBe('Не удалось построить граф: Метод не найден: Demo.sumPairs');
  });
});

describe('methodAfterParse', () => {
  it('keeps a method that still exists', () => {
    expect(methodAfterParse('b', ['a', 'b'])).toBe('b');
  });

  it('falls back to the first method of the new file', () => {
    expect(methodAfterParse('Demo.sumPairs', ['find_duplicates', 'sum_pairs'])).toBe('find_duplicates');
    expect(methodAfterParse(null, ['find_duplicates'])).toBe('find_duplicates');
  });

  it('is null when the file has no methods', () => {
    expect(methodAfterParse('Demo.sumPairs', [])).toBeNull();
  });
});
