import { create } from 'zustand';
import { Node, Edge } from 'reactflow';
import { fragmentPresent } from '../utils/fragment';
import { CompileError, Defect, RunResult, CompareResult, DecomposedFile, GraphType, QualityGateResult } from '../types';

export interface AiPatch {
  oldCode: string;
  newCode: string;
  imports: string[];
  startLine: number;
  endLine: number;
  valid: boolean;
  problems: string[];
  warnings: string[];
  bigoBefore?: Record<string, string>;
  bigoAfter?: Record<string, string>;
}

export interface AiItem {
  line: number | null;
  title: string;
  detail: string;
  example: string;
  patch?: AiPatch | null;
}

export interface AiAnswer {
  title: string;
  text: string;
  code?: string;
  source: string;
  note?: string;
  items?: AiItem[];
  patch?: AiPatch | null;
}

interface AppState {
  /* ── data ── */
  language: 'java' | 'python';
  code: string;
  originalCode: string;
  ast: unknown;
  methods: string[];
  syntaxErrors: string[];
  /** null = javac did not run (parser errors are the only signal) */
  compileErrors: CompileError[] | null;
  lineMap: Record<string, number>;
  showGraph: boolean;
  setShowGraph: (show: boolean) => void;
  toggleGraph: () => void;
  hasBottom: boolean;
  openBottom: () => void;
  graphType: GraphType;
  selectedMethod: string | null;
  /** why the last /graph request failed (shown in the empty graph), null if it succeeded */
  graphError: string | null;
  /** bumped by every loadDocument, so a load re-parses even when the text is unchanged */
  docNonce: number;
  nodes: Node[];
  edges: Edge[];
  defects: Defect[];
  bigo: Record<string, string>;
  hoveredLine: number | null;
  hoveredNode: string | null;
  runResult: RunResult | null;
  compareResult: CompareResult | null;
  /** bumped by the "Сравнить" button: asks the bottom panel to show the run comparison tab */
  compareTabNonce: number;
  openCompareTab: () => void;
  decomposition: DecomposedFile[] | null;
  decomposeWarnings: string[];
  gateResult: QualityGateResult | null;
  past: string[];
  future: string[];
  jumpTo: { line: number; ts: number } | null;
  editingNode: string | null;
  syncStatus: 'idle' | 'syncing' | 'error';
  stdin: string;
  runNonce: number;
  ai: AiAnswer | null;
  aiLoading: boolean;
  aiEnabled: boolean;
  aiAuto: boolean;
  aiReviewing: boolean;
  aiReview: AiAnswer | null;
  /** code the AI must not auto-review again (e.g. the result of an applied AI patch) */
  reviewSkip: string;
  isLoading: boolean;
  error: string | null;
  storageWarning: string | null;

