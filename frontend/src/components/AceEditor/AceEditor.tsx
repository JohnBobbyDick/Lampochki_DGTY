import React, { useEffect, useMemo, useRef } from 'react';
import AceEditor from 'react-ace';
import ace from 'ace-builds';
import { diffLines } from 'diff';
import 'ace-builds/src-noconflict/mode-java';
import 'ace-builds/src-noconflict/theme-tomorrow_night';
import 'ace-builds/src-noconflict/theme-tomorrow';
import 'ace-builds/src-noconflict/ext-language_tools';
import { useStore } from '../../store/useStore';
import { useProject } from '../../store/useProject';
import { useTheme } from '../../hooks/useTheme';
import { lineStates, LineState } from '../../utils/coverage';

const NO_COV: Map<number, LineState> = new Map();
const SEVERITY_TYPE = { error: 'error', warning: 'warning', hint: 'info' } as const;

const JavaEditor: React.FC = () => {
  const code = useStore((s) => s.code);
  const originalCode = useStore((s) => s.originalCode);
  const defects = useStore((s) => s.defects);
  const runResult = useStore((s) => s.runResult);
  const hoveredLine = useStore((s) => s.hoveredLine);
  const jumpTo = useStore((s) => s.jumpTo);
  const setCode = useStore((s) => s.setCode);
  const setHoveredLine = useStore((s) => s.setHoveredLine);
  const ref = useRef<AceEditor>(null);
  const theme = useTheme();

  /* debounced snapshots → undo/redo history covers manual typing too */
  const snapTimer = useRef<ReturnType<typeof setTimeout>>();
  const onChange = (value: string) => {
    setCode(value);
    clearTimeout(snapTimer.current);
    snapTimer.current = setTimeout(() => useStore.getState().snapshot(), 800);
  };

  /* click-to-jump from graph */
  useEffect(() => {
    const ed = ref.current?.editor;
    if (!jumpTo || !ed) return;
    ed.scrollToLine(jumpTo.line, true, true, () => {});
    ed.gotoLine(jumpTo.line, 0, true);
    ed.focus();
  }, [jumpTo]);

  /* hover line in editor → highlight graph node */
  useEffect(() => {
    const ed = ref.current?.editor;
    if (!ed) return;
    const onMove = (e: any) => {
      const pos = e.getDocumentPosition();
      setHoveredLine(pos.row + 1);
    };
    const onLeave = () => setHoveredLine(null);
    ed.on('mousemove', onMove);
    ed.container.addEventListener('mouseleave', onLeave);
    /* app-level undo/redo instead of Ace's own stack */
    ed.commands.addCommand({
      name: 'appUndo', bindKey: { win: 'Ctrl-Z', mac: 'Command-Z' },
      exec: () => { useStore.getState().snapshot(); useStore.getState().undo(); },
    });
    ed.commands.addCommand({
      name: 'appRedo', bindKey: { win: 'Ctrl-Y|Ctrl-Shift-Z', mac: 'Command-Y|Command-Shift-Z' },
      exec: () => useStore.getState().redo(),
    });
    return () => {
      ed.off('mousemove', onMove);
      ed.container.removeEventListener('mouseleave', onLeave);
    };
  }, [setHoveredLine]);

  /* coverage: gutter stripes + hover tooltip, only while the text matches the run */
  const cov = useProject((s) => s.coverage[s.activeId]);
  const covStates = useMemo<Map<number, LineState>>(
    () => (cov && cov.code === code ? lineStates(cov) : NO_COV),
    [cov, code],
  );
  const covStatesRef = useRef(covStates);
  covStatesRef.current = covStates;

  useEffect(() => {
    const session = ref.current?.editor?.session;
    if (!session || covStates.size === 0) return;
    covStates.forEach((st, line) => session.addGutterDecoration(line - 1, `ace-cov-${st.state}`));
    return () => {
      /* Ace has already shifted rows after the edit: clear every row, not the remembered ones */
      for (let r = 0; r < session.getLength(); r++) {
        for (const c of ['hit', 'miss', 'partial']) session.removeGutterDecoration(r, `ace-cov-${c}`);
      }
    };
  }, [covStates]);

  useEffect(() => {
    const ed = ref.current?.editor;
    if (!ed) return;
    const tip = document.createElement('div');
    tip.className = 'ace-cov-tip';
    tip.style.display = 'none';
    ed.container.appendChild(tip);
    const hide = () => { tip.style.display = 'none'; };
    const onGutter = (e: any) => {
      const row = ed.renderer.screenToTextCoordinates(e.clientX, e.clientY).row;
      const st = covStatesRef.current.get(row + 1);
      if (!st) { hide(); return; }
      tip.textContent = st.state === 'miss' ? 'Не выполнялась'
        : st.state === 'hit' ? `Выполнений: ${st.count}`
        : `Выполнений: ${st.count} · не пройдено: ${st.missing.join('; ')}`;
      const box = ed.container.getBoundingClientRect();
      tip.style.display = 'block';
      tip.style.left = `${e.clientX - box.left + 12}px`;
      tip.style.top = `${e.clientY - box.top + 12}px`;
    };
    ed.on('guttermousemove' as any, onGutter);
    ed.on('guttermouseout' as any, hide);
    ed.on('mousemove', hide);
    ed.on('mouseout' as any, hide);
    ed.container.addEventListener('mouseleave', hide);
    ed.on('mousewheel' as any, hide);
    return () => {
      ed.off('guttermousemove' as any, onGutter);
      ed.off('guttermouseout' as any, hide);
      ed.off('mousemove', hide);
      ed.off('mouseout' as any, hide);
      ed.off('mousewheel' as any, hide);
      ed.container.removeEventListener('mouseleave', hide);
      tip.remove();
    };
  }, []);

  /* gutter annotations: defects + compile errors */
  const annotations = useMemo(() => {
    const a = defects.map((d) => ({
      row: Math.max(0, d.lineStart - 1),
      column: 0,
      type: SEVERITY_TYPE[d.severity] ?? 'info',
      text: `${d.bigO ? `[${d.bigO}] ` : ''}${d.message}`,
    }));
    (runResult?.compileErrors ?? []).forEach((e) =>
      a.push({ row: Math.max(0, e.line - 1), column: 0, type: 'error', text: `javac: ${e.message}` }),
    );
    return a;
  }, [defects, runResult]);

  /* full-line markers: defects, hovered line, changed lines vs original */
  const markers = useMemo(() => {
    const m: any[] = [];
    const add = (line: number, end: number, className: string) =>
      m.push({ startRow: line - 1, startCol: 0, endRow: Math.max(line, end) - 1, endCol: 1, className, type: 'fullLine' });
    defects.forEach((d) => d.lineStart && add(d.lineStart, d.lineEnd || d.lineStart, `ace-defect ace-defect-${d.severity}`));
    (runResult?.compileErrors ?? []).forEach((e) => add(e.line, e.line, 'ace-defect ace-defect-error'));
    if (originalCode && originalCode !== code) {
      let line = 1;
      for (const part of diffLines(originalCode, code)) {
        const n = part.count ?? 0;
        if (part.added) add(line, line + n - 1, 'ace-changed');
        if (!part.removed) line += n;
      }
    }
    if (hoveredLine) add(hoveredLine, hoveredLine, 'ace-hover-line');
    return m;
  }, [defects, runResult, originalCode, code, hoveredLine]);

  return (
    <AceEditor
      ref={ref}
      mode="java"
      theme={theme === 'dark' ? 'tomorrow_night' : 'tomorrow'}
      name="java-editor"
      value={code}
      onChange={onChange}
      annotations={annotations}
      markers={markers}
      width="100%"
      height="100%"
      fontSize={13}
      tabSize={4}
      showPrintMargin={false}
      setOptions={{
        useWorker: false, enableBasicAutocompletion: true, enableLiveAutocompletion: false,
        /* Enter starts editing, Esc leaves the editor so Tab moves on (no keyboard trap) */
        enableKeyboardAccessibility: true,
      }}
      placeholder="Загрузите .java файл или вставьте код сюда…"
      editorProps={{ $blockScrolling: true }}
    />
  );
};

export default JavaEditor;
// keep a reference so bundlers don't tree-shake the ace global used by language tools
void ace;
