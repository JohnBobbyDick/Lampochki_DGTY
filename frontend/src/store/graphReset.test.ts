import { describe, it, expect, beforeEach } from 'vitest';
import { useStore } from './useStore';
import { useProject } from './useProject';

/** state left behind by a Java file whose method was picked in the graph */
const javaLeftovers = () => useStore.setState({
  selectedMethod: 'Demo.sumPairs',
  methods: ['Demo.sumPairs', 'Demo.main'],
  ast: { classes: [] } as never,
  nodes: [{ id: 'n0', position: { x: 0, y: 0 }, data: {} }],
  edges: [{ id: 'e0', source: 'n0', target: 'n0' }],
  graphError: 'старая ошибка',
});

const expectFresh = () => {
  const s = useStore.getState();
  expect(s.language).toBe('python');
  expect(s.selectedMethod).toBeNull();
  expect(s.methods).toEqual([]);
  expect(s.ast).toBeNull();
  expect(s.nodes).toEqual([]);
  expect(s.edges).toEqual([]);
  expect(s.graphError).toBeNull();
};

describe('switching file or language resets the graph state', () => {
  beforeEach(() => {
    useProject.getState().switchLanguage('java');
    useProject.getState().open('src/Demo.java');
    javaLeftovers();
  });

  it('opening a Python file drops the Java method, methods, AST and graph', () => {
    useProject.getState().open('examples/analyzer.py');
    expectFresh();
  });

  it('switching the language in the header does the same', () => {
    useProject.getState().switchLanguage('python');
    expectFresh();
  });
});
