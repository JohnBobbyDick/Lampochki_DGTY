import React, { useMemo } from 'react';
import { diffLines } from 'diff';
import { useStore } from '../../store/useStore';
import { RunResult } from '../../types';

const Out: React.FC<{ title: string; r: RunResult | null; lines?: React.ReactNode }> = ({ title, r, lines }) => (
  <div className="out-col">
    <div className="out-title">
      {title}
      {r && <span className="muted"> · exit {r.exitCode} · {r.durationMs} ms</span>}
    </div>
    <pre>{lines ?? r?.stdout}</pre>
    {r?.stderr && <pre className="stderr">{r.stderr}</pre>}
  </div>
);

const RunComparePanel: React.FC = () => {
  const cmp = useStore((s) => s.compareResult);

  const { left, right } = useMemo(() => {
    if (!cmp) return { left: null, right: null };
    const parts = diffLines(cmp.before.stdout, cmp.after.stdout);
    const L: React.ReactNode[] = [];
    const R: React.ReactNode[] = [];
    parts.forEach((p, i) => {
      if (p.added) R.push(<span key={i} className="diff-add">{p.value}</span>);
      else if (p.removed) L.push(<span key={i} className="diff-del">{p.value}</span>);
      else { L.push(<span key={i}>{p.value}</span>); R.push(<span key={i}>{p.value}</span>); }
    });
    return { left: L, right: R };
  }, [cmp]);

  if (cmp) {
    return (
      <div className="run-panel">
        <div className={`status ${cmp.behaviorPreserved ? 'ok' : 'fail'}`}>
          {cmp.behaviorPreserved ? '✅ Поведение сохранено' : '❌ Поведение изменилось'}
          <button className="btn small" style={{ marginLeft: 10 }} onClick={() => useStore.getState().setCompareResult(null)}>✕ к консоли</button>
        </div>
        <Out title="BEFORE (оригинал)" r={cmp.before} lines={left} />
        <Out title="AFTER (текущий код)" r={cmp.after} lines={right} />
      </div>
    );
  }
  return <div className="empty small">Run ▶ (Ctrl+Enter) — запустить код · Compare — сравнить с оригиналом</div>;
};

export default RunComparePanel;
