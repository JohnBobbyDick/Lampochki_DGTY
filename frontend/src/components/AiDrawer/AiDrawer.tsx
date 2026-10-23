import React from 'react';
import { FiX, FiCopy } from 'react-icons/fi';
import { useStore } from '../../store/useStore';
import PatchView from './PatchView';

const SOURCE_LABEL: Record<string, string> = {
  gemini: '✨ Gemini',
  ollama: '✨ Ollama',
  static: '📚 База паттернов (без LLM)',
};

/** Slide-in panel with the LLM answer; never replaces the static analysis. */
const AiDrawer: React.FC = () => {
  const ai = useStore((s) => s.ai);
  const loading = useStore((s) => s.aiLoading);
  const close = () => useStore.getState().setAi(null);
  if (!ai && !loading) return null;

  return (
    <aside className="ai-drawer">
      <div className="ai-head">
        <b>{ai?.title ?? '✨ AI'}</b>
        <span className="spacer" />
        <button className="btn small" onClick={close} aria-label="close"><FiX /></button>
      </div>
      {loading && <div className="ai-body"><span className="spinner" /> Думаю…</div>}
      {ai && !loading && (
        <div className="ai-body">
          <div className="muted">{SOURCE_LABEL[ai.source] ?? ai.source}</div>
          {ai.note && <div className="ai-note">ℹ {ai.note}</div>}
          {ai.text && <p className="ai-text">{ai.text}</p>}
          {ai.items && ai.items.length === 0 && !ai.note && <div className="muted">Идей для улучшения не найдено 👍</div>}
          {ai.items?.map((it, i) => (
            <div key={i} className={`ai-item ${it.line ? 'clickable' : ''}`} onClick={() => it.line && useStore.getState().jumpToLine(it.line)}>
              <div className="ai-item-title">
                {it.line && <span className="bigo-badge">стр. {it.line}</span>} {it.title}
              </div>
              <div>{it.detail}</div>
              {it.patch ? (
                <div onClick={(e) => e.stopPropagation()}><PatchView key={it.patch.oldCode + it.patch.newCode} patch={it.patch} /></div>
              ) : (
                it.example && <pre className="code-preview">{it.example}</pre>
              )}
            </div>
          ))}
          {ai.patch && <PatchView key={ai.patch.oldCode + ai.patch.newCode} patch={ai.patch} />}
          {ai.code && (
            <>
              <div className="ai-code-head">
                <span className="muted">Пример кода</span>
                <button className="btn small" onClick={() => navigator.clipboard?.writeText(ai.code!)}><FiCopy /> Копировать</button>
              </div>
              <pre className="code-preview">{ai.code}</pre>
            </>
          )}
          <div className="muted ai-privacy">Код отправляется во внешний LLM по кнопке «✨ AI» и, если включено «Авто-ИИ», через 5 с после последней правки.</div>
        </div>
      )}
    </aside>
  );
};

export default AiDrawer;
