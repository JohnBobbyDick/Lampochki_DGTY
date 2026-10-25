export interface StoredProjectFile {
  id: string;
  name: string;
  folder: string;
  path: string;
  code: string;
  original: string;
  language: 'java' | 'python';
  isExample?: boolean;
}

export interface ProjectStorageData {
  version: 1;
  files: StoredProjectFile[];
  folders?: string[];
  deletedExampleIds?: string[];
  activeJavaId?: string;
  activePythonId?: string;
  openJavaIds?: string[];
  openPythonIds?: string[];
}

export const DB_NAME = 'jb';
export const STORE_NAME = 'project';
export const PROJECT_KEY = 'jb.project.v1';

function getIdbFactory(): IDBFactory | undefined {
  if (typeof indexedDB !== 'undefined') return indexedDB;
  if (typeof window !== 'undefined' && window.indexedDB) return window.indexedDB;
  return undefined;
}

export function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const idb = getIdbFactory();
    if (!idb) {
      return reject(new Error('IndexedDB is not available'));
    }
    try {
      const req = idb.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME);
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error || new Error('Failed to open IndexedDB'));
      req.onblocked = () => reject(new Error('IndexedDB open blocked'));
    } catch (err) {
      reject(err);
    }
  });
}

export async function saveProject(data: ProjectStorageData): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    try {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const store = tx.objectStore(STORE_NAME);
      const req = store.put(data, PROJECT_KEY);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error || new Error('Failed to write to IndexedDB'));
      tx.onabort = () => reject(tx.error || new Error('IndexedDB transaction aborted'));
      tx.onerror = () => reject(tx.error || new Error('IndexedDB transaction error'));
    } catch (err) {
      reject(err);
    }
  });
}

export async function loadProject(): Promise<ProjectStorageData | null> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    try {
      const tx = db.transaction(STORE_NAME, 'readonly');
      const store = tx.objectStore(STORE_NAME);
      const req = store.get(PROJECT_KEY);
      req.onsuccess = () => resolve((req.result as ProjectStorageData) ?? null);
      req.onerror = () => reject(req.error || new Error('Failed to read from IndexedDB'));
      tx.onabort = () => reject(tx.error || new Error('IndexedDB transaction aborted'));
      tx.onerror = () => reject(tx.error || new Error('IndexedDB transaction error'));
    } catch (err) {
      reject(err);
    }
  });
}

export async function clearProject(): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    try {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      const store = tx.objectStore(STORE_NAME);
      const req = store.delete(PROJECT_KEY);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error || new Error('Failed to delete from IndexedDB'));
      tx.onabort = () => reject(tx.error || new Error('IndexedDB transaction aborted'));
      tx.onerror = () => reject(tx.error || new Error('IndexedDB transaction error'));
    } catch (err) {
      reject(err);
    }
  });
}

export function isValidProjectData(data: unknown): data is ProjectStorageData {
  if (!data || typeof data !== 'object') return false;
  const d = data as Record<string, unknown>;
  if (!Array.isArray(d.files)) return false;
  for (const f of d.files) {
    if (!f || typeof f !== 'object') return false;
    const file = f as Record<string, unknown>;
    if (typeof file.id !== 'string' || !file.id) return false;
    if (typeof file.name !== 'string' || !file.name) return false;
    if (typeof file.folder !== 'string') return false;
    if (typeof file.code !== 'string') return false;
    if (typeof file.original !== 'string') return false;
    if (file.language !== 'java' && file.language !== 'python') return false;
  }
  return true;
}

export function mergeWithBuiltinExamples<T extends { id: string; isExample?: boolean; path?: string }>(
  savedFiles: T[],
  builtinFiles: T[],
  deletedExampleIds: string[] = []
): T[] {
  const deletedSet = new Set(deletedExampleIds);
  const userMap = new Map<string, T>();
  for (const f of savedFiles) {
    userMap.set(f.id, f);
  }

  const result: T[] = [];

  // Keep existing user files (preserving user modifications)
  for (const f of savedFiles) {
    result.push({
      ...f,
      path: f.path || f.id,
      isExample: f.isExample ?? builtinFiles.some((b) => b.id === f.id),
    });
  }

  // Add new builtin examples that user hasn't explicitly deleted and doesn't already have
  for (const b of builtinFiles) {
    if (deletedSet.has(b.id)) continue;
    if (!userMap.has(b.id)) {
      result.push(b);
    }
  }

  return result;
}
