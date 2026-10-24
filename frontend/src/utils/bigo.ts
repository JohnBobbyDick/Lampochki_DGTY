export type Grade = 'good' | 'ok' | 'bad' | 'unknown';

/** Growth class of a Big O string like "O(n²)": colour tone + the factual name of the class. */
export const classifyBigO = (v: string): { grade: Grade; name: string } => {
  const s = v.trim();
  if (/\?/.test(s)) return { grade: 'unknown', name: 'нужен ручной анализ' };
  if (/\^|!/.test(s)) return { grade: 'bad', name: 'экспоненциальная' };
  if (/³/.test(s)) return { grade: 'bad', name: 'кубическая' };
  if (/²/.test(s)) return { grade: 'bad', name: 'квадратичная' };
  if (/n\s*log/i.test(s)) return { grade: 'ok', name: 'линейно-логарифмическая' };
  if (/log/i.test(s)) return { grade: 'good', name: 'логарифмическая' };
  if (/^O\(1\)$/.test(s)) return { grade: 'good', name: 'константная' };
  if (/^O\(n\)$/.test(s)) return { grade: 'ok', name: 'линейная' };
  return { grade: 'unknown', name: '' };
};
