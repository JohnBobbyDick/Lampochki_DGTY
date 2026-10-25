import React, { useEffect, useState } from 'react';
import { FiPlay, FiGitMerge, FiRotateCcw, FiRotateCw, FiLayers, FiSun, FiMoon, FiSidebar, FiHelpCircle, FiShare2 } from 'react-icons/fi';
import FileUpload from './components/FileUpload/FileUpload';
import CodeEditor from './components/AceEditor/AceEditor';
import GraphCanvas from './components/GraphCanvas/GraphCanvas';
import DiagnosticsPanel from './components/DiagnosticsPanel/DiagnosticsPanel';
import DecomposePanel from './components/DecomposePanel/DecomposePanel';
import ProjectTree from './components/ProjectTree/ProjectTree';
import FileTabs from './components/ProjectTree/FileTabs';
import BottomPanel from './components/BottomPanel/BottomPanel';
import Resizer from './components/Layout/Resizer';
import Welcome from './components/Welcome/Welcome';
import AiDrawer from './components/AiDrawer/AiDrawer';
import { useStore } from './store/useStore';
import { useProject } from './store/useProject';
import { LuSparkles } from 'react-icons/lu';
import { FiAlertCircle, FiX, FiAlertTriangle } from 'react-icons/fi';
import { useApi } from './hooks/useApi';
import { useSync } from './hooks/useSync';
import { useAutoReview } from './hooks/useAutoReview';
import { useBigoAfter } from './hooks/useBigoAfter';
import { useTheme, toggleTheme } from './hooks/useTheme';
import { useColumns, COL_LIMITS } from './hooks/useColumns';

type Side = 'diagnostics' | 'decompose' | 'ai';

/** Russian plural form: plural(2, ['идея', 'идеи', 'идей']) → 'идеи'. */
const plural = (n: number, forms: [string, string, string]) => {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return forms[0];
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return forms[1];
  return forms[2];
};

