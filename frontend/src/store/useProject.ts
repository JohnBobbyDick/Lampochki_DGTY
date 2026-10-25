import { create } from 'zustand';
import { useStore } from './useStore';
import { DEMO, DEMO_PY, EXAMPLES } from '../project/examples';
import { pushRun, RunRecord } from '../utils/runs';
import { languageOf } from '../utils/language';
import { Coverage, Probe, mergeCoverage } from '../utils/coverage';
import {
  saveProject,
  loadProject,
  isValidProjectData,
  mergeWithBuiltinExamples,
  ProjectStorageData,
} from '../utils/projectStorage';
import {
  validateFileName,
  validateFolderName,
  ValidationResult,
} from '../utils/fileValidation';

export interface ProjectFile {
  id: string; // "folder/Name.ext"
  name: string;
  folder: string;
  path: string;
  code: string; // last saved editor content (the active file's live text is in useStore.code)
  original: string; // content as loaded, used for the "modified" marker and Reset
  language: 'java' | 'python';
  isExample?: boolean;
}

interface ProjectState {
  files: ProjectFile[];
  folders: string[];
  deletedExampleIds: string[];
  activeJavaId: string;
  activePythonId: string;
  openJavaIds: string[];
  openPythonIds: string[];

  // Active file and open tabs for the currently selected language
  activeId: string;
  openIds: string[];
  /** last runs per file id (in memory), for the previous-vs-last comparison */
  runs: Record<string, RunRecord[]>;
  recordRun: (r: RunRecord, fileId?: string) => void;
  /** accumulated coverage per file id (valid only for the text it was collected on) */
  coverage: Record<string, Coverage>;
  coverageError: Record<string, string | null>;
  /** coverage was dropped because the code was edited */
  coverageReset: Record<string, boolean>;
  recordCoverage: (fileId: string, code: string, probes: Probe[], hits: number[]) => void;
  setCoverageError: (fileId: string, error: string) => void;
  resetCoverage: (fileId: string) => void;
  open: (id: string) => void;
  close: (id: string) => void;
  switchLanguage: (lang: 'java' | 'python') => void;
  addFile: (name: string, text: string) => void;
  createFile: (folder: string, name: string, code?: string) => ValidationResult;
  createFolder: (parentFolder: string, name: string) => ValidationResult;
  renameFile: (oldId: string, newName: string) => ValidationResult;
  renameFolder: (oldFolder: string, newName: string) => ValidationResult;
  deleteFile: (id: string) => void;
  deleteFolder: (folder: string) => void;
  resetFile: (id: string) => void;
  restoreExamples: () => void;
  init: () => Promise<void>;
}

const mk = (folder: string, name: string, code: string, isExample = true): ProjectFile => {
  const path = folder ? `${folder}/${name}` : name;
  return {
    id: path,
    name,
    folder,
    path,
    code,
    original: code,
    language: languageOf(name),
    isExample,
  };
};

export const DEMO_JAVA_ID = 'src/Demo.java';
export const DEMO_PY_ID = 'src/Demo.py';

export const INITIAL: ProjectFile[] = [
  mk('src', 'Demo.java', DEMO),
  mk('src', 'Demo.py', DEMO_PY),
  ...EXAMPLES.map((e) => mk('examples', e.name, e.code)),
];

/** Copy the editor's live text into the active file before switching away */
const saved = (files: ProjectFile[], activeId: string) => {
  const live = useStore.getState().code;
  return files.map((f) => (f.id === activeId ? { ...f, code: live } : f));
};

let isInitialized = false;
let saveTimeout: ReturnType<typeof setTimeout> | null = null;
let storageWarned = false;

export function setInitializedForTests(val: boolean) {
  isInitialized = val;
}

export function resetStorageWarningState() {
  storageWarned = false;
}

export function cancelScheduledSave() {
  if (saveTimeout) {
    clearTimeout(saveTimeout);
    saveTimeout = null;
  }
}

