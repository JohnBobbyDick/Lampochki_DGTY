import { useEffect, useRef } from 'react';
import { Node, Edge, MarkerType } from 'reactflow';
import dagre from '@dagrejs/dagre';
import { useStore } from '../store/useStore';
import { useApi } from './useApi';
import { GraphNode, GraphEdge } from '../types';

/* mid-tone hues that read on both the light and the dark graph canvas */
const EDGE_COLOR: Record<string, string> = {
  normal: '#8a8a8a',
  true: '#22a55b',
  false: '#e5534b',
  back: '#4f8ef7',
  exception: '#e5534b',
  extends: '#9b7af0',
  implements: '#9b7af0',
};

const EDGE_LABEL: Record<string, string> = { true: 'да', false: 'нет', back: 'повтор' };

function layoutGraph(
  graphNodes: GraphNode[],
  graphEdges: GraphEdge[],
  direction: 'TB' | 'LR',
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 84 });

  const size = (n: GraphNode) =>
    n.type === 'class' || n.type === 'interface'
      ? { width: 280, height: 64 + 12 * 2 + 18 * (Math.max(1, n.data.fields?.length ?? 0) + Math.max(1, n.data.methods?.length ?? 0)) }
      : n.type === 'method'
        ? { width: 170, height: 90 }
        : n.type.startsWith('stream-')
          ? { width: 220, height: 46 + 18 * Math.ceil((n.label?.length ?? 0) / 26) }
          : { width: 220, height: 70 };

  graphNodes.forEach((n) => g.setNode(n.id, size(n)));
  graphEdges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);

  const nodes: Node[] = graphNodes.map((n) => {
    const pos = g.node(n.id);
    const { width, height } = size(n);
    return {
      id: n.id,
      type: n.type,
      position: { x: (pos?.x ?? 0) - width / 2, y: (pos?.y ?? 0) - height / 2 },
      data: { label: n.label, ...n.data, nodeType: n.type },
    };
  });

  let backIndex = 0;
  const centerX = (id: string) => g.node(id)?.x ?? 0;
  const edges: Edge[] = graphEdges.map((e) => {
    const color = EDGE_COLOR[e.type] ?? EDGE_COLOR.normal;
    const back = e.type === 'back' && direction === 'TB';
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      /* back edges are explained by their dashed style and the legend; a label there only adds clutter */
      label: back ? undefined : (e.label && (EDGE_LABEL[e.label] ?? e.label)) || undefined,
      animated: e.type === 'back',
      type: 'labeled',
      /* a body left of its loop header loops back on the left, otherwise on the right */
      ...(back ? (centerX(e.source) < centerX(e.target) - 1
        ? { sourceHandle: 'back-out-l', targetHandle: 'back-in-l' }
        : { sourceHandle: 'back-out-r', targetHandle: 'back-in-r' }) : {}),
      data: { color, offset: back ? 22 + 14 * backIndex++ : 20 },
      style: {
        stroke: color,
        strokeWidth: 1.6,
        strokeDasharray: ['back', 'exception', 'implements'].includes(e.type) ? '6 4' : undefined,
      },
      markerEnd: { type: MarkerType.ArrowClosed, color },
    };
  });
  return { nodes, edges };
}

/** Debounced code → parse → graph + analysis pipeline. */
export function useSync() {
  const code = useStore((s) => s.code);
  const graphType = useStore((s) => s.graphType);
  const selectedMethod = useStore((s) => s.selectedMethod);
  const setSyncStatus = useStore((s) => s.setSyncStatus);
  const api = useApi();
  const reqId = useRef(0);
  /** bumped only by code edits: a graph/method switch must not invalidate in-flight parse/analyze results */
  const codeReq = useRef(0);

  const refreshGraph = async (id: number) => {
    const st = useStore.getState();
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
    const { nodes, edges } = layoutGraph(data.nodes ?? [], data.edges ?? [], st.graphType === 'class' ? 'LR' : 'TB');
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

  /* code changed → drop stale AI tips at once, then debounce 500 ms → parse, analyse, rebuild graph */
  useEffect(() => {
    /* bump at once so an in-flight analyze for older code is ignored */
    const cid = ++codeReq.current;
    if (!code.trim()) return;
    useStore.getState().pruneStale(code);
    const timer = setTimeout(async () => {
      const id = ++reqId.current;
      setSyncStatus('syncing');
      const parsed = await api.parseCode(code, () => cid === codeReq.current);
      if (cid !== codeReq.current) return;
      if (!parsed) return setSyncStatus('error');
      await Promise.all([refreshAnalysis(cid), refreshGraph(id)]);
    }, 500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  /* tab / method switch → only rebuild the graph */
  useEffect(() => {
    if (!useStore.getState().code.trim() || !useStore.getState().ast) return;
    const id = ++reqId.current;
    setSyncStatus('syncing');
    refreshGraph(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphType, selectedMethod]);
}
