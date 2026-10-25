import { useProject } from '../store/useProject';
import { useStore } from '../store/useStore';
import { workPerCall } from '../utils/coverage';
import { estimateN } from '../utils/speedup';

/** Data size for the speedup: a number, 'pending' while the background run goes, null when it is unknown. */
export type MeasuredN = number | 'pending' | null;

/**
 * Data size n of a method (or of its lines from..to), read from the coverage counters of the user's last run of
 * the current text, else of the background run (useAutoMeasure). Feeds the speedup estimate of BigoChange.
 */
export function useMeasuredN() {
  const cov = useProject((s) => s.coverage[s.activeId]);
  const measure = useStore((s) => s.measure);
  const code = useStore((s) => s.code);
  const own = cov && cov.code === code ? cov : null;
  const auto = measure?.code === code ? measure : null;
  return (bigo: string, method?: string, from?: number, to?: number): MeasuredN => {
    if (!method) return null;
    for (const c of [own, auto?.coverage]) {
      const work = c ? workPerCall(c, method, from, to) : null;
      if (work !== null) return estimateN(bigo, work);
    }
    return auto?.status === 'pending' ? 'pending' : null;
  };
}
