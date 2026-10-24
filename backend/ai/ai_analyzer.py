"""AI features: explain defects, suggest refactorings, advise on decomposition."""

from __future__ import annotations

from pathlib import Path

import asyncio

from ai import llm_client, patcher, static_tips
from core.call_graph import resolve_calls

PROMPTS = Path(__file__).parent / "prompts"
MAX_CODE_CHARS = 12_000
REPAIR_ROUNDS = 2


def _prompt(name: str, **kw: object) -> str:
    return (PROMPTS / f"{name}.txt").read_text(encoding="utf-8").format(**kw)


def _clip(code: str) -> str:
    return code if len(code) <= MAX_CODE_CHARS else code[:MAX_CODE_CHARS] + "\n// …обрезано"


def fragment_for(code: str, line_start: int, line_end: int, ast: dict, method: str = "") -> str:
    """The defect's method (if known) or ±3 lines of context around it."""
    lines = code.splitlines()
    if method:
        cls_name, _, mname = method.rpartition(".")
        for c in ast.get("classes", []):
            if cls_name and c["name"] != cls_name:
                continue
            for m in c["methods"]:
                if m["name"] == mname and m.get("span"):
                    sp = m["span"]
                    return "\n".join(lines[sp["start"] - 1: sp["end"]])
    a, b = max(0, line_start - 4), min(len(lines), max(line_end, line_start) + 3)
    return "\n".join(lines[a:b])


def _has_code(cand: dict) -> bool:
    return bool(str(cand.get("old_code") or "").strip() and str(cand.get("new_code") or "").strip())


async def _generate_patches(prompt: str, code: str, validate_json, extract, fix_line: int | None = None):
    """Ask the LLM, build patches for what it returned and re-ask (up to REPAIR_ROUNDS times) while it gave edits
    but none of them is valid. `extract(data)` -> list of dicts with old_code/new_code/imports/line.
    Returns (data, [(candidate, patch_or_None), ...]) of the last response; raises LLMUnavailable only when
    the very first request fails."""
    current, data, results = prompt, {}, []
    for attempt in range(REPAIR_ROUNDS + 1):
        try:
            raw = await llm_client.generate(current, validate=validate_json)
        except llm_client.LLMUnavailable:
            if attempt == 0:
                raise
            break
        data = llm_client.parse_json(raw)
        cands = extract(data)
        patches = await asyncio.gather(*(
            patcher.build_patch(code, str(c.get("old_code") or ""), str(c.get("new_code") or ""),
                                c.get("imports") if isinstance(c.get("imports"), list) else [],
                                c.get("line") if isinstance(c.get("line"), int) else None, fix_line=fix_line)
            for c in cands))
        results = list(zip(cands, patches))
        if any(p and p["valid"] for _, p in results) or not any(_has_code(c) for c in cands):
            break
        errors = "; ".join(dict.fromkeys(
            pr for _, p in results if p and not p["valid"] for pr in p["problems"]))[:1500] or "ошибка применения"
        current = prompt + "\n\n" + _prompt("repair", errors=errors)
    return data, results


async def explain(defect: dict, code: str, full_code: str | None = None) -> dict:
    fallback_text, fallback_code = static_tips.tip_for(defect.get("message", ""), defect.get("recommendation", ""))
    try:
        prompt = _prompt(
            "defect_explain",
            message=defect.get("message", ""), method=defect.get("method", "") or "—",
            bigo=defect.get("bigO") or "—", severity=defect.get("severity", ""),
            recommendation=defect.get("recommendation", "") or "—",
            line_start=defect.get("lineStart", "?"), line_end=defect.get("lineEnd", "?"),
            code=_clip(code))
        line = defect.get("lineStart")
        data, results = await _generate_patches(
            prompt, full_code if full_code is not None else code,
            lambda t: bool(llm_client.parse_json(t).get("explanation")),
            lambda d: [{"old_code": d.get("old_code", ""), "new_code": d.get("fixed_code", ""),
                        "imports": d.get("imports"), "line": line if isinstance(line, int) else None}])
        if data.get("explanation"):
            patch = results[0][1] if results and results[0][1] and results[0][1]["valid"] else None
            return {"explanation": data["explanation"], "fixed_code": data.get("fixed_code", "") if patch else "",
                    "patch": patch, "source": llm_client.settings()["provider"],
                    "note": "" if patch else "ИИ не нашёл правки, которую можно безопасно применить."}
        note = "LLM вернул ответ в неожиданном формате — показан совет из базы паттернов."
    except llm_client.LLMUnavailable as exc:
        note = str(exc)
    return {"explanation": fallback_text, "fixed_code": fallback_code, "patch": None, "source": "static", "note": note}


