import type { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';

type Retried = InternalAxiosRequestConfig & { _sessionRetried?: boolean };

/**
 * The server drops idle / evicted sessions, so a request that needs one can get 409.
 * Re-send /parse with the current code once, then retry the original request once (no loops).
 */
export function installSessionRecovery(
  api: AxiosInstance,
  getParseBody: () => { code: string; language?: string },
): void {
  api.interceptors.response.use(undefined, async (err: AxiosError) => {
    const cfg = err.config as Retried | undefined;
    if (!cfg || err.response?.status !== 409 || cfg._sessionRetried || cfg.url === '/parse') throw err;
    cfg._sessionRetried = true;
    const body = getParseBody();
    if (!body.code) throw err;
    await api.post('/parse', body);
    return api.request(cfg);
  });
}
