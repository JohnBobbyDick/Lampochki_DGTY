import React from 'react';
import { FiArrowRight } from 'react-icons/fi';
import { classifyBigO } from '../../utils/bigo';
import { isBigoChange } from '../../utils/bigoChange';
import { speedup } from '../../utils/speedup';
import type { MeasuredN } from '../../hooks/useMeasuredN';

const UNKNOWN_HINT = 'Ускорение зависит от размера данных n, а запуск без ввода его не показал (код не выполнялся '
  + 'или сложность от n не зависит). Запустите программу со своими данными, чтобы оценить ускорение.';

/** «было → станет · ~N× быстрее при n≈…»; `n` — the measured data size (no number without it). */
const BigoChange: React.FC<{ before: string; after?: string; title?: string; n?: MeasuredN }> = ({ before, after, title, n }) => {
  if (!after || !isBigoChange(before, after)) return null;
  const sp = typeof n === 'number' ? speedup(before, after, n) : null;
  return (
    <span className="bigo-change" title={title}>
      <span className={`bigo-chip small ${classifyBigO(before).grade}`}>{before}</span>
      <FiArrowRight className="bigo-arrow" aria-label="станет" />
      <span className={`bigo-chip small ${classifyBigO(after).grade}`}>{after}</span>
      {sp?.label ? (
        <span className={`bigo-speed ${sp.worse ? 'worse' : 'better'}`} title={sp.hint}>
          · {sp.label}<span className="bigo-n"> при n≈{n}</span>
        </span>
      ) : n === 'pending' ? (
        <span className="bigo-n" role="status">· замеряем ускорение…</span>
      ) : !sp ? (
        <span className="bigo-n" title={UNKNOWN_HINT}>· ускорение — после запуска</span>
      ) : null}
    </span>
  );
};

export default BigoChange;
