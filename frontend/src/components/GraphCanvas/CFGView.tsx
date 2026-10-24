import React, { useEffect } from 'react';
import ReactFlow, { useReactFlow } from 'reactflow';
import 'reactflow/dist/style.css';
import GraphChrome from './GraphChrome';
import LabeledEdge from './LabeledEdge';

const edgeTypes = { labeled: LabeledEdge };
import CFGNode from './nodes/CFGNode';
import { useStore } from '../../store/useStore';

const nodeTypes = {
  start: CFGNode,
  end: CFGNode,
  statement: CFGNode,
  condition: CFGNode,
  loop: CFGNode,
  try: CFGNode,
  catch: CFGNode,
  finally: CFGNode,
  switch: CFGNode,
  return: CFGNode,
  throw: CFGNode,
  'stream-source': CFGNode,
  'stream-op': CFGNode,
  'stream-terminal': CFGNode,
};

const CFGView: React.FC = () => {
  const nodes = useStore((s) => s.nodes);
  const edges = useStore((s) => s.edges);
  const { fitView } = useReactFlow();
  useEffect(() => {
    const t = setTimeout(() => fitView({ padding: 0.25, maxZoom: 1.1 }), 60);
    return () => clearTimeout(t);
  }, [nodes, fitView]);
  const jumpToLine = useStore((s) => s.jumpToLine);
  const setEditingNode = useStore((s) => s.setEditingNode);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodeClick={(_, n) => n.data.lineStart && jumpToLine(n.data.lineStart as number)}
      onNodeDoubleClick={(_, n) => !['start', 'end', 'try', 'finally', 'case'].includes(n.type ?? '') && setEditingNode(n.id)}
      fitView
      fitViewOptions={{ padding: 0.3 }}
      minZoom={0.2}
      maxZoom={2}
      nodesConnectable={false}
      edgesFocusable={false}
      onSelectionChange={({ nodes: sel }) => sel[0]?.data.lineStart && jumpToLine(sel[0].data.lineStart as number)}
      proOptions={{ hideAttribution: true }}
    >
      <GraphChrome />
    </ReactFlow>
  );
};

export default CFGView;
