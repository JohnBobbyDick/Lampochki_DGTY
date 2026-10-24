import { describe, it, expect, beforeEach } from 'vitest';
import { useStore } from './useStore';

const patch = (oldCode: string) => ({ oldCode, newCode: 'x', explanation: '' }) as never;

describe('pruneStale', () => {
  beforeEach(() => useStore.setState({ ai: null, aiReview: null, reviewSkip: '' }));

  it('removes review items whose fragment is gone', () => {
    useStore.setState({
      aiReview: { title: 't', text: '', source: 's', items: [
        { patch: patch('int a = 1;') }, { patch: patch('int b = 2;') },
      ] as never },
    });
    useStore.getState().pruneStale('int a = 1;');
    expect(useStore.getState().aiReview?.items).toHaveLength(1);
  });

  it('nulls ai.patch when its fragment is gone', () => {
    useStore.setState({ ai: { title: 't', text: '', source: 's', patch: patch('int a = 1;') } });
    useStore.getState().pruneStale('int c = 3;');
    expect(useStore.getState().ai?.patch).toBeNull();
  });

  it('keeps ai.patch while the fragment is present', () => {
    useStore.setState({ ai: { title: 't', text: '', source: 's', patch: patch('int a = 1;') } });
    useStore.getState().pruneStale('int a = 1;');
    expect(useStore.getState().ai?.patch).not.toBeNull();
  });

  it('keeps ai untouched when code equals reviewSkip', () => {
    useStore.setState({ ai: { title: 't', text: '', source: 's', patch: patch('int a = 1;') }, reviewSkip: 'int z;' });
    useStore.getState().pruneStale('int z;');
    expect(useStore.getState().ai?.patch).not.toBeNull();
  });
});
