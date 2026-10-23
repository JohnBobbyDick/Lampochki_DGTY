"""Проверка обращения к Gemini: python3 test_gemini.py [свой вопрос]

Берёт настройки из backend/.env (ключи, прокси, модели), пробует каждый прокси во всех протоколах,
затем делает реальный запрос через общую систему ретраев. Секреты не печатаются.
Запускать там, где будет работать приложение (VPS / без VPN).
"""

import asyncio
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.chdir(os.path.join(ROOT, "backend"))

import config
from ai import llm_client, proxy_scheme
from ai.gemini_pool import mask_proxy


async def probe(key: str, model: str, proxy: str | None, s: dict) -> str:
    t = time.monotonic()
    try:
        await llm_client._gemini(key, model, "Ответь одним словом: привет", False, proxy, 20)
        return f"OK   {time.monotonic() - t:.1f}s"
    except Exception as exc:  # noqa: BLE001
        return f"FAIL {time.monotonic() - t:.1f}s  {llm_client._scrub(str(exc), s)[:160]}"


async def main() -> int:
    prompt = " ".join(sys.argv[1:]) or "Объясни в одном предложении, что такое Big O."
    s = llm_client.settings()
    print(f"enabled={s['enabled']} keys={len(s['gemini_keys'])} proxies={len(s['gemini_proxies'])} "
          f"models={s['gemini_models']} retries={s['retries']}")
    if not s["gemini_keys"]:
        print("GEMINI_API_KEY пуст — заполните backend/.env")
        return 1

    key, model = s["gemini_keys"][0], s["gemini_models"][0]
    print("\n── 1. Проверка каждого прокси × протокола ──")
    for proxy in s["gemini_proxies"]:
        schemes = (*proxy_scheme.FALLBACK_ORDER, "socks5h") if proxy_scheme.is_auto(proxy) else (None,)
        for scheme in schemes:
            url = proxy_scheme.with_scheme(proxy, scheme) if scheme else proxy
            print(f"  {mask_proxy(url):<34} {await probe(key, model, url, s)}")
    print(f"  {'direct':<34} {await probe(key, model, None, s)}")

    print("\n── 2. Реальный запрос через ретраи (прокси/ключи/модели/протоколы) ──")
    print(f"  вопрос: {prompt}")
    t = time.monotonic()
    try:
        answer = await llm_client.generate(prompt)
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL {time.monotonic() - t:.1f}s  {llm_client._scrub(str(exc), s)[:300]}")
        return 1
    print(f"  OK {time.monotonic() - t:.1f}s\n  ответ: {answer.strip()[:500]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
