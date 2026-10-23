import React, { useRef, useState } from 'react';
import { FiUpload } from 'react-icons/fi';
import { useStore } from '../../store/useStore';

/** Header button + drag-n-drop target covering the whole window. */
const FileUpload: React.FC = () => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const load = async (file: File | undefined) => {
    if (!file) return;
    if (!file.name.endsWith('.java')) {
      useStore.getState().setError('Нужен файл с расширением .java');
      return;
    }
    const text = await file.text();
    const st = useStore.getState();
    st.setOriginalCode(text);
    st.replaceCode(text);
    st.setRunResult(null);
    st.setCompareResult(null);
    st.setDecomposition(null);
    st.setGateResult(null);
    st.setSelectedMethod(null);
  };

  React.useEffect(() => {
    const over = (e: DragEvent) => {
      e.preventDefault();
      setDragging(true);
    };
    const leave = (e: DragEvent) => {
      if (e.relatedTarget === null) setDragging(false);
    };
    const drop = (e: DragEvent) => {
      e.preventDefault();
      setDragging(false);
      load(e.dataTransfer?.files?.[0]);
    };
    window.addEventListener('dragover', over);
    window.addEventListener('dragleave', leave);
    window.addEventListener('drop', drop);
    return () => {
      window.removeEventListener('dragover', over);
      window.removeEventListener('dragleave', leave);
      window.removeEventListener('drop', drop);
    };
  }, []);

  return (
    <>
      <button className="btn" onClick={() => inputRef.current?.click()} title="Загрузить .java (или перетащите файл в окно)">
        <FiUpload /> Upload .java
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".java"
        hidden
        onChange={(e) => {
          load(e.target.files?.[0]);
          e.target.value = '';
        }}
      />
      {dragging && <div className="drop-overlay">Отпустите .java файл, чтобы загрузить</div>}
    </>
  );
};

export default FileUpload;
