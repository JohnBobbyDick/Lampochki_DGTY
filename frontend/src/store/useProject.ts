import { create } from 'zustand';
import { useStore } from './useStore';
import { DEMO, DEMO_PY, EXAMPLES } from '../project/examples';
import { pushRun, RunRecord } from '../utils/runs';
import { languageOf } from '../utils/language';
import { Coverage, Probe, mergeCoverage } from '../utils/coverage';

export interface ProjectFile {
  id: string; // "folder/Name.ext"
  name: string;
  folder: string;
  code: string; // last saved editor content (the active file's live text is in useStore.code)
  original: string; // content as loaded, used for the "modified" marker and Reset
  language: 'java' | 'python';
}

interface ProjectState {
  files: ProjectFile[];
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
  init: () => void;
}

const mk = (folder: string, name: string, code: string): ProjectFile => ({
  id: `${folder}/${name}`,
  name,
  folder,
  code,
  original: code,
  language: languageOf(name),
});

const DEMO_JAVA_ID = 'src/Demo.java';
const DEMO_PY_ID = 'src/Demo.py';

const INITIAL: ProjectFile[] = [
  mk('src', 'Demo.java', DEMO),
  mk('src', 'Demo.py', DEMO_PY),
  ...EXAMPLES.map((e) => mk('examples', e.name, e.code)),
];

/** Copy the editor's live text into the active file before switching away */
const saved = (files: ProjectFile[], activeId: string) => {
  const live = useStore.getState().code;
  return files.map((f) => (f.id === activeId ? { ...f, code: live } : f));
};

export const useProject = create<ProjectState>((set, get) => ({
  files: INITIAL,
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
  },

  switchLanguage: (lang) => {
    const s = get();
    const curLang = useStore.getState().language;
    if (curLang === lang && (lang === 'python' ? s.activeId.endsWith('.py') : s.activeId.endsWith('.java'))) {
      return;
    }

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

    const file = mk('src', unique, text);
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
  },

  init: () => {
    const s = get();
    if (useStore.getState().code) return;
    const lang = useStore.getState().language;
    const targetId = lang === 'python' ? s.activePythonId : s.activeJavaId;
    const f = s.files.find((x) => x.id === targetId);
    if (f) {
      useStore.getState().loadDocument(f.code, f.original, lang);
    }
  },
}));

/* editing the active file invalidates its coverage (line numbers and probes no longer match) */
useStore.subscribe((st, prev) => {
  if (st.code === prev.code) return;
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
