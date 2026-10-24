import React, { useEffect, useMemo, useRef } from 'react';
import AceEditor from 'react-ace';
import ace from 'ace-builds';
import { diffLines } from 'diff';
import 'ace-builds/src-noconflict/mode-java';
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/theme-tomorrow_night';
import 'ace-builds/src-noconflict/theme-tomorrow';
import 'ace-builds/src-noconflict/ext-language_tools';
import { useStore } from '../../store/useStore';
import { useTheme } from '../../hooks/useTheme';

const SEVERITY_TYPE = { error: 'error', warning: 'warning', hint: 'info' } as const;

const CodeEditor: React.FC = () => {
  const code = useStore((s) => s.code);
  const language = useStore((s) => s.language);
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

  /* gutter annotations: defects + compile errors */
  const annotations = useMemo(() => {
    const a = defects.map((d) => ({
      row: Math.max(0, d.lineStart - 1),
      column: 0,
      type: SEVERITY_TYPE[d.severity] ?? 'info',
      text: `${d.bigO ? `[${d.bigO}] ` : ''}${d.message}`,
    }));
    (runResult?.compileErrors ?? []).forEach((e) =>
      a.push({ row: Math.max(0, e.line - 1), column: 0, type: 'error', text: `${e.message}` }),
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
      mode={language === 'python' ? 'python' : 'java'}
      theme={theme === 'dark' ? 'tomorrow_night' : 'tomorrow'}
      name="code-editor"
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
      placeholder="Загрузите файл (.java / .py) или вставьте код сюда…"
      editorProps={{ $blockScrolling: true }}
    />
  );
};

export default CodeEditor;
// keep a reference so bundlers don't tree-shake the ace global used by language tools
void ace;
