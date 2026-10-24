import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { useStore } from '../../../store/useStore';
import { classifyBigO } from '../../../utils/bigo';

const CallNode: React.FC<NodeProps> = ({ id, data }) => {
  const hoveredNode = useStore((s) => s.hoveredNode);
  const setHoveredNode = useStore((s) => s.setHoveredNode);
  const setHoveredLine = useStore((s) => s.setHoveredLine);
  const hoveredLine = useStore((s) => s.hoveredLine);
  const isHovered = hoveredNode === id || (hoveredLine != null && data.lineStart === hoveredLine);

  const label = data.label as string;
  const parts = label.split('.');
  const className = parts.length > 1 ? parts.slice(0, -1).join('.') : '';
  const methodName = parts[parts.length - 1];

  return (
    <div
      title={`${label}${data.bigO ? ` · Big O: ${data.bigO}` : ''}`}
      data-kind="call"
      className={`g-node g-call ${isHovered ? 'is-hover' : ''}`}
      onMouseEnter={() => {
        setHoveredNode(id);
        if (data.lineStart) setHoveredLine(data.lineStart as number);
      }}
      onMouseLeave={() => {
        setHoveredNode(null);
        setHoveredLine(null);
      }}
    >
      <Handle type="target" position={Position.Top} />
      {className && <div className="g-owner">{className}</div>}
      <div className="g-method">{methodName}<span className="g-parens">()</span></div>
      {data.bigO && <span className={`g-bigo ${classifyBigO(data.bigO as string).grade}`}>{data.bigO as string}</span>}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

export default memo(CallNode);
