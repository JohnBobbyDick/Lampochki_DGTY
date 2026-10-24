# Этапы 1–3: актуальные дефекты, сравнение по файлу, выгрузка — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Панель «Дефекты» всегда отражает текущий код, ИИ показывает только применимые правки (включая
исправление ошибок компиляции), сравнение выводов идёт по истории запусков каждого файла, изменённые файлы
можно скачать.

**Architecture:** Бэкенд: единое правило валидности патча в `ai/patcher.py`, фильтрация и «ремонтные»
повторы в `ai/ai_analyzer.py`, новый `/api/ai/fix`, ошибки `javac` в `/api/analyze`, `/api/files/zip`.
Фронтенд: чистые утилиты (`utils/fragment.ts`, `utils/runs.ts`) с тестами vitest, история запусков в
`useProject`, обновлённые `DiagnosticsPanel`, `RunComparePanel`, `AiDrawer`, шапка.

**Tech Stack:** FastAPI, pytest, javalang/javac; React 18, Zustand, TypeScript, Vite, vitest (новая dev-зависимость).

**Spec:** `docs/superpowers/specs/2026-10-24-multilang-coverage-design.md` — разделы 1, 2, 3.
Остальные разделы (покрытие, сложность, стримы, Python, C++) — отдельные планы.

## Global Constraints

- Все строки UI и сообщений — на русском; визуальный стиль — по `DESIGN.md` (существующие классы `btn`, `state-card`, `defect`, `muted`).
- Бэкенд-тесты: `cd backend && python -m pytest` — проходят после каждой задачи. Фронтенд: `cd frontend && npm run build` и `npx vitest run` — без ошибок.
- Форма существующих ответов API не меняется, только добавляются поля (camelCase через `CamelModel`).
- Ключи/прокси ИИ не попадают в ответы и логи.
- Пользователь видит только применимые правки: невалидный патч не показывается вообще (spec §1).
- Критерий «применимо» един для ревью, «Объяснить», «Исправить»: правка не добавляет новых ошибок относительно текущего кода; для «Исправить» — ещё и устраняет целевую ошибку.
- «Старый» вывод = предыдущий запуск этого же файла (по `ProjectFile.id`); хранится 2 последних запуска на файл, в памяти.
- Ошибки компиляции в историю запусков не попадают; запуски с исключением, ненулевым exit, таймаутом, лимитом вывода, Stop — попадают со статусом.
- Zip изменённых файлов собирается на сервере; текущий файл скачивается на клиенте (Blob).

## Review Focus

- Пользователь посреди правки (файл не компилируется) — авто-ревью всё равно возвращает применимые патчи, не добавляющие ошибок (тест в Task 1).
- Ответ `/analyze` от старой версии кода приходит позже ответа от новой и перетирает дефекты — в `useSync` ответы старше текущего `reqId` игнорируются (ручная проверка в Task 6).
- Два файла с одинаковым именем в разных папках (`src/Demo.java`, `examples/Demo.java`) — истории запусков не смешиваются (тест в Task 7).
- Запуск, остановленный Stop или по лимиту вывода, записывается со статусом и вытесняет самый старый (тест в Task 7).
- Имя файла вида `../evil.java` или абсолютный путь в zip-запросе — отклоняется, архив не пишет за пределы (тест в Task 8).

---

### Task 1: Единое правило валидности патча

**Files:**
- Modify: `backend/ai/patcher.py` (`validate`, `build_patch`, `apply_patch`)
- Test: `backend/tests/test_patcher.py`

**Interfaces:**
- Produces: `async def validate(original: str, patched: str, *, fix_line: int | None = None) -> tuple[bool, list[str], list[str]]`
  и `async def build_patch(code, old, new, imports, hint_line=None, *, fix_line: int | None = None) -> dict | None`
  (ключи результата прежние). `fix_line` — строка целевой ошибки для режима «Исправить».

Правило (`javac` доступен): `E(x)` = список ошибок `runner.check_compiles(x)`.
- обычный режим: valid ⇔ `len(E(patched)) <= len(E(original))` и (`E(original) == []` ⇒ `E(patched) == []`);
- режим fix (`fix_line` задан): valid ⇔ `len(E(patched)) < len(E(original))` и ни одна ошибка `E(patched)` не стоит на строке `fix_line` с тем же текстом, что была в `E(original)`.
- Синтаксис (`parse_java(...)["errors"]`): если у `original` синтаксических ошибок не было, а у `patched` есть — invalid (как сейчас). Если были у обоих — решает javac-правило выше.
- `javac` недоступен (`None`): обычный режим — как сейчас (только синтаксис, предупреждение); fix-режим — valid ⇔ у `patched` нет синтаксических ошибок.

