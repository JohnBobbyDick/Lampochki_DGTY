# AGENTS.md

This file provides guidance to Codex (claude.ai/code) when working with code in this repository.

**Java Blueprints** — a Java code visualizer/analyzer: editor ↔ graph (CFG / Call Graph / Class Diagram), defect
diagnostics and Big O, code regeneration from edited graph nodes, monolith decomposition, running Java with a
Quality Gate, and optional Gemini/Ollama AI hints. UI text, error messages and docs are in Russian — keep new
user-facing strings in Russian.

## Commands

```bash
# Full stack (UI on http://localhost, nginx proxies /api to backend:8000)
docker compose up --build

# Backend — Python 3.11+, needs JDK 11+ (javac/java) on PATH
cd backend && python3 -m venv venv && source venv/bin/activate && pip3 install -r requirements.txt
uvicorn main:app --reload --port 8000
python -m pytest                                   # all tests (run from backend/; pytest.ini sets pythonpath=.)
python -m pytest tests/test_cfg.py::test_name -q   # single test
python check_llm.py                                # probe Gemini through each configured proxy + direct

# Frontend — Vite dev server on :3000, proxies /api (incl. WebSocket) to $API_TARGET or 127.0.0.1:8000
cd frontend && npm install && npm run dev
npm run build                                      # tsc -b && vite build — the only type check / "lint"
```

There is no frontend test suite or linter config. Optional hardened runner image: `docker build -t lampochki-sandbox ./sandbox`.

## Architecture

**Backend (`backend/`, FastAPI).** `main.py` mounts every router in `api/` under `/api`. Run from inside
`backend/` — imports are top-level (`import state`, `from core.parser import …`), not package-relative.

- `state.py` holds a single global `SESSION` (last parsed code, AST, line map). Most endpoints call
  `state.require()` and operate on that, so `/api/parse` must be called first (else 409). This is a deliberate
  single-user demo design. `state.find_method` resolves `"Class.method"` refs used across endpoints.
- `core/parser.py` turns `javalang` output into a JSON AST with declaration spans (via `core/source_map.py`,
  token-based). `javalang` is vendored in `backend/javalang/` (MIT, not a pip dependency) and extended to Java 17:
  `RecordDeclaration` (compact ctor → `ConstructorDeclaration.compact`), `sealed`/`non-sealed` modifiers + `permits`,
  arrow cases (`SwitchStatementCase.arrow`, `case A, B`), `SwitchExpression`, `YieldStatement`, `instanceof` patterns
  (`pattern_name` on the type), text blocks, `\s` escape. Java 21 `switch` patterns are not supported. Records and
  enums are listed in `ast["classes"]` with `kind` (`class|record|enum`); interfaces stay in `ast["interfaces"]`, and
  their methods with bodies are found by `state.method_names`/`find_method`. Every statement dict gets `col`,
  `range`/`src` (char offsets / exact source) and `head_range` (inside the parens of if/while/for/switch/catch);
  statements whose text can't be rebuilt from the tree (switch expressions, anonymous classes, block lambdas,
  local classes) are `lossy` and show/edit their real source (`raw`).
- `core/cfg_builder.py` builds a per-method CFG with **deterministic node ids** (`n0…`). Graph editing relies on
  this: `/api/generate` rebuilds the CFG server-side, diffs the client's node labels against its own, and passes
  only changed labels to `core/code_generator.py`. `splice_edits` replaces just the edited nodes' `range`/`head_range`
  in the source (everything else stays byte-identical); only if a range is missing (e.g. `\uXXXX` escapes) does it
  fall back to re-rendering the method body, where unedited statements are still emitted from `src`. Changing CFG
  id assignment breaks round-tripping. Java arrow `switch` has no fall-through in the CFG.
