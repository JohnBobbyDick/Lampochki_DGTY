import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Controls, MiniMap, Background, BackgroundVariant, useOnViewportChange } from 'reactflow';

/** Zoom controls, minimap and dotted background shared by all graph views (colours come from CSS tokens). */
const GraphChrome: React.FC = () => {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hoveredRef = useRef(false);
  const minimapRef = useRef<HTMLDivElement>(null);

  const showMap = useCallback(() => {
    setVisible(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      if (!hoveredRef.current) {
        setVisible(false);
      }
    }, 3000);
  }, []);

  useOnViewportChange({
    onStart: showMap,
    onChange: showMap,
  });

  useEffect(() => {
    const el = minimapRef.current?.querySelector('.react-flow__minimap');
    if (!el) return;
    const onEnter = () => {
      hoveredRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      setVisible(true);
    };
    const onLeave = () => {
      hoveredRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        setVisible(false);
      }, 3000);
    };
    el.addEventListener('mouseenter', onEnter);
    el.addEventListener('mouseleave', onLeave);
    return () => {
      el.removeEventListener('mouseenter', onEnter);
      el.removeEventListener('mouseleave', onLeave);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return (
    <>
      <Controls showInteractive={false} position="bottom-left" />
      <div ref={minimapRef} className={`graph-minimap-wrap ${visible ? 'visible' : ''}`}>
        <MiniMap
          pannable
          zoomable
          position="bottom-right"
          ariaLabel="Миникарта графа"
          className={visible ? 'visible' : ''}
        />
      </div>
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} />
    </>
  );
};

export default GraphChrome;
