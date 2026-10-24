import io
import zipfile

from fastapi import APIRouter
from fastapi.responses import Response

import state
from core.comparator import compare_runs
from core import lang as langs
from core.runner import detect_main_class, run_files, run_code
from models.schemas import DecomposeRequest, DecomposeResponse, QualityGateResponse

router = APIRouter()


@router.post("/decompose", response_model=DecomposeResponse)
def decompose(req: DecomposeRequest | None = None) -> DecomposeResponse:
    s = state.require(req.code if req else None, req.language if req else None)
    return langs.get(s.language).decompose(s.code, s.ast)


@router.post("/decompose/zip")
def decompose_zip(req: DecomposeRequest | None = None) -> Response:
    s = state.require(req.code if req else None, req.language if req else None)
    result = langs.get(s.language).decompose(s.code, s.ast)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in result.files:
            z.writestr(f.name, f.code)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=decomposed.zip"})


@router.post("/decompose/verify", response_model=QualityGateResponse)
def decompose_verify(req: DecomposeRequest | None = None) -> QualityGateResponse:
    """Quality gate for a decomposition: original vs. multi-file result."""
    s = state.require(req.code if req else None, req.language if req else None)
    result = langs.get(s.language).decompose(s.code, s.ast)
    if not result.files:
        return QualityGateResponse(passed=False, details={"reason": "нечего выделять", "warnings": result.warnings})
    if s.language == "python":
        main = langs.PYTHON.entry_file[:-3]     # run_files → main.py (the decomposed entry module)
    else:
        main = detect_main_class(s.code) or result.files[0].name[:-5]
    before = run_code(s.code, main, language=s.language)
    after = run_files({f.name: f.code for f in result.files}, main)
    cmp = compare_runs(before, after)
    return QualityGateResponse(
        passed=cmp.behavior_preserved,
        details={"compiled": not after.compile_errors, "behaviorPreserved": cmp.behavior_preserved,
                 "compileErrors": after.compile_errors, "diff": cmp.diff, "stderr": after.stderr[:2000]},
    )
