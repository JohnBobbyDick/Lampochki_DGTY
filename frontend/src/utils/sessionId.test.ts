import { afterEach, describe, expect, it, vi } from 'vitest';
import { getSessionId, resetSessionIdCache } from './sessionId';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function fakeStorage(init: Record<string, string> = {}) {
  const m = { ...init };
  return {
    getItem: (k: string) => (k in m ? m[k] : null),
    setItem: (k: string, v: string) => { m[k] = v; },
    m,
  };
}

afterEach(() => { vi.unstubAllGlobals(); resetSessionIdCache(); });

describe('getSessionId', () => {
  it('creates a UUID, stores it under jb.sid and reuses it', () => {
    const st = fakeStorage();
    vi.stubGlobal('sessionStorage', st);
    const id = getSessionId();
    expect(id).toMatch(UUID);
    expect(st.m['jb.sid']).toBe(id);
    expect(getSessionId()).toBe(id);
  });

  it('takes an existing id from sessionStorage (tab reload)', () => {
    const old = '11111111-2222-4333-8444-555555555555';
    vi.stubGlobal('sessionStorage', fakeStorage({ 'jb.sid': old }));
    expect(getSessionId()).toBe(old);
  });

  it('ignores a malformed stored id', () => {
    vi.stubGlobal('sessionStorage', fakeStorage({ 'jb.sid': 'junk' }));
    expect(getSessionId()).toMatch(UUID);
  });

  it('falls back to a stable in-memory id when storage throws', () => {
    vi.stubGlobal('sessionStorage', {
      getItem: () => { throw new Error('blocked'); },
      setItem: () => { throw new Error('blocked'); },
    });
    const id = getSessionId();
    expect(id).toMatch(UUID);
    expect(getSessionId()).toBe(id);
  });
});
