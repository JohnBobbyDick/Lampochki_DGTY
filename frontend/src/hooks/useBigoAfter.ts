import { useEffect } from 'react';
import { useStore } from '../store/useStore';
import { applicablePatches, bigoAfter } from '../utils/bigoAfter';
import { useApi } from './useApi';

export const BIGO_COMBINED_DELAY_MS = 400;

/** Keeps `useStore.bigoAfterAi` in sync with the currently applicable AI suggestions. Call once in App. */
export function useBigoAfter() {
  const code = useStore((s) => s.code);
  const ai = useStore((s) => s.ai);
  const aiReview = useStore((s) => s.aiReview);
  const api = useApi();

  useEffect(() => {
    const patches = applicablePatches(code, [ai, aiReview]);
    const set = useStore.getState().setBigoAfterAi;
    set(bigoAfter(patches, null));
    if (patches.length < 2) return;

    let stale = false;
    const timer = setTimeout(async () => {
      const combined = await api.bigoCombined(code, patches);
      if (stale || !combined) return;
      set(bigoAfter(patches, combined));
    }, BIGO_COMBINED_DELAY_MS);
    return () => { stale = true; clearTimeout(timer); };
  }, [code, ai, aiReview]); // eslint-disable-line react-hooks/exhaustive-deps
}
