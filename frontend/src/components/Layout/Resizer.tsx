import React, { useRef } from 'react';

interface Props {
  label: string;
  value: number;
  min: number;
  max: number;
  /** +1 when dragging right grows the column, -1 when dragging left does */
  dir: 1 | -1;
  side: 'left' | 'right';
  onChange: (v: number) => void;
}

const STEP = 16;

/** Draggable, keyboard-operable column border (role="separator"). */
const Resizer: React.FC<Props> = ({ label, value, min, max, dir, side, onChange }) => {
  const drag = useRef<{ x: number; v: number } | null>(null);
  const clamp = (v: number) => Math.round(Math.min(max, Math.max(min, v)));

  return (
    <div
      className={`resizer ${side}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onPointerDown={(e) => {
        drag.current = { x: e.clientX, v: value };
        e.currentTarget.setPointerCapture(e.pointerId);
        document.body.classList.add('is-resizing');
      }}
      onPointerMove={(e) => {
        if (drag.current) onChange(clamp(drag.current.v + dir * (e.clientX - drag.current.x)));
      }}
      onPointerUp={() => {
        drag.current = null;
        document.body.classList.remove('is-resizing');
      }}
      onKeyDown={(e) => {
        if (e.key === 'ArrowRight') onChange(clamp(value + dir * STEP));
        else if (e.key === 'ArrowLeft') onChange(clamp(value - dir * STEP));
        else if (e.key === 'Home') onChange(min);
        else if (e.key === 'End') onChange(max);
        else return;
        e.preventDefault();
      }}
    />
  );
};

export default Resizer;
