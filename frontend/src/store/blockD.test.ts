import { describe, expect, it } from 'vitest';
import { layoutGraph, getNodeSize, pointsToSvgPath } from '../utils/elkLayout';
import { GraphNode, GraphEdge } from '../types';

describe('Block D: ELK Layered Graph Layout', () => {
  const sampleNodes: GraphNode[] = [
    {
      id: 'n0',
      type: 'start',
      label: 'start',
      data: { lineStart: 1, lineEnd: 1, codeSnippet: 'start' },
    },
    {
      id: 'n1',
      type: 'condition',
      label: 'if (x > 0)',
      data: { lineStart: 2, lineEnd: 2, codeSnippet: 'if (x > 0)' },
    },
    {
      id: 'n2',
      type: 'statement',
      label: 'x++',
      data: { lineStart: 3, lineEnd: 3, codeSnippet: 'x++' },
    },
    {
      id: 'n3',
      type: 'end',
      label: 'end',
      data: { lineStart: 4, lineEnd: 4, codeSnippet: 'end' },
    },
  ];

  const sampleEdges: GraphEdge[] = [
    { id: 'e0', source: 'n0', target: 'n1', type: 'normal', label: '' },
    { id: 'e1', source: 'n1', target: 'n2', type: 'true', label: 'true' },
    { id: 'e2', source: 'n1', target: 'n3', type: 'false', label: 'false' },
    { id: 'e3', source: 'n2', target: 'n1', type: 'back', label: 'back' },
  ];

  it('layout is deterministic (same input produces identical positions and points)', async () => {
    const layout1 = await layoutGraph(sampleNodes, sampleEdges, 'TB');
    const layout2 = await layoutGraph(sampleNodes, sampleEdges, 'TB');

    expect(layout1.nodes.length).toBe(sampleNodes.length);
    expect(layout2.nodes.length).toBe(sampleNodes.length);

    for (let i = 0; i < layout1.nodes.length; i++) {
      expect(layout1.nodes[i].id).toBe(layout2.nodes[i].id);
      expect(layout1.nodes[i].position.x).toBe(layout2.nodes[i].position.x);
      expect(layout1.nodes[i].position.y).toBe(layout2.nodes[i].position.y);
    }

    for (let i = 0; i < layout1.edges.length; i++) {
      expect(layout1.edges[i].id).toBe(layout2.edges[i].id);
      expect(layout1.edges[i].data.points).toEqual(layout2.edges[i].data.points);
    }
  });

  it('all edges have route points with at least startPoint and endPoint', async () => {
    const { edges } = await layoutGraph(sampleNodes, sampleEdges, 'TB');

    expect(edges.length).toBe(sampleEdges.length);
    for (const edge of edges) {
      expect(edge.data).toBeDefined();
      expect(Array.isArray(edge.data.points)).toBe(true);
      expect(edge.data.points.length).toBeGreaterThanOrEqual(2);
      for (const pt of edge.data.points) {
        expect(typeof pt.x).toBe('number');
        expect(typeof pt.y).toBe('number');
        expect(Number.isFinite(pt.x)).toBe(true);
        expect(Number.isFinite(pt.y)).toBe(true);
      }
    }
  });

  it('edge labels are placed on segments rather than nodes', async () => {
    const { edges } = await layoutGraph(sampleNodes, sampleEdges, 'TB');

    const trueEdge = edges.find((e) => e.id === 'e1');
    expect(trueEdge).toBeDefined();
    expect(trueEdge?.label).toBe('да');
    expect(trueEdge?.data.labelPos).toBeDefined();
    expect(typeof trueEdge?.data.labelPos.x).toBe('number');
    expect(typeof trueEdge?.data.labelPos.y).toBe('number');

    const falseEdge = edges.find((e) => e.id === 'e2');
    expect(falseEdge).toBeDefined();
    expect(falseEdge?.label).toBe('нет');
    expect(falseEdge?.data.labelPos).toBeDefined();
  });

  it('supports TB direction (downwards) and LR direction (rightwards)', async () => {
    const tb = await layoutGraph(sampleNodes, sampleEdges, 'TB');
    const lr = await layoutGraph(sampleNodes, sampleEdges, 'LR');

    // In TB, Y generally increases from start to end
    const tbStart = tb.nodes.find((n) => n.id === 'n0')!;
    const tbEnd = tb.nodes.find((n) => n.id === 'n3')!;
    expect(tbEnd.position.y).toBeGreaterThan(tbStart.position.y);

    // In LR, X generally increases from start to end
    const lrStart = lr.nodes.find((n) => n.id === 'n0')!;
    const lrEnd = lr.nodes.find((n) => n.id === 'n3')!;
    expect(lrEnd.position.x).toBeGreaterThan(lrStart.position.x);
  });

  it('preserves node dimensions for different node types', () => {
    const classNode: GraphNode = {
      id: 'c1',
      type: 'class',
      label: 'Demo',
      data: { lineStart: 1, lineEnd: 10, codeSnippet: '', fields: ['f1', 'f2'], methods: ['m1', 'm2'] },
    };
    const methodNode: GraphNode = {
      id: 'm1',
      type: 'method',
      label: 'sum()',
      data: { lineStart: 2, lineEnd: 5, codeSnippet: '' },
    };
    const streamNode: GraphNode = {
      id: 's1',
      type: 'stream-filter',
      label: 'filter(x -> x > 0)',
      data: { lineStart: 3, lineEnd: 3, codeSnippet: '' },
    };

    expect(getNodeSize(classNode).width).toBe(280);
    expect(getNodeSize(classNode).height).toBeGreaterThan(100);
    expect(getNodeSize(methodNode)).toEqual({ width: 170, height: 90 });
    expect(getNodeSize(streamNode).width).toBe(220);
  });

  it('pointsToSvgPath generates valid SVG path data', () => {
    const points = [
      { x: 10, y: 20 },
      { x: 10, y: 50 },
      { x: 80, y: 50 },
    ];
    const path = pointsToSvgPath(points);
    expect(path).toBe('M 10 20 L 10 50 L 80 50');
  });
});
