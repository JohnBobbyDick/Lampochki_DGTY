import React from 'react';
import { FiArrowRight } from 'react-icons/fi';
import { classifyBigO } from '../../utils/bigo';
import { isBigoChange } from '../../utils/bigoChange';
import { speedup } from '../../utils/speedup';

/** «было → станет · ~N× быстрее»; `n` — data size of the last run, else the speedup is a range. */
const BigoChange: React.FC<{ before: string; after?: string; title?: string; n?: number | null }> = ({ before, after, title, n }) => {
  if (!after || !isBigoChange(before, after)) return null;
  const sp = speedup(before, after, n);
  return (
    <span className="bigo-change" title={title}>
      <span className={`bigo-chip small ${classifyBigO(before).grade}`}>{before}</span>
      <FiArrowRight className="bigo-arrow" aria-label="станет" />
      <span className={`bigo-chip small ${classifyBigO(after).grade}`}>{after}</span>
      {sp.label && (
        <span className={`bigo-speed ${sp.worse ? 'worse' : 'better'}`} title={sp.hint}>
          · {sp.label}{n ? <span className="bigo-n"> при n≈{n}</span> : null}
        </span>
      )}
    </span>
  );
};

export default BigoChange;
