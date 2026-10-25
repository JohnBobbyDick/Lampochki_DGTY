export interface GraphNode {
  id: string;
  type: string; // "start", "end", "statement", "condition", "loop", "try", "catch", "finally", "switch", "return", "throw", "method", "class"
  label: string;
  data: {
    lineStart: number;
    lineEnd: number;
    codeSnippet: string;
    bigO?: string;
    defects?: string[];
    fields?: string[];
    methods?: string[];
  };
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string; // "normal", "true", "false", "back", "exception", "extends", "implements"
  label: string;
}

export interface Defect {
  lineStart: number;
  lineEnd: number;
  nodeId: string;
  method?: string;
  severity: 'error' | 'warning' | 'hint';
  bigO?: string;
  /** Expected Big O of the fragment once the recommendation is applied (static rule, no LLM). */
  bigOAfter?: string;
  message: string;
  recommendation: string;
}

export interface CompileError {
  file?: string;
  line: number;
  message: string;
}

export interface RunResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  durationMs: number;
  compileErrors?: CompileError[];
}

export interface QualityGateResult {
  passed: boolean;
  details: Record<string, any>;
}

export interface CompareResult {
  before: RunResult;
  after: RunResult;
  diff: string;
  behaviorPreserved: boolean;
}

export interface DecomposedFile {
  name: string;
  methods: string[];
  code: string;
}

export type GraphType = 'cfg' | 'call' | 'class';
