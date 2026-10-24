"""Java source-code parser built on top of *javalang*.

Produces a structured AST dictionary, a *line_map* (node-id → line number),
and a list of parse errors.  The parser is intentionally lenient: when
javalang cannot parse the source it still returns as much information as
possible together with an error list.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import javalang
from javalang.tree import (
    ClassDeclaration,
    CompilationUnit,
    ConstructorDeclaration,
    EnumDeclaration,
    FieldDeclaration,
    FormalParameter,
    InterfaceDeclaration,
    MethodDeclaration,
    MethodInvocation,
    ClassCreator,
    MemberReference,
    VariableDeclarator,
    TryStatement,
    CatchClause,
    IfStatement,
    WhileStatement,
    ForStatement,
    DoStatement,
    SwitchStatement,
    SwitchStatementCase,
    ReturnStatement,
    ThrowStatement,
    BlockStatement,
    StatementExpression,
    LocalVariableDeclaration,
    BinaryOperation,
    Assignment,
    BasicType,
    ReferenceType,
    ArraySelector,
    SuperMethodInvocation,
    This,
    TernaryExpression,
    Cast,
    ArrayCreator,
    ArrayInitializer,
    LambdaExpression,
    InferredFormalParameter,
    MethodReference,
    VariableDeclaration,
    EnhancedForControl,
    ForControl,
    Literal,
    BreakStatement,
    ContinueStatement,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_java(code: str) -> dict[str, Any]:
    """Parse Java source into a structured dict.

    Returns
    -------
    dict
        Keys: ``ast`` (structured dict), ``line_map`` (node-id → line),
        ``errors`` (list[str]).
    """
    errors: list[str] = []
    line_map: dict[str, int] = {}
    ast_dict: dict[str, Any] = {
        "package": None,
        "imports": [],
        "classes": [],
        "interfaces": [],
        "enums": [],
    }

    try:
        tree: CompilationUnit = javalang.parse.parse(code)
    except javalang.parser.JavaSyntaxError as exc:
        errors.append(f"Syntax error: {exc}")
        # Try a best-effort tokenization to extract *something*
        ast_dict = _best_effort_parse(code, errors)
        return {"ast": ast_dict, "line_map": line_map, "errors": errors}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Parse error: {exc}")
        return {"ast": ast_dict, "line_map": line_map, "errors": errors}

    # Package
    if tree.package:
        ast_dict["package"] = tree.package.name

    # Imports
    ast_dict["imports"] = [
        {"path": imp.path, "static": imp.static, "wildcard": imp.wildcard}
        for imp in (tree.imports or [])
    ]

    code_lines = code.splitlines()

    # Walk top-level type declarations
    for path, node in tree.filter(ClassDeclaration):
        cls = _extract_class(node, code_lines, line_map)
        ast_dict["classes"].append(cls)

    for path, node in tree.filter(InterfaceDeclaration):
        iface = _extract_interface(node, code_lines, line_map)
        ast_dict["interfaces"].append(iface)

    for path, node in tree.filter(EnumDeclaration):
        enum = _extract_enum(node, code_lines, line_map)
        ast_dict["enums"].append(enum)

    _attach_spans(ast_dict, code)
    return {"ast": ast_dict, "line_map": line_map, "errors": errors}


def _attach_spans(ast_dict: dict, code: str) -> None:
    """Add a ``span`` ({start, end} lines incl. modifiers and closing brace)."""
    from core.source_map import declaration_span, tokenize

    tokens = tokenize(code)
    if not tokens:
        return

    def visit(decl: dict) -> None:
        for key in ("methods", "constructors"):
            for m in decl.get(key, []):
                if m.get("line_start") and m.get("col"):
                    sp = declaration_span(tokens, m["line_start"], m["col"])
                    if sp:
                        m["span"] = {"start": sp["start"], "end": sp["end"]}
                        bt = sp.get("body_start_tok")
                        if bt is not None:
                            pos = tokens[bt].position
                            m["body_open"] = {"line": pos.line, "col": pos.column}
        if decl.get("line_start") and decl.get("col"):
            sp = declaration_span(tokens, decl["line_start"], decl["col"])
            if sp:
                decl["span"] = {"start": sp["start"], "end": sp["end"]}
        for inner in decl.get("inner_classes", []):
            visit(inner)

    for c in ast_dict["classes"]:
        visit(c)
    for i in ast_dict["interfaces"]:
        visit(i)


# ---------------------------------------------------------------------------
# Class / interface / enum extraction
# ---------------------------------------------------------------------------

def _make_id(prefix: str, name: str) -> str:
    """Deterministic short id from prefix + name."""
    digest = hashlib.md5(f"{prefix}:{name}".encode()).hexdigest()[:8]
    return f"{prefix}_{name}_{digest}"


def _type_to_str(type_node: Any) -> str:
    """Convert a javalang type node to a readable string."""
    if type_node is None:
        return "void"
    if isinstance(type_node, BasicType):
        name = type_node.name
        dims = "[]" * len(type_node.dimensions) if type_node.dimensions else ""
        return f"{name}{dims}"
    if isinstance(type_node, ReferenceType):
        name = type_node.name
        args = ""
        if type_node.arguments:
            arg_strs = [_type_to_str(a.type) if hasattr(a, "type") else str(a) for a in type_node.arguments]
            args = f"<{', '.join(arg_strs)}>"
        dims = "[]" * len(type_node.dimensions) if type_node.dimensions else ""
        sub = ""
        if type_node.sub_type:
            sub = "." + _type_to_str(type_node.sub_type)
        return f"{name}{args}{sub}{dims}"
    return str(type_node)


def _modifiers_list(modifiers: Any) -> list[str]:
    """Extract modifier strings from a set/frozenset/None."""
    if modifiers is None:
        return []
    return sorted(str(m) for m in modifiers)


def _extract_class(node: ClassDeclaration, code_lines: list[str], line_map: dict[str, int]) -> dict:
    """Extract a full class description."""
    cls_id = _make_id("class", node.name)
    if node.position:
        line_map[cls_id] = node.position.line

    extends = None
    if node.extends:
        extends = _type_to_str(node.extends)

    implements: list[str] = []
    if node.implements:
        implements = [_type_to_str(i) for i in node.implements]

    fields = _extract_fields(node, code_lines, line_map, cls_id)
    methods = _extract_methods(node, code_lines, line_map, cls_id)
    constructors = _extract_constructors(node, code_lines, line_map, cls_id)

    # Inner classes
    inner_classes: list[dict] = []
    for member in (node.body or []):
        if isinstance(member, ClassDeclaration):
            inner_classes.append(_extract_class(member, code_lines, line_map))

    return {
        "id": cls_id,
        "name": node.name,
        "modifiers": _modifiers_list(node.modifiers),
        "extends": extends,
        "implements": implements,
        "fields": fields,
        "constructors": constructors,
        "methods": methods,
        "inner_classes": inner_classes,
        "line_start": node.position.line if node.position else None,
        "col": node.position.column if node.position else None,
    }


def _extract_interface(node: InterfaceDeclaration, code_lines: list[str], line_map: dict[str, int]) -> dict:
    """Extract an interface description."""
    iface_id = _make_id("iface", node.name)
    if node.position:
        line_map[iface_id] = node.position.line

    extends: list[str] = []
    if node.extends:
        extends = [_type_to_str(e) for e in node.extends]

    methods: list[dict] = []
    for member in (node.body or []):
        if isinstance(member, MethodDeclaration):
            m = _extract_single_method(member, code_lines, line_map, iface_id)
            methods.append(m)

    return {
        "id": iface_id,
        "name": node.name,
        "modifiers": _modifiers_list(node.modifiers),
        "extends": extends,
        "methods": methods,
        "line_start": node.position.line if node.position else None,
    }


def _extract_enum(node: EnumDeclaration, code_lines: list[str], line_map: dict[str, int]) -> dict:
    """Extract an enum description."""
    enum_id = _make_id("enum", node.name)
    if node.position:
        line_map[enum_id] = node.position.line

    constants: list[str] = []
    if node.body and hasattr(node.body, "constants") and node.body.constants:
        constants = [c.name for c in node.body.constants]
    elif hasattr(node, "constants") and node.constants:
        constants = [c.name for c in node.constants]

    return {
        "id": enum_id,
        "name": node.name,
        "modifiers": _modifiers_list(node.modifiers),
        "constants": constants,
        "line_start": node.position.line if node.position else None,
    }


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------

def _extract_fields(
    cls_node: ClassDeclaration,
    code_lines: list[str],
    line_map: dict[str, int],
    parent_id: str,
) -> list[dict]:
    """Extract field declarations from a class body."""
    fields: list[dict] = []
    for member in (cls_node.body or []):
        if isinstance(member, FieldDeclaration):
            type_str = _type_to_str(member.type)
            for decl in (member.declarators or []):
                f_id = _make_id(f"{parent_id}.field", decl.name)
                if member.position:
                    line_map[f_id] = member.position.line
                dims = ""
                if hasattr(decl, "dimensions") and decl.dimensions:
                    dims = "[]" * len(decl.dimensions)
                fields.append({
                    "id": f_id,
                    "name": decl.name,
                    "type": f"{type_str}{dims}",
                    "modifiers": _modifiers_list(member.modifiers),
                    "line": member.position.line if member.position else None,
                })
    return fields


# ---------------------------------------------------------------------------
# Methods & constructors
# ---------------------------------------------------------------------------

def _extract_methods(
    cls_node: ClassDeclaration,
    code_lines: list[str],
    line_map: dict[str, int],
    parent_id: str,
) -> list[dict]:
    """Extract all method declarations from a class body."""
    methods: list[dict] = []
    for member in (cls_node.body or []):
        if isinstance(member, MethodDeclaration):
            methods.append(_extract_single_method(member, code_lines, line_map, parent_id))
    return methods


def _extract_single_method(
    node: MethodDeclaration,
    code_lines: list[str],
    line_map: dict[str, int],
    parent_id: str,
) -> dict:
    """Extract one method declaration."""
    m_id = _make_id(f"{parent_id}.method", node.name)
    if node.position:
        line_map[m_id] = node.position.line

    params = _extract_params(node.parameters)
    return_type = _type_to_str(node.return_type) if node.return_type else "void"

    body_lines = _body_line_range(node, code_lines)
    body_ast = _extract_body_statements(node.body) if node.body else []

    throws: list[str] = []
    if node.throws:
        throws = [str(t) for t in node.throws]

    return {
        "id": m_id,
        "name": node.name,
        "modifiers": _modifiers_list(node.modifiers),
        "return_type": return_type,
        "parameters": params,
        "throws": throws,
        "body": body_ast,
        "body_lines": body_lines,
        "line_start": node.position.line if node.position else None,
        "col": node.position.column if node.position else None,
    }


def _extract_constructors(
    cls_node: ClassDeclaration,
    code_lines: list[str],
    line_map: dict[str, int],
    parent_id: str,
) -> list[dict]:
    """Extract constructor declarations."""
    constructors: list[dict] = []
    for member in (cls_node.body or []):
        if isinstance(member, ConstructorDeclaration):
            c_id = _make_id(f"{parent_id}.ctor", member.name)
            if member.position:
                line_map[c_id] = member.position.line

            params = _extract_params(member.parameters)
            body_lines = _body_line_range(member, code_lines)
            body_ast = _extract_body_statements(member.body) if member.body else []

            throws: list[str] = []
            if member.throws:
                throws = [str(t) for t in member.throws]

            constructors.append({
                "id": c_id,
                "name": member.name,
                "modifiers": _modifiers_list(member.modifiers),
                "parameters": params,
                "throws": throws,
                "body": body_ast,
                "body_lines": body_lines,
                "line_start": member.position.line if member.position else None,
                "col": member.position.column if member.position else None,
            })
    return constructors


def _extract_params(params: list | None) -> list[dict]:
    """Extract parameter list."""
    if not params:
        return []
    result: list[dict] = []
    for p in params:
        if isinstance(p, FormalParameter):
            result.append({
                "name": p.name,
                "type": _type_to_str(p.type),
                "varargs": getattr(p, "varargs", False),
            })
    return result


def _body_line_range(node: Any, code_lines: list[str]) -> dict:
    """Determine the start/end lines of a method/constructor body."""
    start = node.position.line if node.position else 1
    # Heuristic: walk all sub-nodes to find the max line
    end = start
    try:
        for _, child in node.filter(javalang.tree.Node):
            if hasattr(child, "position") and child.position:
                end = max(end, child.position.line)
    except Exception:
        pass
    return {"start": start, "end": end}


# ---------------------------------------------------------------------------
# Body statement extraction  (recursive, produces nested list[dict])
# ---------------------------------------------------------------------------

def _extract_body_statements(body: list | None) -> list[dict]:
    """Convert a javalang statement list into a JSON-serialisable form."""
    if not body:
        return []
    result: list[dict] = []
    for stmt in body:
        result.append(_stmt_to_dict(stmt))
    return result


def _stmt_to_dict(stmt: Any) -> dict:
    """Recursively convert a single statement to a dict."""
    if stmt is None:
        return {"type": "empty"}

    d: dict[str, Any] = {"type": type(stmt).__name__}
    if hasattr(stmt, "position") and stmt.position:
        d["line"] = stmt.position.line

    # ── IfStatement ────────────────────────────────────────────────────
    if isinstance(stmt, IfStatement):
        d["condition"] = _expr_to_str(stmt.condition)
        d["then"] = _extract_body_statements(
            stmt.then_statement if isinstance(stmt.then_statement, list)
            else ([stmt.then_statement] if stmt.then_statement else [])
        )
        d["else"] = _extract_body_statements(
            stmt.else_statement if isinstance(stmt.else_statement, list)
            else ([stmt.else_statement] if stmt.else_statement else [])
        )
        return d

    # ── For / While / Do ───────────────────────────────────────────────
    if isinstance(stmt, ForStatement):
        d["control"] = _expr_to_str(stmt.control) if stmt.control else ""
        d["body"] = _extract_body_statements(
            stmt.body if isinstance(stmt.body, list) else ([stmt.body] if stmt.body else [])
        )
        return d

    if isinstance(stmt, WhileStatement):
        d["condition"] = _expr_to_str(stmt.condition)
        d["body"] = _extract_body_statements(
            stmt.body if isinstance(stmt.body, list) else ([stmt.body] if stmt.body else [])
        )
        return d

    if isinstance(stmt, DoStatement):
        d["condition"] = _expr_to_str(stmt.condition)
        d["body"] = _extract_body_statements(
            stmt.body if isinstance(stmt.body, list) else ([stmt.body] if stmt.body else [])
        )
        return d

    # ── Switch ─────────────────────────────────────────────────────────
    if isinstance(stmt, SwitchStatement):
        d["expression"] = _expr_to_str(stmt.expression)
        cases: list[dict] = []
        for case in (stmt.cases or []):
            case_labels = [_expr_to_str(c) for c in case.case] if case.case else ["default"]
            case_body = _extract_body_statements(case.statements) if case.statements else []
            cases.append({"labels": case_labels, "body": case_body})
        d["cases"] = cases
        return d

    # ── Try / Catch / Finally ──────────────────────────────────────────
    if isinstance(stmt, TryStatement):
        d["body"] = _extract_body_statements(stmt.block) if stmt.block else []
        catches: list[dict] = []
        for catch in (stmt.catches or []):
            catch_types: list[str] = []
            if catch.parameter and catch.parameter.types:
                catch_types = [str(t) for t in catch.parameter.types]
            catch_name = catch.parameter.name if catch.parameter else ""
            catches.append({
                "types": catch_types,
                "name": catch_name,
                "body": _extract_body_statements(catch.block) if catch.block else [],
            })
        d["catches"] = catches
        res = getattr(stmt, "resources", None)
        if res:
            d["resources"] = [
                f"{_type_to_str(r.type)} {r.name} = {_expr_to_str(r.value)}" for r in res
            ]
        d["finally"] = _extract_body_statements(stmt.finally_block) if stmt.finally_block else []
        return d

    # ── Return / Throw ─────────────────────────────────────────────────
    if isinstance(stmt, ReturnStatement):
        d["expression"] = _expr_to_str(stmt.expression)
        return d

    if isinstance(stmt, ThrowStatement):
        d["expression"] = _expr_to_str(stmt.expression)
        return d

    # ── Block ──────────────────────────────────────────────────────────
    if isinstance(stmt, BlockStatement):
        d["body"] = _extract_body_statements(stmt.statements) if stmt.statements else []
        return d

    # ── Local variable declaration ─────────────────────────────────────
    if isinstance(stmt, LocalVariableDeclaration):
        d["var_type"] = _type_to_str(stmt.type)
        d["modifiers"] = _modifiers_list(getattr(stmt, "modifiers", None))
        declarators: list[dict] = []
        for decl in (stmt.declarators or []):
            declarators.append({
                "name": decl.name,
                "initializer": _expr_to_str(decl.initializer),
            })
        d["declarators"] = declarators
        return d

    # ── Statement expression (method call, assignment, etc.) ───────────
    if isinstance(stmt, StatementExpression):
        d["expression"] = _expr_to_str(stmt.expression)
        return d

    if isinstance(stmt, BreakStatement):
        d["label"] = stmt.goto
        return d
    if isinstance(stmt, ContinueStatement):
        d["label"] = stmt.goto
        return d

    # ── Fallback ───────────────────────────────────────────────────────
    d["raw"] = _expr_to_str(stmt)
    return d


# ---------------------------------------------------------------------------
# Expression → string helper
# ---------------------------------------------------------------------------

def _prefix_postfix(expr: Any, core: str) -> str:
    pre = "".join(getattr(expr, "prefix_operators", None) or [])
    post = "".join(getattr(expr, "postfix_operators", None) or [])
    sel = ""
    for s in (getattr(expr, "selectors", None) or []):
        if isinstance(s, ArraySelector):
            sel += f"[{_expr_to_str(s.index)}]"
        elif isinstance(s, MethodInvocation):
            args = ", ".join(_expr_to_str(a) for a in (s.arguments or []))
            sel += f".{s.member}({args})"
        elif isinstance(s, MemberReference):
            sel += f".{s.member}"
        else:
            sel += "." + _expr_to_str(s)
    return f"{pre}{core}{sel}{post}"


def _lambda_param(p: Any) -> str:
    """Lambda parameter text. javalang parses a bare `x -> …` parameter as a MemberReference."""
    if isinstance(p, InferredFormalParameter):
        return p.name
    if isinstance(p, MemberReference):
        return p.member
    if getattr(p, "type", None) is not None:
        return f"{_type_to_str(p.type)} {p.name}"
    return str(getattr(p, "name", p))


def _wrap(expr: Any, parent_op: str) -> str:
    text = _expr_to_str(expr)
    if isinstance(expr, BinaryOperation) and expr.operator != parent_op:
        return f"({text})"
    if isinstance(expr, (TernaryExpression, Assignment, LambdaExpression)):
        return f"({text})"
    return text


def _expr_to_str(expr: Any) -> str:
    """Best-effort conversion of any javalang expression/node to Java source."""
    if expr is None:
        return ""
    if isinstance(expr, str):
        return expr
    if isinstance(expr, (list, tuple, set)):
        return ", ".join(_expr_to_str(e) for e in expr)

    if isinstance(expr, MethodInvocation):
        qualifier = f"{expr.qualifier}." if expr.qualifier else ""
        args = ", ".join(_expr_to_str(a) for a in (expr.arguments or []))
        return _prefix_postfix(expr, f"{qualifier}{expr.member}({args})")

    if isinstance(expr, SuperMethodInvocation):
        args = ", ".join(_expr_to_str(a) for a in (expr.arguments or []))
        return _prefix_postfix(expr, f"super.{expr.member}({args})")

    if isinstance(expr, MemberReference):
        qualifier = f"{expr.qualifier}." if expr.qualifier else ""
        return _prefix_postfix(expr, f"{qualifier}{expr.member}")

    if isinstance(expr, This):
        qualifier = f"{expr.qualifier}." if getattr(expr, "qualifier", None) else ""
        return _prefix_postfix(expr, f"{qualifier}this")

    if isinstance(expr, BinaryOperation):
        return f"{_wrap(expr.operandl, expr.operator)} {expr.operator} {_wrap(expr.operandr, expr.operator)}"

    if isinstance(expr, Assignment):
        return f"{_expr_to_str(expr.expressionl)} {expr.type} {_expr_to_str(expr.value)}"

    if isinstance(expr, TernaryExpression):
        return (f"{_wrap(expr.condition, '?')} ? {_wrap(expr.if_true, '?')} : "
                f"{_wrap(expr.if_false, '?')}")

    if isinstance(expr, Cast):
        return _prefix_postfix(expr, f"({_type_to_str(expr.type)}) {_wrap(expr.expression, 'cast')}")

    if isinstance(expr, ClassCreator):
        args = ", ".join(_expr_to_str(a) for a in (expr.arguments or []))
        diamond = "<>" if (isinstance(expr.type, ReferenceType) and expr.type.arguments == []) else ""
        tname = _type_to_str(expr.type)
        if diamond and "<" not in tname:
            tname += diamond
        return _prefix_postfix(expr, f"new {tname}({args})")

    if isinstance(expr, ArrayCreator):
        dims = "".join(f"[{_expr_to_str(d)}]" if d is not None else "[]" for d in (expr.dimensions or []))
        init = f" {_expr_to_str(expr.initializer)}" if expr.initializer else ""
        base = _type_to_str(expr.type).replace("[]", "")
        return f"new {base}{dims}{init}"

    if isinstance(expr, ArrayInitializer):
        return "{" + ", ".join(_expr_to_str(i) for i in (expr.initializers or [])) + "}"

    if isinstance(expr, LambdaExpression):
        params = ", ".join(_lambda_param(p) for p in (expr.parameters or []))
        body = expr.body
        if isinstance(body, list):
            body_s = "{ " + " ".join(_stmt_text(s) for s in body) + " }"
        else:
            body_s = _expr_to_str(body)
        return f"({params}) -> {body_s}"

    if isinstance(expr, MethodReference):
        return f"{_expr_to_str(expr.expression)}::{_expr_to_str(expr.method)}"

    if isinstance(expr, VariableDeclaration):
        names = ", ".join(
            d.name + ("[]" * len(d.dimensions) if getattr(d, "dimensions", None) else "")
            + (f" = {_expr_to_str(d.initializer)}" if d.initializer is not None else "")
            for d in (expr.declarators or [])
        )
        return f"{_type_to_str(expr.type)} {names}"

    if isinstance(expr, EnhancedForControl):
        var = expr.var
        return f"{_type_to_str(var.type)} {var.declarators[0].name} : {_expr_to_str(expr.iterable)}"

    if isinstance(expr, ForControl):
        init = _expr_to_str(expr.init) if expr.init else ""
        cond = _expr_to_str(expr.condition) if expr.condition else ""
        upd = _expr_to_str(expr.update) if expr.update else ""
        return f"{init}; {cond}; {upd}"

    if isinstance(expr, ReferenceType) or isinstance(expr, BasicType):
        return _type_to_str(expr)

    if isinstance(expr, Literal):
        return _prefix_postfix(expr, str(expr.value))

    if hasattr(expr, "value"):
        return str(expr.value)

    return type(expr).__name__


def _stmt_text(stmt: Any) -> str:
    """Single-line text for a raw javalang statement (used inside lambdas)."""
    if isinstance(stmt, StatementExpression):
        return _expr_to_str(stmt.expression) + ";"
    if isinstance(stmt, ReturnStatement):
        return f"return {_expr_to_str(stmt.expression)};".replace("return ;", "return;")
    if isinstance(stmt, LocalVariableDeclaration):
        return _expr_to_str(stmt) + ";"
    return _expr_to_str(stmt)


# ---------------------------------------------------------------------------
# Best-effort parse (token-level fallback)
# ---------------------------------------------------------------------------

def _best_effort_parse(code: str, errors: list[str]) -> dict:
    """Attempt to extract basic structure via tokenization when full parse fails."""
    ast_dict: dict[str, Any] = {
        "package": None,
        "imports": [],
        "classes": [],
        "interfaces": [],
        "enums": [],
    }
    try:
        tokens = list(javalang.tokenizer.tokenize(code))
    except Exception as exc:
        errors.append(f"Tokenization error: {exc}")
        return ast_dict

    # Very simple heuristic: find class / interface declarations via tokens
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.value == "class" and i + 1 < len(tokens):
            name = tokens[i + 1].value
            cls_id = _make_id("class", name)
            ast_dict["classes"].append({
                "id": cls_id,
                "name": name,
                "modifiers": [],
                "extends": None,
                "implements": [],
                "fields": [],
                "constructors": [],
                "methods": [],
                "inner_classes": [],
                "line_start": tok.position.line if tok.position else None,
            })
        elif tok.value == "interface" and i + 1 < len(tokens):
            name = tokens[i + 1].value
            iface_id = _make_id("iface", name)
            ast_dict["interfaces"].append({
                "id": iface_id,
                "name": name,
                "modifiers": [],
                "extends": [],
                "methods": [],
                "line_start": tok.position.line if tok.position else None,
            })
        i += 1

    return ast_dict
