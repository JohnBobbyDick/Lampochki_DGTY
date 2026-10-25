import React from 'react';
import { FiInfo, FiCheckCircle, FiCornerDownRight } from 'react-icons/fi';
import { LuSparkles } from 'react-icons/lu';
import { useStore } from '../../store/useStore';
import PatchView from './PatchView';

const SOURCE_LABEL: Record<string, string> = {
  gemini: 'Gemini',
  ollama: 'Ollama',
  static: 'База паттернов (без LLM)',
};

/** «ИИ-помощник» tab of the right panel with the LLM answer; never replaces the static analysis. */
const AiDrawer: React.FC = () => {
  const ai = useStore((s) => s.ai);
  const loading = useStore((s) => s.aiLoading);
  if (!ai && !loading) return null;

  return (
    <div className="ai-pane" aria-label="Ответ ИИ">
      <div className="ai-head">
        <span className="ai-head-icon" aria-hidden="true"><LuSparkles /></span>
        <div className="ai-head-text">
          <b title={ai?.title ?? undefined}>{ai?.title?.replace(/^\p{Extended_Pictographic}️?\s*/u, '') || 'ИИ-помощник'}</b>
          {ai && !loading && <span className="muted">{SOURCE_LABEL[ai.source] ?? ai.source}</span>}
        </div>
      </div>
      {loading && (
        <div className="ai-body">
          <div className="ai-loading"><span className="spinner" /> Думаю над вашим кодом…</div>
          <div className="skeleton" /><div className="skeleton short" /><div className="skeleton" />
        </div>
      )}
      {ai && !loading && (
        <div className="ai-body">
          {ai.note && <div className="ai-note"><FiInfo /> {ai.note}</div>}
          {ai.text && <p className="ai-text">{ai.text}</p>}
          {ai.items && ai.items.length === 0 && !ai.note && (
            <div className="state-card"><FiCheckCircle className="state-icon ok" /><div className="state-title">ИИ не нашёл применимых правок</div></div>
          )}
          {ai.items?.map((it, i) => (
            <div key={i} className="ai-item">
              <div className="ai-item-title">
                {it.title}
                {it.line && (
                  <button className="ai-line" onClick={() => useStore.getState().jumpToLine(it.line!)} title="Перейти к строке в редакторе">
                    <FiCornerDownRight aria-hidden="true" /> стр. {it.line}
                  </button>
                )}
              </div>
              <div className="ai-item-detail">{it.detail}</div>
              {it.patch?.valid && (
                <div onClick={(e) => e.stopPropagation()}><PatchView key={it.patch.oldCode + it.patch.newCode} patch={it.patch} /></div>
              )}
            </div>
          ))}
          {ai.patch?.valid && <PatchView key={ai.patch.oldCode + ai.patch.newCode} patch={ai.patch} />}
          <div className="muted ai-privacy">Код отправляется во внешний LLM по кнопке «Объяснить с ИИ» и, если включено «Авто-ИИ», через 5 с после последней правки.</div>
        </div>
      )}
    </div>
  );
};

export default AiDrawer;