- [ ] **Step 1: Write the failing tests**

```python
BROKEN = CALC.replace("return result;", "return result")          # одна ошибка компиляции

def test_patch_on_non_compiling_code_is_valid_if_it_adds_no_errors():
    p = asyncio.run(patcher.build_patch(BROKEN, OLD_LOOP, NEW_LOOP, []))   # правка в другом месте файла
    assert p and p["valid"]

def test_patch_that_adds_error_to_non_compiling_code_is_rejected():
    p = asyncio.run(patcher.build_patch(BROKEN, OLD_LOOP, "int y = undefinedVar;", []))
    assert p and not p["valid"]

def test_fix_mode_requires_target_error_gone():
    line = BROKEN.split("\n").index(next(l for l in BROKEN.split("\n") if "return result" in l)) + 1
    ok = asyncio.run(patcher.build_patch(BROKEN, "return result", "return result;", [], fix_line=line))
    noop = asyncio.run(patcher.build_patch(BROKEN, "return result", "return  result", [], fix_line=line))
    assert ok["valid"] and (noop is None or not noop["valid"])
```

Используйте существующие константы/фикстуры `test_patcher.py` для `CALC`, `OLD_LOOP`, `NEW_LOOP` (или заведите их рядом с имеющимися тестами на `Calculator.java`).

- [ ] **Step 2: Run** `cd backend && python -m pytest tests/test_patcher.py -q` — Expected: 3 новых FAIL.
- [ ] **Step 3: Implement** правило в `validate`; `build_patch`/`apply_patch` пробрасывают `fix_line`.
- [ ] **Step 4: Run** `python -m pytest -q` — Expected: всё PASS (включая старые `test_patch_*`).
- [ ] **Step 5: Commit** `git commit -m "feat(ai): unified patch validity rule, fix mode"`

---

### Task 2: ИИ отдаёт только применимые правки + ремонтные повторы

**Files:**
- Modify: `backend/ai/ai_analyzer.py` (`explain`, `review`)
- Create: `backend/ai/prompts/repair.txt`
- Test: `backend/tests/test_patcher.py` (рядом с `test_review_returns_applicable_patch_...`)

**Interfaces:**
- Consumes: `patcher.build_patch(..., fix_line=...)` из Task 1.
- Produces: `REPAIR_ROUNDS = 2` в `ai_analyzer`; `async def _generate_patches(prompt: str, code: str, validate_json, extract) -> ...` — внутренний помощник, на усмотрение исполнителя. Контракт ответов:
  - `review` → в `suggestions` только элементы с `patch` и `patch["valid"] is True`;
  - `explain` → если валидного патча нет: `patch=None`, `fixed_code=""`, `note="ИИ не нашёл правки, которую можно безопасно применить."` (объяснение остаётся). Статический фолбэк (без LLM) — `fixed_code` как сейчас (фронт его больше не рисует, Task 6).

`repair.txt` (str.format, фигурные скобки удваивать): «Предложенные правки не компилируются: {errors}. Исправь их, сохрани формат ответа.» — добавляется к исходному промпту. Повтор делается, только если в ответе модели были правки (непустые `old_code/new_code`), но ни одна не прошла `valid`; максимум `REPAIR_ROUNDS` повторов.

- [ ] **Step 1: Write the failing tests** (Gemini замокан через `httpx.MockTransport`, как в `test_ai.py`)

```python
def test_review_hides_invalid_and_adviceonly_items(monkeypatch): ...
    # ответ модели: 1 валидная правка, 1 некомпилируемая, 1 совет без кода
    assert [s["title"] for s in r["suggestions"]] == ["валидная"]

def test_review_repairs_when_all_patches_invalid(monkeypatch): ...
    # 1-й ответ: некомпилируемая правка; 2-й: валидная. Ожидаем 2 HTTP-запроса,
    # второй промпт содержит "не компилируются", в ответе 1 suggestion
    assert calls == 2 and len(r["suggestions"]) == 1

def test_explain_drops_invalid_patch(monkeypatch): ...
    # все 3 ответа (1 + 2 повтора) некомпилируемые
    assert r["patch"] is None and r["fixedCode"] == "" and "безопасно применить" in r["note"]
```

