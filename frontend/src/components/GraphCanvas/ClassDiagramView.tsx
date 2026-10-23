import React, { useEffect } from 'react';
import ReactFlow, { useReactFlow, Controls, MiniMap, Background, BackgroundVariant } from 'reactflow';
import 'reactflow/dist/style.css';
import ClassNode from './nodes/ClassNode';
import { useStore } from '../../store/useStore';

const nodeTypes = {
  class: ClassNode,
  interface: ClassNode,
};

const ClassDiagramView: React.FC = () => {
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
      onNodeClick={(_, n) => n.data.lineStart && jumpToLine(n.data.lineStart as number)}
      fitView
      fitViewOptions={{ padding: 0.3 }}
      minZoom={0.2}
      maxZoom={2}
      nodesConnectable={false}
      proOptions={{ hideAttribution: true }}
    >
      <Controls
        style={{ background: '#333', borderRadius: 6, border: '1px solid #555' }}
      />
      <MiniMap
        style={{ background: '#1e1e1e', border: '1px solid #333' }}
        nodeColor="#569cd6"
        maskColor="rgba(0,0,0,.6)"
      />
      <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#333" />
    </ReactFlow>
  );
};

export default ClassDiagramView;
