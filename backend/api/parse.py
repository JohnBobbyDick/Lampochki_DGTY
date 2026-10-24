from fastapi import APIRouter

import state
from models.schemas import ParseRequest, ParseResponse

router = APIRouter()


@router.post("/parse", response_model=ParseResponse)
def parse(req: ParseRequest) -> ParseResponse:
    s = state.load(req.code, req.language)
    classes = [c["name"] for c in s.ast.get("classes", []) if c["name"] not in ("Module", "")]
    if not classes and s.ast.get("classes"):
        classes = [s.ast["classes"][0]["name"]]
    return ParseResponse(
        ast=s.ast, line_map=s.line_map, errors=s.errors,
        methods=state.method_names(s.ast),
        classes=classes,
        language=s.language,
    )
