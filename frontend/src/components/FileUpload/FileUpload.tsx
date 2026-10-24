import React, { useRef, useState } from 'react';
import { FiUpload } from 'react-icons/fi';
import { useStore } from '../../store/useStore';
import { useProject } from '../../store/useProject';

/** Header button + drag-n-drop target covering the whole window. */
const FileUpload: React.FC = () => {
  const language = useStore((s) => s.language);
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const load = async (file: File | undefined) => {
    if (!file) return;
    const name = file.name;
    if (!name.endsWith('.java') && !name.endsWith('.py')) {
      useStore.getState().setError(
        language === 'python' ? 'Нужен файл с расширением .py' : 'Нужен файл с расширением .java'
      );
      return;
    }
    const text = await file.text();
    useProject.getState().addFile(name, text);
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
  }, [language]);

  const ext = language === 'python' ? '.py' : '.java';

  return (
    <>
      <button
        className="btn"
        onClick={() => inputRef.current?.click()}
        title={`Загрузить ${ext} (или перетащите файл в окно)`}
        aria-label="Загрузить файл"
      >
        <FiUpload />
        <span className="lbl">Загрузить {ext}</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ext}
        hidden
        onChange={(e) => {
          load(e.target.files?.[0]);
          e.target.value = '';
        }}
      />
      {dragging && (
        <div className="drop-overlay">
          Отпустите {ext} файл, чтобы загрузить
        </div>
      )}
    </>
  );
};

export default FileUpload;
