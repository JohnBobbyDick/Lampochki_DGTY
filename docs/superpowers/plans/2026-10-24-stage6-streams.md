# Этап 6: Stream API и Collectors — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Цепочки Stream API в Java — конвейер узлов на CFG с правкой шагов через граф, структурная оценка Big O
вместо regex и 6 дефект-правил/советов для стримов, плюс демо-пример.

**Architecture:** Парсер распознаёт цепочку в операторе (объявление, выражение, присваивание, `return`) и кладёт
в словарь оператора поле `stream` (префикс, источник, операции, терминал). `cfg_builder` разворачивает такой
оператор в узлы `stream-source → stream-op × N → stream-terminal` (id продолжают нумерацию `n…`, `stmt_of` ведёт
на словари частей цепочки), `code_generator` собирает текст оператора из частей, поэтому правка метки шага
меняет только этот шаг. `bigo_analyzer` считает цепочку по шагам, `defect_detector` — правила по полю `stream`.

**Tech Stack:** FastAPI, javalang, pytest; React 18 + React Flow, vitest.

**Spec:** `docs/superpowers/specs/2026-10-24-multilang-coverage-design.md` — раздел 6.

## Global Constraints

- UI и тексты дефектов — на русском; стиль — `DESIGN.md` и существующие токены CSS.
- Парсер — javalang (Java ≤ 8); records и switch-выражения не поддерживаются (как сейчас).
- Id узлов CFG детерминированы (`n0…`); один и тот же код всегда даёт те же id; правка через граф опирается на это.
- Без правок перегенерация метода даёт тот же текст, что и без стримов (roundtrip не ломается).
- Big O: проход стрима — O(n) × стоимость лямбды на элемент; `sorted` — O(n log n); `distinct`/`groupingBy`/`toSet`/`toMap`/`joining` — O(n); `flatMap` — умножение на O(n); стрим в цикле — умножение (уже даёт цикл); `limit`/`findFirst`/`anyMatch`/`allMatch`/`noneMatch`/`findAny` оценку не снижают.
- Форма существующих ответов API не меняется; новые типы узлов — только новые значения `GraphNode.type`.
- Проверка после каждой задачи: `cd backend && venv/bin/python -m pytest -q`; `cd frontend && npm run build && npx vitest run`.
- Не коммитить чужие неотслеживаемые файлы (`AGENTS.md`, `.DS_Store`, `backend/package-lock.json`). ИИ-функции вручную не проверять.

## Решения (обязательны для исполнителей)

- **Где распознаётся цепочка:** инициализатор локальной переменной с одним декларатором; всё выражение
  `StatementExpression`; правая часть присваивания в `StatementExpression`; выражение `return`. Цепочки внутри
  аргументов, условий, лямбд и полей класса не раскладываются (остаются одним узлом, Big O — прежним regex).
- **Источник** — выражение до и включая первый вызов-источник: `.stream()`, `.parallelStream()`, `Arrays.stream(…)`,
  `Stream.of(…)`, `Stream.iterate(…)`, `Stream.generate(…)`, `IntStream|LongStream|DoubleStream.range|rangeClosed|of(…)`.
- **Операции:** `filter, map, mapToInt, mapToLong, mapToDouble, mapToObj, flatMap, sorted, distinct, limit, skip, peek, boxed`.
  **Терминал:** `collect, forEach, forEachOrdered, reduce, count, sum, min, max, average, anyMatch, allMatch, noneMatch, findFirst, findAny, toArray`.
  Всё после терминала (`.size()`, `.isPresent()`, `.get()`, `.orElse(…)`) — `tail`, часть текста терминала.
  Неизвестный метод между источником и терминалом — цепочка не раскладывается.
- **Поле `stream`** в словаре оператора:
  `{"prefix": str, "source": {"type": "StreamSource", "text": str, "line": int},
    "ops": [{"type": "StreamOp", "name": str, "args": str, "text": str, "line": int}],
    "terminal": {"type": "StreamTerminal", "name": str, "args": str, "tail": str, "text": str, "line": int} | None}`.
  `text` операции — `name(args)` (без точки); `text` терминала — `name(args)` + `tail`; `prefix` — всё до источника
  (`List<Integer> r = `, `r = `, `return `, префиксные операторы вроде `!`). Нужна хотя бы одна операция или терминал.
  `line` — позиция javalang вызова, если есть, иначе строка оператора.
