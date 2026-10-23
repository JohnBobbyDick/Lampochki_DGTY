import React from 'react';
import { ReactFlowProvider } from 'reactflow';
import { toPng } from 'html-to-image';
import { FiImage } from 'react-icons/fi';
import CFGView from './CFGView';
import CallGraphView from './CallGraphView';
import ClassDiagramView from './ClassDiagramView';
import NodeEditor from './NodeEditor';
import { useStore } from '../../store/useStore';
import { GraphType } from '../../types';

const TABS: { id: GraphType; label: string }[] = [
  { id: 'cfg', label: 'CFG' },
  { id: 'call', label: 'Call Graph' },
  { id: 'class', label: 'Classes' },
];

const LEGEND: [string, string][] = [
  ['#2d6a4f', 'start'], ['#9d0208', 'end/return'], ['#b5851e', 'if/switch'],
  ['#1d3557', 'loop'], ['#5e548e', 'try'], ['#3a3a3c', 'statement'],
];

async function exportPng() {
  const root = document.querySelector<HTMLElement>('.graph-body .react-flow');
  if (!root) return;
  const url = await toPng(root, {
    backgroundColor: '#1e1e1e',
    filter: (n) => {
      const cl = (n as HTMLElement).classList;
      return !(cl?.contains('react-flow__minimap') || cl?.contains('react-flow__controls'));
    },
  });
  const a = document.createElement('a');
  a.href = url;
  a.download = 'graph.png';
  a.click();
}

const GraphCanvas: React.FC = () => {
  const graphType = useStore((s) => s.graphType);
  const setGraphType = useStore((s) => s.setGraphType);
  const methods = useStore((s) => s.methods);
  const selectedMethod = useStore((s) => s.selectedMethod);
  const setSelectedMethod = useStore((s) => s.setSelectedMethod);
  const hasNodes = useStore((s) => s.nodes.length > 0);
  const syncStatus = useStore((s) => s.syncStatus);

  return (
    <div className="graph-panel">
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab ${graphType === t.id ? 'active' : ''}`} onClick={() => setGraphType(t.id)}>
            {t.label}
          </button>
        ))}
        {graphType === 'cfg' && methods.length > 0 && (
          <select className="method-select" value={selectedMethod ?? ''} onChange={(e) => setSelectedMethod(e.target.value)}>
            {methods.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        )}
        <span className="spacer" />
        <span className={`sync-dot ${syncStatus}`} title={`sync: ${syncStatus}`} />
        <button className="btn small" onClick={exportPng} title="Export graph as PNG"><FiImage /> PNG</button>
      </div>
      <div className="graph-body">
        {!hasNodes ? (
          <div className="empty">Граф появится после загрузки или ввода Java-кода</div>
        ) : (
          <ReactFlowProvider key={graphType}>
            {graphType === 'cfg' && <CFGView />}
            {graphType === 'call' && <CallGraphView />}
            {graphType === 'class' && <ClassDiagramView />}
          </ReactFlowProvider>
        )}
        {graphType === 'cfg' && hasNodes && (
          <div className="legend">
            {LEGEND.map(([c, l]) => <span key={l}><i style={{ background: c }} />{l}</span>)}
          </div>
        )}
      </div>
      <NodeEditor />
    </div>
  );
};

export default GraphCanvas;
