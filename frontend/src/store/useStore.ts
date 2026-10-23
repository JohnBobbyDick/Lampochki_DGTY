import { create } from 'zustand';
import { Node, Edge } from 'reactflow';
import { Defect, RunResult, CompareResult, DecomposedFile, GraphType, QualityGateResult } from '../types';

export interface AiPatch {
  oldCode: string;
  newCode: string;
  imports: string[];
  startLine: number;
  endLine: number;
  valid: boolean;
  problems: string[];
  warnings: string[];
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
  code: string;
  originalCode: string;
  ast: unknown;
  methods: string[];
  syntaxErrors: string[];
  lineMap: Record<string, number>;
  graphType: GraphType;
  selectedMethod: string | null;
  nodes: Node[];
  edges: Edge[];
  defects: Defect[];
  bigo: Record<string, string>;
  hoveredLine: number | null;
  hoveredNode: string | null;
  runResult: RunResult | null;
  compareResult: CompareResult | null;
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
  isLoading: boolean;
  error: string | null;

  /* ── actions ── */
  setCode: (code: string) => void;
  setOriginalCode: (code: string) => void;
  setAst: (ast: unknown) => void;
  setMethods: (methods: string[]) => void;
  setSyntaxErrors: (errors: string[]) => void;
  setDecomposeWarnings: (w: string[]) => void;
  setGateResult: (r: QualityGateResult | null) => void;
  /** set code coming from outside the typing flow (upload / generate / undo) */
  replaceCode: (code: string) => void;
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
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  setDefects: (defects: Defect[]) => void;
  setBigo: (bigo: Record<string, string>) => void;
  setHoveredLine: (line: number | null) => void;
  setHoveredNode: (nodeId: string | null) => void;
  setRunResult: (result: RunResult | null) => void;
  setCompareResult: (result: CompareResult | null) => void;
  setDecomposition: (decomposition: DecomposedFile[] | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useStore = create<AppState>((set, get) => ({
  code: '',
  originalCode: '',
  ast: null,
  methods: [],
  syntaxErrors: [],
  lineMap: {},
  graphType: 'cfg',
  selectedMethod: null,
  nodes: [],
  edges: [],
  defects: [],
  bigo: {},
  hoveredLine: null,
  hoveredNode: null,
  runResult: null,
  compareResult: null,
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
  isLoading: false,
  error: null,

  setCode: (code) => set({ code }),
  setOriginalCode: (code) => set({ originalCode: code }),
  setAst: (ast) => set({ ast }),
  setMethods: (methods) => set({ methods }),
  setSyntaxErrors: (syntaxErrors) => set({ syntaxErrors }),
  setDecomposeWarnings: (decomposeWarnings) => set({ decomposeWarnings }),
  setGateResult: (gateResult) => set({ gateResult }),
  replaceCode: (code) => {
    get().snapshot();
    set({ code });
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
  requestRun: () => set((st) => ({ runNonce: st.runNonce + 1, compareResult: null })),
  setLineMap: (lineMap) => set({ lineMap }),
  setGraphType: (graphType) => set({ graphType }),
  setSelectedMethod: (method) => set({ selectedMethod: method }),
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  setDefects: (defects) => set({ defects }),
  setBigo: (bigo) => set({ bigo }),
  setHoveredLine: (line) => set({ hoveredLine: line }),
  setHoveredNode: (nodeId) => set({ hoveredNode: nodeId }),
  setRunResult: (result) => set({ runResult: result }),
  setCompareResult: (result) => set({ compareResult: result }),
  setDecomposition: (decomposition) => set({ decomposition }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
}));