- [ ] **Step 2: Run** `python -m pytest tests/test_patcher.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** фильтрацию и повторы в `review`/`explain`.
- [ ] **Step 4: Run** `python -m pytest -q` — Expected: PASS (поправьте старые тесты, которые ожидали заблокированный патч в ответе, — это теперь изменённый контракт).
- [ ] **Step 5: Commit** `git commit -m "feat(ai): show only applicable patches, repair rounds"`

---

### Task 3: Ошибки компиляции в `/api/analyze`

**Files:**
- Modify: `backend/api/analyze.py`, `backend/models/schemas.py` (`AnalyzeResponse`)
- Test: `backend/tests/test_api_flow.py`

**Interfaces:**
- Produces: `AnalyzeResponse.compile_errors: list[dict]` (JSON `compileErrors`, элементы `{file, line, message}` как у `runner.parse_compile_errors`). Значение: `runner.check_compiles(s.code) or []` — считается всегда, в т.ч. при синтаксических ошибках парсера (у javalang они без номера строки, у javac — с номером).

- [ ] **Step 1: Write the failing test**

```python
def test_analyze_reports_compile_errors(read_java):
    parse(read_java("Calculator").replace("return result;", "return result", 1))
    errs = client.post("/api/analyze").json()["compileErrors"]
    assert errs and errs[0]["line"] > 0

def test_analyze_compiles_clean_code(read_java):
    parse(read_java("Calculator"))
    assert client.post("/api/analyze").json()["compileErrors"] == []
```

- [ ] **Step 2: Run** `python -m pytest tests/test_api_flow.py -q` — Expected: FAIL (`KeyError`).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python -m pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(analyze): include javac errors"`

---

### Task 4: `/api/ai/fix` — исправление ошибки компиляции/синтаксиса

**Files:**
- Modify: `backend/api/ai.py`, `backend/ai/ai_analyzer.py`, `backend/models/schemas.py`
- Create: `backend/ai/prompts/syntax_fix.txt`
- Test: `backend/tests/test_ai.py`

**Interfaces:**
- Consumes: `build_patch(..., fix_line=...)` (Task 1), механизм повторов (Task 2).
- Produces:
  - `class AiFixRequest(CamelModel): code: str; line: int | None = None; message: str`
  - `POST /api/ai/fix` → `AiExplainResponse` (`explanation`, `patch`, `source`, `note`; `fixed_code` пустой).
  - `async def fix_error(code: str, line: int | None, message: str) -> dict` в `ai_analyzer`.
- Без LLM: `explanation` — короткий текст «ИИ не настроен — исправьте ошибку вручную: {message}», `patch=None`, `source="static"`.
- Промпт `syntax_fix.txt`: Java-код целиком (`_clip`), текст ошибки и строка, тот же JSON-формат `old_code/new_code/imports` + `explanation`.

- [ ] **Step 1: Write the failing tests**

```python
def test_fix_without_llm_is_static():
    r = client.post("/api/ai/fix", json={"code": "class A { int f() { return 1 } }", "line": 1, "message": "';' expected"}).json()
    assert r["source"] == "static" and r["patch"] is None

def test_fix_with_mocked_gemini_returns_valid_patch(monkeypatch, read_java):
    broken = read_java("Calculator").replace("return result;", "return result", 1)
    # мок возвращает {"explanation": "...", "old_code": "return result", "new_code": "return result;", "imports": []}
    r = client.post("/api/ai/fix", json={"code": broken, "line": LINE, "message": "';' expected"}).json()
    assert r["patch"]["valid"] and r["patch"]["newCode"].strip() == "return result;"
```

- [ ] **Step 2: Run** `python -m pytest tests/test_ai.py -q` — Expected: FAIL (404).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python -m pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(ai): /api/ai/fix for compile errors"`

---

### Task 5: vitest + `fragmentPresent`

**Files:**
- Modify: `frontend/package.json` (devDependency `vitest`, script `"test": "vitest run"`)
- Create: `frontend/src/utils/fragment.ts`, `frontend/src/utils/fragment.test.ts`

**Interfaces:**
- Produces: `export function fragmentPresent(code: string, old: string): boolean` — зеркало `patcher.locate` без подсказки: непустые строки `old` (после `trim`) встречаются в `code` подряд среди непустых строк, хотя бы один раз (неоднозначность здесь не важна — нужно лишь «фрагмент ещё на месте»). Пустой `old` → `false`.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';
import { fragmentPresent } from './fragment';

