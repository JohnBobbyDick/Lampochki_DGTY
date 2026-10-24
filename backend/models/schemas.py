"""Pydantic models for the Java Blueprints API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model: snake_case in Python, camelCase on the wire."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ── Parse ──────────────────────────────────────────────────────────────────────

class ParseRequest(CamelModel):
    """Request body for parsing Java source code."""
    code: str = Field(..., description="Java source code to parse")


class ParseResponse(CamelModel):
    """Response containing the parsed AST."""
    ast: dict = Field(default_factory=dict, description="Structured AST dictionary")
    line_map: dict = Field(default_factory=dict, description="Node ID → line number mapping")
    errors: list[str] = Field(default_factory=list, description="Parse errors, if any")
    methods: list[str] = Field(default_factory=list, description="Method names found")
    classes: list[str] = Field(default_factory=list, description="Class names found")


# ── Graph ──────────────────────────────────────────────────────────────────────

class GraphRequest(CamelModel):
    """Query parameters for graph generation."""
    type: str = Field(..., description="Graph type: 'cfg', 'call', or 'class'")
    method: str | None = Field(None, description="Method name (required for CFG)")


class GraphNode(CamelModel):
    """Single node in a graph."""
    id: str
    type: str = Field(..., description="Node type, e.g. 'start', 'end', 'statement', 'condition'")
    label: str = Field(..., description="Human-readable label")
    data: dict = Field(
        default_factory=dict,
        description="Extra data: line_start, line_end, code_snippet, etc.",
    )


class GraphEdge(CamelModel):
    """Single edge in a graph."""
    id: str
    source: str
    target: str
    type: str = Field(
        "normal",
        description="Edge type: 'normal', 'true', 'false', 'back', 'exception'",
    )
    label: str = Field("", description="Optional label on the edge")


class GraphResponse(CamelModel):
    """Response containing nodes and edges of a graph."""
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


# ── Analyze ────────────────────────────────────────────────────────────────────

class Defect(CamelModel):
    """A single detected code defect."""
    line_start: int
    line_end: int
    node_id: str = ""
    method: str = ""
    severity: str = Field("warning", description="'hint', 'warning', or 'error'")
    big_o: str = Field("", description="Big-O impact if relevant")
    message: str
    recommendation: str = ""


class AnalyzeResponse(CamelModel):
    """Response with defect list and Big-O analysis per method."""
    defects: list[Defect] = Field(default_factory=list)
    bigo: dict = Field(default_factory=dict, description="method_name → O(...) mapping")
    compile_errors: list[dict] | None = Field(default=None, description="javac errors {file, line, message}; [] when javac ran clean, null when javac did not run")


# ── Generate ───────────────────────────────────────────────────────────────────

class GenerateRequest(CamelModel):
    """Request to generate Java code from an edited graph."""
    graph: dict = Field(..., description="Graph dict: {type, method, nodes:[{id,label}], edges}")


class GenerateResponse(CamelModel):
    """Response with generated Java code."""
    code: str
    changed_nodes: list[str] = Field(default_factory=list)


# ── Run ────────────────────────────────────────────────────────────────────────

class RunRequest(CamelModel):
    """Request to compile and run Java code."""
    code: str
    main_class: str | None = Field(None, description="Name of the class containing main(); autodetected if omitted")
    stdin_input: str = Field("", description="Text to feed via stdin")
    timeout_sec: int = Field(10, description="Execution timeout")


class RunResponse(CamelModel):
    """Result of running Java code."""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    duration_ms: int = 0
    compile_errors: list[dict] = Field(default_factory=list, description="[{line, message}] from javac")


# ── Compare ────────────────────────────────────────────────────────────────────

class CompareRequest(CamelModel):
    """Request to run and compare two versions of Java code."""
    original: str
    modified: str
    main_class: str | None = None
    stdin_input: str = ""


class CompareResponse(CamelModel):
    """Comparison result between original and modified code runs."""
    before: RunResponse
    after: RunResponse
    diff: str = ""
    behavior_preserved: bool = True


# ── Decompose ──────────────────────────────────────────────────────────────────

class DecomposedFile(CamelModel):
    """One file proposed by the decomposer."""
    name: str
    methods: list[str] = Field(default_factory=list)
    code: str = ""


class DecomposeRequest(CamelModel):
    code: str | None = Field(None, description="Source to decompose; defaults to last parsed code")


class DecomposeResponse(CamelModel):
    """Response with decomposition suggestions."""
    files: list[DecomposedFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── Quality Gate ───────────────────────────────────────────────────────────────

class QualityGateResponse(CamelModel):
    """Result of running the quality gate checks."""
    passed: bool
    details: dict = Field(default_factory=dict)


# ── AI ─────────────────────────────────────────────────────────────────────────

class AiStatus(CamelModel):
    enabled: bool
    provider: str = ""
    model: str = ""


class AiPatch(CamelModel):
    old_code: str
    new_code: str
    imports: list[str] = Field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    valid: bool = True
    problems: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    bigo_before: dict[str, str] = Field(default_factory=dict)
    bigo_after: dict[str, str] = Field(default_factory=dict)


class AiBigoCombinedRequest(CamelModel):
    code: str
    patches: list[AiPatch] = Field(default_factory=list)


class AiBigoCombinedResponse(CamelModel):
    bigo: dict[str, str] = Field(default_factory=dict)


class AiApplyRequest(CamelModel):
    code: str = Field(..., description="Current editor content")
    patch: AiPatch


class AiApplyResponse(CamelModel):
    ok: bool
    code: str
    problems: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    start_line: int = 0
    end_line: int = 0


class AiExplainRequest(CamelModel):
    defect: dict = Field(..., description="Defect as returned by /api/analyze")
    code_fragment: str | None = Field(None, description="Overrides the fragment taken from the parsed code")


class AiExplainResponse(CamelModel):
    explanation: str
    fixed_code: str = ""
    patch: AiPatch | None = None
    source: str = Field("static", description="gemini | ollama | static")
    note: str = ""


class AiFixRequest(CamelModel):
    code: str
    line: int | None = None
    message: str


class AiSuggestRequest(CamelModel):
    code_fragment: str
    context: str = ""


class AiSuggestResponse(CamelModel):
    suggestion: str
    example: str = ""
    source: str = "static"
    note: str = ""


class AiDecomposeResponse(CamelModel):
    advice: str
    source: str = "static"
    note: str = ""


class AiReviewRequest(CamelModel):
    code: str


class AiReviewItem(CamelModel):
    line: int | None = None
    title: str = ""
    detail: str = ""
    example: str = ""
    patch: AiPatch | None = None


class AiReviewResponse(CamelModel):
    summary: str = ""
    suggestions: list[AiReviewItem] = Field(default_factory=list)
    source: str = "none"
    note: str = ""


# ── Files ──────────────────────────────────────────────────────────────────────

class ZipFile(CamelModel):
    """One file to put into the downloaded archive; `path` is the project file id (`src/Demo.java`)."""
    path: str
    code: str


class ZipRequest(CamelModel):
    files: list[ZipFile]
