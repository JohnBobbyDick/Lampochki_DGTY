import { describe, expect, it, beforeEach } from 'vitest';
import { useStore } from './useStore';
import { useProject, INITIAL, DEMO_JAVA_ID, DEMO_PY_ID } from './useProject';
import { validateFileName, validateFolderName } from '../utils/fileValidation';

describe('Block C2: File & folder creation, renaming, deletion, name validation', () => {
  beforeEach(() => {
    useStore.setState({
      code: '',
      originalCode: '',
      language: 'java',
      error: null,
      storageWarning: null,
    });
    useProject.setState({
      files: [...INITIAL],
      folders: ['src', 'examples'],
      deletedExampleIds: [],
      activeId: DEMO_JAVA_ID,
      activeJavaId: DEMO_JAVA_ID,
      activePythonId: DEMO_PY_ID,
      openIds: [DEMO_JAVA_ID],
      openJavaIds: [DEMO_JAVA_ID],
      openPythonIds: [DEMO_PY_ID],
      runs: {},
      coverage: {},
      coverageError: {},
      coverageReset: {},
    });
  });

  describe('Name validation', () => {
    it('rejects empty names', () => {
      expect(validateFileName('').error).toBe('Имя не может быть пустым');
      expect(validateFileName('   ').error).toBe('Имя не может быть пустым');
      expect(validateFolderName('').error).toBe('Имя не может быть пустым');
    });

    it('rejects invalid characters (/ \\ : * ? " < > |)', () => {
      const invalid = ['foo/bar', 'foo\\bar', 'foo:bar', 'foo*bar', 'foo?bar', 'foo"bar', 'foo<bar', 'foo>bar', 'foo|bar'];
      for (const name of invalid) {
        expect(validateFileName(name).error).toContain('недопустимые символы');
        expect(validateFolderName(name).error).toContain('недопустимые символы');
      }
    });

    it('rejects duplicate names in the same folder', () => {
      const existingFiles = ['Demo.java', 'Test.py'];
      expect(validateFileName('Demo.java', existingFiles).error).toBe('Файл с таким именем уже существует в этой папке');
      expect(validateFileName('Other.java', existingFiles).error).toBeUndefined();

      const existingFolders = ['utils', 'models'];
      expect(validateFolderName('utils', existingFolders).error).toBe('Папка с таким именем уже существует');
      expect(validateFolderName('services', existingFolders).error).toBeUndefined();
    });

    it('warns when file extension is neither .java nor .py', () => {
      expect(validateFileName('notes.txt').warning).toBe('Рекомендуется расширение .java или .py');
      expect(validateFileName('script.sh').warning).toBe('Рекомендуется расширение .java или .py');
      expect(validateFileName('Demo.java').warning).toBeUndefined();
      expect(validateFileName('script.py').warning).toBeUndefined();
    });
  });

  describe('Create file and folder', () => {
    it('creates a new file in a folder and opens it', () => {
      const res = useProject.getState().createFile('src', 'NewService.java', 'public class NewService {}');
      expect(res.error).toBeUndefined();

      const state = useProject.getState();
      const file = state.files.find((f) => f.id === 'src/NewService.java');
      expect(file).toBeDefined();
      expect(file?.name).toBe('NewService.java');
      expect(file?.folder).toBe('src');
      expect(file?.language).toBe('java');
      expect(state.activeId).toBe('src/NewService.java');
      expect(useStore.getState().code).toBe('public class NewService {}');
    });

    it('creates a new folder', () => {
      const res = useProject.getState().createFolder('src', 'services');
      expect(res.error).toBeUndefined();
      expect(useProject.getState().folders).toContain('src/services');
    });
  });

  describe('Rename file and language switching', () => {
    it('renames a file and preserves history and coverage', () => {
      const resCreate = useProject.getState().createFile('src', 'OldName.java', 'class OldName {}');
      expect(resCreate.error).toBeUndefined();

      // attach mock runs and coverage
      useProject.setState((s) => ({
        runs: {
          ...s.runs,
          'src/OldName.java': [
            {
              exitCode: 0,
              stdout: 'ok',
              stderr: '',
              durationMs: 1,
              stdin: '',
              code: 'class OldName {}',
              status: 'ok',
              at: Date.now(),
            },
          ],
        },
        coverage: {
          ...s.coverage,
          'src/OldName.java': { code: '', probes: [], hits: [], runs: 1 },
        },
      }));

      const resRename = useProject.getState().renameFile('src/OldName.java', 'Renamed.java');
      expect(resRename.error).toBeUndefined();

      const state = useProject.getState();
      expect(state.files.some((f) => f.id === 'src/OldName.java')).toBe(false);
      expect(state.files.some((f) => f.id === 'src/Renamed.java')).toBe(true);
      expect(state.activeId).toBe('src/Renamed.java');

      // runs and coverage migrated
      expect(state.runs['src/Renamed.java']).toBeDefined();
      expect(state.runs['src/OldName.java']).toBeUndefined();
      expect(state.coverage['src/Renamed.java']).toBeDefined();
      expect(state.coverage['src/OldName.java']).toBeUndefined();
    });

    it('changes language when renaming .java to .py', () => {
      useProject.getState().createFile('src', 'Worker.java', 'class Worker {}');
      expect(useProject.getState().files.find((f) => f.id === 'src/Worker.java')?.language).toBe('java');

      useProject.getState().renameFile('src/Worker.java', 'Worker.py');

      const file = useProject.getState().files.find((f) => f.id === 'src/Worker.py');
      expect(file).toBeDefined();
      expect(file?.language).toBe('python');
      expect(useStore.getState().language).toBe('python');
      expect(useProject.getState().openPythonIds).toContain('src/Worker.py');
      expect(useProject.getState().openJavaIds).not.toContain('src/Worker.py');
    });
  });

  describe('Rename folder', () => {
    it('renames a folder and updates all files inside it', () => {
      useProject.getState().createFolder('src', 'oldfolder');
      useProject.getState().createFile('src/oldfolder', 'Helper.java', '// helper');

      const res = useProject.getState().renameFolder('src/oldfolder', 'newfolder');
      expect(res.error).toBeUndefined();

      const state = useProject.getState();
      expect(state.folders).toContain('src/newfolder');
      expect(state.folders).not.toContain('src/oldfolder');
      expect(state.files.some((f) => f.id === 'src/newfolder/Helper.java')).toBe(true);
      expect(state.files.some((f) => f.id === 'src/oldfolder/Helper.java')).toBe(false);
    });
  });

  describe('Delete file and folder', () => {
    it('deleting active file opens a neighbor file', () => {
      useProject.getState().createFile('src', 'FileA.java', 'class A {}');
      useProject.getState().createFile('src', 'FileB.java', 'class B {}');
      expect(useProject.getState().activeId).toBe('src/FileB.java');

      useProject.getState().deleteFile('src/FileB.java');

      expect(useProject.getState().files.some((f) => f.id === 'src/FileB.java')).toBe(false);
      expect(useProject.getState().activeId).toBe('src/FileA.java');
      expect(useStore.getState().code).toBe('class A {}');
    });

    it('deleting last file shows empty state', () => {
      // keep only one file
      useProject.setState({
        files: [{ id: 'src/Last.java', name: 'Last.java', folder: 'src', path: 'src/Last.java', code: 'last', original: 'last', language: 'java' }],
        openJavaIds: ['src/Last.java'],
        openPythonIds: [],
        openIds: ['src/Last.java'],
        activeId: 'src/Last.java',
        activeJavaId: 'src/Last.java',
      });
      useStore.setState({ code: 'last', originalCode: 'last', language: 'java' });

      useProject.getState().deleteFile('src/Last.java');

      expect(useProject.getState().files.length).toBe(0);
      expect(useProject.getState().activeId).toBe('');
      expect(useStore.getState().code).toBe('');
    });

    it('deleting an example file tracks it in deletedExampleIds', () => {
      expect(useProject.getState().deletedExampleIds).toEqual([]);

      useProject.getState().deleteFile(DEMO_JAVA_ID);

      expect(useProject.getState().deletedExampleIds).toContain(DEMO_JAVA_ID);
    });

    it('restoreExamples restores deleted examples and resets modified examples without touching user files', () => {
      // User creates custom file
      useProject.getState().createFile('src', 'MyCustom.java', 'class MyCustom {}');

      // User deletes Demo.java
      useProject.getState().deleteFile(DEMO_JAVA_ID);
      expect(useProject.getState().files.some((f) => f.id === DEMO_JAVA_ID)).toBe(false);

      // User restores examples
      useProject.getState().restoreExamples();

      const files = useProject.getState().files;
      // Demo.java is restored
      expect(files.some((f) => f.id === DEMO_JAVA_ID)).toBe(true);
      // User's custom file is preserved
      expect(files.some((f) => f.id === 'src/MyCustom.java')).toBe(true);
      // deletedExampleIds is cleared
      expect(useProject.getState().deletedExampleIds).toEqual([]);
    });

    it('deletes folder and all contained files', () => {
      useProject.getState().createFolder('src', 'temp');
      useProject.getState().createFile('src/temp', 'F1.java', '');
      useProject.getState().createFile('src/temp', 'F2.java', '');

      expect(useProject.getState().files.some((f) => f.id === 'src/temp/F1.java')).toBe(true);

      useProject.getState().deleteFolder('src/temp');

      expect(useProject.getState().folders).not.toContain('src/temp');
      expect(useProject.getState().files.some((f) => f.folder === 'src/temp')).toBe(false);
    });
  });
});
