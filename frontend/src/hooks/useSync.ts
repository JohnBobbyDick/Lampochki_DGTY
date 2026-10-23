import { useEffect, useRef } from 'react';
import { Node, Edge, MarkerType } from 'reactflow';
import dagre from '@dagrejs/dagre';
import { useStore } from '../store/useStore';
import { useApi } from './useApi';
import { GraphNode, GraphEdge } from '../types';

const EDGE_COLOR: Record<string, string> = {
  normal: '#8a8a8a',
  true: '#4ec9b0',
  false: '#f48771',
  back: '#569cd6',
  exception: '#f44747',
  extends: '#c586c0',
  implements: '#c586c0',
};

function layoutGraph(
  graphNodes: GraphNode[],
  graphEdges: GraphEdge[],
  direction: 'TB' | 'LR',
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 50, ranksep: 70 });

  const size = (n: GraphNode) =>
    n.type === 'class' || n.type === 'interface'
      ? { width: 240, height: 60 + 16 * ((n.data.fields?.length ?? 0) + (n.data.methods?.length ?? 0)) }
      : n.type === 'method'
        ? { width: 170, height: 90 }
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

  const edges: Edge[] = graphEdges.map((e) => {
    const color = EDGE_COLOR[e.type] ?? '#8a8a8a';
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label || undefined,
      animated: e.type === 'back',
      type: 'smoothstep',
      style: {
        stroke: color,
        strokeWidth: 1.6,
        strokeDasharray: ['back', 'exception', 'implements'].includes(e.type) ? '6 4' : undefined,
      },
      labelStyle: { fill: color, fontSize: 11 },
      labelBgStyle: { fill: '#1e1e1e', fillOpacity: 0.85 },
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

  const refreshGraph = async (id: number) => {
    const st = useStore.getState();
    const data = await api.getGraph(st.graphType, st.selectedMethod ?? undefined);
    if (id !== reqId.current) return; // a newer request superseded this one
    if (!data) {
      st.setNodes([]);
      st.setEdges([]);
      setSyncStatus('error');
      return;
    }
    const { nodes, edges } = layoutGraph(data.nodes ?? [], data.edges ?? [], st.graphType === 'class' ? 'LR' : 'TB');
    st.setNodes(nodes);
    st.setEdges(edges);
    setSyncStatus('idle');
  };

  /* code changed → debounce 500 ms → parse, analyse, rebuild graph */
  useEffect(() => {
    if (!code.trim()) return;
    const timer = setTimeout(async () => {
      const id = ++reqId.current;
      setSyncStatus('syncing');
      const parsed = await api.parseCode(code);
      if (!parsed) return setSyncStatus('error');
      await Promise.all([api.analyzeCode(), refreshGraph(id)]);
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
