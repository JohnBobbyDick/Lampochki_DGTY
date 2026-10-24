import React from 'react';
import { FiCheckCircle, FiXCircle, FiMinusCircle, FiShield, FiAlertTriangle } from 'react-icons/fi';
import { useStore } from '../../store/useStore';
import { RunResult } from '../../types';
import { compareVerdict, VERDICT_TITLE } from '../../utils/verdict';

type Step = { label: string; detail?: string; ok: boolean | null };

const StepRow: React.FC<{ s: Step }> = ({ s }) => (
  <li className={`step ${s.ok === null ? 'na' : s.ok ? 'ok' : 'fail'}`}>
    {s.ok === null ? <FiMinusCircle /> : s.ok ? <FiCheckCircle /> : <FiXCircle />}
    <span className="step-label">{s.label}</span>
    {s.detail && <span className="step-detail">{s.detail}</span>}
  </li>
);

const run = (r: RunResult) => `exit ${r.exitCode} · ${r.durationMs} мс`;

/** Behaviour-preservation verdict, built only from results the backend actually returned. */
const ChecksPanel: React.FC = () => {
  const cmp = useStore((s) => s.compareResult);
  const gate = useStore((s) => s.gateResult);

  if (!cmp && !gate) {
    return (
      <div className="checks-empty">
        <FiShield className="state-icon" />
        <div>
          <div className="state-title">Здесь появится проверка поведения</div>
          <div className="muted">Нажмите <kbd>Сравнить</kbd>: мы запустим исходный и текущий код и сравним их вывод. Для декомпозиции есть <b>Quality Gate</b> во вкладке «Декомпозиция».</div>
        </div>
      </div>
    );
  }

  return (
    <div className="checks">
      {cmp && (() => {
        const v = compareVerdict(cmp);
        return (
        <section className={`check-card ${v}`}>
          <header>
            <span className="verdict">{v === 'ok' ? <FiCheckCircle /> : v === 'warn' ? <FiAlertTriangle /> : <FiXCircle />}
              {VERDICT_TITLE[v]}</span>
            <span className="muted">Исходный код против текущего</span>
          </header>
          {v === 'warn' && (
            <p className="check-note">Вывод двух версий совпал, но программа завершилась с ошибкой, поэтому это ничего не доказывает. Проверьте, что в системе установлена Java (JDK 11+).</p>
          )}
          <ul className="steps">
            <StepRow s={{ label: 'Компиляция', ok: !(cmp.before.compileErrors?.length || cmp.after.compileErrors?.length),
              detail: cmp.after.compileErrors?.length ? `ошибок: ${cmp.after.compileErrors.length}` : undefined }} />
            <StepRow s={{ label: 'Запуск исходного кода', ok: cmp.before.exitCode === 0, detail: run(cmp.before) }} />
            <StepRow s={{ label: 'Запуск текущего кода', ok: cmp.after.exitCode === 0, detail: run(cmp.after) }} />
            <StepRow s={{ label: 'Вывод программы совпадает', ok: cmp.behaviorPreserved }} />
          </ul>
        </section>
        );
      })()}
      {gate && (
        <section className={`check-card ${gate.passed ? 'ok' : 'fail'}`}>
          <header>
            <span className="verdict">{gate.passed ? <FiCheckCircle /> : <FiXCircle />}
              {gate.passed ? 'Quality Gate пройден' : 'Quality Gate не пройден'}</span>
            <span className="muted">Декомпозиция на файлы</span>
          </header>
          <ul className="steps">
            <StepRow s={{ label: 'Сборка файлов', ok: gate.details?.compiled ?? null }} />
            <StepRow s={{ label: 'Поведение сохранено', ok: gate.details?.behaviorPreserved ?? null }} />
            {gate.details?.reason && <StepRow s={{ label: String(gate.details.reason), ok: false }} />}
          </ul>
        </section>
      )}
    </div>
  );
};

export default ChecksPanel;
