import React, { useEffect, useRef, useState } from 'react';
import { useStore } from '../../store/useStore';
import { useApi } from '../../hooks/useApi';
import Dialog from '../Layout/Dialog';
import { CFG_KINDS } from './nodes/kinds';

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

  const close = () => setEditingNode(null);

  const apply = async () => {
    if (!node) return;
    const st = useStore.getState();
    const graphNodes = st.nodes.map((n) => ({ id: n.id, label: n.id === node.id ? text.trim() : n.data.label }));
    // labels sent to the server are the *displayed* labels; the server diffs them against its own
    const res = await api.generateCode({ type: 'cfg', method: st.selectedMethod, nodes: graphNodes });
    if (res?.code) {
      const before = st.code;
      st.replaceCode(res.code);
      close();
      // graph → Java → run both versions: the verdict lands in the «Проверка» tab
      if (res.code !== before) api.compareCode(before, res.code);
    }
  };

  const kind = node ? (CFG_KINDS[node.data.nodeType] ?? CFG_KINDS.statement).label : '';

  return (
    <Dialog open={!!node} onClose={close} labelledBy="node-editor-title">
      <div className="modal-title" id="node-editor-title">Изменить узел · {kind}</div>
      <label className="modal-label" htmlFor="node-editor-text">Код узла</label>
      <textarea
        id="node-editor-text"
        ref={ref}
        value={text}
        rows={3}
        spellCheck={false}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            apply();
          }
        }}
      />
      <div className="modal-hint"><kbd>Enter</kbd> применить и пересобрать код · <kbd>Shift</kbd> + <kbd>Enter</kbd> новая строка · <kbd>Esc</kbd> отмена</div>
      <div className="modal-actions">
        <button className="btn" onClick={close}>Отмена</button>
        <button className="btn primary" onClick={apply}>Применить</button>
      </div>
    </Dialog>
  );
};

export default NodeEditor;
