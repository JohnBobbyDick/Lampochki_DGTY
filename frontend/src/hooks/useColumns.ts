import { useState } from 'react';

export type ColKey = 'tree' | 'editor' | 'side';

export const COL_LIMITS: Record<ColKey, [number, number]> = {
  tree: [180, 380],
  editor: [280, 900],
  side: [280, 600],
};

const DEFAULTS: Record<ColKey, number> = { tree: 244, editor: 460, side: 380 };
const KEY = 'jb.columns';

/** Widths of the resizable columns, remembered per browser. */
export function useColumns() {
  const [cols, setCols] = useState<Record<ColKey, number>>(() => {
    try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch { return DEFAULTS; }
  });
  const setCol = (k: ColKey, v: number) =>
    setCols((c) => {
      const next = { ...c, [k]: v };
      try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* private mode */ }
      return next;
    });
  return { cols, setCol };
}
