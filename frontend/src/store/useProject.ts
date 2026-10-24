import { create } from 'zustand';
import { useStore } from './useStore';
import { DEMO, EXAMPLES } from '../project/examples';
import { pushRun, RunRecord } from '../utils/runs';
import { Coverage, Probe, mergeCoverage } from '../utils/coverage';

export interface ProjectFile {
  id: string;        // "folder/Name.java"
  name: string;
  folder: string;
  code: string;      // last saved editor content (the active file's live text is in useStore.code)
  original: string;  // content as loaded, used for the "modified" marker and Reset
}

interface ProjectState {
  files: ProjectFile[];
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
  addFile: (name: string, text: string) => void;
  init: () => void;
}

const mk = (folder: string, name: string, code: string): ProjectFile => ({ id: `${folder}/${name}`, name, folder, code, original: code });

const INITIAL: ProjectFile[] = [
  mk('src', 'Demo.java', DEMO),
  ...EXAMPLES.map((e) => mk('examples', e.name, e.code)),
];
const DEMO_ID = 'src/Demo.java';

/** copy the editor's live text into the active file before switching away */
const saved = (files: ProjectFile[], activeId: string) => {
  const live = useStore.getState().code;
  return files.map((f) => (f.id === activeId ? { ...f, code: live } : f));
};

export const useProject = create<ProjectState>((set, get) => ({
  files: INITIAL,
  activeId: DEMO_ID,
  openIds: [DEMO_ID],
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
    set({ files, activeId: id, openIds: s.openIds.includes(id) ? s.openIds : [...s.openIds, id] });
    useStore.getState().loadDocument(target.code, target.original);
  },

  close: (id) => {
    const s = get();
    if (s.openIds.length <= 1) return;
    const idx = s.openIds.indexOf(id);
    const openIds = s.openIds.filter((x) => x !== id);
    if (id !== s.activeId) { set({ openIds }); return; }
    const files = saved(s.files, s.activeId);
    const nextId = openIds[Math.min(idx, openIds.length - 1)];
    const target = files.find((f) => f.id === nextId)!;
    set({ files, openIds, activeId: nextId });
    useStore.getState().loadDocument(target.code, target.original);
  },

  addFile: (name, text) => {
    const s = get();
    const files = saved(s.files, s.activeId);
    const same = files.find((f) => f.id === `src/${name}`);
    if (same && same.code === text) { get().open(same.id); return; }
    /* never overwrite an existing file (and its edits): pick "Name (2).java" instead */
    let unique = name;
    for (let n = 2; files.some((f) => f.id === `src/${unique}`); n++) unique = name.replace(/(\.java)?$/, ` (${n})$1`);
    const file = mk('src', unique, text);
    set({ files: [...files, file], activeId: file.id, openIds: [...s.openIds, file.id] });
    useStore.getState().loadDocument(text, text);
  },

  /** first start: put the demo file into the editor */
  init: () => {
    if (useStore.getState().code) return;
    const f = get().files.find((x) => x.id === get().activeId);
    if (f) useStore.getState().loadDocument(f.code, f.original);
  },
}));

/* editing the active file invalidates its coverage (line numbers and probes no longer match) */
useStore.subscribe((st, prev) => {
  if (st.code === prev.code) return;
  const { activeId, coverage } = useProject.getState();
  const c = coverage[activeId];
  if (!c || c.code === st.code) return;
  const { [activeId]: _c, ...rest } = coverage;
  useProject.setState((s) => ({ coverage: rest, coverageReset: { ...s.coverageReset, [activeId]: true } }));
});
