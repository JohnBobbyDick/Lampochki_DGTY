import { useCallback, useMemo } from 'react';
import axios, { AxiosError } from 'axios';
import { useStore, AiPatch } from '../store/useStore';
import { useProject } from '../store/useProject';
import { downloadFile } from '../utils/download';
import { GraphType, QualityGateResult } from '../types';

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
  timeout: 90_000,
});

/** Pull a readable message out of any thrown value. */
function errorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    const d = err.response?.data?.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((x) => x.msg).join('; ');
    if (err.code === AxiosError.ECONNABORTED) return 'Сервер слишком долго не отвечает. Повторите действие или уменьшите объём кода.';
    if (!err.response) return 'Нет связи с сервером. Проверьте, что бэкенд запущен (порт 8000), и повторите действие.';
    if (err.response.status >= 500) return 'Сервер не смог обработать запрос. Повторите действие; если ошибка останется, посмотрите журнал бэкенда.';
    return err.response.data?.message ?? `Запрос не выполнен (код ${err.response.status}). Повторите действие.`;
  }
  return err instanceof Error ? err.message : 'Неизвестная ошибка. Повторите действие.';
}

/**
 * Thin wrappers over the REST API.  They read/write the store through
 * `useStore.getState()` so the returned functions are referentially stable.
 */
export function useApi() {
  const call = useCallback(async <T,>(fn: () => Promise<T>, quiet = false): Promise<T | null> => {
    const st = useStore.getState();
    try {
      if (!quiet) st.setLoading(true);
      st.setError(null);
      return await fn();
    } catch (e) {
      st.setError(errorMessage(e));
      return null;
    } finally {
      if (!quiet) useStore.getState().setLoading(false);
    }
  }, []);

  return useMemo(() => {
    const S = () => useStore.getState();

    /** `isCurrent` is checked after the response arrives; stale responses are dropped. */
    const parseCode = (code: string, isCurrent: () => boolean = () => true) =>
      call(async () => {
        const { data } = await api.post('/parse', { code, language: S().language });
        if (!isCurrent()) return data;
        const st = S();
        st.setAst(data.ast);
        st.setLineMap(data.lineMap ?? {});
        st.setMethods(data.methods ?? []);
        st.setSyntaxErrors(data.errors ?? []);
        if (data.language && data.language !== st.language) {
          st.setLanguage(data.language);
        }
        if (!st.selectedMethod || !(data.methods ?? []).includes(st.selectedMethod)) {
          st.setSelectedMethod(data.methods?.[0] ?? null);
        }
        return data;
      }, true);

    const getGraph = (type: GraphType, method?: string) =>
      call(async () => {
        const params: Record<string, string> = { type };
        if (method) params.method = method;
        return (await api.get('/graph', { params })).data;
      }, true);

    const analyzeCode = () =>
      call(async () => {
        const { data } = await api.post('/analyze');
        return data;
      }, true);

    const generateCode = (graph: unknown) =>
      call(async () => (await api.post('/generate', { graph, language: S().language })).data);

    const runCode = (code: string) =>
      call(async () => {
        const { data } = await api.post('/run', { code, stdinInput: S().stdin, language: S().language });
        S().setRunResult(data);
        return data;
      });

    const compareCode = (original: string, modified: string) =>
      call(async () => {
        const { data } = await api.post('/run/compare', { original, modified, stdinInput: S().stdin, language: S().language });
        S().setCompareResult(data);
        return data;
      });

    const decomposeCode = () =>
      call(async () => {
        const { data } = await api.post('/decompose', { language: S().language });
        S().setDecomposition(data.files ?? []);
        S().setDecomposeWarnings(data.warnings ?? []);
        S().setGateResult(null);
        return data;
      });

    const verifyDecomposition = () =>
      call(async () => {
        const { data } = await api.post<QualityGateResult>('/decompose/verify', { language: S().language });
        S().setGateResult(data);
        return data;
      });

    const downloadDecomposition = () =>
      call(async () => {
        const { data } = await api.post('/decompose/zip', { language: S().language }, { responseType: 'blob' });
        downloadFile('decomposed.zip', data);
        return true;
      });

    /** Zip of every project file whose current text differs from its original (server builds the archive). */
    const downloadChanged = () =>
      call(async () => {
        const { files, activeId } = useProject.getState();
        const changed = files
          .map((f) => ({ path: f.id, code: f.id === activeId ? S().code : f.code, original: f.original }))
          .filter((f) => f.code !== f.original)
          .map(({ path, code }) => ({ path, code }));
        if (!changed.length) return false;
        const { data } = await api.post('/files/zip', { files: changed }, { responseType: 'blob' });
        downloadFile('changed.zip', data);
        return true;
      });

    const qualityGate = (original: string, modified: string) =>
      call(async () => {
        const { data } = await api.post<QualityGateResult>('/quality-gate', { original, modified, stdinInput: S().stdin, language: S().language });
        S().setGateResult(data);
        return data;
      });

    const aiExplain = async (defect: unknown) => {
      const st = S();
      st.setAi(null);
      st.setAiLoading(true);
      const data = await call(async () => (await api.post('/ai/explain', { defect, language: S().language })).data, true);
      st.setAiLoading(false);
      if (data) {
        st.setAi({ title: '✨ Объяснение дефекта', text: data.explanation, patch: data.patch, source: data.source, note: data.note });
        S().pruneStale(S().code); // the code may have changed while the answer was in flight
      }
      return data;
    };

    const aiFix = async (err: { line: number | null; message: string }) => {
      const st = S();
      st.setAi(null);
      st.setAiLoading(true);
      const data = await call(async () => (await api.post('/ai/fix', { code: st.code, line: err.line, message: err.message, language: st.language })).data, true);
      st.setAiLoading(false);
      if (data) {
        st.setAi({ title: '✨ Исправление ошибки', text: data.explanation, patch: data.patch, source: data.source, note: data.note });
        S().pruneStale(S().code);
      }
      return data;
    };

    const aiDecompose = async () => {
      const st = S();
      st.setAi(null);
      st.setAiLoading(true);
      const data = await call(async () => (await api.post('/ai/decompose')).data, true);
      st.setAiLoading(false);
      if (data) st.setAi({ title: '✨ Совет по декомпозиции', text: data.advice, source: data.source, note: data.note });
      return data;
    };

    /** Replace the suggested fragment in the current code (server re-validates against the live text). */
    const aiApply = (patch: unknown) =>
      call(async () => (await api.post('/ai/apply', { code: S().code, patch, language: S().language })).data, true);

    /** Big O after applying several patches together; silent (no spinner, no error toast). */
    const bigoCombined = async (code: string, patches: AiPatch[]): Promise<Record<string, string> | null> => {
      try {
        const { data } = await api.post('/ai/bigo-combined', { code, patches, language: S().language });
        return (data?.bigo ?? null) as Record<string, string> | null;
      } catch {
        return null;
      }
    };

    const aiStatus = async () => {
      try {
        const { data } = await api.get('/ai/status');
        S().setAiEnabled(!!data.enabled);
      } catch {
        S().setAiEnabled(false);
      }
    };

    return {
      aiApply, aiStatus, bigoCombined, aiExplain, aiFix, aiDecompose,
      parseCode, getGraph, analyzeCode, generateCode, runCode, compareCode,
      decomposeCode, verifyDecomposition, downloadDecomposition, downloadChanged, qualityGate,
    };
  }, [call]);
}
