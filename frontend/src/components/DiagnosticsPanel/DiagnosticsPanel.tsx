import React from 'react';
import { FiAlertCircle, FiAlertTriangle, FiInfo, FiCheckCircle, FiZap } from 'react-icons/fi';
import { useStore } from '../../store/useStore';
import { useApi } from '../../hooks/useApi';
import { classifyBigO } from '../../utils/bigo';
import { LuSparkles } from 'react-icons/lu';

const SEVERITY = {
  error: { icon: FiAlertCircle, label: 'Ошибка' },
  warning: { icon: FiAlertTriangle, label: 'Стоит исправить' },
  hint: { icon: FiInfo, label: 'Совет' },
} as const;

const DiagnosticsPanel: React.FC = () => {
  const api = useApi();
  const defects = useStore((s) => s.defects);
  const bigo = useStore((s) => s.bigo);
  const syntaxErrors = useStore((s) => s.syntaxErrors);
  const jumpToLine = useStore((s) => s.jumpToLine);
  const setHoveredNode = useStore((s) => s.setHoveredNode);
  const setSelectedMethod = useStore((s) => s.setSelectedMethod);
  const setGraphType = useStore((s) => s.setGraphType);

  const methodRows = Object.entries(bigo).filter(([k]) => k.includes('.') && !k.endsWith('.' + k.split('.')[0]));

  const open = (d: (typeof defects)[number]) => {
    if (d.lineStart) jumpToLine(d.lineStart);
    if (d.method) {
      setGraphType('cfg');
      setSelectedMethod(d.method);
    }
    setHoveredNode(d.nodeId || null);
    setTimeout(() => setHoveredNode(null), 2500);
  };

  return (
    <div className="panel-scroll">
      {syntaxErrors.length > 0 && (
        <section>
          <h4>Синтаксис</h4>
          {syntaxErrors.map((e, i) => (
            <div key={i} className="defect error">
              <FiAlertCircle className="defect-icon" aria-hidden="true" />
              <div className="defect-main defect-msg">{e}</div>
            </div>
          ))}
        </section>
      )}

      <section>
        <h4>Дефекты <span className="count">{defects.length}</span></h4>
        {defects.length === 0 && (
          <div className="state-card">
            <FiCheckCircle className="state-icon ok" aria-hidden="true" />
            <div className="state-title">Дефектов не найдено</div>
            <div className="muted">Код выглядит аккуратно. Если измените его, проверка запустится заново.</div>
          </div>
        )}
        {defects.map((d, i) => {
          const sev = SEVERITY[d.severity] ?? SEVERITY.hint;
          const Icon = sev.icon;
          return (
            <div key={i} className={`defect ${d.severity}`}>
              <Icon className="defect-icon" aria-hidden="true" />
              <div className="defect-main">
                <button className="defect-open" onClick={() => open(d)} title="Показать в коде и на схеме">
                  <span className="defect-head">
                    <b className="sev-label">{sev.label}</b>
                    {d.bigO && <span className={`bigo-chip small ${classifyBigO(d.bigO).grade}`}>{d.bigO}</span>}
                    <span className="muted">стр. {d.lineStart}{d.lineEnd > d.lineStart ? `–${d.lineEnd}` : ''}</span>
                  </span>
                  <span className="defect-msg">{d.message}</span>
                </button>
                {d.recommendation && <div className="reco"><FiZap aria-hidden="true" /> {d.recommendation}</div>}
                <button className="btn small ai-btn" onClick={(e) => { e.stopPropagation(); api.aiExplain(d); }}><LuSparkles /> Объяснить с ИИ</button>
              </div>
            </div>
          );
        })}
      </section>

      <section>
        <h4>Сложность методов · Big O</h4>
        {methodRows.length === 0 && <div className="muted">Появится после разбора кода.</div>}
        <div className="bigo-list">
          {methodRows.map(([m, v]) => {
            const c = classifyBigO(v);
            return (
              <button key={m} className="bigo-row" onClick={() => { setGraphType('cfg'); setSelectedMethod(m); }}
                      title="Показать метод на графе">
                <span className="bigo-name" title={m}>{m}</span>
                <span className="bigo-hint">{c.name}</span>
                <span className={`bigo-chip ${c.grade}`}>{v}</span>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
};

export default DiagnosticsPanel;
