import React, { useEffect, useRef, useState } from 'react';
import { useStore } from '../../store/useStore';
import { useApi } from '../../hooks/useApi';

/** Modal for editing a CFG node's text; Enter applies → POST /api/generate. */
const NodeEditor: React.FC = () => {
  const editingNode = useStore((s) => s.editingNode);
  const nodes = useStore((s) => s.nodes);
  const setEditingNode = useStore((s) => s.setEditingNode);
  const api = useApi();
  const node = nodes.find((n) => n.id === editingNode);
  const [text, setText] = useState('');
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (node) {
      setText(node.data.codeSnippet ?? node.data.label ?? '');
      setTimeout(() => ref.current?.select(), 0);
    }
  }, [editingNode]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!node) return null;

  const apply = async () => {
    const st = useStore.getState();
    const graphNodes = st.nodes.map((n) => ({ id: n.id, label: n.id === node.id ? text.trim() : n.data.label }));
    // labels sent to the server are the *displayed* labels; the server diffs them against its own
    const res = await api.generateCode({ type: 'cfg', method: st.selectedMethod, nodes: graphNodes });
    if (res?.code) {
      st.replaceCode(res.code);
      setEditingNode(null);
    }
  };

  return (
    <div className="modal-backdrop" onClick={() => setEditingNode(null)}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">Редактирование узла · {node.data.nodeType}</div>
        <textarea
          ref={ref}
          value={text}
          rows={3}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              apply();
            }
            if (e.key === 'Escape') setEditingNode(null);
          }}
        />
        <div className="modal-hint">Enter — применить и перегенерировать код · Shift+Enter — перенос · Esc — отмена</div>
        <div className="modal-actions">
          <button className="btn" onClick={() => setEditingNode(null)}>Отмена</button>
          <button className="btn primary" onClick={apply}>Применить</button>
        </div>
      </div>
    </div>
  );
};

export default NodeEditor;
