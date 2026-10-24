import React from 'react';
import { FiDownload, FiX } from 'react-icons/fi';
import { LuFileCode } from 'react-icons/lu';
import { useStore } from '../../store/useStore';
import { useProject } from '../../store/useProject';
import { downloadFile } from '../../utils/download';

/** Open files above the editor, showing only tabs for the active language. */
const FileTabs: React.FC = () => {
  const language = useStore((s) => s.language);
  const allFiles = useProject((s) => s.files);
  const openIds = useProject((s) => s.openIds);
  const activeId = useProject((s) => s.activeId);
  const open = useProject((s) => s.open);
  const close = useProject((s) => s.close);
  const live = useStore((s) => s.code);

  const visibleIds = openIds.filter((id) =>
    language === 'python' ? id.endsWith('.py') : id.endsWith('.java')
  );

  return (
    <nav className="file-tabs" aria-label="Открытые файлы">
      {visibleIds.map((id) => {
        const f = allFiles.find((x) => x.id === id);
        if (!f) return null;
        const active = id === activeId;
        const dirty = (active ? live : f.code) !== f.original;
        return (
          <div key={id} className={`file-tab ${active ? 'active' : ''}`}>
            <button className="file-tab-main" aria-current={active ? 'page' : undefined} onClick={() => open(id)}>
              <LuFileCode className="file-ico" aria-hidden="true" />
              <span>{f.name}</span>
              {dirty && <i className="dirty" title="Файл изменён"><span className="sr-only">(изменён)</span></i>}
            </button>
            {active && (
              <button className="file-tab-close" aria-label={`Скачать ${f.name}`} title="Скачать файл"
                      onClick={() => downloadFile(f.name, live)}><FiDownload /></button>
            )}
            {visibleIds.length > 1 && (
              <button className="file-tab-close" aria-label={`Закрыть ${f.name}`} onClick={() => close(id)}><FiX /></button>
            )}
          </div>
        );
      })}
    </nav>
  );
};

export default FileTabs;
