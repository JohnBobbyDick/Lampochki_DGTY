/** CFG node type → colour family (CSS `data-kind`) and a human label. */
export const CFG_KINDS: Record<string, { kind: string; label: string }> = {
  start: { kind: 'start', label: 'Начало' },
  end: { kind: 'end', label: 'Конец' },
  return: { kind: 'end', label: 'Возврат' },
  throw: { kind: 'end', label: 'Исключение' },
  condition: { kind: 'cond', label: 'Условие' },
  switch: { kind: 'cond', label: 'Выбор' },
  loop: { kind: 'loop', label: 'Цикл' },
  try: { kind: 'try', label: 'try' },
  catch: { kind: 'try', label: 'catch' },
  finally: { kind: 'try', label: 'finally' },
  statement: { kind: 'stmt', label: 'Операция' },
  'stream-source': { kind: 'stream', label: 'Источник стрима' },
  'stream-op': { kind: 'stream', label: 'Шаг стрима' },
  'stream-terminal': { kind: 'stream', label: 'Итог стрима' },
};

/** Legend entries, one per colour family. */
export const LEGEND: { kind: string; label: string }[] = [
  { kind: 'start', label: 'Начало' },
  { kind: 'cond', label: 'Условие' },
  { kind: 'loop', label: 'Цикл' },
  { kind: 'try', label: 'try / catch' },
  { kind: 'stmt', label: 'Операция' },
  { kind: 'stream', label: 'Стрим' },
  { kind: 'end', label: 'Возврат / конец' },
];
