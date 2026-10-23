import React from 'react';
import { useStore } from '../../store/useStore';
import { useApi } from '../../hooks/useApi';

const ICON = { error: '🔴', warning: '⚠️', hint: '💡' } as const;

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
          {syntaxErrors.map((e, i) => <div key={i} className="defect error"><span>🔴</span><div>{e}</div></div>)}
        </section>
      )}

      <section>
        <h4>Дефекты · {defects.length}</h4>
        {defects.length === 0 && <div className="muted">Дефектов не найдено</div>}
        {defects.map((d, i) => (
          <div key={i} className={`defect ${d.severity}`} onClick={() => open(d)}>
            <span>{ICON[d.severity] ?? '💡'}</span>
            <div>
              <div className="defect-head">
                {d.bigO && <b className="bigo-badge">{d.bigO}</b>}
                <span className="muted">стр. {d.lineStart}{d.lineEnd > d.lineStart ? `–${d.lineEnd}` : ''}</span>
              </div>
              <div>{d.message}</div>
              {d.recommendation && <div className="reco">✦ {d.recommendation}</div>}
              <button className="btn small ai-btn" onClick={(e) => { e.stopPropagation(); api.aiExplain(d); }}>✨ AI</button>
            </div>
          </div>
        ))}
      </section>

      <section>
        <h4>Big O по методам</h4>
        <table className="bigo-table">
          <tbody>
            {methodRows.map(([m, v]) => (
              <tr key={m} onClick={() => { setGraphType('cfg'); setSelectedMethod(m); }}>
                <td>{m}</td>
                <td className={v.includes('²') || v.includes('³') ? 'bad' : ''}>{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
};

export default DiagnosticsPanel;
