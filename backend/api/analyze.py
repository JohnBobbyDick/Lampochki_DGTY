from fastapi import APIRouter

import state
from core.bigo_analyzer import analyze_ast
from core.defect_detector import detect_defects
from models.schemas import AnalyzeResponse

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze() -> AnalyzeResponse:
    s = state.require()
    bigo = analyze_ast(s.ast)
    return AnalyzeResponse(defects=detect_defects(s.ast, s.code, bigo), bigo=bigo)
