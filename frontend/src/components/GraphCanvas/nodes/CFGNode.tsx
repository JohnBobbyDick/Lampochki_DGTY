import React, { memo } from 'react';
import { Handle, Position, NodeProps } from 'reactflow';
import { FiAlertTriangle } from 'react-icons/fi';
import { useStore } from '../../../store/useStore';
import { classifyBigO } from '../../../utils/bigo';
import { CFG_KINDS } from './kinds';

const CFGNode: React.FC<NodeProps> = ({ id, data }) => {
  const hoveredNode = useStore((s) => s.hoveredNode);
  const setHoveredNode = useStore((s) => s.setHoveredNode);
  const setHoveredLine = useStore((s) => s.setHoveredLine);
  const hoveredLine = useStore((s) => s.hoveredLine);
  const isHovered = hoveredNode === id || (hoveredLine != null && data.lineStart === hoveredLine);
  const nodeType: string = data.nodeType ?? 'statement';
  const k = CFG_KINDS[nodeType] ?? CFG_KINDS.statement;
  const defects = (data.defects as string[] | undefined) ?? [];

  const tooltip = [
    `${k.label}${data.lineStart ? ` · строка ${data.lineStart}` : ''}`,
    data.bigO ? `Big O: ${data.bigO}` : '',
    ...defects.map((d) => `⚠ ${d}`),
    'двойной клик — редактировать',
  ].filter(Boolean).join('\n');

  return (
    <div
      title={tooltip}
      data-kind={k.kind}
      className={`g-node g-cfg ${isHovered ? 'is-hover' : ''} ${defects.length ? 'has-defect' : ''}`}
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
      <div className="g-kind">
        <i className="g-dot" />
        {k.label}
        {data.lineStart ? <span className="g-line">стр. {data.lineStart as number}</span> : null}
      </div>
      <div className="g-label">{data.label as string}</div>
      {defects.length > 0 && <span className="g-flag" aria-label="Есть дефект"><FiAlertTriangle /></span>}
      {data.bigO && <span className={`g-bigo ${classifyBigO(data.bigO as string).grade}`}>{data.bigO as string}</span>}
      <Handle type="source" position={Position.Bottom} />
      {/* side handles for loop back edges: the loop is drawn on the side facing away from the flow */}
      <Handle type="source" position={Position.Right} id="back-out-r" className="g-handle-side" style={{ top: '65%' }} />
      <Handle type="target" position={Position.Right} id="back-in-r" className="g-handle-side" style={{ top: '35%' }} />
      <Handle type="source" position={Position.Left} id="back-out-l" className="g-handle-side" style={{ top: '65%' }} />
      <Handle type="target" position={Position.Left} id="back-in-l" className="g-handle-side" style={{ top: '35%' }} />
    </div>
  );
};

export default memo(CFGNode);