const App: React.FC = () => {
  useSync();
  useAutoReview();
  useBigoAfter();
  const api = useApi();
  const theme = useTheme();
  const [side, setSide] = useState<Side>('diagnostics');
  const [sidebar, setSidebar] = useState(() => {
    try { return localStorage.getItem('jb.sidebar') !== '0'; } catch { return true; }
  });
  const toggleSidebar = () => setSidebar((v) => {
    try { localStorage.setItem('jb.sidebar', v ? '0' : '1'); } catch { /* private mode */ }
    return !v;
  });
  const { cols, setCol } = useColumns();
  const [welcome, setWelcome] = useState(() => {
    try { return localStorage.getItem('jb.welcome') !== '0'; } catch { return true; }
  });
  const closeWelcome = () => {
    setWelcome(false);
    try { localStorage.setItem('jb.welcome', '0'); } catch { /* private mode */ }
  };
  const language = useStore((s) => s.language);
  const isLoading = useStore((s) => s.isLoading);
  const error = useStore((s) => s.error);
  const setError = useStore((s) => s.setError);
  const storageWarning = useStore((s) => s.storageWarning);
  const setStorageWarning = useStore((s) => s.setStorageWarning);
  const canUndo = useStore((s) => s.past.length > 0);
  const canRedo = useStore((s) => s.future.length > 0);
  const aiEnabled = useStore((s) => s.aiEnabled);
  const aiAuto = useStore((s) => s.aiAuto);
  const aiReviewing = useStore((s) => s.aiReviewing);
  const aiReview = useStore((s) => s.aiReview);
  const showGraph = useStore((s) => s.showGraph);
  const hasBottom = useStore((s) => s.hasBottom);
  const decomposition = useStore((s) => s.decomposition);
  const hasDecomposition = !!(decomposition && decomposition.length > 0);
  const aiOpen = useStore((s) => !!s.ai || s.aiLoading);
  const aiFocus = useStore((s) => s.aiFocus);

  useEffect(() => {
    if (aiFocus) setSide('ai');
  }, [aiFocus]);

  useEffect(() => {
    if (side === 'ai' && !aiOpen) setSide('diagnostics');
  }, [side, aiOpen]);

  useEffect(() => {
    if (side === 'decompose' && !hasDecomposition && !isLoading) {
      setSide('diagnostics');
    }
  }, [side, hasDecomposition, isLoading]);

  const run = () => useStore.getState().requestRun();
  const compare = () => useStore.getState().openCompareTab();
  const decompose = () => {
    setSide('decompose');
    return api.decomposeCode();
  };

  /* sync data-lang attribute with root element */
  useEffect(() => {
    document.documentElement.dataset.lang = language;
  }, [language]);

  /* put the demo file into the editor on first start */
  useEffect(() => { useProject.getState().init(); }, []);

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
    <div className={`app ${!hasBottom ? 'no-bottom' : ''}`} data-lang={language}>
      <header className="header">
        <div className="header-group">
          <button className="btn icon ghost" onClick={toggleSidebar} aria-pressed={sidebar} aria-label="Файлы проекта" title="Файлы проекта"><FiSidebar /></button>
          <div className="logo">
            <span className="logo-mark" aria-hidden="true" />
            <span className="lbl">{language === 'python' ? 'Python Blueprints' : 'Java Blueprints'}</span>
          </div>
        </div>

        <div className="header-group">
          <div className="lang-toggle" role="group" aria-label="Выбор языка">
            <button
              className={language === 'java' ? 'active' : ''}
              onClick={() => useProject.getState().switchLanguage('java')}
              title="Java"
            >
              Java
            </button>
            <button
              className={language === 'python' ? 'active' : ''}
              onClick={() => useProject.getState().switchLanguage('python')}
              title="Python 3.11+"
            >
              Python
            </button>
          </div>
          <span className="sep" aria-hidden="true" />
          <FileUpload />
          <span className="sep" aria-hidden="true" />
          <button className="btn icon" onClick={() => useStore.getState().undo()} disabled={!canUndo} title="Отменить (Ctrl+Z)" aria-label="Отменить"><FiRotateCcw /></button>
          <button className="btn icon" onClick={() => useStore.getState().redo()} disabled={!canRedo} title="Повторить (Ctrl+Y)" aria-label="Повторить"><FiRotateCw /></button>
          <button
            className={`btn ${showGraph ? 'active' : ''}`}
            aria-pressed={showGraph}
            onClick={() => useStore.getState().toggleGraph()}
            title="Показать или скрыть граф"
            aria-label="Граф"
          >
            <FiShare2 aria-hidden="true" /><span className="lbl">Граф</span>
          </button>
        </div>
        <span className="spacer" />
        <div className="header-group ai-group">
          {aiEnabled && aiReview && !aiReviewing && !!(aiReview.items?.length || aiReview.note) && (
            <button className="btn small ai-chip" onClick={() => useStore.getState().setAi(aiReview)} title="Открыть результат ИИ-ревью">
              <LuSparkles /> {aiReview.items?.length ? `${aiReview.items.length} ${plural(aiReview.items.length, ['идея', 'идеи', 'идей'])}` : aiReview.note ? 'ИИ недоступен' : 'ревью готово'}
            </button>
          )}
          <label className="ai-toggle" title={aiEnabled
            ? 'Через 5 секунд после последней правки ИИ предложит, как улучшить код (код отправляется в LLM)'
            : 'LLM не настроен: задайте LLM_ENABLED и GEMINI_API_KEY в backend/.env'}>
            <input type="checkbox" className="switch" role="switch" checked={aiAuto && aiEnabled} disabled={!aiEnabled}
                   onChange={(e) => useStore.getState().setAiAuto(e.target.checked)} />
            <span>Авто-ИИ</span>
          </label>
        </div>
        <div className="header-group">
          <button className="btn icon ghost" onClick={() => setWelcome(true)} aria-label="Как пользоваться" title="Как пользоваться"><FiHelpCircle /></button>
          <button className="btn icon ghost" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'}
                  title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}>
            {theme === 'dark' ? <FiSun /> : <FiMoon />}
          </button>
        </div>
        <div className="header-group">
          {isLoading && <span className="spinner" role="status" aria-label="Выполняется" />}
          <button className="btn" onClick={decompose} title="Ctrl+D" aria-label="Декомпозиция"><FiLayers /><span className="lbl">Декомпозиция</span></button>
          <button className="btn" onClick={compare} title="Сравнить предыдущий и последний запуск этого файла" aria-label="Сравнить"><FiGitMerge /><span className="lbl">Сравнить</span></button>
          <button className="btn primary run-btn" onClick={run} disabled={isLoading} title="Ctrl+Enter" aria-label="Запустить"><FiPlay /><span className="lbl">Запустить</span></button>
        </div>
      </header>

      {error && (
        <div className="toast" role="alert">
          <FiAlertCircle className="toast-icon" aria-hidden="true" />
          <span className="toast-text">{error}</span>
          <button className="btn small icon ghost" onClick={() => setError(null)} aria-label="Закрыть сообщение"><FiX /></button>
        </div>
      )}
      {storageWarning && (
        <div className="toast toast-warn" role="status">
          <FiAlertTriangle className="toast-icon warn" aria-hidden="true" />
          <span className="toast-text">{storageWarning}</span>
          <button className="btn small icon ghost" onClick={() => setStorageWarning(null)} aria-label="Закрыть сообщение"><FiX /></button>
        </div>
      )}

      <main
        className={`main ${sidebar ? 'with-sidebar' : ''} ${!showGraph ? 'no-graph' : ''}`}
        style={{ '--w-tree': `${cols.tree}px`, '--w-editor': `${cols.editor}px`, '--w-side': `${cols.side}px` } as React.CSSProperties}
      >
        {sidebar && (
          <section className="col tree-col">
            <ProjectTree />
            <Resizer label="Ширина панели файлов" side="right" dir={1} value={cols.tree}
                     min={COL_LIMITS.tree[0]} max={COL_LIMITS.tree[1]} onChange={(v) => setCol('tree', v)} />
          </section>
        )}
        <section className="col editor-col">
          <FileTabs />
          <div className="editor-body"><CodeEditor /></div>
          {showGraph && (
            <Resizer label="Ширина редактора" side="right" dir={1} value={cols.editor}
                     min={COL_LIMITS.editor[0]} max={COL_LIMITS.editor[1]} onChange={(v) => setCol('editor', v)} />
          )}
        </section>
        {showGraph && <section className="col graph-col"><GraphCanvas /></section>}
        <section className="col side-col">
          <Resizer label="Ширина правой панели" side="left" dir={-1} value={cols.side}
                   min={COL_LIMITS.side[0]} max={COL_LIMITS.side[1]} onChange={(v) => setCol('side', v)} />
          <div className="tabs">
            <button className={`tab ${side === 'diagnostics' ? 'active' : ''}`} aria-pressed={side === 'diagnostics'} onClick={() => setSide('diagnostics')}>Диагностика</button>
            {(hasDecomposition || (isLoading && side === 'decompose')) && (
              <button className={`tab ${side === 'decompose' ? 'active' : ''}`} aria-pressed={side === 'decompose'} onClick={() => setSide('decompose')}>Декомпозиция</button>
            )}
            {aiOpen && (
              <span className={`tab tab-closable ${side === 'ai' ? 'active' : ''}`}>
                <button className="tab-label" aria-pressed={side === 'ai'} onClick={() => setSide('ai')}><LuSparkles aria-hidden="true" /> ИИ-помощник</button>
                <button className="tab-close" onClick={() => useStore.getState().closeAi()} aria-label="Закрыть вкладку «ИИ-помощник»" title="Закрыть"><FiX /></button>
              </span>
            )}
          </div>
          {side === 'diagnostics' ? <DiagnosticsPanel /> : side === 'decompose' ? <DecomposePanel /> : <AiDrawer />}
        </section>
      </main>

      {aiReviewing && (
        <div className="ai-banner" role="status">
          <span className="spinner" aria-hidden="true" /> <LuSparkles className="ai-banner-icon" aria-hidden="true" /> ИИ смотрит, как улучшить ваш код…
        </div>
      )}

      {hasBottom && (
        <footer className="bottom"><BottomPanel /></footer>
      )}
      <Welcome open={welcome} onClose={closeWelcome} />
    </div>
  );
};

export default App;
