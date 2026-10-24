import { create } from 'zustand';
import { useStore } from './useStore';
import { DEMO, DEMO_PY, EXAMPLES } from '../project/examples';

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
  language: name.endsWith('.py') ? 'python' : 'java',
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
