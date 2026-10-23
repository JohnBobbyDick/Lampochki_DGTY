"""Diagnose the Gemini setup: python check_llm.py   (run it where the app will run, e.g. on the VPS).

Sends one tiny request per proxy (and one direct) and prints OK/FAIL with the reason.
Secrets are never printed.
"""

import asyncio
import time

import config  # noqa: F401  (loads backend/.env)
from ai import llm_client, proxy_scheme
from ai.gemini_pool import mask_proxy


async def probe(key: str, model: str, proxy: str | None, s: dict) -> str:
    t = time.monotonic()
    try:
        await llm_client._gemini(key, model, 'Верни JSON {"a":"ок"}', True, proxy, 20)
        return f"OK   {time.monotonic() - t:.1f}s"
    except Exception as exc:  # noqa: BLE001
        return f"FAIL {time.monotonic() - t:.1f}s  {llm_client._scrub(str(exc), s)[:200]}"


async def main() -> None:
    s = llm_client.settings()
    print(f"enabled={s['enabled']} provider={s['provider']} keys={len(s['gemini_keys'])} "
          f"proxies={len(s['gemini_proxies'])} models={s['gemini_models']} retries={s['retries']}")
    if not s["gemini_keys"]:
        print("GEMINI_API_KEY is empty")
        return
    key, model = s["gemini_keys"][0], s["gemini_models"][0]
    for proxy in s["gemini_proxies"]:
        schemes = proxy_scheme.FALLBACK_ORDER + ("socks5h",) if proxy_scheme.is_auto(proxy) else (None,)
        for scheme in schemes:
            url = proxy_scheme.with_scheme(proxy, scheme) if scheme else proxy
            print(f"via {mask_proxy(url):<34} {await probe(key, model, url, s)}")
    print(f"direct{'':<20} {await probe(key, model, None, s)}")
    print("\nУ вас должен быть хотя бы один OK. 'User location is not supported' = регион выхода не поддерживается;\n"
          "'нет ответа' через прокси = прокси недоступен/не тот протокол (http|socks5, GEMINI_PROXY_SCHEME).")


asyncio.run(main())
