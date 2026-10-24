import React, { useState } from 'react';
import { FiChevronRight, FiFolder } from 'react-icons/fi';
import { LuFileCode } from 'react-icons/lu';
import { useStore } from '../../store/useStore';
import { useProject } from '../../store/useProject';

const FOLDERS: { id: string; label: string; hint: string }[] = [
  { id: 'src', label: 'src', hint: 'Ваши файлы' },
  { id: 'examples', label: 'examples', hint: 'Готовые монолиты для проверки' },
];

const lines = (code: string) => (code ? code.split('\n').length : 0);

/** Left sidebar: the project's files. Click opens a file in the editor. */
const ProjectTree: React.FC = () => {
  const language = useStore((s) => s.language);
  const allFiles = useProject((s) => s.files);
  const activeId = useProject((s) => s.activeId);
  const open = useProject((s) => s.open);
  const live = useStore((s) => s.code);
  const [closed, setClosed] = useState<Record<string, boolean>>({});

  // Explicit separation: show only files belonging to the currently selected language
  const files = allFiles.filter((f) => (language === 'python' ? f.language === 'python' : f.language === 'java'));

  return (
    <nav className="tree-nav" aria-label="Файлы проекта">
      <div className="tree-head">
        <span>Проект ({language === 'python' ? 'Python' : 'Java'})</span>
        <span className="count">{files.length}</span>
      </div>
      <div className="tree-body">
        <div className="tree-root">
          <FiFolder /> {language === 'python' ? 'python-blueprints' : 'java-blueprints'}
        </div>
        {FOLDERS.map((fd) => {
          const items = files.filter((f) => f.folder === fd.id);
          if (!items.length) return null;
          const isClosed = !!closed[fd.id];
          return (
            <div key={fd.id} className="tree-group">
              <button
                className="tree-folder"
                aria-expanded={!isClosed}
                title={fd.hint}
                onClick={() => setClosed((c) => ({ ...c, [fd.id]: !c[fd.id] }))}
              >
                <FiChevronRight className={`chev ${isClosed ? '' : 'open'}`} />
                <FiFolder /> {fd.label}
              </button>
              {!isClosed &&
                items.map((f) => {
                  const text = f.id === activeId ? live : f.code;
                  const dirty = text !== f.original;
                  return (
                    <button
                      key={f.id}
                      className={`tree-item ${f.id === activeId ? 'active' : ''}`}
                      aria-current={f.id === activeId ? 'true' : undefined}
                      onClick={() => open(f.id)}
                    >
                      <LuFileCode className="file-ico" aria-hidden="true" />
                      <span className="tree-name" title={f.name}>
                        {f.name}
                      </span>
                      {dirty && (
                        <i className="dirty" title="Файл изменён">
                          <span className="sr-only">(изменён)</span>
                        </i>
                      )}
                      <span className="tree-meta" title="Строк в файле">
                        {lines(text)}
                        <span className="sr-only"> строк</span>
                      </span>
                    </button>
                  );
                })}
            </div>
          );
        })}
      </div>
      <div className="tree-foot">
        {language === 'python' ? (
          <>
            Загрузите <b>.py</b> — он появится в <b>src</b>.
          </>
        ) : (
          <>
            Загрузите <b>.java</b> — он появится в <b>src</b>.
          </>
        )}
      </div>
    </nav>
  );
};

export default ProjectTree;