- **Инвариант:** `compose(stream) = prefix + source.text + "".join("." + op.text) + ("." + terminal.text if terminal)`
  равен обычному тексту оператора без `;` (тому, что сейчас рендерит `code_generator` / показывает CFG). Если
  не равен — поле `stream` не ставится (оператор остаётся обычным).
- **Узлы CFG:** `stream-source` (метка `prefix + source.text`), `stream-op` (метка `op.text`), `stream-terminal`
  (метка `terminal.text`); метки не обрезаются; рёбра последовательные `normal`; `code_snippet` — полный текст
  оператора у источника, текст шага у остальных; `line_start` — `line` части. `stmt_of` узла указывает на словарь
  части (`source`/`op`/`terminal`).
- **Правка:** `apply_edit` для `StreamSource`/`StreamOp`/`StreamTerminal` заменяет `text` (у источника — текст после
  `prefix`; если пользователь оставил префикс в метке источника, он отрезается; ведущая `.` у шага отбрасывается).
  `render_stmt` для оператора с `stream` рендерит `_end(compose(stream))` с отступом. `regenerate_method` при этом не
  меняется.
- **Дефект-правила** (каждое — отдельный `Defect` с `line_start` строки цепочки, `node_id` узла этой строки):
  1. Стрим по той же коллекции внутри цикла по ней (`for (T x : xs)` / `xs.size()`-цикл, внутри `xs.stream()`) — warning, `O(n²)`.
  2. `collect(Collectors.toList()|toSet()).size()` — hint: «используйте `count()`».
  3. `filter(…).findFirst().isPresent()` / `findAny().isPresent()` — hint: «используйте `anyMatch(…)`».
  4. `sorted(…).findFirst()` — warning, `O(n log n)`: «используйте `min(…)`/`max(…)` — O(n)».
  5. `forEach(…)` с лямбдой, которая вызывает `add/put/remove` у внешней коллекции, — hint: «соберите результат через `collect(…)`».
  6. Цикл for-each, тело которого — один `if (…) list.add(x)` (или просто `list.add(f(x))`), — hint «цикл можно заменить стримом: `xs.stream().filter(…).collect(…)`».
  Советы при выключенном ИИ — в `ai/static_tips.py` (по тексту сообщения, как существующие).

## Review Focus

- Многострочная цепочка (`.filter` на следующей строке) — узлы получают свои строки, roundtrip без правок даёт тот же текст (тест в Task 2).
- Цепочка с лямбдой-блоком `x -> { … }` и ссылкой на метод `String::valueOf` — разбирается, правка соседнего шага не портит лямбду (тест в Task 2).
- Оператор без стрима после стрима — id остальных узлов детерминированы, правка обычного узла по-прежнему работает (тест в Task 2).
- `list.stream().forEach(...)` в цикле по `list` — `O(n²)` и дефект правила 1; стрим в цикле по другой коллекции — `O(n²)` без дефекта (тесты в Task 4 и Task 5).
- Цепочка, которую парсер не узнал (неизвестный метод в середине), — остаётся обычным узлом, Big O не падает (тест в Task 1 и Task 4).

---

### Task 1: Разбор цепочек в парсере

**Files:**
- Create: `backend/core/streams.py` (распознавание цепочки по узлу javalang и `compose`)
- Modify: `backend/core/parser.py` (`_stmt_to_dict` ставит `stream`)
- Test: `backend/tests/test_streams.py`

**Interfaces:**
- Produces: `stream_of(expr, prefix: str, stmt_line: int | None) -> dict | None` (javalang-выражение → поле `stream` или `None`); `compose(stream: dict) -> str`; константы `SOURCE_CALLS`, `STREAM_OPS`, `TERMINALS`. Поле `stream` по «Решениям».

- [ ] **Step 1: Тесты** (через `parse_java` на маленьком классе):
  - `List<String> r = list.stream().filter(x -> x > 0).map(String::valueOf).collect(Collectors.toList());` → `prefix == "List<String> r = "`, `source.text == "list.stream()"`, имена операций `["filter","map"]`, `terminal.name == "collect"`, `terminal.tail == ""`; `compose(...)` равен тексту оператора без `;`.
  - `return items.stream().anyMatch(i -> i.price > 10);` → `prefix == "return "`, операций нет, терминал `anyMatch`.
  - `long c = Arrays.stream(arr).filter(v -> v % 2 == 0).count();`, `IntStream.range(0, n).map(i -> i * i).sum();`, `this.items.stream().sorted().findFirst().get();` (`tail == ".get()"`), `r = xs.stream().distinct().collect(Collectors.toSet());` (присваивание, `prefix == "r = "`).
  - многострочная цепочка: `line` у `.filter` на второй строке — 2-я строка цепочки.
  - не раскладываются: `foo(list.stream().count());`, `list.stream().weird().count();`, `int n = list.size();` → нет `stream`.
