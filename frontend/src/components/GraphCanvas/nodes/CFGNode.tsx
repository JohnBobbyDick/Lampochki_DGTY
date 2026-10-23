import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { useStore } from '../../../store/useStore';

const COLOR_MAP: Record<string, string> = {
  start: '#2d6a4f',
  end: '#9d0208',
  condition: '#b5851e',
  loop: '#1d3557',
  try: '#5e548e',
  catch: '#774c60',
  finally: '#5e548e',
  switch: '#b5851e',
  return: '#9d0208',
  throw: '#9d0208',
  statement: '#3a3a3c',
};

const CFGNode: React.FC<NodeProps> = ({ id, data }) => {
  const hoveredNode = useStore((s) => s.hoveredNode);
  const setHoveredNode = useStore((s) => s.setHoveredNode);
  const setHoveredLine = useStore((s) => s.setHoveredLine);
  const hoveredLine = useStore((s) => s.hoveredLine);
  const isHovered = hoveredNode === id || (hoveredLine != null && data.lineStart === hoveredLine);
  const nodeType: string = data.nodeType ?? 'statement';
  const bg = COLOR_MAP[nodeType] ?? COLOR_MAP.statement;

  const tooltip = [
    `${nodeType}${data.lineStart ? ` · строка ${data.lineStart}` : ''}`,
    data.bigO ? `Big O: ${data.bigO}` : '',
    ...((data.defects as string[] | undefined) ?? []).map((d) => `⚠ ${d}`),
    'двойной клик — редактировать',
  ].filter(Boolean).join('\n');
  const hasDefect = ((data.defects as string[] | undefined) ?? []).length > 0;

  return (
    <div
      title={tooltip}
      style={{
        background: bg,
        border: isHovered ? '2px solid #007acc' : hasDefect ? '2px solid #e5c07b' : '2px solid transparent',
        borderRadius: nodeType === 'condition' || nodeType === 'switch' ? 4 : 8,
        padding: '8px 14px',
        color: '#e0e0e0',
        fontSize: 12,
        fontFamily: "'JetBrains Mono', Consolas, monospace",
        minWidth: 140,
        maxWidth: 220,
        textAlign: 'center',
        boxShadow: isHovered ? '0 0 12px rgba(0,122,204,.6)' : '0 2px 6px rgba(0,0,0,.4)',
        transition: 'border .15s, box-shadow .15s',
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

      <div
        style={{
          fontSize: 10,
          textTransform: 'uppercase',
          letterSpacing: 1,
          opacity: 0.7,
          marginBottom: 4,
        }}
      >
        {nodeType}
      </div>
      <div style={{ wordBreak: 'break-word' }}>{data.label as string}</div>
      {data.bigO && (
        <span
          style={{
            position: 'absolute',
            top: -8,
            right: -8,
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

export default memo(CFGNode);
