import React, { useMemo } from 'react';
import { diffLines } from 'diff';
import { useStore } from '../../store/useStore';
import { RunResult } from '../../types';
import { compareVerdict, VERDICT_TITLE } from '../../utils/verdict';

const Out: React.FC<{ title: string; r: RunResult | null; lines?: React.ReactNode }> = ({ title, r, lines }) => (
  <div className="out-col">
    <div className="out-title">
      {title}
      {r && <span className="muted"> · exit {r.exitCode} · {r.durationMs} мс</span>}
    </div>
    <pre tabIndex={0} aria-label={`Вывод: ${title}`}>{lines ?? r?.stdout}</pre>
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
        <div className={`status ${compareVerdict(cmp)}`}>{VERDICT_TITLE[compareVerdict(cmp)]}</div>
        <Out title="До (оригинал)" r={cmp.before} lines={left} />
        <Out title="После (текущий код)" r={cmp.after} lines={right} />
      </div>
    );
  }
  return (
    <div className="checks-empty">
      <div>
        <div className="state-title">Сравнение вывода «до» и «после»</div>
        <div className="muted">Нажмите <kbd>Сравнить</kbd>: исходный и текущий код запустятся, а различия в выводе подсветятся здесь.</div>
      </div>
    </div>
  );
};

export default RunComparePanel;
