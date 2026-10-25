import { useEffect, useRef } from 'react';
import { useStore } from '../store/useStore';
import { useApi } from './useApi';
import { layoutGraph } from '../utils/elkLayout';

/** Debounced code → parse → graph + analysis pipeline. */
export function useSync() {
  const code = useStore((s) => s.code);
  const graphType = useStore((s) => s.graphType);
  const selectedMethod = useStore((s) => s.selectedMethod);
  const docNonce = useStore((s) => s.docNonce);
  const showGraph = useStore((s) => s.showGraph);
  const setSyncStatus = useStore((s) => s.setSyncStatus);
  const api = useApi();
  const reqId = useRef(0);
  /** bumped only by code edits: a graph/method switch must not invalidate in-flight parse/analyze results */
  const codeReq = useRef(0);

  const refreshGraph = async (id: number) => {
    const st = useStore.getState();
    if (!st.showGraph) {
      setSyncStatus('idle');
      return;
    }
    const { data, error } = await api.getGraph(st.graphType, st.selectedMethod ?? undefined);
    if (id !== reqId.current) return; // a newer request superseded this one
    if (!data) {
      st.setNodes([]);
      st.setEdges([]);
      st.setGraphError(error ?? null);
      setSyncStatus('error');
      return;
    }
    st.setGraphError(null);
    const { nodes, edges } = await layoutGraph(
      data.nodes ?? [],
      data.edges ?? [],
      st.graphType === 'class' ? 'LR' : 'TB'
    );
    if (id !== reqId.current) return; // stale check after async ELK layout
    st.setNodes(nodes);
    st.setEdges(edges);
    setSyncStatus('idle');
  };

  const refreshAnalysis = async (id: number) => {
    const data = await api.analyzeCode();
    if (id !== codeReq.current || !data) return; // stale or failed: keep what is shown
    const st = useStore.getState();
    st.setDefects(data.defects ?? []);
    st.setBigo(data.bigo ?? {});
    st.setCompileErrors(data.compileErrors ?? null);
  };

  /* code changed or a document was loaded → drop stale AI tips at once, then debounce 500 ms → parse, analyse,
     rebuild graph */
  useEffect(() => {
    /* bump both at once so in-flight parse/analyze/graph responses for older code are ignored */
    const cid = ++codeReq.current;
    ++reqId.current;
    if (!code.trim()) return setSyncStatus('idle'); // a dropped in-flight request must not leave the spinner on
    useStore.getState().pruneStale(code);
    const timer = setTimeout(async () => {
      const id = ++reqId.current;
      setSyncStatus('syncing');
      const parsed = await api.parseCode(code, () => cid === codeReq.current);
      if (cid !== codeReq.current) return;
      if (!parsed) {
        /* the shown graph (or its error) belongs to older code */
        const st = useStore.getState();
        st.setNodes([]);
        st.setEdges([]);
        st.setGraphError(st.error ?? 'Не удалось разобрать код');
        return setSyncStatus('error');
      }
      await Promise.all([refreshAnalysis(cid), refreshGraph(id)]);
    }, 500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, docNonce]);

  /* tab / method switch → only rebuild the graph */
  useEffect(() => {
    if (!useStore.getState().code.trim() || !useStore.getState().ast) return;
    const id = ++reqId.current;
    setSyncStatus('syncing');
    refreshGraph(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphType, selectedMethod]);

  /* when graph is shown again → rebuild the graph */
  useEffect(() => {
    if (!showGraph || !useStore.getState().code.trim() || !useStore.getState().ast) return;
    const id = ++reqId.current;
    setSyncStatus('syncing');
    refreshGraph(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showGraph]);
}