export function scheduleProjectSave() {
  if (!isInitialized) return;
  if (saveTimeout) {
    clearTimeout(saveTimeout);
  }
  saveTimeout = setTimeout(async () => {
    await flushProjectSave();
  }, 500);
}

export async function flushProjectSave(): Promise<void> {
  if (saveTimeout) {
    clearTimeout(saveTimeout);
    saveTimeout = null;
  }
  try {
    const proj = useProject.getState();
    const liveCode = useStore.getState().code;
    const files = proj.files.map((f) =>
      f.id === proj.activeId ? { ...f, code: liveCode } : f
    );
    const data: ProjectStorageData = {
      version: 1,
      files: files.map((f) => ({
        id: f.id,
        name: f.name,
        folder: f.folder,
        path: f.path || f.id,
        code: f.code,
        original: f.original,
        language: f.language,
        isExample: f.isExample,
      })),
      folders: proj.folders,
      deletedExampleIds: proj.deletedExampleIds,
      activeJavaId: proj.activeJavaId,
      activePythonId: proj.activePythonId,
      openJavaIds: proj.openJavaIds,
      openPythonIds: proj.openPythonIds,
    };
    await saveProject(data);
  } catch {
    if (!storageWarned) {
      storageWarned = true;
      useStore.getState().setStorageWarning('Изменения не сохранятся после перезагрузки');
    }
  }
}

