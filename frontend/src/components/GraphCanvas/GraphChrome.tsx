import React from 'react';
import { Controls, MiniMap, Background, BackgroundVariant } from 'reactflow';

/** Zoom controls, minimap and dotted background shared by all graph views (colours come from CSS tokens). */
const GraphChrome: React.FC = () => (
  <>
    <Controls showInteractive={false} position="bottom-left" />
    <MiniMap pannable zoomable position="bottom-right" ariaLabel="Миникарта графа" />
    <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} />
  </>
);

export default GraphChrome;
