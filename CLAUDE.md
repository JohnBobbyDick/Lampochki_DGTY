# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
npx vitest run                                     # frontend unit tests (also `npm test`)
```

There is no linter config. Optional hardened runner image: `docker build -t lampochki-sandbox ./sandbox`.

## Architecture

**Backend (`backend/`, FastAPI).** `main.py` mounts every router in `api/` under `/api`. Run from inside
`backend/` — imports are top-level (`import state`, `from core.parser import …`), not package-relative.

- `state.py` holds a single global `SESSION` (last parsed code, AST, line map). Most endpoints call
  `state.require()` and operate on that, so `/api/parse` must be called first (else 409). This is a deliberate
  single-user demo design. `state.find_method` resolves `"Class.method"` refs used across endpoints.
- `core/parser.py` turns `javalang` output into a JSON AST with declaration spans (via `core/source_map.py`,
  token-based). javalang limits syntax to ~Java 8.
- `core/cfg_builder.py` builds a per-method CFG with **deterministic node ids** (`n0…`). Graph editing relies on
  this: `/api/generate` rebuilds the CFG server-side, diffs the client's node labels against its own, and passes
  only changed labels to `core/code_generator.py`, which regenerates the method body and splices it into the
  source by span. Changing CFG id assignment breaks round-tripping.
- `/api/graph?type=cfg|call|class` also decorates nodes with Big O (`bigo_analyzer`) and defects
  (`defect_detector`); node `data` keys are camelCased for the frontend in `api/graph.py`.
- `core/decomposer.py` groups static methods by name prefix + call graph; `/decompose/verify` and
  `/quality-gate` compile and compare stdout of original vs. new code (`core/comparator.py` masks timestamps).
- Execution: `core/runner.py` (batch run, `JAVA_SANDBOX_MODE=subprocess|docker`, 10 s timeout, `-Xmx256m`) and
  `core/interactive.py` + `api/ws.py` (`/api/ws/run` streams stdout and accepts stdin for `Scanner`).
  Subprocess mode is not a sandbox.
- `config.py` loads `backend/.env` itself (no python-dotenv; real env vars win) and enforces `ALLOWED_ORIGINS`
  / same-host Origin checks for HTTP and WebSocket.
- `/api/analyze` also returns `compileErrors` (javac, `{file, line, message}`) for the diagnostics panel.
- `api/files.py` `/api/files/zip` packs `{files:[{path, code}]}` into a zip (unsafe paths → 422); the current file is
  downloaded client-side.
- Coverage (`core/coverage/`): `instrument.py` instruments source by javalang tokens + AST, inserting probes
  (line/method/branch/cond/rel) without newlines so line numbers are kept; `conditions.py` parses conditions at
  token level. `Cov.java` (`__Cov`) writes int32 counters into a memory-mapped file given by `-Djb.cov`, so data
  survives Stop/timeout/kill. `build.py` compiles with degradation (strip decision probes → strip all probes on
  failing lines → run the original without coverage) and reads hits (`CovPlan`, `read_hits`). Only the interactive
  run (`core/interactive.py`, `/api/ws/run`) is instrumented: it sends `{type:"coverage", probes, hits}` or
  `{type:"coverage", error}` after all output and before `exit`, never after a compile error (docker mode uses a
  `/cov` mount and a `compiled` marker). Batch runs (Quality Gate, decompose verify) are not instrumented.
- Streams (`core/streams.py`): `stream_of` recognises `src.stream().op(…).terminal(…)` and the parser's
  `_stmt_to_dict` sets `stmt["stream"]` (`prefix`, `source`, `ops`, `terminal`; `compose` must reproduce the statement
  text, otherwise no field). Only whole initializers / expression statements / assignment values / returns are
  decomposed. `cfg_builder` emits `stream-source`/`stream-op`/`stream-terminal` nodes (new `GraphNode.type` values);
  `code_generator` edits a step by replacing its `text` (empty op label deletes it) and renders via `compose`;
  `bigo_analyzer._stream_cost` gives structural Big O; `defect_detector._stream_defects` has 6 rules (tips in
  `ai/static_tips.py`). Demo: `test_monoliths/Streams.java` (+ `frontend/src/examples/`).
- Python (stage 7): requests carry `language` (`state.SESSION.language`); `core/lang/` is the registry
  (`LANGS`, `Language`: parse / check / regenerate / decompose per language). `core/py_parser.py` maps the stdlib `ast`
  onto the Java statement types (`IfStatement`, `TryStatement`…, elif = nested if) with source text, `span` and
  `header`; free functions go to the pseudo-class `Module` (`Module.f`), top-level code to `Module.main`
  (`Module.__main__` if there is a `def main`). `cfg_builder` gives Python methods Python labels (`if x > 0`,
  `for x in xs`, `except E as e`) and flow (loop/try `else`, `with` nodes, `match` without fall-through).
  `core/py_codegen.py` edits by replacing only the node's `span`/`header` (keyword kept, rest byte-identical).
  `bigo_analyzer` parses statement texts with `ast` (comprehensions, builtins, `in` by collection type);
  `defect_detector._python_defects`: `in list` in a loop, nested loop over one collection, `s +=` string in a loop,
  `range(len(x))`, swallowed `except: pass`, mutable default argument. `decomposer._decompose_python` moves
  top-level functions / whole classes into modules, `main.py` stays the facade. Run: `runner.python_command`
  (`python3 -u`, env = `runner.python_env()` allowlist, `RLIMIT_AS` 512 MB via `python_preexec`; docker mode
  never falls back to the host). Coverage: `core/coverage/py_cov.py` (stdlib-only `ast.NodeTransformer`,
  builtin `_jb_cov`, same `Probe`/`hits` format) is copied next to `main.py` with the loader `_jb_run.py`
  (`build.prepare_python`); the child instruments `main.py` itself and counts into `$JB_COV` (`cov/hits.bin`,
  `/cov/hits.bin` in docker) with `$JB_COV_SLOTS`; instrumentation failure → original runs, bare reason in `error`.
- `models/schemas.py` — all Pydantic request/response models.

**AI layer (`backend/ai/`).** `llm_client.generate` is the single entry point: retries with a different random
key + proxy per attempt, degrades models along `GEMINI_FALLBACK_MODELS`, backoff 2/4/6… s, and scrubs keys/proxy
credentials from all errors/logs (only `host:port` and last 4 key chars may appear). `gemini_pool.py` parses
key/proxy env lists; `proxy_scheme.py` sniffs whether a proxy port is SOCKS5 or HTTP and caches it.
`ai_analyzer.py` fills templates from `ai/prompts/*.txt` (`str.format`, so literal braces must be doubled).
When the LLM is disabled, `static_tips.py` provides fallback advice. AI edits come back as a "fragment →
replacement" pair; `patcher.py` locates the fragment (whitespace-insensitive, must be unique), reindents, adds
imports, and validates with parse + `javac` before the UI offers "Apply"; `/api/ai/apply` re-validates against
the current code. A patch is returned only if it is *applicable*: it adds no compile errors vs. the current code
(`/api/ai/fix` for a single javac error additionally requires removing the target error). `ai_analyzer._generate_patches`
re-asks the model up to `REPAIR_ROUNDS` times (`prompts/repair.txt`) when no edit is valid. `/api/ai/fix` takes
`{code, line, message}`.
Big O before/after: `ai/bigo_diff.py` fills `AiPatch.bigoBefore/bigoAfter` (affected methods = span intersects the edit
+ methods whose `analyze_ast` label changed; only for valid patches); `POST /api/ai/bigo-combined` (`{code, patches[]}`,
no LLM) applies several patches together (disjoint in order via `patcher.replace_range`, overlapping → best single).

**Frontend (`frontend/src/`, React 18 + Zustand + React Flow + Ace).** `store/useStore.ts` is the main app state
(active code, graph, diagnostics); `store/useProject.ts` manages the multi-file project tree (the active file's
live text lives in `useStore.code`, not in `ProjectFile.code`). `useProject.runs` keeps the last 2 runs per
`ProjectFile.id` in memory (`utils/runs.ts`) for the «Сравнение» tab; compile errors are never recorded there.
`useProject.coverage`/`coverageError`/`coverageReset` (+ `recordCoverage`/`setCoverageError`/`resetCoverage`)
accumulate coverage per `ProjectFile.id` by exact code text via `utils/coverage.ts` (`mergeCoverage`, `summarize`,
`lineStates`, `percent`); any edit resets it for good. `AceEditor` draws gutter stripes + hover tooltip, and the
BottomPanel tab «Покрытие» (`CoveragePanel`) shows the summary.
Big O after AI: `utils/speedup.ts` (f(n) ratio at n = 1000, nice rounding), `utils/bigoAfter.ts` + `hooks/useBigoAfter.ts` →
`useStore.bigoAfterAi` (one applicable advice: `patch.bigoAfter`; ≥2: `/api/ai/bigo-combined`, debounced 400 ms), shown by
`components/BigoChange` (`utils/bigoChange.ts`) in DiagnosticsPanel's «Сложность методов · Big O» row and `PatchView`.
`hooks/useApi.ts` wraps all backend calls;
`hooks/useSync.ts` drives the edit → 500 ms debounce → `/parse` → `/analyze` + `/graph` loop and lays graphs
out with dagre. `hooks/useAutoReview.ts` fires `/api/ai/review` 5 s after the last edit and cancels on new edits.
Example Java files live in both `frontend/src/examples/` and `test_monoliths/` (the latter used by backend tests).

## Tests

`tests/conftest.py` sets `JB_NO_DOTENV=1` and strips all `GEMINI_*`/`LLM_*`/`OLLAMA_*` env vars per test, so
tests never touch a real `.env`; LLM tests opt in with `monkeypatch.setenv`. Use the `read_java("Calculator")`
fixture to load files from `test_monoliths/`. Runner/compare tests need a JDK on PATH.

## Other files

`DESIGN.md` is the UI design spec (dark canvas, `#faff69` yellow accent, Inter / JetBrains Mono) — follow it for
UI work. `docs/architecture.md` is a short module overview; `to-do.md` is the original task plan (partly
outdated, e.g. mentions tree-sitter). `test_gemini.py`, `message.txt`, `api_gemini.txt` at the root are scratch
files, not part of the app.
