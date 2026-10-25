import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { useStore } from './useStore';
import {
  useProject,
  INITIAL,
  DEMO_JAVA_ID,
  setInitializedForTests,
  resetStorageWarningState,
  flushProjectSave,
} from './useProject';
import {
  PROJECT_KEY,
  mergeWithBuiltinExamples,
  isValidProjectData,
  ProjectStorageData,
} from '../utils/projectStorage';

class FakeIDBRequest {
  result: any;
  error: any = null;
  onsuccess: any = null;
  onerror: any = null;
  onblocked: any = null;
  onupgradeneeded: any = null;
}

function createFakeIndexedDB(initialData: Record<string, any> = {}) {
  const store = new Map<string, any>(Object.entries(initialData));
  let failOpen = false;
  let failWrite = false;
  let failRead = false;

  return {
    setFailOpen: (val: boolean) => { failOpen = val; },
    setFailWrite: (val: boolean) => { failWrite = val; },
    setFailRead: (val: boolean) => { failRead = val; },
    getRawStore: () => store,
    open: (_name: string, _version?: number) => {
      const req = new FakeIDBRequest();
      setTimeout(() => {
        if (failOpen) {
          req.error = new DOMException('SecurityError', 'SecurityError');
          req.onerror?.({ target: req });
          return;
        }
        const db = {
          objectStoreNames: {
            contains: (_s: string) => true,
          },
          createObjectStore: (_s: string) => {},
          transaction: (_stores: any, _mode: string) => {
            const tx: any = {
              onabort: null,
              onerror: null,
              objectStore: (_name: string) => ({
                get: (key: string) => {
                  const r = new FakeIDBRequest();
                  setTimeout(() => {
                    if (failRead) {
                      r.error = new DOMException('Read failed', 'UnknownError');
                      r.onerror?.({ target: r });
                    } else {
                      r.result = store.get(key);
                      r.onsuccess?.({ target: r });
                    }
                  }, 0);
                  return r;
                },
                put: (val: any, key: string) => {
                  const r = new FakeIDBRequest();
                  setTimeout(() => {
                    if (failWrite) {
                      r.error = new DOMException('QuotaExceededError', 'QuotaExceededError');
                      r.onerror?.({ target: r });
                      tx.onerror?.({ target: tx });
                    } else {
                      store.set(key, JSON.parse(JSON.stringify(val)));
                      r.onsuccess?.({ target: r });
                    }
                  }, 0);
                  return r;
                },
                delete: (key: string) => {
                  const r = new FakeIDBRequest();
                  setTimeout(() => {
                    store.delete(key);
                    r.onsuccess?.({ target: r });
                  }, 0);
                  return r;
                },
              }),
            };
            return tx;
          },
        };
        req.result = db;
        req.onupgradeneeded?.({ target: req });
        req.onsuccess?.({ target: req });
      }, 0);
      return req;
    },
  };
}

