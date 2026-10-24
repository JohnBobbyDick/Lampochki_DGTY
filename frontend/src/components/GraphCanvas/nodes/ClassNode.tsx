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
      data-kind={isInterface ? 'iface' : 'class'}
      className={`g-node g-class ${isHovered ? 'is-hover' : ''}`}
      onMouseEnter={() => setHoveredNode(id)}
      onMouseLeave={() => setHoveredNode(null)}
    >
      <Handle type="target" position={Position.Top} />
      <div className="g-class-head">
        <span className="g-stereo">{isInterface ? '«interface»' : isAbstract ? '«abstract»' : 'class'}</span>
        <span className={`g-class-name ${isAbstract ? 'abstract' : ''}`}>{displayName}</span>
      </div>
      <div className="g-class-sec">
        {fields.length === 0
          ? <div className="g-empty">нет полей</div>
          : fields.map((f, i) => <div key={i} className="g-member" title={f}>{f}</div>)}
      </div>
      <div className="g-class-sec">
        {methods.length === 0
          ? <div className="g-empty">нет методов</div>
          : methods.map((m, i) => { const sig = m.includes('(') ? m : `${m}()`; return <div key={i} className="g-member" title={sig}>{sig}</div>; })}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

export default memo(ClassNode);
