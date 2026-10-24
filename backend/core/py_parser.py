"""Python source-code parser built on top of the standard library *ast* module.

Produces a structured AST dictionary, a line_map (node-id -> line number),
and a list of syntax/parse errors, compatible with the Java AST schema
used by CFG builder, Call Graph, Class Diagram, and Defect Detector.

Python-specific additions (see docs/superpowers/plans/2026-10-24-stage7-python.md, «Решения»):
statement text is taken from the source (``ast.get_source_segment``), every statement has
``span = {line, col, end_line, end_col}`` (``col`` — 0-based character offset), compound statements
(and except/case clauses) have ``header`` — from the keyword up to the header ``:`` (excluded).
"""

from __future__ import annotations

import ast
import hashlib
import re
import textwrap
import tokenize
from typing import Any

_LINE_RE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$")
_OPEN = "([{"
_CLOSE = ")]}"


def _make_id(prefix: str, name: str) -> str:
    digest = hashlib.md5(f"{prefix}:{name}".encode()).hexdigest()[:8]
    return f"{prefix}_{name}_{digest}"


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001
        return ""


def _is_docstring(s: ast.stmt) -> bool:
    return (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
            and isinstance(s.value.value, str))


class _Extractor:
    """Walks one module; keeps the source for text/position lookups."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.lines = _LINE_RE.findall(code)
        self.line_map: dict[str, int] = {}
        self._collect: list[list[dict[str, Any]]] = []  # nested-def methods of the current function
        self._names: list[str] = []  # qualified name of the current function

    # -- positions and text ------------------------------------------------

    def _line(self, lineno: int) -> str:
        return self.lines[lineno - 1] if 0 < lineno <= len(self.lines) else ""

    def _char_col(self, lineno: int, byte_col: int) -> int:
        """ast offsets are UTF-8 bytes; convert to characters."""
        return len(self._line(lineno).encode("utf-8")[:byte_col].decode("utf-8", errors="replace"))

    def _start(self, node: ast.AST) -> tuple[int, int]:
        return node.lineno, self._char_col(node.lineno, node.col_offset)

    def _end(self, node: ast.AST) -> tuple[int, int]:
        end_line = getattr(node, "end_lineno", None) or node.lineno
        end_col = getattr(node, "end_col_offset", None)
        if end_col is None:
            return end_line, len(self._line(end_line).rstrip("\r\n"))
        return end_line, self._char_col(end_line, end_col)

    def span(self, node: ast.AST) -> dict[str, int]:
        (line, col), (end_line, end_col) = self._start(node), self._end(node)
        return {"line": line, "col": col, "end_line": end_line, "end_col": end_col}

    def text(self, line: int, col: int, end_line: int, end_col: int) -> str:
        """Source between two character positions; continuation lines dedented against the first."""
        if line == end_line:
            return self._line(line)[col:end_col]
        parts = [self._line(line)[col:]]
        parts += self.lines[line:end_line - 1]
        parts.append(self._line(end_line)[:end_col])
        raw = "".join(parts).replace("\r\n", "\n").replace("\r", "\n")
        return textwrap.dedent(" " * col + raw).lstrip(" ")

    def seg(self, node: ast.AST | None) -> str:
        if node is None:
            return ""
        try:
            (line, col), (end_line, end_col) = self._start(node), self._end(node)
            out = self.text(line, col, end_line, end_col)
        except Exception:  # noqa: BLE001
            out = ""
        return out or _unparse(node)

    def seg_between(self, first: ast.AST, last: ast.AST) -> str:
        (line, col), (end_line, end_col) = self._start(first), self._end(last)
        return self.text(line, col, end_line, end_col)

    def header(self, line: int, col: int) -> dict[str, int]:
        """Range from (line, col) to the header ``:`` (excluded): the first ``:`` at bracket depth 0
        that does not belong to a depth-0 ``lambda``."""
        first = self._line(line)[col:]
        rest = iter(self.lines[line:])

        def readline() -> str:
            nonlocal first
            if first is not None:
                out, first = first, None
                return out
            return next(rest, "")

        def absolute(pos: tuple[int, int]) -> tuple[int, int]:
            row, c = pos
            return line + row - 1, (col + c if row == 1 else c)

        depth = lambdas = 0
        last_end: tuple[int, int] | None = None
        skip = (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)
        try:
            for tok in tokenize.generate_tokens(readline):
                if tok.type in skip:
                    continue
                if tok.type == tokenize.ENDMARKER:
                    break
                if tok.type == tokenize.OP:
                    if tok.string in _OPEN:
                        depth += 1
                    elif tok.string in _CLOSE:
                        depth -= 1
                    elif tok.string == ":" and depth == 0:
                        if lambdas:
                            lambdas -= 1
                        elif last_end is not None:
                            end_line, end_col = absolute(last_end)
                            return {"line": line, "col": col, "end_line": end_line, "end_col": end_col}
                elif tok.type == tokenize.NAME and tok.string == "lambda" and depth == 0:
                    lambdas += 1
                last_end = tok.end
        except (tokenize.TokenError, SyntaxError):
            pass
        # fallback: the rest of the first line without a trailing colon/comment
        text = self._line(line)[col:].split("#", 1)[0].rstrip().rstrip(":").rstrip()
        return {"line": line, "col": col, "end_line": line, "end_col": col + len(text)}

    def header_of(self, node: ast.AST) -> dict[str, int]:
        return self.header(*self._start(node))

    def header_text(self, rng: dict[str, int]) -> str:
        return self.text(rng["line"], rng["col"], rng["end_line"], rng["end_col"])

    def keyword_header(self, after: ast.AST, keyword: str) -> dict[str, int] | None:
        """Header of a clause keyword (``finally``) that follows *after*: only blank/comment lines between."""
        start = getattr(after, "end_lineno", None) or after.lineno
        for lineno in range(start + 1, len(self.lines) + 1):
            stripped = self._line(lineno).lstrip()
            if re.match(rf"{keyword}\s*:", stripped):
                return self.header(lineno, len(self._line(lineno)) - len(stripped))
        return None

    # -- statements --------------------------------------------------------

    def stmts(self, body: list[ast.stmt], parent_id: str) -> list[dict[str, Any]]:
        return [self.stmt(x, parent_id) for x in body]

    def stmt(self, s: ast.stmt, parent_id: str) -> dict[str, Any]:
        d: dict[str, Any] = {
            "line": getattr(s, "lineno", None),
            "line_end": getattr(s, "end_lineno", getattr(s, "lineno", None)),
        }
        stmt_id = _make_id(f"{parent_id}_s", f"{getattr(s, 'lineno', 0)}_{type(s).__name__}")
        d["id"] = stmt_id
        if d["line"] is not None:
            self.line_map[stmt_id] = d["line"]
        d["span"] = self.span(s)

        if isinstance(s, ast.If):
            d["type"] = "IfStatement"
            d["header"] = self.header_of(s)
            d["condition"] = self.seg(s.test)
            d["then"] = self.stmts(s.body, stmt_id)
            d["else"] = self.stmts(s.orelse, stmt_id)
            if len(s.orelse) == 1 and isinstance(s.orelse[0], ast.If):
                line, col = self._start(s.orelse[0])
                if self._line(line)[col:].startswith("elif"):
                    d["else"][0]["elif"] = True
            return d

        if isinstance(s, (ast.For, ast.AsyncFor)):
            d["type"] = "ForStatement"
            d["header"] = self.header_of(s)
            d["control"] = self.seg_between(s.target, s.iter)
            d["body"] = self.stmts(s.body, stmt_id)
            d["else"] = self.stmts(s.orelse, stmt_id)
            return d

        if isinstance(s, ast.While):
            d["type"] = "WhileStatement"
            d["header"] = self.header_of(s)
            d["condition"] = self.seg(s.test)
            d["body"] = self.stmts(s.body, stmt_id)
            d["else"] = self.stmts(s.orelse, stmt_id)
            return d

        if isinstance(s, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            d["type"] = "TryStatement"
            d["header"] = self.header_of(s)
            d["body"] = self.stmts(s.body, stmt_id)
            catches: list[dict[str, Any]] = []
            for handler in s.handlers:
                catches.append({
                    "types": [self.seg(handler.type)] if handler.type else [],
                    "name": handler.name or "",
                    "line": getattr(handler, "lineno", d["line"]),
                    "span": self.span(handler),
                    "header": self.header_of(handler),
                    "body": self.stmts(handler.body, stmt_id),
                })
            d["catches"] = catches
            d["else"] = self.stmts(s.orelse, stmt_id)
            d["finally"] = self.stmts(s.finalbody, stmt_id)
            if s.finalbody:
                before = (s.orelse or (s.handlers and s.handlers[-1].body) or s.body)[-1]
                fin = self.keyword_header(before, "finally")
                if fin:
                    d["finally_header"] = fin
            return d

        if isinstance(s, ast.Match):
            d["type"] = "SwitchStatement"
            d["header"] = self.header_of(s)
            d["expression"] = self.seg(s.subject)
            d["no_fallthrough"] = True
            d["cases"] = [self.case(c, stmt_id, d["line"]) for c in s.cases]
            return d

        if isinstance(s, (ast.With, ast.AsyncWith)):
            d["type"] = "WithStatement"
            d["header"] = self.header_of(s)
            last = s.items[-1]
            d["items"] = self.seg_between(s.items[0].context_expr, last.optional_vars or last.context_expr)
            d["body"] = self.stmts(s.body, stmt_id)
            return d

        if isinstance(s, ast.Return):
            d["type"] = "ReturnStatement"
            d["expression"] = self.seg(s.value)
            return d

        if isinstance(s, ast.Raise):
            d["type"] = "ThrowStatement"
            d["expression"] = self.seg_between(s.exc, s.cause or s.exc) if s.exc else ""
            return d

        if isinstance(s, ast.Break):
            d["type"] = "BreakStatement"
            return d

        if isinstance(s, ast.Continue):
            d["type"] = "ContinueStatement"
            return d

        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and self._collect:
            d["type"] = "StatementExpression"
            d["expression"] = self.header_text(self.header_of(s))
            d["nested_def"] = True
            cls_name, qual = self._names[-1]
            self._collect[-1].extend(self.func(s, cls_name, f"{qual}.{s.name}"))
            return d

        d["type"] = "StatementExpression"
        if isinstance(s, ast.ClassDef):
            d["expression"] = self.header_text(self.header_of(s))
        elif isinstance(s, ast.Expr):
            d["expression"] = self.seg(s.value)
        else:  # assignments, pass, assert, global, nonlocal, del, import, …
            d["expression"] = self.seg(s)
        return d

    def case(self, c: ast.match_case, parent_id: str, line: int | None) -> dict[str, Any]:
        p_line, p_col = self._start(c.pattern)
        kw_col = self._line(p_line)[:p_col].rstrip().rfind("case")
        hdr = self.header(p_line, max(kw_col, 0))
        last = c.body[-1] if c.body else c.pattern
        end_line, end_col = self._end(last)
        return {
            "labels": [self.seg(c.pattern)],
            "guard": self.seg(c.guard) if c.guard is not None else None,
            "line": p_line or line,
            "header": hdr,
            "span": {"line": hdr["line"], "col": hdr["col"], "end_line": end_line, "end_col": end_col},
            "body": self.stmts(c.body, parent_id),
        }

    # -- functions and classes ---------------------------------------------

    def func(self, fn: ast.FunctionDef | ast.AsyncFunctionDef, cls_name: str,
             qual: str | None = None) -> list[dict[str, Any]]:
        """The method for *fn* followed by the methods of its nested defs (``outer.inner``)."""
        qual = qual or fn.name
        fn_id = _make_id(f"fn_{cls_name}", qual)
        line_start = fn.lineno
        line_end = getattr(fn, "end_lineno", line_start)
        self.line_map[fn_id] = line_start

        params: list[dict[str, str]] = []
        for arg in fn.args.posonlyargs + fn.args.args:
            ann = self.seg(arg.annotation) if arg.annotation else ""
            params.append({"name": arg.arg, "type": ann or "Any"})
        if fn.args.vararg:
            params.append({"name": f"*{fn.args.vararg.arg}", "type": "tuple"})
        for arg in fn.args.kwonlyargs:
            ann = self.seg(arg.annotation) if arg.annotation else ""
            params.append({"name": arg.arg, "type": ann or "Any"})
        if fn.args.kwarg:
            params.append({"name": f"**{fn.args.kwarg.arg}", "type": "dict"})

        ret_type = self.seg(fn.returns) if fn.returns else "None"
        modifiers = ["async"] if isinstance(fn, ast.AsyncFunctionDef) else []
        for dec in fn.decorator_list:
            dec_str = _unparse(dec)
            if dec_str in ("staticmethod", "classmethod"):
                modifiers.append(dec_str)

        body = fn.body[1:] if fn.body and _is_docstring(fn.body[0]) else fn.body
        nested: list[dict[str, Any]] = []
        self._collect.append(nested)
        self._names.append((cls_name, qual))
        try:
            body_stmts = self.stmts(body, fn_id)
        finally:
            self._collect.pop()
            self._names.pop()

        method = {
            "id": fn_id,
            "name": qual,
            "return_type": ret_type,
            "modifiers": modifiers,
            "parameters": params,
            "line_start": line_start,
            "col": fn.col_offset,
            "span": {"start": line_start, "end": line_end},
            "body": body_stmts,
            "language": "python",
            "synthetic": False,
        }
        return [method, *nested]

    def cls(self, cls_node: ast.ClassDef) -> dict[str, Any]:
        cls_id = _make_id("class", cls_node.name)
        line_start = cls_node.lineno
        line_end = getattr(cls_node, "end_lineno", line_start)
        self.line_map[cls_id] = line_start

        extends = [_unparse(b) for b in cls_node.bases]
        methods: list[dict[str, Any]] = []
        fields: list[dict[str, Any]] = []

        for item in cls_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.extend(self.func(item, cls_node.name))
                if item.name == "__init__":  # attributes assigned to self inside __init__
                    for sub in ast.walk(item):
                        if isinstance(sub, ast.Assign):
                            for tgt in sub.targets:
                                if (isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name)
                                        and tgt.value.id == "self"):
                                    fields.append({
                                        "id": _make_id(f"{cls_id}.field", tgt.attr),
                                        "name": tgt.attr,
                                        "type": "Any",
                                        "modifiers": ["private"] if tgt.attr.startswith("__") else ["public"],
                                        "line": getattr(sub, "lineno", line_start),
                                    })
            elif isinstance(item, (ast.Assign, ast.AnnAssign)):
                targets = [item.target] if isinstance(item, ast.AnnAssign) else item.targets
                for t in targets:
                    name = _unparse(t)
                    ann = _unparse(item.annotation) if isinstance(item, ast.AnnAssign) else "Any"
                    if name:
                        fields.append({
                            "id": _make_id(f"{cls_id}.field", name),
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
        return {"ast": ast_dict, "line_map": {}, "errors": errors}
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Parse error: {exc}")
        return {"ast": ast_dict, "line_map": {}, "errors": errors}

    ex = _Extractor(code)
    top_functions: list[dict[str, Any]] = []
    top_nodes: list[ast.stmt] = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                ast_dict["imports"].append({"path": alias.name, "alias": alias.asname})
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                ast_dict["imports"].append({"path": f"{mod}.{alias.name}", "alias": alias.asname})
        elif isinstance(node, ast.ClassDef):
            ast_dict["classes"].append(ex.cls(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_functions.extend(ex.func(node, "Module"))
        else:
            top_nodes.append(node)

    # the pseudo-method for top-level statements must not clash with a user's own `def main()`
    taken = {f["name"] for f in top_functions}
    main_name = "main" if "main" not in taken else "__main__"
    nested: list[dict[str, Any]] = []
    ex._collect.append(nested)
    ex._names.append(("Module", main_name))
    top_statements = ex.stmts(top_nodes, "module_top")
    ex._collect.pop()
    ex._names.pop()

    # top-level functions and statements are grouped under a synthetic "Module" class
    if top_functions or top_statements or not ast_dict["classes"]:
        module_methods = list(top_functions)
        if top_statements:
            first_line = top_statements[0].get("line") or 1
            module_methods.append({
                "id": "fn_module_main",
                "name": main_name,
                "return_type": "None",
                "modifiers": ["def"],
                "parameters": [],
                "line_start": first_line,
                "col": 0,
                "span": {"start": first_line, "end": top_statements[-1].get("line_end", 1)},
                "body": top_statements,
                "language": "python",
                "synthetic": True,
            })
            module_methods.extend(nested)
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

    return {"ast": ast_dict, "line_map": ex.line_map, "errors": errors}
