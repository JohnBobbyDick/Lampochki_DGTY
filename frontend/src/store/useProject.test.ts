import { describe, it, expect, beforeEach } from 'vitest';
import { useStore } from './useStore';
import { useProject } from './useProject';
import type { Probe } from '../utils/coverage';

const probes: Probe[] = [{ id: 0, kind: 'line', line: 1, method: 'A.m', label: '', outcomes: ['hit'], slot: 0 }];
const A = 'class A {}';
const B = 'class B {}';

describe('per-file coverage', () => {
  beforeEach(() => {
    useProject.setState({ coverage: {}, coverageError: {}, coverageReset: {} });
    useProject.getState().open('src/Demo.java');
    useStore.getState().loadDocument(A, A);
  });
  const id = () => useProject.getState().activeId;

  it('sums two runs of the same text', () => {
    useProject.getState().recordCoverage(id(), A, probes, [1]);
    useProject.getState().recordCoverage(id(), A, probes, [2]);
    const c = useProject.getState().coverage[id()];
    expect(c.runs).toBe(2);
    expect(c.hits).toEqual([3]);
  });

  it('drops coverage on edit and does not restore it when text returns', () => {
    useProject.getState().recordCoverage(id(), A, probes, [1]);
    useStore.getState().setCode(B);
    expect(useProject.getState().coverage[id()]).toBeUndefined();
    expect(useProject.getState().coverageReset[id()]).toBe(true);
    useStore.getState().setCode(A);
    expect(useProject.getState().coverage[id()]).toBeUndefined();
  });

  it('clears a stale coverage error on edit', () => {
    useProject.getState().recordCoverage(id(), A, probes, [1]);
    useProject.getState().setCoverageError(id(), 'старая причина');
    useStore.getState().setCode(B);
    expect(useProject.getState().coverageError[id()]).toBeNull();
    expect(useProject.getState().coverageReset[id()]).toBe(true);
  });

  it('ignores a run whose code differs from the current text', () => {
    useProject.getState().recordCoverage(id(), B, probes, [1]);
    expect(useProject.getState().coverage[id()]).toBeUndefined();
    expect(useProject.getState().coverageReset[id()]).toBe(true);
  });

  it('keeps coverage of a file after switching away and back', () => {
    const first = id();
    useProject.getState().recordCoverage(first, A, probes, [1]);
    useProject.getState().open('examples/' + useProject.getState().files.find((f) => f.folder === 'examples')!.name);
    expect(useProject.getState().coverage[first]).toBeDefined();
    useProject.getState().open(first);
    expect(useProject.getState().coverage[first]?.runs).toBe(1);
    expect(useProject.getState().coverageReset[first]).toBeFalsy();
  });

  it('resetCoverage clears everything and error keeps accumulated data', () => {
    useProject.getState().recordCoverage(id(), A, probes, [1]);
    useProject.getState().setCoverageError(id(), 'boom');
    expect(useProject.getState().coverage[id()]).toBeDefined();
    expect(useProject.getState().coverageError[id()]).toBe('boom');
    useProject.getState().resetCoverage(id());
    const s = useProject.getState();
    expect(s.coverage[id()]).toBeUndefined();
    expect(s.coverageError[id()]).toBeUndefined();
    expect(s.coverageReset[id()]).toBeUndefined();
  });
});