describe('fragmentPresent', () => {
  const code = 'class A {\n    void f() {\n        int x = 1;\n\n        x++;\n    }\n}';
  it('ignores indentation and blank lines', () => expect(fragmentPresent(code, 'int x = 1;\n  x++;')).toBe(true));
  it('false when edited', () => expect(fragmentPresent(code.replace('x++', 'x--'), 'int x = 1;\nx++;')).toBe(false));
  it('false for empty', () => expect(fragmentPresent(code, '  \n')).toBe(false));
});
```

- [ ] **Step 2: Run** `cd frontend && npm i -D vitest && npx vitest run` — Expected: FAIL (module not found).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npx vitest run && npm run build` — Expected: PASS, сборка без ошибок (тестовые файлы не должны попадать в `tsc -b`-сборку с ошибками — при необходимости исключите `*.test.ts` в `tsconfig.json`).
- [ ] **Step 5: Commit** `git commit -m "test(frontend): vitest, fragmentPresent util"`

---

### Task 6: Фронтенд — дефекты и советы всегда актуальны, «✨ Исправить»

**Files:**
- Modify: `frontend/src/store/useStore.ts`, `frontend/src/hooks/useApi.ts`, `frontend/src/hooks/useSync.ts`,
  `frontend/src/components/DiagnosticsPanel/DiagnosticsPanel.tsx`, `frontend/src/components/AiDrawer/AiDrawer.tsx`,
  `frontend/src/components/AiDrawer/PatchView.tsx`, `frontend/src/types/index.ts`

**Interfaces:**
- Consumes: `compileErrors` (Task 3), `POST /api/ai/fix` (Task 4), `fragmentPresent` (Task 5).
- Produces:
  - store: `compileErrors: CompileError[]`, `setCompileErrors(e: CompileError[])`, `pruneStale(code: string): void` — убирает из `aiReview.items` элементы без `patch` или с `!fragmentPresent(code, patch.oldCode)`; у `ai` (ответ «Объяснить/Исправить») обнуляет `patch`, если фрагмент пропал; `loadDocument` также очищает `compileErrors`, `defects`, `bigo`.
  - `useApi().aiFix(err: { line: number | null; message: string })` — как `aiExplain`, заголовок `'✨ Исправление ошибки'`, отправляет текущий `code`.

Поведение:
- `useSync`: `pruneStale(code)` вызывается сразу при изменении `code` (до debounce). Ответы `parse`/`analyze`/`graph` применяются, только если их `reqId` всё ещё текущий (сейчас проверяется только граф) — перенесите `setDefects/setBigo/setCompileErrors` из `analyzeCode` в `useSync` под эту проверку или передайте `id` внутрь.
- `DiagnosticsPanel`: раздел «Синтаксис и компиляция» показывает `compileErrors` (стр. N + текст; клик — переход к строке), а если их нет — `syntaxErrors`. У каждой ошибки — кнопка `✨ Исправить с ИИ` (только при `aiEnabled`).
- `AiDrawer`: блок `ai.code` («Пример кода») больше не рисуется; `PatchView` рисуется только для `patch.valid`. `PatchView`: ветка `blocked` удаляется.
- Если после фильтрации у ревью нет элементов — состояние «ИИ не нашёл применимых правок» (вместо «Идей для улучшения не найдено»), кнопка в шапке скрывается.

- [ ] **Step 1: Implement** store/хуки/компоненты по описанию.
- [ ] **Step 2: Run** `cd frontend && npm run build && npx vitest run` — Expected: без ошибок.
- [ ] **Step 3: Ручная проверка** (бэкенд `uvicorn main:app --port 8000`, фронт `npm run dev`; можно через навык `run`):
  1. Открыть `examples/Analyzer.java`, найти дефект «Вложенный цикл по … items» в `mergeItems`. Переписать метод через `HashMap` → через ~1 с дефект исчезает, Big O метода меняется.
  2. Удалить `;` в любой строке → в «Синтаксис и компиляция» появляется javac-ошибка со строкой; вернуть `;` → ошибка исчезает.
  3. С включённым ИИ: дождаться «✨ N идей», отредактировать строку из `old_code` одного совета → этот совет пропадает сразу, не дожидаясь нового ревью.
  4. Быстро набрать несколько символов подряд — дефекты соответствуют последней версии (нет «мигания» к старым).
- [ ] **Step 4: Commit** `git commit -m "fix(ui): defects and AI tips follow current code; AI fix button"`

---

### Task 7: История запусков по файлу и сравнение «предыдущий ↔ последний»

