import { useCallback, useMemo } from 'react';
import axios, { AxiosError } from 'axios';
import { useStore } from '../store/useStore';
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
    return err.response?.data?.message ?? err.message;
  }
  return err instanceof Error ? err.message : 'Unknown error';
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

    const parseCode = (code: string) =>
      call(async () => {
        const { data } = await api.post('/parse', { code });
        const st = S();
        st.setAst(data.ast);
        st.setLineMap(data.lineMap ?? {});
        st.setMethods(data.methods ?? []);
        st.setSyntaxErrors(data.errors ?? []);
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
        S().setDefects(data.defects ?? []);
        S().setBigo(data.bigo ?? {});
        return data;
      }, true);

    const generateCode = (graph: unknown) =>
      call(async () => (await api.post('/generate', { graph })).data);

    const runCode = (code: string) =>
      call(async () => {
        const { data } = await api.post('/run', { code, stdinInput: S().stdin });
        S().setRunResult(data);
        return data;
      });

    const compareCode = (original: string, modified: string) =>
      call(async () => {
        const { data } = await api.post('/run/compare', { original, modified, stdinInput: S().stdin });
        S().setCompareResult(data);
        return data;
      });

    const decomposeCode = () =>
      call(async () => {
        const { data } = await api.post('/decompose');
        S().setDecomposition(data.files ?? []);
        S().setDecomposeWarnings(data.warnings ?? []);
        S().setGateResult(null);
        return data;
      });

    const verifyDecomposition = () =>
      call(async () => {
        const { data } = await api.post<QualityGateResult>('/decompose/verify');
        S().setGateResult(data);
        return data;
      });

    const downloadDecomposition = () =>
      call(async () => {
        const { data } = await api.post('/decompose/zip', {}, { responseType: 'blob' });
        const url = URL.createObjectURL(data);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'decomposed.zip';
        a.click();
        URL.revokeObjectURL(url);
        return true;
      });

    const qualityGate = (original: string, modified: string) =>
      call(async () => {
        const { data } = await api.post<QualityGateResult>('/quality-gate', { original, modified, stdinInput: S().stdin });
        S().setGateResult(data);
        return data;
      });

    const aiExplain = async (defect: unknown) => {
      const st = S();
      st.setAi(null);
      st.setAiLoading(true);
      const data = await call(async () => (await api.post('/ai/explain', { defect })).data, true);
      st.setAiLoading(false);
      if (data) st.setAi({ title: '✨ Объяснение дефекта', text: data.explanation, code: data.patch ? undefined : data.fixedCode, patch: data.patch, source: data.source, note: data.note });
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
      call(async () => (await api.post('/ai/apply', { code: S().code, patch })).data, true);

    const aiStatus = async () => {
      try {
        const { data } = await api.get('/ai/status');
        S().setAiEnabled(!!data.enabled);
      } catch {
        S().setAiEnabled(false);
      }
    };

    return {
      aiApply, aiStatus, aiExplain, aiDecompose,
      parseCode, getGraph, analyzeCode, generateCode, runCode, compareCode,
      decomposeCode, verifyDecomposition, downloadDecomposition, qualityGate,
    };
  }, [call]);
}
