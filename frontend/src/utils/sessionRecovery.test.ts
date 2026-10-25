import axios, { AxiosAdapter, AxiosError } from 'axios';
import { describe, expect, it } from 'vitest';
import { installSessionRecovery } from './sessionRecovery';

function make(sessionAlive: { v: boolean; sticky?: boolean }, calls: string[]) {
  const adapter: AxiosAdapter = async (config) => {
    const url = config.url ?? '';
    calls.push(url);
    const respond = (status: number, data: unknown) => ({ data, status, statusText: '', headers: {}, config });
    if (url === '/parse') { sessionAlive.v = !sessionAlive.sticky; return respond(200, {}); }
    if (!sessionAlive.v) {
      throw new AxiosError('conflict', 'ERR_BAD_REQUEST', config, null, respond(409, { detail: 'parse first' }));
    }
    return respond(200, { ok: true });
  };
  const api = axios.create({ adapter });
  installSessionRecovery(api, () => ({ code: 'class A {}', language: 'java' }));
  return api;
}

describe('installSessionRecovery', () => {
  it('on 409 re-parses once and retries the request', async () => {
    const calls: string[] = [];
    const api = make({ v: false }, calls);
    const r = await api.get('/graph');
    expect(r.data).toEqual({ ok: true });
    expect(calls).toEqual(['/graph', '/parse', '/graph']);
  });

  it('does not loop when the retry also fails', async () => {
    const calls: string[] = [];
    const alive = { v: false, sticky: true };
    const api = make(alive, calls);
    await expect(api.get('/graph')).rejects.toBeTruthy();
    expect(calls.filter((u) => u === '/parse')).toHaveLength(1);
    expect(calls.filter((u) => u === '/graph')).toHaveLength(2);
  });
});
