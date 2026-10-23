import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { useStore } from '../../../store/useStore';

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
      style={{
        background: isHovered ? '#1a3a5c' : '#252526',
        border: isHovered ? '2px solid #007acc' : '2px solid #444',
        borderRadius: '50%',
        width: 150,
        height: 80,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#d4d4d4',
        fontSize: 12,
        fontFamily: "'JetBrains Mono', Consolas, monospace",
        boxShadow: isHovered ? '0 0 12px rgba(0,122,204,.5)' : '0 2px 6px rgba(0,0,0,.4)',
        transition: 'all .15s',
        cursor: 'pointer',
        position: 'relative',
      }}
      onMouseEnter={() => {
        setHoveredNode(id);
        if (data.lineStart) setHoveredLine(data.lineStart as number);
      }}
      onMouseLeave={() => {
        setHoveredNode(null);
        setHoveredLine(null);
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />

      {className && (
        <div style={{ fontSize: 9, opacity: 0.5, marginBottom: 2 }}>{className}</div>
      )}
      <div style={{ fontWeight: 600 }}>{methodName}</div>

      {data.bigO && (
        <span
          style={{
            position: 'absolute',
            top: -6,
            right: -6,
            background: '#007acc',
            color: '#fff',
            fontSize: 9,
            fontWeight: 700,
            padding: '2px 6px',
            borderRadius: 8,
          }}
        >
          {data.bigO as string}
        </span>
      )}

      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
    </div>
  );
};

export default memo(CallNode);
