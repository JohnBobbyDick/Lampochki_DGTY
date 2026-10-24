from fastapi import APIRouter, Request

import asyncio

import state
from ai import ai_analyzer, bigo_diff, llm_client, patcher
from core import runner
from core.decomposer import decompose as run_decompose
from core.bigo_analyzer import analyze_ast
from core.defect_detector import detect_defects
from models.schemas import (AiBigoCombinedRequest, AiBigoCombinedResponse, AiApplyRequest, AiApplyResponse, AiDecomposeResponse, AiReviewRequest, AiReviewResponse, AiExplainRequest, AiExplainResponse, AiFixRequest, AiStatus,
                            AiSuggestRequest, AiSuggestResponse)

router = APIRouter(prefix="/ai")

# never hammer the LLM (and its keys) with more than a couple of parallel reviews
_REVIEW_SLOTS = asyncio.Semaphore(2)


@router.get("/status", response_model=AiStatus)
def status() -> AiStatus:
    s = llm_client.settings()
    return AiStatus(enabled=llm_client.is_configured(), provider=s["provider"],
                    model=s["gemini_model"] if s["provider"] == "gemini" else s["ollama_model"])


@router.post("/explain", response_model=AiExplainResponse)
async def explain(req: AiExplainRequest) -> AiExplainResponse:
    s = state.require()
    d = req.defect
    fragment = req.code_fragment or ai_analyzer.fragment_for(
        s.code, int(d.get("lineStart") or 1), int(d.get("lineEnd") or d.get("lineStart") or 1),
        s.ast, d.get("method", ""),
    )
    lang = req.language or s.language
    return AiExplainResponse(**await ai_analyzer.explain(d, fragment, s.code, language=lang))


@router.post("/fix", response_model=AiExplainResponse)
async def fix(req: AiFixRequest) -> AiExplainResponse:
    """Fix a compile/syntax error in the code sent with the request (no prior /api/parse needed)."""
    lang = "python" if runner.is_python_code(req.code, req.language) else "java"
    return AiExplainResponse(**await ai_analyzer.fix_error(req.code, req.line, req.message, language=lang))


@router.post("/suggest", response_model=AiSuggestResponse)
async def suggest(req: AiSuggestRequest) -> AiSuggestResponse:
    lang = req.language or (state.SESSION.language if state.SESSION else "java")
    return AiSuggestResponse(**await ai_analyzer.suggest(req.code_fragment, req.context, language=lang))


@router.post("/decompose", response_model=AiDecomposeResponse)
async def decompose() -> AiDecomposeResponse:
    s = state.require()
    plan = run_decompose(s.code, s.ast)
    return AiDecomposeResponse(**await ai_analyzer.decompose_advice(
        s.ast, [{"name": f.name, "methods": f.methods} for f in plan.files]))


@router.post("/review", response_model=AiReviewResponse)
async def review(req: AiReviewRequest, request: Request) -> AiReviewResponse:
    """Auto-review fired by the UI 5 s after the user stops typing."""
    if not llm_client.is_configured():
        return AiReviewResponse(note="LLM отключён или не настроен")
    lang = req.language or (state.SESSION.language if state.SESSION else "java")
    s = state.require(req.code, language=lang)
    known = [d.message for d in detect_defects(s.ast, s.code, analyze_ast(s.ast))]
    async with _REVIEW_SLOTS:
        # the UI aborts the request when the user edits again: stop retrying then, don't burn keys
        job = asyncio.ensure_future(ai_analyzer.review(s.code, known, language=s.language))
        while not job.done():
            if await request.is_disconnected():
                job.cancel()
                return AiReviewResponse(note="отменено")
            await asyncio.wait({job}, timeout=0.5)
        return AiReviewResponse(**job.result())


def _req_language(language: str | None) -> str | None:
    """Request language, else the session's; None → legacy autodetect from the text."""
    return language or (state.SESSION.language if state.SESSION and state.SESSION.code else None)


@router.post("/apply", response_model=AiApplyResponse)
async def apply(req: AiApplyRequest) -> AiApplyResponse:
    """Replace the suggested fragment in the *current* code, after re-validating the result."""
    p = req.patch
    return AiApplyResponse(**await patcher.apply_patch(req.code, p.old_code, p.new_code, p.imports, p.start_line,
                                                       language=_req_language(req.language)))


@router.post("/bigo-combined", response_model=AiBigoCombinedResponse)
def bigo_combined(req: AiBigoCombinedRequest) -> AiBigoCombinedResponse:
    """Big O of the affected methods if several suggestions are applied together (no LLM, no session state)."""
    patches = [p.model_dump() for p in req.patches]
    return AiBigoCombinedResponse(bigo=bigo_diff.combined_bigo(req.code, patches, language=_req_language(req.language)))
