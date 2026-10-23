import React, { useEffect, useState } from 'react';
import { FiPlay, FiGitMerge, FiRotateCcw, FiRotateCw, FiLayers } from 'react-icons/fi';
import FileUpload from './components/FileUpload/FileUpload';
import JavaEditor from './components/AceEditor/AceEditor';
import GraphCanvas from './components/GraphCanvas/GraphCanvas';
import DiagnosticsPanel from './components/DiagnosticsPanel/DiagnosticsPanel';
import DecomposePanel from './components/DecomposePanel/DecomposePanel';
import Console from './components/Console/Console';
import AiDrawer from './components/AiDrawer/AiDrawer';
import RunComparePanel from './components/RunComparePanel/RunComparePanel';
import { useStore } from './store/useStore';
import { useApi } from './hooks/useApi';
import { useSync } from './hooks/useSync';
import { useAutoReview } from './hooks/useAutoReview';

const SAMPLE = `import java.util.*;

public class Demo {
    public static int sumPairs(List<Integer> items) {
        int total = 0;
        for (Integer a : items) {
            for (Integer b : items) {
                if (a < b) {
                    total += a * b;
                }
            }
        }
        return total;
    }

    public static void main(String[] args) {
        List<Integer> xs = Arrays.asList(1, 2, 3, 4);
        System.out.println("pairs = " + sumPairs(xs));
    }
}
`;

type Side = 'diagnostics' | 'decompose';

const App: React.FC = () => {
  useSync();
  useAutoReview();
  const api = useApi();
  const [side, setSide] = useState<Side>('diagnostics');
  const isLoading = useStore((s) => s.isLoading);
  const error = useStore((s) => s.error);
  const setError = useStore((s) => s.setError);
  const canUndo = useStore((s) => s.past.length > 0);
  const canRedo = useStore((s) => s.future.length > 0);
  const hasCompare = useStore((s) => !!s.compareResult);
  const aiEnabled = useStore((s) => s.aiEnabled);
  const aiAuto = useStore((s) => s.aiAuto);
  const aiReviewing = useStore((s) => s.aiReviewing);
  const aiReview = useStore((s) => s.aiReview);
  const hasOriginal = useStore((s) => !!s.originalCode);

  const run = () => useStore.getState().requestRun();
  const compare = () => {
    const st = useStore.getState();
    return api.compareCode(st.originalCode || st.code, st.code);
  };
  const decompose = () => {
    setSide('decompose');
    return api.decomposeCode();
  };

  /* load a demo snippet on first start */
  useEffect(() => {
    const st = useStore.getState();
    if (!st.code) {
      st.setOriginalCode(SAMPLE);
      st.setCode(SAMPLE);
    }
  }, []);

  /* global shortcuts (Ace handles undo/redo itself while focused) */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (!mod) return;
      const k = e.key.toLowerCase();
      if (k === 'enter') { e.preventDefault(); run(); }
      else if (k === 'd') { e.preventDefault(); decompose(); }
      else if (k === 'z' && !e.shiftKey) { e.preventDefault(); useStore.getState().snapshot(); useStore.getState().undo(); }
      else if (k === 'y' || (k === 'z' && e.shiftKey)) { e.preventDefault(); useStore.getState().redo(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="app">
      <header className="header">
        <div className="logo">🔵 Java Blueprints</div>
        <FileUpload />
        <button className="btn" onClick={() => useStore.getState().undo()} disabled={!canUndo} title="Undo (Ctrl+Z)"><FiRotateCcw /></button>
        <button className="btn" onClick={() => useStore.getState().redo()} disabled={!canRedo} title="Redo (Ctrl+Y)"><FiRotateCw /></button>
        {hasOriginal && (
          <button className="btn" title="Вернуть исходный код" onClick={() => useStore.getState().replaceCode(useStore.getState().originalCode)}>
            Reset
          </button>
        )}
        <span className="spacer" />
        {aiEnabled && aiReview && !aiReviewing && (
          <button className="btn ai-chip" onClick={() => useStore.getState().setAi(aiReview)}
                  title="Открыть результат ИИ-ревью">
            ✨ {aiReview.items?.length ? `${aiReview.items.length} идей` : aiReview.note ? 'ИИ недоступен' : 'ревью готово'}
          </button>
        )}
        <label className="ai-toggle" title={aiEnabled
          ? 'Через 5 секунд после последней правки ИИ предложит, как улучшить код (код отправляется в LLM)'
          : 'LLM не настроен: задайте LLM_ENABLED и GEMINI_API_KEY в backend/.env'}>
          <input type="checkbox" checked={aiAuto && aiEnabled} disabled={!aiEnabled}
                 onChange={(e) => useStore.getState().setAiAuto(e.target.checked)} /> Авто-ИИ
        </label>
        {isLoading && <span className="spinner" aria-label="loading" />}
        <button className="btn" onClick={decompose} title="Ctrl+D"><FiLayers /> Decompose</button>
        <button className="btn" onClick={compare} disabled={isLoading}><FiGitMerge /> Compare</button>
        <button className="btn primary" onClick={run} disabled={isLoading} title="Ctrl+Enter"><FiPlay /> Run</button>
      </header>

      {error && (
        <div className="toast" onClick={() => setError(null)}>⚠ {error} <span className="muted">(клик — закрыть)</span></div>
      )}

      <main className="main">
        <section className="col editor-col"><JavaEditor /></section>
        <section className="col graph-col"><GraphCanvas /></section>
        <section className="col side-col">
          <div className="tabs">
            <button className={`tab ${side === 'diagnostics' ? 'active' : ''}`} onClick={() => setSide('diagnostics')}>Диагностика</button>
            <button className={`tab ${side === 'decompose' ? 'active' : ''}`} onClick={() => setSide('decompose')}>Декомпозиция</button>
          </div>
          {side === 'diagnostics' ? <DiagnosticsPanel /> : <DecomposePanel />}
        </section>
      </main>

      <AiDrawer />
      {aiReviewing && (
        <div className="ai-banner" role="status">
          <span className="spinner" /> ✨ ИИ-модель смотрит, как улучшить ваш код…
        </div>
      )}

      <footer className="bottom">
        <div style={{ display: hasCompare ? 'none' : 'contents' }}><Console /></div>
        {hasCompare && <RunComparePanel />}
      </footer>
    </div>
  );
};

export default App;
