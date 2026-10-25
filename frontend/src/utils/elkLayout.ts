import ELK, { ElkNode, ElkExtendedEdge } from 'elkjs/lib/elk.bundled.js';
import { Node, Edge, MarkerType } from 'reactflow';
import { GraphNode, GraphEdge } from '../types';

const elk = new ELK();

export const EDGE_COLOR: Record<string, string> = {
  normal: '#8a8a8a',
  true: '#22a55b',
  false: '#e5534b',
  back: '#4f8ef7',
  exception: '#e5534b',
  extends: '#9b7af0',
  implements: '#9b7af0',
};

export const EDGE_LABEL: Record<string, string> = {
  true: 'да',
  false: 'нет',
  back: 'повтор',
};

export const getNodeSize = (n: GraphNode): { width: number; height: number } => {
  if (n.type === 'class' || n.type === 'interface') {
    return {
      width: 280,
      height: 64 + 12 * 2 + 18 * (Math.max(1, n.data.fields?.length ?? 0) + Math.max(1, n.data.methods?.length ?? 0)),
    };
  }
  if (n.type === 'method') {
    return { width: 170, height: 90 };
  }
  if (n.type.startsWith('stream-')) {
    return { width: 220, height: 46 + 18 * Math.ceil((n.label?.length ?? 0) / 26) };
  }
  return { width: 220, height: 70 };
};

export function pointsToSvgPath(points: { x: number; y: number }[]): string {
  if (!points || points.length === 0) return '';
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
}

export async function layoutGraph(
  graphNodes: GraphNode[],
  graphEdges: GraphEdge[],
  direction: 'TB' | 'LR' = 'TB'
): Promise<{ nodes: Node[]; edges: Edge[] }> {
  if (graphNodes.length === 0) {
    return { nodes: [], edges: [] };
  }

  const isLR = direction === 'LR';

  const elkNodes: ElkNode[] = graphNodes.map((n) => {
    const { width, height } = getNodeSize(n);
    return {
      id: n.id,
      width,
      height,
      ports: [
        {
          id: `${n.id}_in`,
          layoutOptions: { 'elk.port.side': isLR ? 'WEST' : 'NORTH' },
        },
        {
          id: `${n.id}_out`,
          layoutOptions: { 'elk.port.side': isLR ? 'EAST' : 'SOUTH' },
        },
        {
          id: `${n.id}_back_in`,
          layoutOptions: { 'elk.port.side': isLR ? 'NORTH' : 'WEST' },
        },
        {
          id: `${n.id}_back_out`,
          layoutOptions: { 'elk.port.side': isLR ? 'SOUTH' : 'WEST' },
        },
      ],
    };
  });

  const elkEdges: ElkExtendedEdge[] = graphEdges.map((e) => {
    const isBack = e.type === 'back';
    const labelText = isBack ? undefined : (e.label && (EDGE_LABEL[e.label] ?? e.label)) || undefined;
    return {
      id: e.id,
      sources: [e.source],
      targets: [e.target],
      sourcePort: isBack ? `${e.source}_back_out` : `${e.source}_out`,
      targetPort: isBack ? `${e.target}_back_in` : `${e.target}_in`,
      labels: labelText
        ? [
            {
              id: `${e.id}_lbl`,
              text: labelText,
              width: 30,
              height: 18,
            },
          ]
        : undefined,
    };
  });

  const rootNode: ElkNode = {
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': isLR ? 'RIGHT' : 'DOWN',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
      'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
      'elk.spacing.nodeNode': '40',
      'elk.layered.spacing.nodeNodeBetweenLayers': '60',
      'elk.layered.spacing.edgeNodeBetweenLayers': '30',
      'elk.layered.spacing.edgeEdgeBetweenLayers': '20',
      'elk.layered.cycleBreaking.strategy': 'DEPTH_FIRST',
    },
    children: elkNodes,
    edges: elkEdges,
  };

  const layoutedRoot = await elk.layout(rootNode);

  const nodeMap = new Map<string, ElkNode>();
  layoutedRoot.children?.forEach((child) => {
    nodeMap.set(child.id, child);
  });

  const nodes: Node[] = graphNodes.map((n) => {
    const elkChild = nodeMap.get(n.id);
    const { width, height } = getNodeSize(n);
    return {
      id: n.id,
      type: n.type,
      position: {
        x: elkChild?.x ?? 0,
        y: elkChild?.y ?? 0,
      },
      data: { label: n.label, ...n.data, nodeType: n.type, width, height },
    };
  });

  const edgeMap = new Map<string, ElkExtendedEdge>();
  layoutedRoot.edges?.forEach((edge) => {
    edgeMap.set(edge.id, edge);
  });

  const edges: Edge[] = graphEdges.map((e) => {
    const elkEdge = edgeMap.get(e.id);
    const color = EDGE_COLOR[e.type] ?? EDGE_COLOR.normal;
    const isBack = e.type === 'back';
    const label = isBack ? undefined : (e.label && (EDGE_LABEL[e.label] ?? e.label)) || undefined;

    const points: { x: number; y: number }[] = [];
    if (elkEdge?.sections) {
      for (const sec of elkEdge.sections) {
        if (points.length === 0 && sec.startPoint) {
          points.push({ x: sec.startPoint.x, y: sec.startPoint.y });
        }
        if (sec.bendPoints) {
          for (const bp of sec.bendPoints) {
            points.push({ x: bp.x, y: bp.y });
          }
        }
        if (sec.endPoint) {
          points.push({ x: sec.endPoint.x, y: sec.endPoint.y });
        }
      }
    }

    let labelPos: { x: number; y: number } | undefined;
    if (
      elkEdge?.labels &&
      elkEdge.labels.length > 0 &&
      elkEdge.labels[0].x !== undefined &&
      elkEdge.labels[0].y !== undefined
    ) {
      labelPos = { x: elkEdge.labels[0].x, y: elkEdge.labels[0].y };
    } else if (points.length >= 2) {
      labelPos = {
        x: (points[0].x + points[1].x) / 2,
        y: (points[0].y + points[1].y) / 2,
      };
    }

    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label,
      animated: isBack,
      type: 'labeled',
      data: {
        color,
        points,
        labelPos,
      },
      style: {
        stroke: color,
        strokeWidth: 1.6,
        strokeDasharray: ['back', 'exception', 'implements'].includes(e.type) ? '6 4' : undefined,
      },
      markerEnd: { type: MarkerType.ArrowClosed, color },
    };
  });

  return { nodes, edges };
}
