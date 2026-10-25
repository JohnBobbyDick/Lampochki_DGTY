import React, { useMemo, useState } from 'react';
import { diffLines } from 'diff';
import { useStore, AiPatch } from '../../store/useStore';
import { useApi } from '../../hooks/useApi';
import BigoChange from '../BigoChange/BigoChange';
import { changedMethods } from '../../utils/bigoChange';
import { useMeasuredN } from '../../hooks/useMeasuredN';
import { FiXOctagon, FiInfo, FiCheckCircle, FiCheck } from 'react-icons/fi';

/** Diff preview of an AI-suggested edit with an "apply" button; the server re-validates on apply. */
const PatchView: React.FC<{ patch: AiPatch }> = ({ patch }) => {
  const api = useApi();
  const [state, setState] = useState<'idle' | 'busy' | 'applied'>('idle');
  const [errors, setErrors] = useState<string[]>([]);
  const [warnings, setWarnings] = useState<string[]>(patch.warnings);
  const [codeBefore, setCodeBefore] = useState<string | null>(null);

  const rows = useMemo(
    () =>
      diffLines(patch.oldCode, patch.newCode).flatMap((part, i) =>
        part.value.replace(/\n$/, '').split('\n').map((text, j) => ({
          key: `${i}-${j}`, text, kind: part.added ? 'add' : part.removed ? 'del' : 'same',
        })),
      ),
    [patch],
  );

  const measuredN = useMeasuredN();
  const changes = useMemo(
    () => changedMethods(patch.bigoBefore ?? {}, patch.bigoAfter ?? {}),
    [patch],
  );

  const apply = async () => {
    setState('busy');
    setErrors([]);
    const currentCode = useStore.getState().code;
    const res = await api.aiApply({
      oldCode: patch.oldCode, newCode: patch.newCode, imports: patch.imports, startLine: patch.startLine,
    });
    if (res?.ok) {
      const st = useStore.getState();
      setCodeBefore(currentCode);
      st.replaceCode(res.code);            // snapshot first → Ctrl+Z restores the previous version
      useStore.setState({ reviewSkip: res.code, aiReview: null });   // don't re-review our own fix
      st.jumpToLine(res.startLine);
      setWarnings(res.warnings ?? []);
      setState('applied');
    } else {
      setErrors(res?.problems ?? ['Не удалось применить правку']);
      setState('idle');
    }
  };

  const checkBehaviour = () => {
    const st = useStore.getState();
    const original = codeBefore || (st.past.length ? st.past[st.past.length - 1] : st.originalCode) || st.code;
    api.compareCode(original, st.code);
  };

  return (
    <div className="patch">
      <div className="patch-head">
        <span className="muted">Замена строк {patch.startLine}–{patch.endLine}</span>
        {patch.imports.length > 0 && <span className="muted"> · + import {patch.imports.join(', ')}</span>}
      </div>
      {changes.map(([m, b, a]) => (
        <div key={m} className="patch-bigo">
          <span className="patch-bigo-name" title={m}>{m}</span>
          <BigoChange before={b} after={a} n={measuredN(b, m)} />
        </div>
      ))}
      <pre className="diff-view">
        {rows.map((r) => (
          <div key={r.key} className={`diff-row ${r.kind}`}>
            <span className="diff-sign">{r.kind === 'add' ? '+' : r.kind === 'del' ? '−' : ' '}</span>{r.text || ' '}
          </div>
        ))}
      </pre>

      {errors.map((p, i) => <div key={i} className="patch-err"><FiXOctagon /> {p}</div>)}
      {warnings.map((w, i) => <div key={i} className="patch-warn"><FiInfo /> {w}</div>)}

      {state === 'applied' ? (
        <div className="patch-done">
          <FiCheckCircle /> Применено <span className="muted">· Ctrl+Z — отменить</span>
          <button className="btn small" onClick={checkBehaviour}>Проверить поведение</button>
        </div>
      ) : (
        <button className="btn primary small" disabled={state === 'busy'} onClick={apply}
                title="Заменить фрагмент в коде">
          {state === 'busy' ? 'Проверяю…' : <><FiCheck /> Применить</>}
        </button>
      )}
    </div>
  );
};

export default PatchView;
