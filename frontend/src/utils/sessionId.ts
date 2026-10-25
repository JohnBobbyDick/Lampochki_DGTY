/** Per-tab session id sent as `X-Session-Id`; survives a reload of the same tab via sessionStorage. */
const KEY = 'jb.sid';
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

let memo: string | null = null;

function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  // insecure contexts (plain http on a LAN host) have no randomUUID
  const h = (n: number) => Array.from({ length: n }, () => Math.floor(Math.random() * 16).toString(16)).join('');
  return `${h(8)}-${h(4)}-4${h(3)}-${'89ab'[Math.floor(Math.random() * 4)]}${h(3)}-${h(12)}`;
}

export function getSessionId(): string {
  if (memo) return memo;
  let id: string | null = null;
  try {
    const s = sessionStorage.getItem(KEY);
    if (s && UUID_RE.test(s)) id = s;
  } catch { /* storage unavailable */ }
  if (!id) {
    id = newId();
    try { sessionStorage.setItem(KEY, id); } catch { /* keep in memory only */ }
  }
  memo = id;
  return id;
}

/** For tests. */
export function resetSessionIdCache(): void {
  memo = null;
}
