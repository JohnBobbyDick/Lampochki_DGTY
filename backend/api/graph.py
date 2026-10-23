from fastapi import APIRouter, HTTPException

import state
from core.bigo_analyzer import analyze_ast
from core.call_graph import build_call_graph
from core.cfg_builder import build_cfg
from core.class_diagram import build_class_diagram
from core.defect_detector import detect_defects
from models.schemas import GraphNode, GraphResponse

router = APIRouter()


def _camel_data(node: GraphNode) -> GraphNode:
    mapping = {"line_start": "lineStart", "line_end": "lineEnd", "code_snippet": "codeSnippet", "big_o": "bigO"}
    node.data = {mapping.get(k, k): v for k, v in node.data.items()}
    return node


@router.get("/graph", response_model=GraphResponse)
def graph(type: str = "cfg", method: str | None = None) -> GraphResponse:
    s = state.require()
    bigo = analyze_ast(s.ast)

    if type == "cfg":
        found = state.find_method(s.ast, method)
        if not found:
            raise HTTPException(404, f"Метод не найден: {method}" if method else "В коде нет методов")
        cls, m = found
        nodes, edges = build_cfg(m)
        key = f"{cls['name']}.{m['name']}"
        for n in nodes:
            if n.type == "start":
                n.data["big_o"] = bigo.get(key)
                n.label = f"START · {key}"
        for d in detect_defects(s.ast, s.code, bigo):
            if d.method == key and d.node_id:
                for n in nodes:
                    if n.id == d.node_id:
                        n.data.setdefault("defects", []).append(d.message)
    elif type == "call":
        nodes, edges = build_call_graph(s.ast, bigo)
    elif type == "class":
        nodes, edges = build_class_diagram(s.ast)
    else:
        raise HTTPException(400, "type должен быть cfg | call | class")
    return GraphResponse(nodes=[_camel_data(n) for n in nodes], edges=edges)