  /* ── actions ── */
  setLanguage: (lang: 'java' | 'python') => void;
  setCode: (code: string) => void;
  setOriginalCode: (code: string) => void;
  setAst: (ast: unknown) => void;
  setMethods: (methods: string[]) => void;
  setSyntaxErrors: (errors: string[]) => void;
  setCompileErrors: (e: CompileError[] | null) => void;
  /** drop AI tips/patches whose fragment is no longer in `code` */
  pruneStale: (code: string) => void;
  setDecomposeWarnings: (w: string[]) => void;
  setGateResult: (r: QualityGateResult | null) => void;
  /** set code coming from outside the typing flow (upload / generate / undo) */
  replaceCode: (code: string) => void;
  /** open a different document: new code + baseline, clears undo history and per-document results */
  loadDocument: (code: string, original: string, lang?: 'java' | 'python') => void;
  snapshot: () => void;
  undo: () => void;
  redo: () => void;
  jumpToLine: (line: number) => void;
  setEditingNode: (id: string | null) => void;
  setSyncStatus: (s: 'idle' | 'syncing' | 'error') => void;
  setStdin: (s: string) => void;
  requestRun: () => void;
  setAi: (a: AiAnswer | null) => void;
  setAiLoading: (b: boolean) => void;
  setAiEnabled: (b: boolean) => void;
  setAiAuto: (b: boolean) => void;
  setAiReviewing: (b: boolean) => void;
  setAiReview: (a: AiAnswer | null) => void;
  setLineMap: (lineMap: Record<string, number>) => void;
  setGraphType: (graphType: GraphType) => void;
  setSelectedMethod: (method: string | null) => void;
  setGraphError: (graphError: string | null) => void;
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  setDefects: (defects: Defect[]) => void;
  setBigo: (bigo: Record<string, string>) => void;
  bigoAfterAi: Record<string, string>;
  setBigoAfterAi: (b: Record<string, string>) => void;
  setHoveredLine: (line: number | null) => void;
  setHoveredNode: (nodeId: string | null) => void;
  setRunResult: (result: RunResult | null) => void;
  setCompareResult: (result: CompareResult | null) => void;
  setDecomposition: (decomposition: DecomposedFile[] | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setStorageWarning: (warning: string | null) => void;
}

export const useStore = create<AppState>((set, get) => ({
  language: 'java',
  code: '',
  originalCode: '',
  ast: null,
  methods: [],
  syntaxErrors: [],
  compileErrors: null,
  lineMap: {},
  showGraph: (() => {
    try { return localStorage.getItem('jb.graph') !== '0'; } catch { return true; }
  })(),
  setShowGraph: (showGraph) => {
    try { localStorage.setItem('jb.graph', showGraph ? '1' : '0'); } catch { /* private mode */ }
    set({ showGraph });
  },
  toggleGraph: () => {
    const next = !get().showGraph;
    try { localStorage.setItem('jb.graph', next ? '1' : '0'); } catch { /* private mode */ }
    set({ showGraph: next });
  },
  hasBottom: false,
  openBottom: () => set({ hasBottom: true }),
  graphType: 'cfg',
  selectedMethod: null,
  graphError: null,
  docNonce: 0,
  nodes: [],
  edges: [],
  defects: [],
  bigo: {},
  bigoAfterAi: {},
  hoveredLine: null,
  hoveredNode: null,
  runResult: null,
  compareResult: null,
  compareTabNonce: 0,
  decomposition: null,
  decomposeWarnings: [],
  gateResult: null,
  past: [],
  future: [],
  jumpTo: null,
  editingNode: null,
  syncStatus: 'idle',
  stdin: '',
  runNonce: 0,
  ai: null,
  aiLoading: false,
  aiEnabled: false,
  aiAuto: (() => {
    try { return localStorage.getItem('jb.aiAuto') !== '0'; } catch { return true; }
  })(),
  aiReviewing: false,
  aiReview: null,
  reviewSkip: '',
  isLoading: false,
  error: null,

  setLanguage: (language) => set({ language }),
  setCode: (code) => set({ code }),
  setOriginalCode: (code) => set({ originalCode: code }),
  setAst: (ast) => set({ ast }),
  setMethods: (methods) => set({ methods }),
  setSyntaxErrors: (syntaxErrors) => set({ syntaxErrors }),
  setCompileErrors: (compileErrors) => set({ compileErrors }),
  pruneStale: (code) => {
    const { ai, aiReview, reviewSkip } = get();
    const pruneAnswer = (a: AiAnswer): AiAnswer => {
      let next = a;
      if (a.items) {
        const items = a.items.filter((it) => it.patch && fragmentPresent(code, it.patch.oldCode));
        if (items.length !== a.items.length) next = { ...next, items };
      }
      if (a.patch && !fragmentPresent(code, a.patch.oldCode)) next = { ...next, patch: null };
      return next;
    };
    // code that is exactly the result of an applied AI patch keeps its "applied" drawer (undo / check behaviour)
    const nextAi = ai && code !== reviewSkip ? pruneAnswer(ai) : ai;
    const nextReview = aiReview && pruneAnswer(aiReview);
    if (nextAi !== ai || nextReview !== aiReview) set({ ai: nextAi, aiReview: nextReview });
  },
  setDecomposeWarnings: (decomposeWarnings) => set({ decomposeWarnings }),
  setGateResult: (gateResult) => set((st) => ({ gateResult, hasBottom: gateResult ? true : st.hasBottom })),
  replaceCode: (code) => {
    get().snapshot();
    set({ code });
  },
  loadDocument: (code, original, lang) => {
    let detected = lang;
    if (!detected) {
      if (/^\s*(def|async\s+def)\s+\w+\s*\(/.test(code) || /__name__\s*==\s*['"]__main__['"]/.test(code)) {
        detected = 'python';
      } else {
        detected = 'java';
      }
    }
    set((st) => ({
      docNonce: st.docNonce + 1,
      code, originalCode: original, language: detected, past: [], future: [],
      runResult: null, compareResult: null, decomposition: null, gateResult: null,
      selectedMethod: null, ai: null, aiReview: null, stdin: '',
      compileErrors: null, syntaxErrors: [], defects: [], bigo: {},
      /* the previous file's AST, methods and graph must not be used for the new one until it is parsed */
      ast: null, methods: [], lineMap: {}, nodes: [], edges: [], graphError: null,
    }));
  },
  /** remember the current code in the undo stack (skips duplicates) */
  snapshot: () => {
    const { code, past } = get();
    if (past[past.length - 1] === code) return;
    set({ past: [...past.slice(-99), code], future: [] });
  },
  undo: () => {
    const { past, future, code } = get();
    if (!past.length) return;
    let i = past.length - 1;
    while (i >= 0 && past[i] === code) i--;
    if (i < 0) return;
    set({ code: past[i], past: past.slice(0, i), future: [code, ...future] });
  },
  redo: () => {
    const { past, future, code } = get();
    if (!future.length) return;
    set({ code: future[0], past: [...past, code], future: future.slice(1) });
  },
  jumpToLine: (line) => set({ jumpTo: { line, ts: Date.now() } }),
  setEditingNode: (editingNode) => set({ editingNode }),
  setSyncStatus: (syncStatus) => set({ syncStatus }),
  setStdin: (stdin) => set({ stdin }),
  setAi: (ai) => set({ ai }),
  setAiLoading: (aiLoading) => set({ aiLoading }),
  setAiEnabled: (aiEnabled) => set({ aiEnabled }),
  setAiAuto: (aiAuto) => {
    try { localStorage.setItem('jb.aiAuto', aiAuto ? '1' : '0'); } catch { /* private mode */ }
    set({ aiAuto });
  },
  setAiReviewing: (aiReviewing) => set({ aiReviewing }),
  setAiReview: (aiReview) => set({ aiReview }),
  requestRun: () => set((st) => ({ runNonce: st.runNonce + 1, compareResult: null, hasBottom: true })),
  setLineMap: (lineMap) => set({ lineMap }),
  setGraphType: (graphType) => set({ graphType }),
  setSelectedMethod: (method) => set({ selectedMethod: method }),
  setGraphError: (graphError) => set({ graphError }),
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  setDefects: (defects) => set({ defects }),
  setBigo: (bigo) => set({ bigo }),
  setBigoAfterAi: (bigoAfterAi) => set({ bigoAfterAi }),
  setHoveredLine: (line) => set({ hoveredLine: line }),
  setHoveredNode: (nodeId) => set({ hoveredNode: nodeId }),
  setRunResult: (result) => set({ runResult: result }),
  setCompareResult: (result) => set((st) => ({ compareResult: result, hasBottom: result ? true : st.hasBottom })),
  openCompareTab: () => set((st) => ({ compareTabNonce: st.compareTabNonce + 1, hasBottom: true })),
  setDecomposition: (decomposition) => set({ decomposition }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  storageWarning: null,
  setStorageWarning: (storageWarning) => set({ storageWarning }),
}));
