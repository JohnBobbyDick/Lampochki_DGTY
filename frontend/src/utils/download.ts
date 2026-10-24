/** Save text or a Blob to the user's disk under the given file name. */
export function downloadFile(name: string, content: string | Blob): void {
  const blob = typeof content === 'string' ? new Blob([content], { type: 'text/plain;charset=utf-8' }) : content;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
