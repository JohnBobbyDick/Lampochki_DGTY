from fastapi import APIRouter

import state
from models.schemas import ParseRequest, ParseResponse

router = APIRouter()


@router.post("/parse", response_model=ParseResponse)
def parse(req: ParseRequest) -> ParseResponse:
    s = state.load(req.code)
    return ParseResponse(
        ast=s.ast, line_map=s.line_map, errors=s.errors,
        methods=[f"{c['name']}.{m['name']}" for c in s.ast.get("classes", []) for m in c["methods"]],
        classes=[c["name"] for c in s.ast.get("classes", [])],
    )
