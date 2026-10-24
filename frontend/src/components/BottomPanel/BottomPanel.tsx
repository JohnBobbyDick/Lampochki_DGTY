import React, { useEffect, useState } from 'react';
import { FiTerminal, FiColumns, FiShield, FiCheck, FiX, FiAlertTriangle } from 'react-icons/fi';
import Console from '../Console/Console';
import RunComparePanel from '../RunComparePanel/RunComparePanel';
import ChecksPanel from '../ChecksPanel/ChecksPanel';
import { useStore } from '../../store/useStore';
import { compareVerdict } from '../../utils/verdict';

type Tab = 'console' | 'compare' | 'checks';

const VERDICT_TEXT = { ok: 'пройдена', warn: 'не подтверждена', fail: 'не пройдена' } as const;

/** Bottom area: console, before/after output, behaviour checks. */
const BottomPanel: React.FC = () => {
  const [tab, setTab] = useState<Tab>('console');
  const runNonce = useStore((s) => s.runNonce);
  const cmp = useStore((s) => s.compareResult);
  const gate = useStore((s) => s.gateResult);

  /* follow what the user just did */
  useEffect(() => { if (runNonce > 0) setTab('console'); }, [runNonce]);
  useEffect(() => { if (cmp) setTab('compare'); }, [cmp]);
  useEffect(() => { if (gate) setTab('checks'); }, [gate]);

  const verdict = gate ? (gate.passed ? 'ok' : 'fail') : cmp ? compareVerdict(cmp) : null;

  const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'console', label: 'Консоль', icon: <FiTerminal /> },
    { id: 'compare', label: 'Сравнение', icon: <FiColumns /> },
    { id: 'checks', label: 'Проверка', icon: <FiShield /> },
  ];

  return (
    <>
      <div className="tabs bottom-tabs">
        {TABS.map((t) => (
          <button key={t.id} aria-pressed={tab === t.id} className={`tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
            {t.icon} {t.label}
            {t.id === 'checks' && verdict !== null && (
              <span className={`verdict-ico ${verdict}`} title={VERDICT_TEXT[verdict]}>
                {verdict === 'ok' ? <FiCheck aria-hidden="true" /> : verdict === 'warn' ? <FiAlertTriangle aria-hidden="true" /> : <FiX aria-hidden="true" />}
                <span className="sr-only">: {VERDICT_TEXT[verdict]}</span>
              </span>
            )}
          </button>
        ))}
      </div>
      {/* the console keeps its WebSocket session, so it stays mounted */}
      <div className="bottom-body" style={{ display: tab === 'console' ? 'flex' : 'none' }}><Console /></div>
      {tab === 'compare' && <div className="bottom-body"><RunComparePanel /></div>}
      {tab === 'checks' && <div className="bottom-body"><ChecksPanel /></div>}
    </>
  );
};

export default BottomPanel;
