import React from 'react';
import { BaseEdge, EdgeLabelRenderer, EdgeProps, getSmoothStepPath } from 'reactflow';

/**
 * Smooth-step edge whose label sits right above the node it leads into,
 * so "да / нет" never lands on a segment shared with other edges.
 */
const LabeledEdge: React.FC<EdgeProps> = ({
  id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, markerEnd, label, data,
}) => {
  const [path] = getSmoothStepPath({
    sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 10, offset: data?.offset ?? 20,
  });
  return (
    <>
      <BaseEdge id={id} path={path} style={style} markerEnd={markerEnd} />
      {label && (
        <EdgeLabelRenderer>
          <div className="g-edge-label nodrag nopan"
               style={{ transform: `translate(-50%, -100%) translate(${targetX}px, ${targetY - 10}px)`, color: data?.color }}>
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
};

export default LabeledEdge;
