/** Text under the empty graph: the server error if the graph failed, else a hint naming the language. */
export const graphEmptyText = (language: 'java' | 'python', error: string | null): string =>
  error
    ? `Не удалось построить граф: ${error}`
    : `Откройте файл слева или вставьте код на ${language === 'python' ? 'Python' : 'Java'}`;

/** Method for the CFG after a parse: keep the current one if the file still has it, else the first one. */
export const methodAfterParse = (current: string | null, methods: string[]): string | null =>
  current && methods.includes(current) ? current : methods[0] ?? null;
