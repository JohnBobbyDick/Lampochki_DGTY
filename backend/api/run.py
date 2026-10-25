import asyncio

from fastapi import APIRouter

from core import interactive
from core.comparator import compare_code
from core.runner import run_code
from models.schemas import CompareRequest, CompareResponse, QualityGateResponse, RunRequest, RunResponse

router = APIRouter()


@router.post("/run", response_model=RunResponse)
def run(req: RunRequest) -> RunResponse:
    return run_code(req.code, req.main_class, req.stdin_input, req.timeout_sec, language=req.language)


# background measuring runs at once; the rest are refused, not queued (the client retries on the next edit)
MEASURE_SLOTS = asyncio.Semaphore(2)
MEASURE_BUSY = "Сервер занят другими замерами"


@router.post("/run/measure")
async def run_measure(req: RunRequest) -> dict:
    """Run the program without input to count line executions: the data size n for the speedup estimate."""
    if MEASURE_SLOTS.locked():
        return {"error": MEASURE_BUSY}
    async with MEASURE_SLOTS:
        msg = await interactive.measure(req.code, req.language)
    msg.pop("type", None)
    return msg


@router.post("/run/compare", response_model=CompareResponse)
def run_compare(req: CompareRequest) -> CompareResponse:
    return compare_code(req.original, req.modified, req.main_class, req.stdin_input, language=req.language)


@router.post("/quality-gate", response_model=QualityGateResponse)
def quality_gate(req: CompareRequest) -> QualityGateResponse:
    cmp = compare_code(req.original, req.modified, req.main_class, req.stdin_input, language=req.language)
    compiled = not cmp.after.compile_errors and not cmp.before.compile_errors
    return QualityGateResponse(
        passed=cmp.behavior_preserved and compiled,
        details={
            "compiled": compiled,
            "behaviorPreserved": cmp.behavior_preserved,
            "exitCodeBefore": cmp.before.exit_code,
            "exitCodeAfter": cmp.after.exit_code,
            "compileErrors": cmp.after.compile_errors,
            "diff": cmp.diff,
        },
    )