- `/api/graph?type=cfg|call|class` also decorates nodes with Big O (`bigo_analyzer`) and defects
  (`defect_detector`); node `data` keys are camelCased for the frontend in `api/graph.py`.
  `Defect.big_o_after` (`bigOAfter`) is the rule's expected Big O of the fragment after its recommendation
  (`defect_detector._power`); the frontend shows it on the defect card and, via `utils/bigoAfter.staticBigoAfter`,
  in the method row when there is no AI estimate.
- `core/decomposer.py` groups static methods by name prefix + call graph, moves nested classes/records/enums to
  files, and extracts closed groups of instance fields + the methods that alone use them into a component class
  (Extract Class: the monolith keeps a `private final` instance and delegating methods; a field's constructor
  assignment moves only if it is side-effect free, see `_SAFE_INIT`); `/decompose/verify` and
  `/quality-gate` compile and compare stdout of original vs. new code (`core/comparator.py` masks timestamps).
- Execution: `core/runner.py` (batch run, `JAVA_SANDBOX_MODE=subprocess|docker`, 10 s timeout, `-Xmx256m`) and
  `core/interactive.py` + `api/ws.py` (`/api/ws/run` streams stdout and accepts stdin for `Scanner`).
  Subprocess mode is not a sandbox.
- `config.py` loads `backend/.env` itself (no python-dotenv; real env vars win) and enforces `ALLOWED_ORIGINS`
  / same-host Origin checks for HTTP and WebSocket.
- `models/schemas.py` — all Pydantic request/response models.

**AI layer (`backend/ai/`).** `llm_client.generate` is the single entry point: retries with a different random
key + proxy per attempt, degrades models along `GEMINI_FALLBACK_MODELS`, backoff 2/4/6… s, and scrubs keys/proxy
credentials from all errors/logs (only `host:port` and last 4 key chars may appear). `gemini_pool.py` parses
key/proxy env lists; `proxy_scheme.py` sniffs whether a proxy port is SOCKS5 or HTTP and caches it.
`ai_analyzer.py` fills templates from `ai/prompts/*.txt` (`str.format`, so literal braces must be doubled).
When the LLM is disabled, `static_tips.py` provides fallback advice. AI edits come back as a "fragment →
replacement" pair; `patcher.py` locates the fragment (whitespace-insensitive, must be unique), reindents, adds
imports, and validates with parse + `javac` before the UI offers "Apply"; `/api/ai/apply` re-validates against
the current code.

**Frontend (`frontend/src/`, React 18 + Zustand + React Flow + Ace).** `store/useStore.ts` is the main app state
(active code, graph, diagnostics); `store/useProject.ts` manages the multi-file project tree (the active file's
live text lives in `useStore.code`, not in `ProjectFile.code`). `hooks/useApi.ts` wraps all backend calls;
`hooks/useSync.ts` drives the edit → 500 ms debounce → `/parse` → `/analyze` + `/graph` loop and lays graphs
out with dagre. `hooks/useAutoReview.ts` fires `/api/ai/review` 5 s after the last edit and cancels on new edits.
Example Java files live in both `frontend/src/examples/` and `test_monoliths/` (the latter used by backend tests).

## Tests

`tests/conftest.py` sets `JB_NO_DOTENV=1` and strips all `GEMINI_*`/`LLM_*`/`OLLAMA_*` env vars per test, so
tests never touch a real `.env`; LLM tests opt in with `monkeypatch.setenv`. Use the `read_java("Calculator")`
fixture to load files from `test_monoliths/`. Runner/compare tests need a JDK on PATH.

## Other files

`results/` holds the saved test runs (pytest local/JDK 17/Docker, vitest, build) and the demo scenario run;
`results/demo_scenario.py` replays the case path against a running stack (`docker compose up -d`).

`DESIGN.md` is the UI design spec (dark canvas, `#faff69` yellow accent, Inter / JetBrains Mono) — follow it for
UI work. `docs/architecture.md` is a short module overview; `to-do.md` is the original task plan (partly
outdated, e.g. mentions tree-sitter). `test_gemini.py`, `message.txt`, `api_gemini.txt` at the root are scratch
files, not part of the app.
