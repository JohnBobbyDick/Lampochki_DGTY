import React, { useEffect, useRef, useState } from 'react';
import { FiSquare } from 'react-icons/fi';
import { useStore } from '../../store/useStore';
import { useProject } from '../../store/useProject';
import { runStatus } from '../../utils/runs';

type Seg = { kind: 'out' | 'err' | 'in' | 'sys'; text: string };

const wsUrl = () => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/ws/run`;

/** Interactive console: program output streams in, typed lines go to the program's stdin. */
const Console: React.FC = () => {
  const runNonce = useStore((s) => s.runNonce);
  const [segs, setSegs] = useState<Seg[]>([]);
  const [running, setRunning] = useState(false);
  const [line, setLine] = useState('');
  const wsRef = useRef<WebSocket | null>(null);
  const inputs = useRef<string[]>([]);
  const stopped = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const push = (s: Seg) => setSegs((prev) => [...prev, s]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [segs]);

  const start = () => {
    wsRef.current?.close();
    const st = useStore.getState();
    st.setRunResult(null);
    inputs.current = [];
    stopped.current = false;
    const fileId = useProject.getState().activeId;
    let stdout = '';
    let stderr = '';
    let compileFailed = false; // the backend sends `exit` after `compile_error`: not a run
    setSegs([]);
    setRunning(true);

    const ws = new WebSocket(wsUrl());
    wsRef.current = ws;
    ws.onopen = () => ws.send(JSON.stringify({ type: 'start', code: st.code }));
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === 'stdout') { stdout += m.data; push({ kind: 'out', text: m.data }); }
      else if (m.type === 'stderr') { stderr += m.data; push({ kind: 'err', text: m.data }); }
      else if (m.type === 'compile_error') {
        compileFailed = true;
        push({ kind: 'err', text: m.text });
        useStore.getState().setRunResult({
          stdout: '', stderr: m.text, exitCode: 1, durationMs: 0, compileErrors: m.errors,
        });
      } else if (m.type === 'exit') {
        push({ kind: 'sys', text: `\n[завершено · exit ${m.code} · ${m.durationMs} ms]\n` });
        setRunning(false);
        const stdin = inputs.current.length ? inputs.current.join('\n') + '\n' : '';
        useStore.getState().setStdin(stdin);
        if (!compileFailed) useProject.getState().recordRun({
          stdout, stderr, exitCode: m.code, durationMs: m.durationMs, stdin, code: st.code,
          status: runStatus(m.code, stderr, stopped.current), at: Date.now(),
        }, fileId);
        ws.close();
      }
    };
    ws.onerror = () => {
      push({ kind: 'err', text: 'Не удалось подключиться к серверу (WebSocket /api/ws/run)\n' });
      setRunning(false);
    };
    ws.onclose = () => setRunning(false);
  };

  useEffect(() => {
    if (runNonce > 0) {
      start();
      setTimeout(() => inputRef.current?.focus(), 100);
    }
    return () => {};
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runNonce]);

  useEffect(() => () => wsRef.current?.close(), []);

  const send = (text: string) => {
    if (!running || wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'stdin', data: text + '\n' }));
    inputs.current.push(text);
    push({ kind: 'in', text: text + '\n' });
    setLine('');
  };

  const stop = () => {
    stopped.current = true;
    wsRef.current?.send(JSON.stringify({ type: 'kill' }));
  };


  return (
    <div className="console" onClick={() => inputRef.current?.focus()}>
      <div className="out-title console-bar">
        <span className={`run-dot ${running ? 'on' : ''}`} aria-hidden="true" />
        <span className="console-status">{running ? 'Выполняется…' : segs.length ? 'Готово' : 'Ожидает запуска'}</span>
        <span className="spacer" />
        {running && (
          <>
            <button className="btn small" onClick={() => wsRef.current?.send(JSON.stringify({ type: 'eof' }))} title="Закрыть ввод программы (Ctrl+D)">Завершить ввод</button>
            <button className="btn small" onClick={stop}><FiSquare /> Остановить</button>
          </>
        )}
        <button className="btn small" onClick={() => setSegs([])}>Очистить</button>
      </div>
      <div className="console-scroll" ref={scrollRef}>
        {segs.length === 0 && !running && (
          <div className="muted console-hint">Нажмите <kbd>Запустить</kbd> или <kbd>Ctrl</kbd> + <kbd>Enter</kbd>, чтобы запустить программу. Если ей нужен ввод, набирайте его прямо здесь.</div>
        )}
        <pre className="console-text">
          {segs.map((s, i) => <span key={i} className={`seg-${s.kind}`}>{s.text}</span>)}
          {running && (
            <input
              ref={inputRef}
              className="console-input"
              value={line}
              spellCheck={false}
              autoComplete="off"
              onChange={(e) => setLine(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { e.preventDefault(); send(line); }
                else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
                  e.preventDefault(); e.stopPropagation();
                  wsRef.current?.send(JSON.stringify({ type: 'eof' }));
                } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) e.stopPropagation();
              }}
            />
          )}
        </pre>
      </div>
    </div>
  );
};

export default Console;