export const useProject = create<ProjectState>((set, get) => ({
  files: INITIAL,
  folders: ['src', 'examples'],
  deletedExampleIds: [],
  activeJavaId: DEMO_JAVA_ID,
  activePythonId: DEMO_PY_ID,
  openJavaIds: [DEMO_JAVA_ID],
  openPythonIds: [DEMO_PY_ID],
  activeId: DEMO_JAVA_ID,
  openIds: [DEMO_JAVA_ID],
  runs: {},
  coverage: {},
  coverageError: {},
  coverageReset: {},

  recordCoverage: (fileId, code, probes, hits) => set((s) => {
    const current = fileId === s.activeId
      ? useStore.getState().code
      : s.files.find((f) => f.id === fileId)?.code;
    if (current !== code) return { coverageReset: { ...s.coverageReset, [fileId]: true } };
    return {
      coverage: { ...s.coverage, [fileId]: mergeCoverage(s.coverage[fileId], code, probes, hits) },
      coverageError: { ...s.coverageError, [fileId]: null },
      coverageReset: { ...s.coverageReset, [fileId]: false },
    };
  }),

  setCoverageError: (fileId, error) => set((s) => ({ coverageError: { ...s.coverageError, [fileId]: error } })),

  resetCoverage: (fileId) => set((s) => {
    const { [fileId]: _c, ...coverage } = s.coverage;
    const { [fileId]: _e, ...coverageError } = s.coverageError;
    const { [fileId]: _r, ...coverageReset } = s.coverageReset;
    return { coverage, coverageError, coverageReset };
  }),

  recordRun: (r, fileId) => set((s) => ({ runs: pushRun(s.runs, fileId ?? s.activeId, r) })),

  open: (id) => {
    const s = get();
    if (id === s.activeId) return;
    const files = saved(s.files, s.activeId);
    const target = files.find((f) => f.id === id);
    if (!target) return;

    const isPy = target.language === 'python';
    const lang: 'java' | 'python' = isPy ? 'python' : 'java';

    const openJavaIds = !isPy && !s.openJavaIds.includes(id) ? [...s.openJavaIds, id] : s.openJavaIds;
    const openPythonIds = isPy && !s.openPythonIds.includes(id) ? [...s.openPythonIds, id] : s.openPythonIds;
    const activeJavaId = !isPy ? id : s.activeJavaId;
    const activePythonId = isPy ? id : s.activePythonId;

    set({
      files,
      activeJavaId,
      activePythonId,
      openJavaIds,
      openPythonIds,
      activeId: id,
      openIds: isPy ? openPythonIds : openJavaIds,
    });

    useStore.getState().loadDocument(target.code, target.original, lang);
    scheduleProjectSave();
  },

  close: (id) => {
    const s = get();
    const isPy = id.endsWith('.py');
    const curOpen = isPy ? s.openPythonIds : s.openJavaIds;
    if (curOpen.length <= 1) return;

    const idx = curOpen.indexOf(id);
    const nextOpen = curOpen.filter((x) => x !== id);
    const files = saved(s.files, s.activeId);

    const isActive = id === (isPy ? s.activePythonId : s.activeJavaId);
    const nextActiveId = isActive
      ? nextOpen[Math.min(idx, nextOpen.length - 1)]
      : isPy
      ? s.activePythonId
      : s.activeJavaId;

    const openJavaIds = isPy ? s.openJavaIds : nextOpen;
    const openPythonIds = isPy ? nextOpen : s.openPythonIds;
    const activeJavaId = isPy ? s.activeJavaId : nextActiveId;
    const activePythonId = isPy ? nextActiveId : s.activePythonId;

    const curLang = useStore.getState().language;
    const currentIsActiveLang = (curLang === 'python') === isPy;

    set({
      files,
      openJavaIds,
      openPythonIds,
      activeJavaId,
      activePythonId,
      activeId: curLang === 'python' ? activePythonId : activeJavaId,
      openIds: curLang === 'python' ? openPythonIds : openJavaIds,
    });

    if (isActive && currentIsActiveLang) {
      const target = files.find((f) => f.id === nextActiveId);
      if (target) {
        useStore.getState().loadDocument(target.code, target.original, curLang);
      }
    }
    scheduleProjectSave();
  },

  switchLanguage: (lang) => {
    const s = get();
    const curLang = useStore.getState().language;
    if (curLang === lang && (lang === 'python' ? s.activeId.endsWith('.py') : s.activeId.endsWith('.java'))) {
      return;
    }

    useStore.getState().setShowGraph(false);

    const files = saved(s.files, s.activeId);
    const targetId = lang === 'python' ? s.activePythonId : s.activeJavaId;
    const target = files.find((f) => f.id === targetId) || files.find((f) => f.language === lang);
    if (!target) return;

    set({
      files,
      activeId: target.id,
      openIds: lang === 'python' ? s.openPythonIds : s.openJavaIds,
      ...(lang === 'python' ? { activePythonId: target.id } : { activeJavaId: target.id }),
    });

    useStore.getState().loadDocument(target.code, target.original, lang);
    scheduleProjectSave();
  },

  addFile: (name, text) => {
    const s = get();
    const files = saved(s.files, s.activeId);
    const isPy = name.endsWith('.py');
    const lang: 'java' | 'python' = isPy ? 'python' : 'java';

    const same = files.find((f) => f.id === `src/${name}`);
    if (same && same.code === text) {
      get().open(same.id);
      return;
    }

    let unique = name;
    const extMatch = name.match(/(\.[a-zA-Z0-9]+)$/);
    const ext = extMatch ? extMatch[1] : '';
    const base = ext ? name.slice(0, -ext.length) : name;
    for (let n = 2; files.some((f) => f.id === `src/${unique}`); n++) {
      unique = `${base} (${n})${ext}`;
    }

    const file = mk('src', unique, text, false);
    const updatedFiles = [...files, file];

    const openJavaIds = !isPy ? [...s.openJavaIds, file.id] : s.openJavaIds;
    const openPythonIds = isPy ? [...s.openPythonIds, file.id] : s.openPythonIds;
    const activeJavaId = !isPy ? file.id : s.activeJavaId;
    const activePythonId = isPy ? file.id : s.activePythonId;

    set({
      files: updatedFiles,
      openJavaIds,
      openPythonIds,
      activeJavaId,
      activePythonId,
      activeId: file.id,
      openIds: isPy ? openPythonIds : openJavaIds,
    });

    useStore.getState().loadDocument(text, text, lang);
    scheduleProjectSave();
  },

  createFile: (folder, name, code = '') => {
    const s = get();
    const existing = s.files.filter((f) => f.folder === folder).map((f) => f.name);
    const v = validateFileName(name, existing);
    if (v.error) return v;

    const id = folder ? `${folder}/${name}` : name;
    const lang = languageOf(name);
    const newFile: ProjectFile = {
      id,
      name,
      folder,
      path: id,
      code,
      original: code,
      language: lang,
      isExample: false,
    };

    const isPy = lang === 'python';
    const openJavaIds = !isPy ? [...s.openJavaIds, id] : s.openJavaIds;
    const openPythonIds = isPy ? [...s.openPythonIds, id] : s.openPythonIds;
    const activeJavaId = !isPy ? id : s.activeJavaId;
    const activePythonId = isPy ? id : s.activePythonId;

    const folders = s.folders.includes(folder) ? s.folders : [...s.folders, folder];

    set({
      files: [...s.files, newFile],
      folders,
      openJavaIds,
      openPythonIds,
      activeJavaId,
      activePythonId,
      activeId: id,
      openIds: isPy ? openPythonIds : openJavaIds,
    });

    useStore.getState().setLanguage(lang);
    useStore.getState().loadDocument(code, code, lang);
    scheduleProjectSave();
    return v;
  },

  createFolder: (parentFolder, name) => {
    const s = get();
    const targetPath = parentFolder ? `${parentFolder}/${name}` : name;
    const existingInParent = s.folders
      .filter((f) => {
        const parent = f.includes('/') ? f.slice(0, f.lastIndexOf('/')) : '';
        return parent === parentFolder;
      })
      .map((f) => (f.includes('/') ? f.slice(f.lastIndexOf('/') + 1) : f));

    const v = validateFolderName(name, existingInParent);
    if (v.error) return v;

    set({
      folders: Array.from(new Set([...s.folders, targetPath])),
    });
    scheduleProjectSave();
    return v;
  },

  renameFile: (oldId, newName) => {
    const s = get();
    const file = s.files.find((f) => f.id === oldId);
    if (!file) return { error: 'Файл не найден' };

    if (file.name === newName) return {};

    const existing = s.files
      .filter((f) => f.folder === file.folder && f.id !== oldId)
      .map((f) => f.name);
    const v = validateFileName(newName, existing);
    if (v.error) return v;

    const newId = file.folder ? `${file.folder}/${newName}` : newName;
    const newLang = languageOf(newName);
    const oldLang = file.language;
    const langChanged = oldLang !== newLang;

    const updatedFiles = s.files.map((f) =>
      f.id === oldId
        ? { ...f, id: newId, name: newName, path: newId, language: newLang }
        : f
    );

    // Migrate runs and coverage
    const runs = { ...s.runs };
    if (runs[oldId]) {
      runs[newId] = runs[oldId];
      delete runs[oldId];
    }

    const coverage = { ...s.coverage };
    if (coverage[oldId]) {
      coverage[newId] = coverage[oldId];
      delete coverage[oldId];
    }

    const coverageError = { ...s.coverageError };
    if (coverageError[oldId] !== undefined) {
      coverageError[newId] = coverageError[oldId];
      delete coverageError[oldId];
    }

    const coverageReset = { ...s.coverageReset };
    if (coverageReset[oldId] !== undefined) {
      coverageReset[newId] = coverageReset[oldId];
      delete coverageReset[oldId];
    }

    // Migrate tabs and active file
    let openJavaIds = [...s.openJavaIds];
    let openPythonIds = [...s.openPythonIds];
    let activeJavaId = s.activeJavaId;
    let activePythonId = s.activePythonId;
    let activeId = s.activeId;

    if (langChanged) {
      if (newLang === 'python') {
        openJavaIds = openJavaIds.filter((x) => x !== oldId);
        if (!openPythonIds.includes(newId)) openPythonIds.push(newId);
        if (activeJavaId === oldId) {
          activeJavaId = openJavaIds[0] || '';
        }
        activePythonId = newId;
      } else {
        openPythonIds = openPythonIds.filter((x) => x !== oldId);
        if (!openJavaIds.includes(newId)) openJavaIds.push(newId);
        if (activePythonId === oldId) {
          activePythonId = openPythonIds[0] || '';
        }
        activeJavaId = newId;
      }
    } else {
      openJavaIds = openJavaIds.map((x) => (x === oldId ? newId : x));
      openPythonIds = openPythonIds.map((x) => (x === oldId ? newId : x));
      if (activeJavaId === oldId) activeJavaId = newId;
      if (activePythonId === oldId) activePythonId = newId;
    }

    if (activeId === oldId) {
      activeId = newId;
      if (langChanged) {
        useStore.getState().setLanguage(newLang);
      }
    }

    const curLang = useStore.getState().language;

    set({
      files: updatedFiles,
      runs,
      coverage,
      coverageError,
      coverageReset,
      openJavaIds,
      openPythonIds,
      activeJavaId,
      activePythonId,
      activeId,
      openIds: curLang === 'python' ? openPythonIds : openJavaIds,
    });

    scheduleProjectSave();
    return v;
  },

  renameFolder: (oldFolder, newName) => {
    const s = get();
    if (!s.folders.includes(oldFolder)) return { error: 'Папка не найдена' };

    const parent = oldFolder.includes('/') ? oldFolder.slice(0, oldFolder.lastIndexOf('/')) : '';
    const existingInParent = s.folders
      .filter((f) => {
        const p = f.includes('/') ? f.slice(0, f.lastIndexOf('/')) : '';
        return p === parent && f !== oldFolder;
      })
      .map((f) => (f.includes('/') ? f.slice(f.lastIndexOf('/') + 1) : f));

    const v = validateFolderName(newName, existingInParent);
    if (v.error) return v;

    const newFolder = parent ? `${parent}/${newName}` : newName;
    if (newFolder === oldFolder) return {};

    const prefix = `${oldFolder}/`;

    const updatedFolders = s.folders.map((f) => {
      if (f === oldFolder) return newFolder;
      if (f.startsWith(prefix)) return `${newFolder}/${f.slice(prefix.length)}`;
      return f;
    });

    const runs = { ...s.runs };
    const coverage = { ...s.coverage };
    const coverageError = { ...s.coverageError };
    const coverageReset = { ...s.coverageReset };

    const remapId = (id: string) => {
      if (id.startsWith(prefix)) {
        return `${newFolder}/${id.slice(prefix.length)}`;
      }
      return id;
    };

    const updatedFiles = s.files.map((f) => {
      if (f.folder === oldFolder) {
        const nextId = `${newFolder}/${f.name}`;
        if (runs[f.id]) { runs[nextId] = runs[f.id]; delete runs[f.id]; }
        if (coverage[f.id]) { coverage[nextId] = coverage[f.id]; delete coverage[f.id]; }
        if (coverageError[f.id] !== undefined) { coverageError[nextId] = coverageError[f.id]; delete coverageError[f.id]; }
        if (coverageReset[f.id] !== undefined) { coverageReset[nextId] = coverageReset[f.id]; delete coverageReset[f.id]; }
        return { ...f, folder: newFolder, id: nextId, path: nextId };
      }
      if (f.folder.startsWith(prefix)) {
        const sub = f.folder.slice(prefix.length);
        const nextFolder = `${newFolder}/${sub}`;
        const nextId = `${nextFolder}/${f.name}`;
        if (runs[f.id]) { runs[nextId] = runs[f.id]; delete runs[f.id]; }
        if (coverage[f.id]) { coverage[nextId] = coverage[f.id]; delete coverage[f.id]; }
        if (coverageError[f.id] !== undefined) { coverageError[nextId] = coverageError[f.id]; delete coverageError[f.id]; }
        if (coverageReset[f.id] !== undefined) { coverageReset[nextId] = coverageReset[f.id]; delete coverageReset[f.id]; }
        return { ...f, folder: nextFolder, id: nextId, path: nextId };
      }
      return f;
    });

    const openJavaIds = s.openJavaIds.map(remapId);
    const openPythonIds = s.openPythonIds.map(remapId);
    const activeJavaId = remapId(s.activeJavaId);
    const activePythonId = remapId(s.activePythonId);
    const activeId = remapId(s.activeId);

    set({
      folders: updatedFolders,
      files: updatedFiles,
      runs,
      coverage,
      coverageError,
      coverageReset,
      openJavaIds,
      openPythonIds,
      activeJavaId,
      activePythonId,
      activeId,
      openIds: useStore.getState().language === 'python' ? openPythonIds : openJavaIds,
    });

    scheduleProjectSave();
    return v;
  },

  deleteFile: (id) => {
    const s = get();
    const file = s.files.find((f) => f.id === id);
    if (!file) return;

    const isPy = file.language === 'python';
    const curOpen = isPy ? s.openPythonIds : s.openJavaIds;
    const nextOpen = curOpen.filter((x) => x !== id);

    const deletedExampleIds = file.isExample || INITIAL.some((init) => init.id === id)
      ? Array.from(new Set([...s.deletedExampleIds, id]))
      : s.deletedExampleIds;

    const nextFiles = s.files.filter((f) => f.id !== id);
    const isActive = id === (isPy ? s.activePythonId : s.activeJavaId);

    const idx = curOpen.indexOf(id);
    const nextActiveId = isActive
      ? nextOpen.length > 0
        ? nextOpen[Math.min(idx, nextOpen.length - 1)]
        : nextFiles.find((f) => (isPy ? f.language === 'python' : f.language === 'java'))?.id || ''
      : isPy
      ? s.activePythonId
      : s.activeJavaId;

    const openJavaIds = isPy ? s.openJavaIds : nextOpen;
    const openPythonIds = isPy ? nextOpen : s.openPythonIds;
    const activeJavaId = isPy ? s.activeJavaId : nextActiveId;
    const activePythonId = isPy ? nextActiveId : s.activePythonId;

    const curLang = useStore.getState().language;
    const currentIsActiveLang = (curLang === 'python') === isPy;

    set({
      files: nextFiles,
      deletedExampleIds,
      openJavaIds,
      openPythonIds,
      activeJavaId,
      activePythonId,
      activeId: curLang === 'python' ? activePythonId : activeJavaId,
      openIds: curLang === 'python' ? openPythonIds : openJavaIds,
    });

    if (isActive && currentIsActiveLang) {
      if (nextActiveId) {
        const target = nextFiles.find((f) => f.id === nextActiveId);
        if (target) {
          useStore.getState().loadDocument(target.code, target.original, curLang);
        }
      } else {
        useStore.getState().loadDocument('', '', curLang);
      }
    }

    scheduleProjectSave();
  },

  deleteFolder: (folderPath) => {
    const s = get();
    const prefix = `${folderPath}/`;
    const isInside = (f: { folder: string }) => f.folder === folderPath || f.folder.startsWith(prefix);

    const filesToDelete = s.files.filter(isInside);
    for (const f of filesToDelete) {
      get().deleteFile(f.id);
    }

    set((state) => ({
      folders: state.folders.filter((fd) => fd !== folderPath && !fd.startsWith(prefix)),
    }));

    scheduleProjectSave();
  },

  resetFile: (id: string) => {
    const s = get();
    const f = s.files.find((x) => x.id === id);
    if (!f) return;
    const nextFiles = s.files.map((x) => (x.id === id ? { ...x, code: f.original } : x));
    set({ files: nextFiles });
    if (id === s.activeId) {
      useStore.getState().replaceCode(f.original);
    }
    scheduleProjectSave();
  },

  restoreExamples: () => {
    const s = get();
    const userFiles = s.files.filter((f) => !INITIAL.some((init) => init.id === f.id));
    const nextFiles = [...INITIAL, ...userFiles];
    set({
      files: nextFiles,
      deletedExampleIds: [],
    });
    const active = nextFiles.find((f) => f.id === s.activeId);
    if (active) {
      useStore.getState().loadDocument(active.code, active.original, active.language);
    }
    scheduleProjectSave();
  },

  init: async () => {
    isInitialized = false;
    try {
      const savedData = await loadProject();
      if (savedData && isValidProjectData(savedData)) {
        const mergedFiles = mergeWithBuiltinExamples(
          savedData.files,
          INITIAL,
          savedData.deletedExampleIds || []
        );
        const folders = Array.from(
          new Set(['src', 'examples', ...(savedData.folders || []), ...mergedFiles.map((f) => f.folder)])
        ).filter(Boolean);

        const javaFiles = mergedFiles.filter((f) => f.language === 'java');
        const pyFiles = mergedFiles.filter((f) => f.language === 'python');

        const activeJavaId =
          savedData.activeJavaId && javaFiles.some((f) => f.id === savedData.activeJavaId)
            ? savedData.activeJavaId
            : javaFiles[0]?.id || DEMO_JAVA_ID;

        const activePythonId =
          savedData.activePythonId && pyFiles.some((f) => f.id === savedData.activePythonId)
            ? savedData.activePythonId
            : pyFiles[0]?.id || DEMO_PY_ID;

        const openJavaIds = (savedData.openJavaIds || [activeJavaId]).filter((id) =>
          javaFiles.some((f) => f.id === id)
        );
        if (openJavaIds.length === 0 && activeJavaId) openJavaIds.push(activeJavaId);

        const openPythonIds = (savedData.openPythonIds || [activePythonId]).filter((id) =>
          pyFiles.some((f) => f.id === id)
        );
        if (openPythonIds.length === 0 && activePythonId) openPythonIds.push(activePythonId);

        const lang = useStore.getState().language;
        const isPy = lang === 'python';
        const activeId = isPy ? activePythonId : activeJavaId;
        const openIds = isPy ? openPythonIds : openJavaIds;

        set({
          files: mergedFiles,
          folders,
          deletedExampleIds: savedData.deletedExampleIds || [],
          activeJavaId,
          activePythonId,
          openJavaIds,
          openPythonIds,
          activeId,
          openIds,
        });

        const activeFile = mergedFiles.find((f) => f.id === activeId);
        if (activeFile) {
          useStore.getState().loadDocument(activeFile.code, activeFile.original, lang);
        }
      } else {
        const s = get();
        const lang = useStore.getState().language;
        const targetId = lang === 'python' ? s.activePythonId : s.activeJavaId;
        const f = s.files.find((x) => x.id === targetId);
        if (f) {
          useStore.getState().loadDocument(f.code, f.original, lang);
        }
      }
    } catch {
      if (!storageWarned) {
        storageWarned = true;
        useStore.getState().setStorageWarning('Изменения не сохранятся после перезагрузки');
      }
      const s = get();
      const lang = useStore.getState().language;
      const targetId = lang === 'python' ? s.activePythonId : s.activeJavaId;
      const f = s.files.find((x) => x.id === targetId);
      if (f) {
        useStore.getState().loadDocument(f.code, f.original, lang);
      }
    } finally {
      isInitialized = true;
    }
  },
}));

/* editing the active file invalidates its coverage and schedules saving to IndexedDB */
useStore.subscribe((st, prev) => {
  if (st.code === prev.code) return;
  scheduleProjectSave();

  const { activeId, coverage } = useProject.getState();
  const c = coverage[activeId];
  if (!c || c.code === st.code) return;
  const { [activeId]: _c, ...rest } = coverage;
  useProject.setState((s) => ({
    coverage: rest,
    coverageError: { ...s.coverageError, [activeId]: null },
    coverageReset: { ...s.coverageReset, [activeId]: true },
  }));
});
