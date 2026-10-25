import { useProject } from '../store/useProject';
import { useStore } from '../store/useStore';
import { workPerCall } from '../utils/coverage';
import { estimateN } from '../utils/speedup';

/**
 * Data size n of a method (or of its lines from..to) in the last run of the active file, read from the coverage
 * counters; null until the current text has been run. Feeds the speedup estimate of BigoChange.
 */
export function useMeasuredN() {
  const cov = useProject((s) => s.coverage[s.activeId]);
  const code = useStore((s) => s.code);
  const live = cov && cov.code === code ? cov : null;
  return (bigo: string, method?: string, from?: number, to?: number): number | null => {
    if (!live || !method) return null;
    const work = workPerCall(live, method, from, to);
    return work === null ? null : estimateN(bigo, work);
  };
}
