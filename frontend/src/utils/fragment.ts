/** Mirror of backend `patcher.locate` without a hint: is the fragment still in the code?
 *  Non-blank lines are compared trimmed and must appear consecutively among the code's non-blank lines. */
export function fragmentPresent(code: string, old: string): boolean {
  const norm = (s: string) => s.replace(/\r\n?/g, '\n').split('\n').map(l => l.trim()).filter(Boolean);
  const want = norm(old);
  if (!want.length) return false;
  const have = norm(code);
  for (let p = 0; p + want.length <= have.length; p++) {
    if (want.every((l, i) => have[p + i] === l)) return true;
  }
  return false;
}
