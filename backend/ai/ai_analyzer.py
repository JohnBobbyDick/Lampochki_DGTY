"""AI features: explain defects, suggest refactorings, advise on decomposition."""

from __future__ import annotations

from pathlib import Path

import asyncio

from ai import llm_client, patcher, static_tips
from core.call_graph import resolve_calls

PROMPTS = Path(__file__).parent / "prompts"
MAX_CODE_CHARS = 12_000


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


async def explain(defect: dict, code: str, full_code: str | None = None) -> dict:
    fallback_text, fallback_code = static_tips.tip_for(defect.get("message", ""), defect.get("recommendation", ""))
    try:
        raw = await llm_client.generate(_prompt(
            "defect_explain",
            message=defect.get("message", ""), method=defect.get("method", "") or "—",
            bigo=defect.get("bigO") or "—", severity=defect.get("severity", ""),
            recommendation=defect.get("recommendation", "") or "—",
            line_start=defect.get("lineStart", "?"), line_end=defect.get("lineEnd", "?"),
            code=_clip(code),
        ), validate=lambda t: bool(llm_client.parse_json(t).get("explanation")))
        data = llm_client.parse_json(raw)
        if data.get("explanation"):
            patch = await patcher.build_patch(
                full_code if full_code is not None else code, data.get("old_code", ""), data.get("fixed_code", ""),
                data.get("imports") or [], defect.get("lineStart"))
            note = "" if patch or not data.get("fixed_code") else \
                "Не удалось точно определить место замены — пример можно применить вручную."
            return {"explanation": data["explanation"], "fixed_code": data.get("fixed_code", ""), "patch": patch,
                    "source": llm_client.settings()["provider"], "note": note}
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
        raw = await llm_client.generate(
            _prompt("review", code=_clip(code), known=known, max_items=MAX_REVIEW_ITEMS),
            validate=lambda t: isinstance(llm_client.parse_json(t).get("suggestions"), list),
        )
        data = llm_client.parse_json(raw)
        raw_items = [it for it in data.get("suggestions", [])[:MAX_REVIEW_ITEMS]
                     if isinstance(it, dict) and (it.get("title") or it.get("detail"))]
        patches = await asyncio.gather(*(
            patcher.build_patch(code, str(it.get("old_code") or ""), str(it.get("new_code") or ""),
                                it.get("imports") if isinstance(it.get("imports"), list) else [],
                                it.get("line") if isinstance(it.get("line"), int) else None)
            for it in raw_items))
        items = []
        for it, patch in zip(raw_items, patches):
            line = it.get("line")
            items.append({
                "line": patch["start_line"] if patch else (line if isinstance(line, int) and line > 0 else None),
                "title": str(it.get("title", ""))[:160],
                "detail": str(it.get("detail", "")),
                "example": str(it.get("new_code") or it.get("example") or ""),
                "patch": patch,
            })
        return {"summary": str(data.get("summary", "")), "suggestions": items,
                "source": llm_client.settings()["provider"], "note": ""}
    except llm_client.LLMUnavailable as exc:
        return {"summary": "", "suggestions": [], "source": "none", "note": str(exc)}
