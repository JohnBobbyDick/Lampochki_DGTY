import React, { useState } from 'react';
import { FiDownload, FiShield, FiLayers, FiRefreshCw, FiChevronRight, FiCheckCircle, FiXCircle, FiInfo } from 'react-icons/fi';
import { LuFileCode } from 'react-icons/lu';
import { LuSparkles } from 'react-icons/lu';
import { useStore } from '../../store/useStore';
import { useApi } from '../../hooks/useApi';

const methodsWord = (n: number) => {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return 'метод';
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'метода';
  return 'методов';
};

const DecomposePanel: React.FC = () => {
  const files = useStore((s) => s.decomposition);
  const warnings = useStore((s) => s.decomposeWarnings);
  const gate = useStore((s) => s.gateResult);
  const isLoading = useStore((s) => s.isLoading);
  const api = useApi();
  const [open, setOpen] = useState<string | null>(null);

  if (!files) {
    if (isLoading) {
      return (
        <div className="panel-scroll">
          <div className="state-card">
            <span className="spinner" role="status" aria-label="Разбиение…" />
            <div className="state-title">Разбиение кода…</div>
          </div>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="panel-scroll">
      <div className="decomp-actions">
        <button className="btn primary" onClick={() => api.downloadDecomposition()} disabled={!files.length}>
          <FiDownload /> Скачать файлы (zip)
        </button>
        <button className="btn" onClick={() => api.verifyDecomposition()} disabled={isLoading || !files.length}
                title="Собрать файлы, запустить и сравнить вывод с исходным кодом">
          <FiShield /> Quality Gate
        </button>
        <button className="btn icon" onClick={() => api.decomposeCode()} title="Пересчитать" aria-label="Пересчитать"><FiRefreshCw /></button>
        <button className="btn icon" onClick={() => api.aiDecompose()} title="Совет ИИ по разбиению" aria-label="Совет ИИ по разбиению"><LuSparkles /></button>
      </div>

      {gate && (
        <div className={`check-card ${gate.passed ? 'ok' : 'fail'} gate-card`}>
          <span className="verdict">{gate.passed ? <FiCheckCircle /> : <FiXCircle />}
            {gate.passed ? 'Поведение сохранено' : 'Проверка не пройдена'}</span>
          <div className="muted">{gate.passed ? 'Файлы собираются, программа даёт тот же вывод, что и исходный код.' : 'Код не компилируется или вывод отличается от исходного.'}</div>
          {!gate.passed && gate.details?.stderr && <pre className="code-preview">{gate.details.stderr}</pre>}
          {!gate.passed && gate.details?.diff && <pre className="code-preview">{gate.details.diff}</pre>}
        </div>
      )}

      {warnings.map((w, i) => <div key={i} className="decomp-note"><FiInfo /> {w}</div>)}
      {files.length === 0 && <div className="muted">Нечего выделять: нет подходящих static-методов.</div>}

      <h4>Предлагаемые файлы <span className="count">{files.length}</span></h4>
      <div className="decomp-files">
        {files.map((f) => {
          const isOpen = open === f.name;
          return (
            <div key={f.name} className={`decomp-file ${isOpen ? 'open' : ''}`}>
              <button className="decomp-file-head" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : f.name)}>
                <LuFileCode className="file-ico" aria-hidden="true" />
                <b>{f.name}</b>
                <span className="muted">{f.methods.length} {methodsWord(f.methods.length)}</span>
                <FiChevronRight className={`chev ${isOpen ? 'open' : ''}`} />
              </button>
              <div className="decomp-methods">
                {f.methods.map((m) => <span key={m} className="method-chip">{m}</span>)}
              </div>
              {isOpen && <pre className="code-preview">{f.code}</pre>}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default DecomposePanel;
