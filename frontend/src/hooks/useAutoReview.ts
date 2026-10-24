import { useEffect, useRef } from 'react';
import axios from 'axios';
import { useStore } from '../store/useStore';
import { useApi } from './useApi';

/** Idle time after the last edit before the AI looks at the code. */
export const REVIEW_IDLE_MS = 5000;

/**
 * Debounced AI review: 5 s after the user stops editing the code, ask the model how to improve it.
 * A newer edit cancels both the pending timer and an in-flight request.
 */
export function useAutoReview() {
  const code = useStore((s) => s.code);
  const auto = useStore((s) => s.aiAuto);
  const enabled = useStore((s) => s.aiEnabled);
  const api = useApi();
  const lastReviewed = useRef<string>('');

  useEffect(() => {
    api.aiStatus();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!auto || !enabled || !code.trim() || code === lastReviewed.current) return;
    if (code === useStore.getState().reviewSkip) return;

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      const st = useStore.getState();
      st.setAiReviewing(true);
      try {
        const { data } = await axios.post('/api/ai/review', { code, language: st.language }, { signal: controller.signal, timeout: 120_000 });
        lastReviewed.current = code;
        const items = (data.suggestions ?? []).filter((it: { patch?: unknown }) => it.patch);
        st.setAiReview(
          items.length || data.summary
            ? { title: '✨ ИИ-ревью кода', text: data.summary, items, source: data.source, note: data.note }
            : data.note
              ? { title: '✨ ИИ-ревью кода', text: '', items: [], source: 'none', note: data.note }
              : null,
        );
      } catch (e) {
        if (!axios.isCancel(e)) {
          lastReviewed.current = code; // don't hammer a failing API with the same code
          st.setAiReview({ title: '✨ ИИ-ревью кода', text: '', items: [], source: 'none', note: 'ИИ сейчас недоступен' });
        }
      } finally {
        if (!controller.signal.aborted) useStore.getState().setAiReviewing(false);
      }
    }, REVIEW_IDLE_MS);

    return () => {
      clearTimeout(timer);
      if (!controller.signal.aborted) controller.abort();
      useStore.getState().setAiReviewing(false);
    };
  }, [code, auto, enabled]);
}