- [ ] **Step 2:** `venv/bin/python -m pytest tests/test_streams.py -q` → FAIL.
- [ ] **Step 3:** Реализовать (текст частей — через `parser._expr_to_str`/`_prefix_postfix`, чтобы совпадал с текстом оператора).
- [ ] **Step 4:** Тесты и весь `pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat(streams): recognise stream chains in the parser`.

---

### Task 2: Узлы конвейера на CFG и правка шагов

**Files:**
- Modify: `backend/core/cfg_builder.py`, `backend/core/code_generator.py`
- Test: `backend/tests/test_streams.py` (CFG и генерация), `backend/tests/test_api_flow.py` (сквозной `/api/generate`)

**Interfaces:**
- Consumes: Task 1 поле `stream`, `compose`.
- Produces: типы узлов `stream-source`, `stream-op`, `stream-terminal`; `apply_edit`/`render_stmt` по «Решениям».

- [ ] **Step 1: Тесты:**
  - метод `s()` с `List<Integer> r = xs.stream().filter(x -> x > 0).map(x -> x * 2).collect(Collectors.toList()); System.out.println(r);` → узлы `START, END, stream-source, stream-op, stream-op, stream-terminal, statement` с метками `"List<Integer> r = xs.stream()"`, `"filter(x -> x > 0)"`, `"map(x -> x * 2)"`, `"collect(Collectors.toList())"`; рёбра идут по цепочке; повторная сборка даёт те же id.
  - `regenerate_method(method, {})` → тело совпадает с текущим рендером без стримов (сравнить с рендером, где поле `stream` удалено).
  - правка `{id_filter: "filter(x -> x >= 0)"}` → строка становится `List<Integer> r = xs.stream().filter(x -> x >= 0).map(x -> x * 2).collect(Collectors.toList());`, остальное тело не меняется; правка с ведущей точкой `".filter(x -> x >= 0)"` даёт то же.
  - правка источника `"List<Integer> r = ys.stream()"` и `"ys.stream()"` → в обоих случаях источник `ys.stream()`, префикс сохранён.
  - многострочная цепочка и цепочка с `x -> { return x + 1; }` и `String::valueOf` — правка одного шага не трогает остальные.
  - `/api/generate` (по образцу существующих тестов в `test_api_flow.py`): правка метки `stream-op` возвращает код, который компилируется (`runner.check_compiles(...) == []`) и печатает ожидаемый результат.
- [ ] **Step 2:** → FAIL. **Step 3:** Реализовать. **Step 4:** весь `pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat(streams): stream pipeline nodes in CFG with editable steps`.

---

### Task 3: Узлы стрима в интерфейсе

**Files:**
- Modify: `frontend/src/components/GraphCanvas/nodes/kinds.ts`, `frontend/src/components/GraphCanvas/nodes/CFGNode.tsx`, `frontend/src/index.css`

**Interfaces:**
- Consumes: Task 2 типы узлов.
- `CFG_KINDS`: `stream-source` → `{kind: 'stream', label: 'Источник стрима'}`, `stream-op` → `{kind: 'stream', label: 'Шаг стрима'}`, `stream-terminal` → `{kind: 'stream', label: 'Итог стрима'}`; `LEGEND` — запись `{kind: 'stream', label: 'Стрим'}`. Цвет семейства `stream` — в стиле `DESIGN.md`, отличим от остальных в тёмной и светлой теме; текст шага — моноширинный; длинная метка переносится, а не обрезается. Двойной клик открывает существующий редактор узла (как у `statement`).

- [ ] **Step 1:** Реализовать.
- [ ] **Step 2:** `npm run build`, `npx vitest run`.
- [ ] **Step 3:** Ручная проверка: `uvicorn` + `npm run dev`, файл с цепочкой — конвейер на графе, правка шага двойным кликом меняет код в редакторе. Скриншоты (тёмная/светлая) — путь в отчёте.
- [ ] **Step 4:** Commit `feat(streams): stream nodes on the graph`.

---

### Task 4: Big O по шагам цепочки

