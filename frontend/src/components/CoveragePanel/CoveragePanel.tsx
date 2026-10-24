import React, { useMemo } from 'react';
import { FiPercent, FiAlertTriangle, FiCheckCircle } from 'react-icons/fi';
import { useStore } from '../../store/useStore';
import { useProject } from '../../store/useProject';
import { Metric, percent, summarize } from '../../utils/coverage';

const fmt = (m: Metric) => `${m.covered} / ${m.total}`;

const MetricRow: React.FC<{ label: string; m: Metric }> = ({ label, m }) => {
  const pct = m.total === 0 ? 0 : Math.round((m.covered / m.total) * 100);
  return (
    <li className="cov-metric">
      <span className="cov-name">{label}</span>
      <span className="cov-num">{fmt(m)} · {percent(m)}</span>
      <span className="cov-bar" aria-hidden="true"><span style={{ width: `${pct}%` }} /></span>
    </li>
  );
};

const cell = (m: Metric) => (m.total === 0 ? '—' : fmt(m));

/** Accumulated code coverage of the active file; valid only for the text it was collected on. */
const CoveragePanel: React.FC = () => {
  const code = useStore((s) => s.code);
  const jumpToLine = useStore((s) => s.jumpToLine);
  const activeId = useProject((s) => s.activeId);
  const cov = useProject((s) => s.coverage[s.activeId]);
  const error = useProject((s) => s.coverageError[s.activeId]);
  const reset = useProject((s) => !!s.coverageReset[s.activeId]);
  const resetCoverage = useProject((s) => s.resetCoverage);
  const language = useStore((s) => s.language);

  const valid = cov && cov.code === code ? cov : undefined;
  const sum = useMemo(() => (valid ? summarize(valid) : null), [valid]);

  if (!valid || !sum) {
    return (
      <div className="checks-empty">
        <FiPercent className="state-icon" aria-hidden="true" />
        <div>
          <div className="state-title">
            {language === 'python' ? 'Покрытие для Python пока не поддерживается.'
              : reset ? 'Код изменён — покрытие сброшено, запустите снова.' : 'Запустите программу, чтобы увидеть покрытие.'}
          </div>
          {error && language !== 'python' && <div className="muted">Покрытие недоступно: {error}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="cov">
      {error && (
        <div className="cov-error" role="status">
          <FiAlertTriangle aria-hidden="true" /> Покрытие недоступно: {error}
        </div>
      )}
      <div className="cov-head">
        <span>Запусков учтено: <b>{valid.runs}</b></span>
        <button className="btn small" onClick={() => resetCoverage(activeId)}>Сбросить покрытие</button>
      </div>
      <div className="cov-grid">
        <section className="check-card">
          <ul className="cov-metrics">
            <MetricRow label="Строки" m={sum.lines} />
            <MetricRow label="Методы" m={sum.methods} />
            <MetricRow label="Ветвления" m={sum.branches} />
            <MetricRow label="Условия (логическое)" m={sum.conditions} />
            <MetricRow label="Сравнения (реляционное)" m={sum.relational} />
          </ul>
        </section>
        <section className="check-card cov-methods">
          <header><span className="cov-title">По методам</span></header>
          <div className="cov-scroll" tabIndex={0} role="region" aria-label="Покрытие по методам">
            <table className="cov-table">
              <thead>
                <tr><th scope="col">Метод</th><th scope="col">Строки</th><th scope="col">Ветвления</th><th scope="col">Условия</th><th scope="col">Сравнения</th></tr>
              </thead>
              <tbody>
                {sum.perMethod.map((m) => (
                  <tr key={m.method}>
                    <th scope="row">{m.method}{!m.called && <span className="cov-uncalled"> не вызывался</span>}</th>
                    <td>{cell(m.lines)}</td><td>{cell(m.branches)}</td><td>{cell(m.conditions)}</td><td>{cell(m.relational)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="check-card">
          <header>
            <span className="cov-title">Не пройдено</span>
            <span className="count">{sum.missing.length}</span>
          </header>
          {sum.missing.length === 0 ? (
            <div className="cov-all"><FiCheckCircle aria-hidden="true" /> Всё пройдено</div>
          ) : (
            <ul className="cov-missing">
              {sum.missing.map((m, i) => (
                <li key={i}>
                  <button className="cov-miss-row" onClick={() => jumpToLine(m.line)}>
                    <span className="cov-line">строка {m.line}<span aria-hidden="true"> ·</span></span>
                    <span className="sr-only">, </span>
                    <span>{m.label} → {m.outcome}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
};

export default CoveragePanel;
