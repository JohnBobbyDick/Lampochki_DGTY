import { useEffect } from 'react';
import { useStore } from '../store/useStore';
import { useApi } from './useApi';

export const AUTO_MEASURE_DELAY_MS = 1000;

/**
 * Runs the current code once in the background (no input, server limits) when there is a Big O change to show,
 * so the speedup is computed for the real data size n instead of a guess. Result: `useStore.measure`. Call once in App.
 */
export function useAutoMeasure() {
  const code = useStore((s) => s.code);
  const defects = useStore((s) => s.defects);
  const bigoAfterAi = useStore((s) => s.bigoAfterAi);
  const compileErrors = useStore((s) => s.compileErrors);
  const syntaxErrors = useStore((s) => s.syntaxErrors);
  const api = useApi();

  useEffect(() => {
    const st = useStore.getState();
    if (st.measure?.code === code) return;
    if (st.measure) st.setMeasure(null); // a measurement of older code says nothing about this one
    const wanted = defects.some((d) => d.bigO && d.bigOAfter) || Object.keys(bigoAfterAi).length > 0;
    if (!code.trim() || !wanted || syntaxErrors.length || compileErrors?.length) return;

    let stale = false;
    const timer = setTimeout(async () => {
      st.setMeasure({ code, status: 'pending' });
      const data = await api.measureRun(code);
      if (stale || useStore.getState().code !== code) return;
      st.setMeasure(data ? { code, status: 'done', coverage: { code, ...data, runs: 1 } } : { code, status: 'error' });
    }, AUTO_MEASURE_DELAY_MS);
    return () => { stale = true; clearTimeout(timer); };
  }, [code, defects, bigoAfterAi, compileErrors, syntaxErrors]); // eslint-disable-line react-hooks/exhaustive-deps
}
