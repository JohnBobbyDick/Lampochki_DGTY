from fastapi import APIRouter, HTTPException

import state
from core.cfg_builder import build_cfg
from core.code_generator import UnsupportedConstruct, generate_skeleton, regenerate_method, splice_method
from core.parser import parse_java
from core.py_parser import parse_python
from models.schemas import GenerateRequest, GenerateResponse

router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    s = state.require()
    lang = req.language or s.language
    graph = req.graph
    if graph.get("type") == "class":
        return GenerateResponse(code=generate_skeleton(s.ast))

    found = state.find_method(s.ast, graph.get("method"))
    if not found:
        raise HTTPException(404, "Метод не найден")
    _, method = found
    built, _ = build_cfg(method)
    original = {n.id: n.label for n in built}
    edits = {
        n["id"]: n["label"]
        for n in graph.get("nodes", [])
        if n.get("id") in original and n.get("label") is not None and n["label"] != original[n["id"]]
        and not str(n["label"]).startswith("START")
    }
    try:
        body, changed = regenerate_method(method, edits, language=lang)
        code = splice_method(s.code, method, body, language=lang)
    except UnsupportedConstruct as exc:
        raise HTTPException(422, str(exc)) from exc

    if lang == "python":
        errors = parse_python(code)["errors"]
        if errors:
            raise HTTPException(422, "Получился некорректный Python-код: " + "; ".join(errors))
    else:
        errors = parse_java(code)["errors"]
        if errors:
            raise HTTPException(422, "Получился некорректный Java-код: " + "; ".join(errors))
    return GenerateResponse(code=code, changed_nodes=changed)
