import React, { useState } from 'react';
import { FiDownload, FiCheckCircle, FiFile } from 'react-icons/fi';
import { useStore } from '../../store/useStore';
import { useApi } from '../../hooks/useApi';

const DecomposePanel: React.FC = () => {
  const files = useStore((s) => s.decomposition);
  const warnings = useStore((s) => s.decomposeWarnings);
  const gate = useStore((s) => s.gateResult);
  const isLoading = useStore((s) => s.isLoading);
  const api = useApi();
  const [open, setOpen] = useState<string | null>(null);

  if (!files) {
    return (
      <div className="panel-scroll">
        <p className="muted">Анализ связности методов и предложение разбиения монолита на файлы.</p>
        <button className="btn primary" onClick={() => api.decomposeCode()}>🧩 Предложить декомпозицию (Ctrl+D)</button>
      </div>
    );
  }

  return (
    <div className="panel-scroll">
      <div className="row">
        <button className="btn" onClick={() => api.decomposeCode()}>↻ Пересчитать</button>
        <button className="btn" onClick={() => api.verifyDecomposition()} disabled={isLoading || !files.length}>
          <FiCheckCircle /> Quality Gate
        </button>
        <button className="btn" onClick={() => api.aiDecompose()}>✨ AI-совет</button>
        <button className="btn primary" onClick={() => api.downloadDecomposition()} disabled={!files.length}>
          <FiDownload /> Применить (zip)
        </button>
      </div>

      {gate && (
        <div className={`gate ${gate.passed ? 'ok' : 'fail'}`}>
          {gate.passed ? '✅ Поведение сохранено — программа даёт тот же вывод' : '❌ Поведение изменилось или код не компилируется'}
          {!gate.passed && gate.details?.stderr && <pre>{gate.details.stderr}</pre>}
          {!gate.passed && gate.details?.diff && <pre>{gate.details.diff}</pre>}
        </div>
      )}
      {warnings.map((w, i) => <div key={i} className="defect hint"><span>💡</span><div>{w}</div></div>)}
      {files.length === 0 && <div className="muted">Нечего выделять: нет подходящих static-методов.</div>}

      <div className="tree">
        {files.map((f) => (
          <div key={f.name}>
            <div className="tree-file" onClick={() => setOpen(open === f.name ? null : f.name)}>
              <FiFile /> <b>{f.name}</b> <span className="muted">· {f.methods.length} методов</span>
            </div>
            {f.methods.map((m) => <div key={m} className="tree-method">ƒ {m}</div>)}
            {open === f.name && <pre className="code-preview">{f.code}</pre>}
          </div>
        ))}
      </div>
    </div>
  );
};

export default DecomposePanel;
