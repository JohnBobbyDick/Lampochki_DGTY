"""Python source-code parser built on top of the standard library *ast* module.

Produces a structured AST dictionary, a line_map (node-id -> line number),
and a list of syntax/parse errors, fully compatible with the Java AST schema
used by CFG builder, Call Graph, Class Diagram, and Defect Detector.
"""

from __future__ import annotations

import ast
import hashlib
import sys
from typing import Any


def _make_id(prefix: str, name: str) -> str:
    digest = hashlib.md5(f"{prefix}:{name}".encode()).hexdigest()[:8]
    return f"{prefix}_{name}_{digest}"


def _expr_to_str(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _extract_py_stmt(s: ast.stmt, line_map: dict[str, int], parent_id: str) -> dict[str, Any]:
    """Recursively convert a Python ast statement to a schema-compatible statement dict."""
    d: dict[str, Any] = {
        "line": getattr(s, "lineno", None),
        "line_end": getattr(s, "end_lineno", getattr(s, "lineno", None)),
    }
    stmt_id = _make_id(f"{parent_id}_s", f"{getattr(s, 'lineno', 0)}_{type(s).__name__}")
    d["id"] = stmt_id
    if d["line"] is not None:
        line_map[stmt_id] = d["line"]

    # 1. If / Elif
    if isinstance(s, ast.If):
        d["type"] = "IfStatement"
        d["condition"] = _expr_to_str(s.test)
        d["then"] = [_extract_py_stmt(x, line_map, stmt_id) for x in s.body]
        d["else"] = [_extract_py_stmt(x, line_map, stmt_id) for x in s.orelse] if s.orelse else []
        return d

    # 2. For loop
    if isinstance(s, (ast.For, ast.AsyncFor)):
        d["type"] = "ForStatement"
        d["control"] = f"{_expr_to_str(s.target)} in {_expr_to_str(s.iter)}"
        d["body"] = [_extract_py_stmt(x, line_map, stmt_id) for x in s.body]
        return d

    # 3. While loop
    if isinstance(s, ast.While):
        d["type"] = "WhileStatement"
        d["condition"] = _expr_to_str(s.test)
        d["body"] = [_extract_py_stmt(x, line_map, stmt_id) for x in s.body]
        return d

    # 4. Try / Except / Finally
    if isinstance(s, ast.Try):
        d["type"] = "TryStatement"
        d["body"] = [_extract_py_stmt(x, line_map, stmt_id) for x in s.body]
        catches: list[dict[str, Any]] = []
        for handler in s.handlers:
            htypes = [_expr_to_str(handler.type)] if handler.type else ["Exception"]
            catches.append({
                "types": htypes,
                "name": handler.name or "",
                "line": getattr(handler, "lineno", d["line"]),
                "body": [_extract_py_stmt(x, line_map, stmt_id) for x in handler.body],
            })
        d["catches"] = catches
        d["finally"] = [_extract_py_stmt(x, line_map, stmt_id) for x in s.finalbody] if s.finalbody else []
        return d

    # 5. Match (Python 3.10+)
    if hasattr(ast, "Match") and isinstance(s, ast.Match):
        d["type"] = "SwitchStatement"
        d["expression"] = _expr_to_str(s.subject)
        cases: list[dict[str, Any]] = []
        for case in s.cases:
            cases.append({
                "labels": [_expr_to_str(case.pattern)],
                "body": [_extract_py_stmt(x, line_map, stmt_id) for x in case.body],
            })
        d["cases"] = cases
        return d

    # 6. With statement (treat as block)
    if isinstance(s, (ast.With, ast.AsyncWith)):
        items_str = ", ".join(_expr_to_str(it) for it in s.items)
        d["type"] = "BlockStatement"
        d["raw"] = f"with {items_str}:"
        d["body"] = [_extract_py_stmt(x, line_map, stmt_id) for x in s.body]
        return d

    # 7. Control flow jumps
    if isinstance(s, ast.Return):
        d["type"] = "ReturnStatement"
        d["expression"] = _expr_to_str(s.value) if s.value else ""
        return d

    if isinstance(s, ast.Raise):
        d["type"] = "ThrowStatement"
        d["expression"] = _expr_to_str(s.exc) if s.exc else ""
        return d

    if isinstance(s, ast.Break):
        d["type"] = "BreakStatement"
        return d

    if isinstance(s, ast.Continue):
        d["type"] = "ContinueStatement"
        return d

    # 8. Variable declaration / Assignment
    if isinstance(s, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        d["type"] = "StatementExpression"
        d["expression"] = _expr_to_str(s)
        return d

    # 9. Expression (call, etc.)
    if isinstance(s, ast.Expr):
        d["type"] = "StatementExpression"
        d["expression"] = _expr_to_str(s.value)
        return d

    # 10. Pass, Assert, Global, Nonlocal, Delete
    d["type"] = "StatementExpression"
    d["expression"] = _expr_to_str(s)
    return d


def _extract_py_func(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    line_map: dict[str, int],
    cls_name: str,
) -> dict[str, Any]:
    fn_id = _make_id(f"fn_{cls_name}", fn.name)
    line_start = fn.lineno
    line_end = getattr(fn, "end_lineno", line_start)
    line_map[fn_id] = line_start

    # Parameters
    params: list[dict[str, str]] = []
    for arg in fn.args.args:
        ann = _expr_to_str(arg.annotation) if arg.annotation else ""
        params.append({"name": arg.arg, "type": ann or "Any"})
    if fn.args.vararg:
        params.append({"name": f"*{fn.args.vararg.arg}", "type": "tuple"})
    if fn.args.kwarg:
        params.append({"name": f"**{fn.args.kwarg.arg}", "type": "dict"})

    ret_type = _expr_to_str(fn.returns) if fn.returns else "None"
    modifiers = ["async"] if isinstance(fn, ast.AsyncFunctionDef) else []
    for dec in fn.decorator_list:
        dec_str = _expr_to_str(dec)
        if dec_str in ("staticmethod", "classmethod"):
            modifiers.append(dec_str)

    body_stmts: list[dict[str, Any]] = []
    # Skip standalone docstring if first expr
    stmts_to_parse = fn.body
    if stmts_to_parse and isinstance(stmts_to_parse[0], ast.Expr) and isinstance(stmts_to_parse[0].value, ast.Constant) and isinstance(stmts_to_parse[0].value.value, str):
        stmts_to_parse = stmts_to_parse[1:]

    for s in stmts_to_parse:
        body_stmts.append(_extract_py_stmt(s, line_map, fn_id))

    return {
        "id": fn_id,
        "name": fn.name,
        "return_type": ret_type,
        "modifiers": modifiers,
        "parameters": params,
        "line_start": line_start,
        "col": fn.col_offset,
        "span": {"start": line_start, "end": line_end},
        "body": body_stmts,
    }


def _extract_py_class(
    cls_node: ast.ClassDef,
    line_map: dict[str, int],
) -> dict[str, Any]:
    cls_id = _make_id("class", cls_node.name)
    line_start = cls_node.lineno
    line_end = getattr(cls_node, "end_lineno", line_start)
    line_map[cls_id] = line_start

    extends = [_expr_to_str(b) for b in cls_node.bases]
    methods: list[dict[str, Any]] = []
    fields: list[dict[str, Any]] = []

    for item in cls_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            m = _extract_py_func(item, line_map, cls_node.name)
            methods.append(m)
            # Check for attributes assigned to self inside __init__
            if item.name == "__init__":
                for sub in ast.walk(item):
                    if isinstance(sub, ast.Assign):
                        for tgt in sub.targets:
                            if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) and tgt.value.id == "self":
                                f_id = _make_id(f"{cls_id}.field", tgt.attr)
                                fields.append({
                                    "id": f_id,
                                    "name": tgt.attr,
                                    "type": "Any",
                                    "modifiers": ["private"] if tgt.attr.startswith("__") else ["public"],
                                    "line": getattr(sub, "lineno", line_start),
                                })
        elif isinstance(item, (ast.Assign, ast.AnnAssign)):
            # Class-level field
            targets = [item.target] if isinstance(item, ast.AnnAssign) else item.targets
            for t in targets:
                name = _expr_to_str(t)
                ann = _expr_to_str(item.annotation) if isinstance(item, ast.AnnAssign) else "Any"
                if name:
                    f_id = _make_id(f"{cls_id}.field", name)
                    fields.append({
                        "id": f_id,
                        "name": name,
                        "type": ann or "Any",
                        "modifiers": ["public"],
                        "line": getattr(item, "lineno", line_start),
                    })

    return {
        "id": cls_id,
        "name": cls_node.name,
        "modifiers": ["class"],
        "extends": extends[0] if extends else None,
        "implements": extends[1:] if len(extends) > 1 else [],
        "fields": fields,
        "methods": methods,
        "inner_classes": [],
        "line_start": line_start,
        "col": cls_node.col_offset,
        "span": {"start": line_start, "end": line_end},
    }


def parse_python(code: str) -> dict[str, Any]:
    """Parse Python source into a structured dict compatible with the Java AST format."""
    errors: list[str] = []
    line_map: dict[str, int] = {}
    ast_dict: dict[str, Any] = {
        "package": None,
        "imports": [],
        "classes": [],
        "interfaces": [],
        "enums": [],
        "language": "python",
    }

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        errors.append(f"Syntax error at line {exc.lineno}: {exc.msg}")
        return {"ast": ast_dict, "line_map": line_map, "errors": errors}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Parse error: {exc}")
        return {"ast": ast_dict, "line_map": line_map, "errors": errors}

    top_functions: list[dict[str, Any]] = []
    top_statements: list[dict[str, Any]] = []

    for node in tree.body:
        # 1. Imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                ast_dict["imports"].append({"path": alias.name, "alias": alias.asname})
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                ast_dict["imports"].append({"path": f"{mod}.{alias.name}", "alias": alias.asname})

        # 2. Classes
        elif isinstance(node, ast.ClassDef):
            cls_desc = _extract_py_class(node, line_map)
            ast_dict["classes"].append(cls_desc)

        # 3. Top-level functions
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_desc = _extract_py_func(node, line_map, "Module")
            top_functions.append(fn_desc)

        # 4. Top-level statements
        else:
            top_statements.append(_extract_py_stmt(node, line_map, "module_top"))

    # If there are top-level functions or statements, group them under a synthetic "Module" class
    if top_functions or top_statements or not ast_dict["classes"]:
        module_methods = list(top_functions)
        if top_statements:
            # Check if there is an `if __name__ == '__main__':` block in statements
            main_stmts = top_statements
            module_methods.append({
                "id": "fn_module_main",
                "name": "main",
                "return_type": "None",
                "modifiers": ["def"],
                "parameters": [],
                "line_start": top_statements[0]["line"] if top_statements[0].get("line") else 1,
                "col": 0,
                "span": {"start": top_statements[0]["line"] or 1, "end": top_statements[-1].get("line_end", 1)},
                "body": main_stmts,
            })
        ast_dict["classes"].insert(0, {
            "id": "class_module",
            "name": "Module",
            "modifiers": ["module"],
            "extends": None,
            "implements": [],
            "fields": [],
            "methods": module_methods,
            "inner_classes": [],
            "line_start": 1,
            "col": 0,
            "span": {"start": 1, "end": len(code.splitlines())},
        })

    return {"ast": ast_dict, "line_map": line_map, "errors": errors}
