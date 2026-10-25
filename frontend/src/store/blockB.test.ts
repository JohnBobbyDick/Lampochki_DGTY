import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { useStore } from './useStore';
import { useProject } from './useProject';

function fakeStorage(init: Record<string, string> = {}) {
  const m = { ...init };
  return {
    getItem: (k: string) => (k in m ? m[k] : null),
    setItem: (k: string, v: string) => { m[k] = v; },
    clear: () => { Object.keys(m).forEach((k) => delete m[k]); },
    m,
  };
}

describe('Block B: UI improvements and state', () => {
  let storage: ReturnType<typeof fakeStorage>;

  beforeEach(() => {
    storage = fakeStorage();
    vi.stubGlobal('localStorage', storage);
    useStore.setState({
      showGraph: true,
      hasBottom: false,
      decomposition: null,
      gateResult: null,
      compareResult: null,
      runNonce: 0,
      compareTabNonce: 0,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('B2: showGraph', () => {
    it('defaults to true and toggles with persistence', () => {
      expect(useStore.getState().showGraph).toBe(true);

      useStore.getState().toggleGraph();
      expect(useStore.getState().showGraph).toBe(false);
      expect(storage.m['jb.graph']).toBe('0');

      useStore.getState().toggleGraph();
      expect(useStore.getState().showGraph).toBe(true);
      expect(storage.m['jb.graph']).toBe('1');
    });

    it('setShowGraph explicitly sets and persists state', () => {
      useStore.getState().setShowGraph(false);
      expect(useStore.getState().showGraph).toBe(false);
      expect(storage.m['jb.graph']).toBe('0');

      useStore.getState().setShowGraph(true);
      expect(useStore.getState().showGraph).toBe(true);
      expect(storage.m['jb.graph']).toBe('1');
    });
  });

  describe('B3: hasBottom appearance after first action', () => {
    it('is initially false', () => {
      expect(useStore.getState().hasBottom).toBe(false);
    });

    it('requestRun enables bottom panel', () => {
      useStore.getState().requestRun();
      expect(useStore.getState().hasBottom).toBe(true);
    });

    it('openCompareTab enables bottom panel', () => {
      useStore.getState().openCompareTab();
      expect(useStore.getState().hasBottom).toBe(true);
    });

    it('setCompareResult enables bottom panel if result provided', () => {
      useStore.getState().setCompareResult({
        before: { stdout: 'hi', stderr: '', exitCode: 0, durationMs: 10 },
        after: { stdout: 'hi', stderr: '', exitCode: 0, durationMs: 10 },
        diff: '',
        behaviorPreserved: true,
      });
      expect(useStore.getState().hasBottom).toBe(true);
    });

    it('setGateResult enables bottom panel if result provided', () => {
      useStore.getState().setGateResult({
        passed: true,
        details: {},
      });
      expect(useStore.getState().hasBottom).toBe(true);
    });
  });

  describe('B4: resetFile in useProject', () => {
    it('resets modified file to its original code', () => {
      const files = useProject.getState().files;
      const file = files[0];
      const origCode = file.original;

      // modify file
      useProject.setState({
        files: files.map((f) => (f.id === file.id ? { ...f, code: 'modified code' } : f)),
        activeId: file.id,
      });
      useStore.setState({ code: 'modified code', originalCode: origCode });

      expect(useProject.getState().files.find((f) => f.id === file.id)?.code).toBe('modified code');
      expect(useStore.getState().code).toBe('modified code');

      // reset file
      useProject.getState().resetFile(file.id);

      expect(useProject.getState().files.find((f) => f.id === file.id)?.code).toBe(origCode);
      expect(useStore.getState().code).toBe(origCode);
    });
  });
});
