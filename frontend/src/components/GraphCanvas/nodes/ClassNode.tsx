import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { useStore } from '../../../store/useStore';

const ClassNode: React.FC<NodeProps> = ({ id, data }) => {
  const hoveredNode = useStore((s) => s.hoveredNode);
  const setHoveredNode = useStore((s) => s.setHoveredNode);
  const hoveredLine = useStore((s) => s.hoveredLine);
  const isHovered = hoveredNode === id || (hoveredLine != null && data.lineStart === hoveredLine);

  const nodeType: string = data.nodeType ?? 'class';
  const isInterface = nodeType === 'interface';
  const isAbstract = (data.label as string)?.startsWith('abstract ');

  const fields: string[] = (data.fields as string[]) ?? [];
  const methods: string[] = (data.methods as string[]) ?? [];
  const displayName = (data.label as string)?.replace(/^abstract\s+/, '') ?? id;

  return (
    <div
      style={{
        background: isInterface ? '#1e3a5f' : '#2d2d30',
        border: isHovered ? '2px solid #007acc' : '2px solid #444',
        borderRadius: 6,
        minWidth: 200,
        maxWidth: 280,
        color: '#d4d4d4',
        fontSize: 12,
        fontFamily: "'JetBrains Mono', Consolas, monospace",
        boxShadow: isHovered ? '0 0 12px rgba(0,122,204,.5)' : '0 2px 6px rgba(0,0,0,.4)',
        transition: 'all .15s',
        cursor: 'pointer',
        overflow: 'hidden',
      }}
      onMouseEnter={() => setHoveredNode(id)}
      onMouseLeave={() => setHoveredNode(null)}
    >
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />

      {/* Header */}
      <div
        style={{
          padding: '8px 12px',
          borderBottom: '1px solid #444',
          textAlign: 'center',
          fontWeight: 700,
          fontStyle: isAbstract ? 'italic' : 'normal',
          background: isInterface ? '#1a4a6f' : '#333',
        }}
      >
        {isInterface && (
          <div style={{ fontSize: 9, opacity: 0.6, marginBottom: 2 }}>«interface»</div>
        )}
        {displayName}
      </div>

      {/* Fields */}
      <div
        style={{
          padding: '6px 12px',
          borderBottom: '1px solid #444',
          minHeight: 20,
        }}
      >
        {fields.length === 0 ? (
          <div style={{ opacity: 0.4, fontSize: 10 }}>— нет полей —</div>
        ) : (
          fields.map((f, i) => (
            <div key={i} style={{ fontSize: 11, lineHeight: '18px' }}>
              {f}
            </div>
          ))
        )}
      </div>

      {/* Methods */}
      <div style={{ padding: '6px 12px', minHeight: 20 }}>
        {methods.length === 0 ? (
          <div style={{ opacity: 0.4, fontSize: 10 }}>— нет методов —</div>
        ) : (
          methods.map((m, i) => (
            <div key={i} style={{ fontSize: 11, lineHeight: '18px' }}>
              {m}()
            </div>
          ))
        )}
      </div>

      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
    </div>
  );
};

export default memo(ClassNode);