**Files:**
- Create: `frontend/src/utils/runs.ts`, `frontend/src/utils/runs.test.ts`
- Modify: `frontend/src/store/useProject.ts`, `frontend/src/components/Console/Console.tsx`,
  `frontend/src/components/RunComparePanel/RunComparePanel.tsx`, `frontend/src/components/BottomPanel/BottomPanel.tsx`,
  `frontend/src/App.tsx` (кнопка «Сравнить»), `frontend/src/utils/verdict.ts`, `frontend/src/store/useStore.ts`

**Interfaces:**
- Produces (`utils/runs.ts`):

```ts
export type RunStatus = 'ok' | 'error' | 'timeout' | 'stopped' | 'limit';
export interface RunRecord { stdout: string; stderr: string; exitCode: number; durationMs: number;
  stdin: string; code: string; status: RunStatus; at: number }
export const RUN_HISTORY = 2;
export function pushRun(history: Record<string, RunRecord[]>, fileId: string, r: RunRecord): Record<string, RunRecord[]>;
export function runStatus(exitCode: number, stderr: string, stoppedByUser: boolean): RunStatus;
export function compareRuns(prev: RunRecord, last: RunRecord): { same: boolean; stdinDiffers: boolean };
```

  - `pushRun` — неизменяемо, хранит последние `RUN_HISTORY` записей файла.
  - `runStatus`: `stoppedByUser` → `'stopped'`; stderr содержит `output limit reached` → `'limit'`; содержит маркер таймаута, который выдаёт `core/interactive.py` (найдите точный текст там) → `'timeout'`; `exitCode !== 0` → `'error'`; иначе `'ok'`.
  - `compareRuns.same` — stdout равны после маскировки таймстемпов той же регуляркой, что `core/comparator.py` (`\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?`), и одинаковый `status`.
- `useProject`: `runs: Record<string, RunRecord[]>`, `recordRun(r: RunRecord): void` (по `activeId`). `loadDocument` историю не трогает (она в `useProject`).
- `useStore`: `compareResult`/`setCompareResult`/`compareCode` больше не используются панелью сравнения (удалите, если не нужны другим местам; `qualityGate` и «Проверить поведение» у ИИ-патча не трогать).

Поведение:
- `Console`: на `exit` — `recordRun` с `status = runStatus(...)`; флаг «нажата Остановить» ставится в `stop()`. На `compile_error` — ничего не записывать.
- `RunComparePanel` для активного файла: < 2 записей → пустое состояние «Запустите файл ещё раз после правки, чтобы сравнить выводы»; иначе «Предыдущий запуск» vs «Последний запуск» с diff (как сейчас), статус каждого (`ok` → «exit 0», остальные — «исключение / таймаут / остановлен / лимит вывода»), плашка «Ввод отличался», если `stdinDiffers`. Вердикт: `same` → «Вывод не изменился», иначе «Вывод изменился».
- Кнопка «Сравнить» в шапке только открывает вкладку «Сравнение» (без запуска); после записи второго запуска файла вкладка «Сравнение» не открывается сама (консоль остаётся видимой). **[решение исполнителя допускается]** подпись кнопки.

- [ ] **Step 1: Write the failing tests** (`runs.test.ts`)

```ts
it('keeps last two runs per file id', () => {
  let h = {}; for (const out of ['1', '2', '3']) h = pushRun(h, 'src/Demo.java', rec(out));
  expect(h['src/Demo.java'].map((r) => r.stdout)).toEqual(['2', '3']);
});
it('does not mix files with the same name in different folders', () => {
  let h = pushRun({}, 'src/Demo.java', rec('12')); h = pushRun(h, 'examples/Demo.java', rec('7'));
  expect(h['src/Demo.java'].map((r) => r.stdout)).toEqual(['12']);
});
it('status: stop / limit / error / ok', () => {
  expect(runStatus(137, '', true)).toBe('stopped');
  expect(runStatus(137, '…[output limit reached, process killed]', false)).toBe('limit');
  expect(runStatus(1, 'Exception in thread "main"', false)).toBe('error');
  expect(runStatus(0, '', false)).toBe('ok');
});
it('compare masks timestamps and flags stdin change', () => {
  const a = rec('at 2026-10-24 10:00:00 sum=12', 'x'), b = rec('at 2026-10-24 11:30:05 sum=12', 'y');
  expect(compareRuns(a, b)).toEqual({ same: true, stdinDiffers: true });
});
```