async def suggest(code: str, context: str = "") -> dict:
    try:
        raw = await llm_client.generate(
            _prompt("optimization", code=_clip(code), context=context or "—"),
            validate=lambda t: bool(llm_client.parse_json(t).get("suggestion")))
        data = llm_client.parse_json(raw)
        if data.get("suggestion"):
            return {"suggestion": data["suggestion"], "example": data.get("example", ""), "source":
                    llm_client.settings()["provider"], "note": ""}
        note = "LLM вернул ответ в неожиданном формате."
    except llm_client.LLMUnavailable as exc:
        note = str(exc)
    text, example = static_tips.tip_for(context or code[:200])
    return {"suggestion": text, "example": example, "source": "static", "note": note}


async def decompose_advice(ast: dict, plan_files: list[dict]) -> dict:
    plan = "\n".join(f"- {f['name']}: {', '.join(f['methods']) or '—'}" for f in plan_files) or "(пусто)"
    calls = "\n".join(f"{k} → {', '.join(sorted(v))}" for k, v in resolve_calls(ast).items() if v) or "(нет)"
    cls = max(ast.get("classes", [{"name": "?", "methods": []}]), key=lambda c: len(c["methods"]))["name"]
    try:
        raw = await llm_client.generate(
            _prompt("decompose_hint", class_name=cls, plan=plan, calls=calls),
            validate=lambda t: bool(llm_client.parse_json(t).get("advice")))
        data = llm_client.parse_json(raw)
        if data.get("advice"):
            return {"advice": data["advice"], "source": llm_client.settings()["provider"], "note": ""}
        note = "LLM вернул ответ в неожиданном формате."
    except llm_client.LLMUnavailable as exc:
        note = str(exc)
    return {
        "advice": "Группы сформированы по префиксам имён методов (parse*, print*, find*…) и связям в графе вызовов. "
                  "Проверьте, что в каждом файле одна зона ответственности, а вызовы между файлами идут в одну "
                  "сторону (без циклических зависимостей).",
        "source": "static", "note": note,
    }


MAX_REVIEW_ITEMS = 5


async def review(code: str, known_defects: list[str]) -> dict:
    """Automatic "how could this code be better" pass; no static fallback (stays silent when AI is down)."""
    known = "\n".join(f"- {m}" for m in known_defects[:15]) or "—"
    try:
        data, results = await _generate_patches(
            _prompt("review", code=_clip(code), known=known, max_items=MAX_REVIEW_ITEMS), code,
            lambda t: isinstance(llm_client.parse_json(t).get("suggestions"), list),
            lambda d: [it for it in d.get("suggestions", [])[:MAX_REVIEW_ITEMS]
                       if isinstance(it, dict) and (it.get("title") or it.get("detail"))])
        items = [{
            "line": patch["start_line"],
            "title": str(it.get("title", ""))[:160],
            "detail": str(it.get("detail", "")),
            "example": str(it.get("new_code") or it.get("example") or ""),
            "patch": patch,
        } for it, patch in results if patch and patch["valid"]]
        return {"summary": str(data.get("summary", "")), "suggestions": items,
                "source": llm_client.settings()["provider"], "note": ""}
    except llm_client.LLMUnavailable as exc:
        return {"summary": "", "suggestions": [], "source": "none", "note": str(exc)}
