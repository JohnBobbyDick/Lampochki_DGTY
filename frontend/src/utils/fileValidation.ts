export interface ValidationResult {
  error?: string;
  warning?: string;
}

const INVALID_CHARS_REGEX = /[/\\:*?"<>|]/;

export function validateFileName(
  name: string,
  existingNamesInFolder: string[] = []
): ValidationResult {
  const trimmed = name.trim();
  if (!trimmed) {
    return { error: 'Имя не может быть пустым' };
  }
  if (INVALID_CHARS_REGEX.test(trimmed)) {
    return { error: 'Имя содержит недопустимые символы (/ \\ : * ? " < > |)' };
  }
  if (existingNamesInFolder.includes(trimmed)) {
    return { error: 'Файл с таким именем уже существует в этой папке' };
  }
  if (!trimmed.endsWith('.java') && !trimmed.endsWith('.py')) {
    return { warning: 'Рекомендуется расширение .java или .py' };
  }
  return {};
}

export function validateFolderName(
  name: string,
  existingFoldersInParent: string[] = []
): ValidationResult {
  const trimmed = name.trim();
  if (!trimmed) {
    return { error: 'Имя не может быть пустым' };
  }
  if (INVALID_CHARS_REGEX.test(trimmed)) {
    return { error: 'Имя содержит недопустимые символы (/ \\ : * ? " < > |)' };
  }
  if (existingFoldersInParent.includes(trimmed)) {
    return { error: 'Папка с таким именем уже существует' };
  }
  return {};
}