**Files:**
- Modify: `backend/core/bigo_analyzer.py`
- Test: `backend/tests/test_bigo.py`

**Interfaces:**
- Consumes: Task 1 поле `stream`.
- Стоимость оператора с `stream` = худшее из: стоимости текста `prefix` и аргументов источника (прежним способом) и стоимости цепочки. Цепочка: `n` = `LINEAR`; для каждой операции/терминала стоимость на элемент = `_expr_cost` его `args` (лямбда); вклад шага = `LINEAR × на_элемент`; `sorted` и терминалы `collect(Collectors.toMap|groupingBy|toSet|joining…)`/`distinct` — по «Global Constraints» (`sorted` → `NLOGN`); `flatMap` → `_mul(LINEAR, LINEAR)` × на элемент. Цепочка не проходит через `_LINEAR_CALL_RE`/`_SORT_RE` повторно (без двойного счёта). Операторы без `stream` — без изменений.

- [ ] **Step 1: Тесты:** `xs.stream().map(x -> x * 2).collect(Collectors.toList())` → `O(n)`; `.sorted().collect(...)` → `O(n log n)`; `.filter(x -> ys.contains(x))` при `List<Integer> ys` → `O(n²)`; `.flatMap(l -> l.stream())` → `O(n²)`; цепочка внутри `for (Integer a : xs)` → `O(n²)`; `.limit(5).collect(...)` → `O(n)`; `IntStream.range(0, n).sum()` → `O(n)`; неузнанная цепочка (`list.stream().weird().count()`) → прежняя оценка, без исключений; оценки `test_monoliths/*` не изменились (сравнить с текущими значениями `analyze_ast`).
- [ ] **Step 2:** → FAIL. **Step 3:** Реализовать. **Step 4:** весь `pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat(streams): Big O from stream steps`.

---

### Task 5: Дефекты и советы для стримов

**Files:**
- Modify: `backend/core/defect_detector.py`, `backend/ai/static_tips.py`
- Test: `backend/tests/test_streams_defects.py`

**Interfaces:**
- Consumes: Task 1 поле `stream`; Task 2 `node_id` по строке (существующий `_node_id_for_line`).
- 6 правил из «Решений»; тексты сообщений и рекомендаций — на русском, с упоминанием метода (`Класс.метод`), как у существующих правил; `severity` и `big_o` — как в «Решениях»; `tip_for` возвращает статический совет для каждого нового сообщения.

- [ ] **Step 1: Тесты:** на каждое правило — положительный пример (1 дефект нужного вида на нужной строке) и отрицательный (похожий код без дефекта: стрим в цикле по другой коллекции; `collect(...)` без `.size()`; `anyMatch`; `min(...)`; `forEach(System.out::println)`; цикл с двумя операторами в теле); `tip_for(message)` не пустой для каждого нового сообщения; существующие дефекты `test_monoliths/*` не изменились.
- [ ] **Step 2:** → FAIL. **Step 3:** Реализовать. **Step 4:** весь `pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat(streams): stream defects and static tips`.

---

### Task 6: Демо-пример и документация

**Files:**
- Create: `test_monoliths/Streams.java`, `frontend/src/examples/Streams.java` (одинаковые)
- Modify: место, где перечислены примеры (`frontend/src/project/examples.ts` или аналог), `backend/tests/test_runner.py` (параметризация `test_monoliths_run`), `README.md`, `CLAUDE.md`, `docs/architecture.md`, `todo.md`

- [ ] **Step 1:** `Streams.java` — программа без ввода, детерминированный вывод: заказы/товары с цепочками `filter/map/collect`, `sorted`, `groupingBy`, `flatMap`, плюс по одному случаю на каждое из 6 правил дефектов.
- [ ] **Step 2:** Тест: `Streams` в `test_monoliths_run`; отдельный тест — `detect_defects` на `Streams.java` находит все 6 видов; CFG `main` содержит узлы `stream-op`.
- [ ] **Step 3:** README — раздел «Стримы»: конвейер на графе, правка шага, Big O, правила; CLAUDE.md — `core/streams.py`, поле `stream`, новые типы узлов; `docs/architecture.md`; `todo.md` — отметить этап 6 и пункты 6.1–6.6 (со ссылкой на этот план).
- [ ] **Step 4:** Полная проверка бэкенда и фронтенда — зелёная.
- [ ] **Step 5:** Commit `feat(streams): demo example and docs (stage 6)`.
