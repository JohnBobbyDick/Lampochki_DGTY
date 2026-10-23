"""Class diagram: classes, fields, methods, extends / implements."""

from __future__ import annotations

from models.schemas import GraphEdge, GraphNode


def _vis(mods: list[str]) -> str:
    if "public" in mods:
        return "+"
    if "private" in mods:
        return "-"
    if "protected" in mods:
        return "#"
    return "~"


def build_class_diagram(ast: dict) -> tuple[list[GraphNode], list[GraphEdge]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    names: set[str] = set()

    for cls in ast.get("classes", []):
        names.add(cls["name"])
        nodes.append(GraphNode(
            id=cls["name"], type="class", label=cls["name"],
            data={
                "line_start": cls.get("line_start"),
                "line_end": (cls.get("span") or {}).get("end", cls.get("line_start")),
                "code_snippet": f"class {cls['name']}",
                "fields": [f"{_vis(f['modifiers'])} {f['name']}: {f['type']}" for f in cls["fields"]],
                "methods": [
                    f"{_vis(m['modifiers'])} {m['name']}({', '.join(p['type'] for p in m['parameters'])}): {m['return_type']}"
                    for m in cls["methods"]
                ],
            },
        ))
    for itf in ast.get("interfaces", []):
        names.add(itf["name"])
        nodes.append(GraphNode(
            id=itf["name"], type="interface", label=f"«interface» {itf['name']}",
            data={
                "line_start": itf.get("line_start"),
                "line_end": (itf.get("span") or {}).get("end", itf.get("line_start")),
                "code_snippet": f"interface {itf['name']}",
                "fields": [],
                "methods": [
                    f"+ {m['name']}({', '.join(p['type'] for p in m['parameters'])}): {m['return_type']}"
                    for m in itf["methods"]
                ],
            },
        ))

    i = 0

    def link(src: str, dst: str, etype: str) -> None:
        nonlocal i
        base = dst.split("<")[0]
        if base in names:
            edges.append(GraphEdge(id=f"r{i}", source=src, target=base, type=etype, label=etype))
            i += 1

    for cls in ast.get("classes", []):
        if cls.get("extends"):
            link(cls["name"], cls["extends"], "extends")
        for impl in cls.get("implements", []):
            link(cls["name"], impl, "implements")
        # composition: field whose type is another known class
        for f in cls["fields"]:
            inner = f["type"].replace("[]", "")
            for part in inner.replace(">", "").replace(",", "<").split("<"):
                part = part.strip()
                if part in names and part != cls["name"]:
                    edges.append(GraphEdge(id=f"r{i}", source=cls["name"], target=part, type="normal", label="has"))
                    i += 1
                    break
    for itf in ast.get("interfaces", []):
        for ext in itf.get("extends", []):
            link(itf["name"], ext, "extends")
    return nodes, edges
