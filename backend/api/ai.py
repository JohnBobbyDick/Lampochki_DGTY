from fastapi import APIRouter, Request

import asyncio

import state
from ai import ai_analyzer, llm_client, patcher
from core.decomposer import decompose as run_decompose
from core.bigo_analyzer import analyze_ast
from core.defect_detector import detect_defects
from models.schemas import (AiApplyRequest, AiApplyResponse, AiDecomposeResponse, AiReviewRequest, AiReviewResponse, AiExplainRequest, AiExplainResponse, AiStatus,
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
    return AiExplainResponse(**await ai_analyzer.explain(d, fragment, s.code))


@router.post("/suggest", response_model=AiSuggestResponse)
async def suggest(req: AiSuggestRequest) -> AiSuggestResponse:
    return AiSuggestResponse(**await ai_analyzer.suggest(req.code_fragment, req.context))


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
    s = state.require(req.code)
    known = [d.message for d in detect_defects(s.ast, s.code, analyze_ast(s.ast))]
    async with _REVIEW_SLOTS:
        # the UI aborts the request when the user edits again: stop retrying then, don't burn keys
        job = asyncio.ensure_future(ai_analyzer.review(s.code, known))
        while not job.done():
            if await request.is_disconnected():
                job.cancel()
                return AiReviewResponse(note="отменено")
            await asyncio.wait({job}, timeout=0.5)
        return AiReviewResponse(**job.result())


@router.post("/apply", response_model=AiApplyResponse)
async def apply(req: AiApplyRequest) -> AiApplyResponse:
    """Replace the suggested fragment in the *current* code, after re-validating the result."""
    p = req.patch
    return AiApplyResponse(**await patcher.apply_patch(req.code, p.old_code, p.new_code, p.imports, p.start_line))
