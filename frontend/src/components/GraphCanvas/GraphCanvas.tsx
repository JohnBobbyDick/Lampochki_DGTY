import React from 'react';
import { ReactFlowProvider } from 'reactflow';
import { toPng } from 'html-to-image';
import { FiImage, FiShare2, FiCheckCircle, FiAlertCircle } from 'react-icons/fi';
import CFGView from './CFGView';
import CallGraphView from './CallGraphView';
import ClassDiagramView from './ClassDiagramView';
import NodeEditor from './NodeEditor';
import { useStore } from '../../store/useStore';
import { GraphType } from '../../types';
import { LEGEND } from './nodes/kinds';

const TABS: { id: GraphType; label: string }[] = [
  { id: 'cfg', label: 'Блок-схема' },
  { id: 'call', label: 'Вызовы' },
  { id: 'class', label: 'Классы' },
];


const SYNC_TEXT = { idle: 'Схема совпадает с кодом', syncing: 'Схема обновляется…', error: 'Не удалось обновить схему' } as const;

async function exportPng() {
  const root = document.querySelector<HTMLElement>('.graph-body .react-flow');
  if (!root) return;
  const url = await toPng(root, {
    backgroundColor: getComputedStyle(root).getPropertyValue('--graph-bg').trim() || '#0d0d0d',
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
          <button key={t.id} className={`tab ${graphType === t.id ? 'active' : ''}`} aria-pressed={graphType === t.id} onClick={() => setGraphType(t.id)}>
            {t.label}
          </button>
        ))}
        {graphType === 'cfg' && methods.length > 0 && (
          <select className="method-select" aria-label="Метод для блок-схемы" value={selectedMethod ?? ''} onChange={(e) => setSelectedMethod(e.target.value)}>
            {methods.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        )}
        <span className="spacer" />
        <span className={`sync-state ${syncStatus}`} role="status" title={SYNC_TEXT[syncStatus]}>
          {syncStatus === 'syncing' ? <span className="spinner small" aria-hidden="true" />
            : syncStatus === 'error' ? <FiAlertCircle aria-hidden="true" /> : <FiCheckCircle aria-hidden="true" />}
          <span className="sr-only">{SYNC_TEXT[syncStatus]}</span>
        </span>
        <button className="btn small icon" onClick={exportPng} title="Сохранить граф картинкой (PNG)" aria-label="Сохранить граф картинкой"><FiImage /></button>
      </div>
      <div className="graph-body">
        {!hasNodes ? (
          <div className="empty graph-empty">
            <FiShare2 className="state-icon" />
            <div className="state-title">Здесь появится граф</div>
            <div className="muted">Откройте файл слева или вставьте Java-код в редактор.</div>
          </div>
        ) : (
          <ReactFlowProvider key={graphType}>
            {graphType === 'cfg' && <CFGView />}
            {graphType === 'call' && <CallGraphView />}
            {graphType === 'class' && <ClassDiagramView />}
          </ReactFlowProvider>
        )}
        {graphType === 'cfg' && hasNodes && (
          <div className="legend">
            {LEGEND.map((l) => <span key={l.kind} data-kind={l.kind}><i />{l.label}</span>)}
            <span className="legend-back"><b aria-hidden="true" />повтор цикла</span>
          </div>
        )}
      </div>
      <NodeEditor />
    </div>
  );
};

export default GraphCanvas;
