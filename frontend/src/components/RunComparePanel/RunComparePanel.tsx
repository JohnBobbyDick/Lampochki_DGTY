import React, { useMemo } from 'react';
import { diffLines } from 'diff';
import { useProject } from '../../store/useProject';
import { compareRuns, RunRecord, RunStatus } from '../../utils/runs';
import { RUN_VERDICT_TITLE } from '../../utils/verdict';

const STATUS_TEXT: Record<RunStatus, string> = {
  ok: 'exit 0', error: 'исключение', timeout: 'таймаут', stopped: 'остановлен', limit: 'лимит вывода',
};

const Out: React.FC<{ title: string; r: RunRecord; lines: React.ReactNode }> = ({ title, r, lines }) => (
  <div className="out-col">
    <div className="out-title">
      {title}
      <span className="muted"> · {STATUS_TEXT[r.status]} · {r.durationMs} мс</span>
    </div>
    <pre tabIndex={0} aria-label={`Вывод: ${title}`}>{lines}</pre>
    {r.stderr && <pre className="stderr">{r.stderr}</pre>}
  </div>
);

/** Previous run vs last run of the active file (runs of other files never mix in). */
const RunComparePanel: React.FC = () => {
  const history = useProject((s) => s.runs[s.activeId]);
  const prev = history && history.length >= 2 ? history[history.length - 2] : null;
  const last = history && history.length >= 2 ? history[history.length - 1] : null;

  const { left, right } = useMemo(() => {
    if (!prev || !last) return { left: null, right: null };
    const L: React.ReactNode[] = [];
    const R: React.ReactNode[] = [];
    diffLines(prev.stdout, last.stdout).forEach((p, i) => {
      if (p.added) R.push(<span key={i} className="diff-add">{p.value}</span>);
      else if (p.removed) L.push(<span key={i} className="diff-del">{p.value}</span>);
      else { L.push(<span key={i}>{p.value}</span>); R.push(<span key={i}>{p.value}</span>); }
    });
    return { left: L, right: R };
  }, [prev, last]);

  if (!prev || !last) {
    return (
      <div className="checks-empty">
        <div>
          <div className="state-title">Сравнение запусков файла</div>
          <div className="muted">Запустите файл ещё раз после правки, чтобы сравнить выводы</div>
        </div>
      </div>
    );
  }

  const { same, stdinDiffers } = compareRuns(prev, last);
  return (
    <div className="run-panel">
      <div className="run-head">
        <div className={`status ${same ? 'ok' : 'warn'}`}>{same ? RUN_VERDICT_TITLE.same : RUN_VERDICT_TITLE.changed}</div>
        {stdinDiffers && <span className="muted">Ввод отличался</span>}
      </div>
      <Out title="Предыдущий запуск" r={prev} lines={left} />
      <Out title="Последний запуск" r={last} lines={right} />
    </div>
  );
};

export default RunComparePanel;
