export type Lang = 'java' | 'python';

/** Language of a project file by its name (.py → python, otherwise java). */
export const languageOf = (name: string): Lang => (name.toLowerCase().endsWith('.py') ? 'python' : 'java');