describe('Block C1: Browser Project Storage (IndexedDB)', () => {
  let fakeIdb: ReturnType<typeof createFakeIndexedDB>;

  beforeEach(() => {
    fakeIdb = createFakeIndexedDB();
    vi.stubGlobal('indexedDB', fakeIdb);
    resetStorageWarningState();
    useStore.setState({
      code: '',
      language: 'java',
      storageWarning: null,
    });
    useProject.setState({
      files: INITIAL,
      folders: ['src', 'examples'],
      deletedExampleIds: [],
      activeId: DEMO_JAVA_ID,
      activeJavaId: DEMO_JAVA_ID,
      openIds: [DEMO_JAVA_ID],
      openJavaIds: [DEMO_JAVA_ID],
    });
    setInitializedForTests(true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('saves project to IndexedDB under jb.project.v1 including live code from useStore', async () => {
    useStore.setState({ code: '// LIVE EDITOR CODE' });
    await flushProjectSave();

    const raw = fakeIdb.getRawStore().get(PROJECT_KEY) as ProjectStorageData;
    expect(raw).toBeDefined();
    expect(raw.version).toBe(1);
    expect(Array.isArray(raw.files)).toBe(true);

    const activeSaved = raw.files.find((f) => f.id === DEMO_JAVA_ID);
    expect(activeSaved).toBeDefined();
    expect(activeSaved?.code).toBe('// LIVE EDITOR CODE');
    expect(activeSaved?.path).toBe(DEMO_JAVA_ID);
    expect(activeSaved?.folder).toBe('src');
    expect(activeSaved?.name).toBe('Demo.java');
  });

  it('loads and restores saved project on init', async () => {
    const savedData: ProjectStorageData = {
      version: 1,
      files: [
        {
          id: DEMO_JAVA_ID,
          name: 'Demo.java',
          folder: 'src',
          path: DEMO_JAVA_ID,
          code: '// RESTORED MODIFIED CODE',
          original: '// ORIGINAL DEMO CODE',
          language: 'java',
          isExample: true,
        },
      ],
      folders: ['src', 'examples'],
      deletedExampleIds: [],
      activeJavaId: DEMO_JAVA_ID,
      openJavaIds: [DEMO_JAVA_ID],
    };
    fakeIdb.getRawStore().set(PROJECT_KEY, savedData);

    await useProject.getState().init();

    expect(useProject.getState().files.find((f) => f.id === DEMO_JAVA_ID)?.code).toBe('// RESTORED MODIFIED CODE');
    expect(useStore.getState().code).toBe('// RESTORED MODIFIED CODE');
  });

  it('corrupted data in storage gracefully falls back to standard examples', async () => {
    // Corrupted data: files is not an array
    fakeIdb.getRawStore().set(PROJECT_KEY, { version: 1, files: 'not-an-array' });

    expect(isValidProjectData({ version: 1, files: 'not-an-array' })).toBe(false);

    await useProject.getState().init();

    // Still has initial files, app doesn't crash
    expect(useProject.getState().files.length).toBeGreaterThan(0);
    expect(useProject.getState().files.some((f) => f.id === DEMO_JAVA_ID)).toBe(true);
  });

  it('unavailable storage (private mode / blocked) works in memory and shows single warning', async () => {
    fakeIdb.setFailOpen(true);

    await useProject.getState().init();

    // App functions in memory
    expect(useProject.getState().files.length).toBeGreaterThan(0);
    expect(useStore.getState().storageWarning).toBe('Изменения не сохранятся после перезагрузки');
  });

  it('storage quota exceeded shows single unobtrusive warning', async () => {
    fakeIdb.setFailWrite(true);

    await flushProjectSave();

    expect(useStore.getState().storageWarning).toBe('Изменения не сохранятся после перезагрузки');
  });

  it('mergeWithBuiltinExamples preserves user modifications, respects deleted examples, and adds new examples', () => {
    const userFiles = [
      {
        id: 'src/Demo.java',
        name: 'Demo.java',
        folder: 'src',
        path: 'src/Demo.java',
        code: '// USER EDITED DEMO',
        original: '// ORIGINAL',
        language: 'java' as const,
      },
    ];

    const builtins = [
      {
        id: 'src/Demo.java',
        name: 'Demo.java',
        folder: 'src',
        path: 'src/Demo.java',
        code: '// SERVER DEFAULT DEMO',
        original: '// SERVER DEFAULT DEMO',
        language: 'java' as const,
      },
      {
        id: 'examples/Deleted.java',
        name: 'Deleted.java',
        folder: 'examples',
        path: 'examples/Deleted.java',
        code: '// SERVER DELETED',
        original: '// SERVER DELETED',
        language: 'java' as const,
      },
      {
        id: 'examples/NewBuiltin.java',
        name: 'NewBuiltin.java',
        folder: 'examples',
        path: 'examples/NewBuiltin.java',
        code: '// BRAND NEW BUILTIN',
        original: '// BRAND NEW BUILTIN',
        language: 'java' as const,
      },
    ];

    const deletedExampleIds = ['examples/Deleted.java'];

    const merged = mergeWithBuiltinExamples(userFiles, builtins, deletedExampleIds);

    // 1. User edited Demo.java is preserved
    const demo = merged.find((f) => f.id === 'src/Demo.java');
    expect(demo?.code).toBe('// USER EDITED DEMO');

    // 2. Deleted example is NOT re-added
    expect(merged.some((f) => f.id === 'examples/Deleted.java')).toBe(false);

    // 3. New builtin example is added
    expect(merged.some((f) => f.id === 'examples/NewBuiltin.java')).toBe(true);
  });
});
