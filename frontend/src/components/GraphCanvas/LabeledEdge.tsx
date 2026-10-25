import React from 'react';
import { BaseEdge, EdgeLabelRenderer, EdgeProps, getSmoothStepPath } from 'reactflow';
import { pointsToSvgPath } from '../../utils/elkLayout';

/**
 * ELK-routed orthogonal edge that follows ELK sections and bend points.
 * Edge label sits on an edge segment rather than on top of any node.
 */
const LabeledEdge: React.FC<EdgeProps> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  label,
  data,
}) => {
  const points = data?.points;
  let path = '';
  if (points && points.length >= 2) {
    path = pointsToSvgPath(points);
  } else {
    const [smoothPath] = getSmoothStepPath({
      sourceX,
      sourceY,
      sourcePosition,
      targetX,
      targetY,
      targetPosition,
      borderRadius: 10,
      offset: data?.offset ?? 20,
    });
    path = smoothPath;
  }

  const labelPos = data?.labelPos;

  return (
    <>
      <BaseEdge id={id} path={path} style={style} markerEnd={markerEnd} />
      {label && labelPos && (
        <EdgeLabelRenderer>
          <div
            className="g-edge-label nodrag nopan"
            style={{
              transform: `translate(-50%, -50%) translate(${labelPos.x}px, ${labelPos.y}px)`,
              color: data?.color,
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
};

export default LabeledEdge;