(`rec(stdout, stdin = '')` — локальный помощник теста со `status: 'ok'`.)

- [ ] **Step 2: Run** `npx vitest run` — Expected: FAIL.
- [ ] **Step 3: Implement** `utils/runs.ts`, затем store/Console/панель/шапку.
- [ ] **Step 4: Run** `npx vitest run && npm run build` — Expected: PASS.
- [ ] **Step 5: Ручная проверка** — сценарий из spec §2: Run `src/Demo.java` → Run `examples/Calculator.java` → правка Demo, Run → вкладка «Сравнение» показывает Demo «старый/новый»; переключение на Calculator → «Запустите файл ещё раз…»; правка Calculator, Run → сравнение только Calculator.
- [ ] **Step 6: Commit** `git commit -m "feat(compare): per-file run history, previous vs last run"`

---

### Task 8: Выгрузка — текущий файл и zip изменённых

**Files:**
- Create: `backend/api/files.py`
- Modify: `backend/main.py` (подключить роутер), `backend/models/schemas.py`
- Test: `backend/tests/test_api_flow.py`
- Modify: `frontend/src/hooks/useApi.ts`, `frontend/src/components/ProjectTree/FileTabs.tsx`, `frontend/src/components/ProjectTree/ProjectTree.tsx`

**Interfaces:**
- Produces:
  - `class ZipFile(CamelModel): path: str; code: str`, `class ZipRequest(CamelModel): files: list[ZipFile]`
  - `POST /api/files/zip` → `application/zip`, `Content-Disposition: attachment; filename="changed.zip"`. Пути — как `ProjectFile.id` (`src/Demo.java`). Путь отклоняется (`422`) если абсолютный, содержит `..`, `\` или пуст; пустой список → `422`.
  - `useApi().downloadChanged()`: собирает файлы, где текущий текст (`useStore.code` для активного) `!== original`, вызывает эндпоинт, скачивает `changed.zip`.
  - `downloadFile(name: string, code: string): void` в `utils/download.ts` (Blob `text/plain;charset=utf-8`); переиспользуйте его и в `downloadDecomposition` для `a.click()`-части.
- UI: в `FileTabs` у активной вкладки — иконка «Скачать файл» (`FiDownload`, `aria-label="Скачать {name}"`); в заголовке `ProjectTree` — кнопка «Скачать изменённые», `disabled`, если изменённых нет.

- [ ] **Step 1: Write the failing tests**

```python
def test_zip_changed_files():
    r = client.post("/api/files/zip", json={"files": [{"path": "src/Demo.java", "code": "class Demo {}"},
                                                     {"path": "examples/Calc (2).java", "code": "class C {}"}]})
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert r.status_code == 200 and sorted(z.namelist()) == ["examples/Calc (2).java", "src/Demo.java"]

@pytest.mark.parametrize("bad", ["../evil.java", "/etc/passwd", "a\\b.java", ""])
def test_zip_rejects_unsafe_paths(bad):
    assert client.post("/api/files/zip", json={"files": [{"path": bad, "code": "x"}]}).status_code == 422
```

- [ ] **Step 2: Run** `python -m pytest tests/test_api_flow.py -q` — Expected: FAIL (404).
- [ ] **Step 3: Implement** бэкенд, затем фронт.
- [ ] **Step 4: Run** `cd backend && python -m pytest -q`; `cd frontend && npm run build && npx vitest run` — Expected: PASS.
- [ ] **Step 5: Ручная проверка:** изменить два файла → «Скачать изменённые» даёт zip с двумя файлами в своих папках; «Скачать файл» у вкладки сохраняет текущий текст под именем файла; без изменений кнопка неактивна.
- [ ] **Step 6: Commit** `git commit -m "feat: download current file and changed files zip"`

---

### Task 9: Документация и финальная проверка

**Files:**
- Modify: `README.md` (раздел «Как пользоваться»: сравнение по истории запусков, скачивание, «✨ Исправить», только применимые советы), `CLAUDE.md` (команда `npx vitest run`; `/api/ai/fix`, `/api/files/zip`, история запусков в `useProject`), `docs/architecture.md` (новые эндпоинты).

- [ ] **Step 1: Обновить документы.**
- [ ] **Step 2: Run** `cd backend && python -m pytest -q` и `cd frontend && npm run build && npx vitest run` — Expected: всё PASS; приложить вывод в отчёт.
- [ ] **Step 3: Commit** `git commit -m "docs: stage 1-3 features"`
