import { useSyncExternalStore } from 'react';

export type Theme = 'dark' | 'light';

const KEY = 'jb-theme';
const listeners = new Set<() => void>();

function read(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch { /* storage unavailable */ }
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

let current: Theme = read();
document.documentElement.dataset.theme = current;

export function setTheme(next: Theme) {
  current = next;
  /* swap all colours at once: suspend transitions for one frame so the switch doesn't smear */
  const root = document.documentElement;
  root.classList.add('no-transitions');
  root.dataset.theme = next;
  void root.offsetHeight;
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('no-transitions')));
  try { localStorage.setItem(KEY, next); } catch { /* storage unavailable */ }
  listeners.forEach((l) => l());
}

export const toggleTheme = () => setTheme(current === 'dark' ? 'light' : 'dark');

const subscribe = (cb: () => void) => {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
};

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, () => current);
}
