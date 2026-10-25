import React, { useState, useEffect, useRef } from 'react';
import {
  FiChevronRight,
  FiDownload,
  FiFolder,
  FiMoreVertical,
  FiFilePlus,
  FiFolderPlus,
  FiEdit2,
  FiTrash2,
  FiRotateCcw,
} from 'react-icons/fi';
import { LuFileCode } from 'react-icons/lu';
import { useStore } from '../../store/useStore';
import { useProject, INITIAL } from '../../store/useProject';
import { useApi } from '../../hooks/useApi';

const lines = (code: string) => (code ? code.split('\n').length : 0);

type MenuState =
  | { type: 'file'; id: string }
  | { type: 'folder'; path: string }
  | { type: 'project' }
  | null;

type CreatingState =
  | { type: 'file'; folder: string }
  | { type: 'folder'; parentFolder: string }
  | null;

/** Left sidebar: the project's files and folders. */
const ProjectTree: React.FC = () => {
  const language = useStore((s) => s.language);
  const allFiles = useProject((s) => s.files);
  const folders = useProject((s) => s.folders);
  const deletedExampleIds = useProject((s) => s.deletedExampleIds);
  const activeId = useProject((s) => s.activeId);
  const open = useProject((s) => s.open);
  const createFile = useProject((s) => s.createFile);
  const createFolder = useProject((s) => s.createFolder);
  const renameFile = useProject((s) => s.renameFile);
  const renameFolder = useProject((s) => s.renameFolder);
  const deleteFile = useProject((s) => s.deleteFile);
  const deleteFolder = useProject((s) => s.deleteFolder);
  const resetFile = useProject((s) => s.resetFile);
  const restoreExamples = useProject((s) => s.restoreExamples);
  const live = useStore((s) => s.code);
  const { downloadChanged } = useApi();

  const hasChanged =
    allFiles.some((f) => (f.id === activeId ? live : f.code) !== f.original) ||
    deletedExampleIds.length > 0 ||
    allFiles.some((f) => !INITIAL.some((init) => init.id === f.id));

  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const [menu, setMenu] = useState<MenuState>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renamingFolder, setRenamingFolder] = useState<string | null>(null);
  const [renameVal, setRenameVal] = useState('');
  const [creating, setCreating] = useState<CreatingState>(null);
  const [createVal, setCreateVal] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return;
    const onDocClick = (e: MouseEvent) => {
      if (menuRef.current && menuRef.current.contains(e.target as Node)) return;
      setMenu(null);
    };
    window.addEventListener('click', onDocClick);
    return () => window.removeEventListener('click', onDocClick);
  }, [menu]);

  // Show files belonging to current language
  const files = allFiles.filter((f) => (language === 'python' ? f.language === 'python' : f.language === 'java'));

  // Collect all unique folders containing files or empty folders
  const allFolderPaths = Array.from(
    new Set(['src', 'examples', ...folders, ...files.map((f) => f.folder)])
  ).filter(Boolean);

  // Sort folders: 'src' first, then 'examples', then others alphabetically
  allFolderPaths.sort((a, b) => {
    if (a === 'src') return -1;
    if (b === 'src') return 1;
    if (a === 'examples') return -1;
    if (b === 'examples') return 1;
    return a.localeCompare(b);
  });

  const handleRenameFileSubmit = (oldId: string) => {
    if (!renameVal.trim()) {
      setRenamingId(null);
      return;
    }
    const res = renameFile(oldId, renameVal.trim());
    if (res.error) {
      useStore.getState().setError(res.error);
    } else {
      if (res.warning) useStore.getState().setStorageWarning(res.warning);
      setRenamingId(null);
    }
  };

  const handleRenameFolderSubmit = (oldFolder: string) => {
    if (!renameVal.trim()) {
      setRenamingFolder(null);
      return;
    }
    const res = renameFolder(oldFolder, renameVal.trim());
    if (res.error) {
      useStore.getState().setError(res.error);
    } else {
      setRenamingFolder(null);
    }
  };

  const handleCreateSubmit = () => {
    if (!creating || !createVal.trim()) {
      setCreating(null);
      setCreateVal('');
      return;
    }
    if (creating.type === 'file') {
      const res = createFile(creating.folder, createVal.trim());
      if (res.error) {
        useStore.getState().setError(res.error);
      } else {
        if (res.warning) useStore.getState().setStorageWarning(res.warning);
        setCreating(null);
        setCreateVal('');
      }
    } else {
      const res = createFolder(creating.parentFolder, createVal.trim());
      if (res.error) {
        useStore.getState().setError(res.error);
      } else {
        setCreating(null);
        setCreateVal('');
      }
    }
  };

  return (
    <nav className="tree-nav" aria-label="Файлы проекта">
      <div className="tree-head">
        <span>Проект ({language === 'python' ? 'Python' : 'Java'})</span>
        <span className="count">{files.length}</span>
      </div>

      <div className="tree-actions">
        <button
          className="btn small"
          onClick={() => {
            setCreating({ type: 'file', folder: 'src' });
            setCreateVal(language === 'python' ? 'script.py' : 'App.java');
          }}
          title="Новый файл"
        >
          <FiFilePlus aria-hidden="true" /> Новый файл
        </button>
        <button
          className="btn small"
          onClick={() => {
            setCreating({ type: 'folder', parentFolder: 'src' });
            setCreateVal('utils');
          }}
          title="Новая папка"
        >
          <FiFolderPlus aria-hidden="true" /> Новая папка
        </button>
        <button
          className="btn small icon"
          disabled={!hasChanged}
          onClick={() => downloadChanged()}
          title={hasChanged ? 'Скачать zip с изменёнными файлами' : 'Нет изменённых файлов'}
        >
          <FiDownload aria-hidden="true" />
        </button>
      </div>

      <div className="tree-body">
        <div
          className="tree-root"
          onContextMenu={(e) => {
            e.preventDefault();
            setMenu({ type: 'project' });
          }}
        >
          <FiFolder />
          <span className="tree-name">
            {language === 'python' ? 'python-blueprints' : 'java-blueprints'}
          </span>
          <div className="tree-item-actions">
            <button
              type="button"
              className="tree-dots-btn"
              title="Меню проекта"
              aria-label="Меню проекта"
              onClick={(e) => {
                e.stopPropagation();
                setMenu((cur) => (cur?.type === 'project' ? null : { type: 'project' }));
              }}
            >
              <FiMoreVertical aria-hidden="true" />
            </button>
            {menu?.type === 'project' && (
              <div className="tree-dropdown-menu" ref={menuRef} role="menu">
                <button
                  type="button"
                  className="tree-dropdown-item"
                  role="menuitem"
                  onClick={() => {
                    restoreExamples();
                    setMenu(null);
                  }}
                >
                  <FiRotateCcw aria-hidden="true" /> Восстановить стандартные примеры
                </button>
              </div>
            )}
          </div>
        </div>

        {allFolderPaths.map((fd) => {
          const items = files.filter((f) => f.folder === fd);
          const isClosed = !!closed[fd];
          const isRenamingThisFolder = renamingFolder === fd;
          const isCreatingInThisFolder =
            creating &&
            ((creating.type === 'file' && creating.folder === fd) ||
              (creating.type === 'folder' && creating.parentFolder === fd));
          const folderDisplayName = fd.includes('/') ? fd.slice(fd.lastIndexOf('/') + 1) : fd;
          const isBuiltinFolder = fd === 'src' || fd === 'examples';

          return (
            <div key={fd} className="tree-group">
              <div
                className="tree-folder-row"
                onContextMenu={(e) => {
                  e.preventDefault();
                  setMenu({ type: 'folder', path: fd });
                }}
              >
                <button
                  className="tree-folder"
                  aria-expanded={!isClosed}
                  onClick={() => setClosed((c) => ({ ...c, [fd]: !c[fd] }))}
                >
                  <FiChevronRight className={`chev ${isClosed ? '' : 'open'}`} />
                  <FiFolder />
                  {isRenamingThisFolder ? (
                    <input
                      className="tree-rename-input"
                      autoFocus
                      value={renameVal}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => setRenameVal(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRenameFolderSubmit(fd);
                        if (e.key === 'Escape') setRenamingFolder(null);
                      }}
                      onBlur={() => handleRenameFolderSubmit(fd)}
                    />
                  ) : (
                    <span className="tree-name">{folderDisplayName}</span>
                  )}
                </button>

                <div className="tree-item-actions">
                  <button
                    type="button"
                    className="tree-dots-btn"
                    title="Действия с папкой"
                    aria-label="Действия с папкой"
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenu((cur) =>
                        cur?.type === 'folder' && cur.path === fd ? null : { type: 'folder', path: fd }
                      );
                    }}
                  >
                    <FiMoreVertical aria-hidden="true" />
                  </button>

                  {menu?.type === 'folder' && menu.path === fd && (
                    <div className="tree-dropdown-menu" ref={menuRef} role="menu">
                      <button
                        type="button"
                        className="tree-dropdown-item"
                        role="menuitem"
                        onClick={() => {
                          setCreating({ type: 'file', folder: fd });
                          setCreateVal(language === 'python' ? 'script.py' : 'NewFile.java');
                          setClosed((c) => ({ ...c, [fd]: false }));
                          setMenu(null);
                        }}
                      >
                        <FiFilePlus aria-hidden="true" /> Новый файл
                      </button>
                      <button
                        type="button"
                        className="tree-dropdown-item"
                        role="menuitem"
                        onClick={() => {
                          setCreating({ type: 'folder', parentFolder: fd });
                          setCreateVal('subfolder');
                          setClosed((c) => ({ ...c, [fd]: false }));
                          setMenu(null);
                        }}
                      >
                        <FiFolderPlus aria-hidden="true" /> Новая папка
                      </button>
                      {!isBuiltinFolder && (
                        <>
                          <button
                            type="button"
                            className="tree-dropdown-item"
                            role="menuitem"
                            onClick={() => {
                              setRenamingFolder(fd);
                              setRenameVal(folderDisplayName);
                              setMenu(null);
                            }}
                          >
                            <FiEdit2 aria-hidden="true" /> Переименовать
                          </button>
                          <button
                            type="button"
                            className="tree-dropdown-item danger"
                            role="menuitem"
                            onClick={() => {
                              if (window.confirm(`Удалить папку "${folderDisplayName}" вместе с содержимым?`)) {
                                deleteFolder(fd);
                              }
                              setMenu(null);
                            }}
                          >
                            <FiTrash2 aria-hidden="true" /> Удалить
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {!isClosed && (
                <div className="tree-group-children">
                  {isCreatingInThisFolder && (
                    <div className="tree-item inline-create">
                      <input
                        className="tree-rename-input"
                        autoFocus
                        value={createVal}
                        placeholder={creating?.type === 'file' ? 'Имя файла...' : 'Имя папки...'}
                        onChange={(e) => setCreateVal(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleCreateSubmit();
                          if (e.key === 'Escape') setCreating(null);
                        }}
                        onBlur={handleCreateSubmit}
                      />
                    </div>
                  )}

                  {items.map((f) => {
                    const text = f.id === activeId ? live : f.code;
                    const dirty = text !== f.original;
                    const isExample = f.isExample ?? INITIAL.some((init) => init.id === f.id);
                    const showReset = dirty && isExample;
                    const isRenaming = renamingId === f.id;

                    return (
                      <div
                        key={f.id}
                        className={`tree-item ${f.id === activeId ? 'active' : ''}`}
                        aria-current={f.id === activeId ? 'true' : undefined}
                        onContextMenu={(e) => {
                          e.preventDefault();
                          setMenu({ type: 'file', id: f.id });
                        }}
                      >
                        {isRenaming ? (
                          <input
                            className="tree-rename-input"
                            autoFocus
                            value={renameVal}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => setRenameVal(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleRenameFileSubmit(f.id);
                              if (e.key === 'Escape') setRenamingId(null);
                            }}
                            onBlur={() => handleRenameFileSubmit(f.id)}
                          />
                        ) : (
                          <button
                            type="button"
                            className="tree-item-btn"
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
                        )}

                        <div className="tree-item-actions">
                          <button
                            type="button"
                            className="tree-dots-btn"
                            title="Действия с файлом"
                            aria-label="Действия с файлом"
                            onClick={(e) => {
                              e.stopPropagation();
                              setMenu((cur) =>
                                cur?.type === 'file' && cur.id === f.id ? null : { type: 'file', id: f.id }
                              );
                            }}
                          >
                            <FiMoreVertical aria-hidden="true" />
                          </button>

                          {menu?.type === 'file' && menu.id === f.id && (
                            <div className="tree-dropdown-menu" ref={menuRef} role="menu">
                              <button
                                type="button"
                                className="tree-dropdown-item"
                                role="menuitem"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setRenamingId(f.id);
                                  setRenameVal(f.name);
                                  setMenu(null);
                                }}
                              >
                                <FiEdit2 aria-hidden="true" /> Переименовать
                              </button>
                              {showReset && (
                                <button
                                  type="button"
                                  className="tree-dropdown-item"
                                  role="menuitem"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    resetFile(f.id);
                                    setMenu(null);
                                  }}
                                >
                                  <FiRotateCcw aria-hidden="true" /> Вернуть исходный вид
                                </button>
                              )}
                              <button
                                type="button"
                                className="tree-dropdown-item danger"
                                role="menuitem"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (window.confirm(`Удалить файл "${f.name}"?`)) {
                                    deleteFile(f.id);
                                  }
                                  setMenu(null);
                                }}
                              >
                                <FiTrash2 aria-hidden="true" /> Удалить
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </nav>
  );
};

export default ProjectTree;
