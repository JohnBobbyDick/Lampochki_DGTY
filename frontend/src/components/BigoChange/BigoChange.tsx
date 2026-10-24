import React from 'react';
import { FiArrowRight } from 'react-icons/fi';
import { classifyBigO } from '../../utils/bigo';
import { isBigoChange } from '../../utils/bigoChange';
import { speedup } from '../../utils/speedup';

/** «было → станет · ~N× быстрее»; renders nothing when there is no known change. */
const BigoChange: React.FC<{ before: string; after?: string }> = ({ before, after }) => {
  if (!after || !isBigoChange(before, after)) return null;
  const sp = speedup(before, after);
  return (
    <span className="bigo-change">
      <span className={`bigo-chip small ${classifyBigO(before).grade}`}>{before}</span>
      <FiArrowRight className="bigo-arrow" aria-label="станет" />
      <span className={`bigo-chip small ${classifyBigO(after).grade}`}>{after}</span>
      {sp.label && (
        <span className={`bigo-speed ${sp.worse ? 'worse' : 'better'}`} title="при n ≈ 1000">· {sp.label}</span>
      )}
    </span>
  );
};

export default BigoChange;
