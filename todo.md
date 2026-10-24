# TODO — Java Blueprints: исправления, покрытие, стримы, Python и C++

Дизайн (главный документ, все решения пользователя): `docs/superpowers/specs/2026-10-24-multilang-coverage-design.md`
Ветка: `feature/multilang-coverage` (в `main` сливаем только после всех этапов)

## Этапы

- [x] **1. Дефекты всегда актуальны + ИИ-исправление ошибок** — код готов, ИИ-функции проверите вы
- [x] **2. Сравнение выводов по файлу (предыдущий ↔ последний запуск)**
- [x] **3. Выгрузка: текущий файл и zip изменённых**
- [ ] **4. Покрытие кода (аналог JavaScope)**
- [ ] **5. Сложность «сейчас → после ИИ» и ожидаемое ускорение**
- [ ] **6. Stream API и Collectors (Java)**
- [ ] **7. Python**
- [ ] **8. C++**
- [ ] **Слить `feature/multilang-coverage` в `main`** — только после завершения всех этапов

## Как продолжить работу (если сессия прервалась)

1. Прочитать этот файл и дизайн-документ (раздел нужного этапа). Все вопросы пользователю уже заданы — ответы в дизайне.
2. Превратить план этапа ниже в подробный план-документ: навык `superpowers:writing-plans` →
   `docs/superpowers/plans/<дата>-stage<N>-<тема>.md` (как `2026-10-24-stage1-3-defects-compare-download.md`).
3. Выполнять: `superpowers:subagent-driven-development` (пользователь выбрал «по задачам с проверкой»).
4. Правила пользователя: ИИ-функции вручную не проверять (проверит сам); в `main` не сливать до конца всех этапов;
   UI на русском; стиль — `DESIGN.md`; в коммит не добавлять чужие неотслеживаемые файлы (`AGENTS.md`, `.DS_Store`,
   `backend/package-lock.json`).
5. Проверка на каждом шаге: `cd backend && venv/bin/python -m pytest -q`; `cd frontend && npm run build && npx vitest run`.
6. После этапа — отметить галочки здесь и закоммитить.

---

## Этапы 1–3 — план работ (выполнено)

План: `docs/superpowers/plans/2026-10-24-stage1-3-defects-compare-download.md`

- [x] Единое правило проверки правок ИИ: правка не добавляет новых ошибок; для «Исправить» — ещё и убирает целевую ошибку
- [x] ИИ показывает только применимые правки; до 2 повторных запросов к модели, если ни одна правка не прошла проверку
- [x] Ошибки `javac` (с номерами строк) приходят в `/api/analyze` (`compileErrors`: `null` — javac не запускался, `[]` — чисто)
- [x] `/api/ai/fix` — исправление ошибки компиляции/синтаксиса через ИИ
- [x] Тесты фронтенда (vitest) + утилита «фрагмент ещё в коде»
- [x] Панель «Дефекты»: устаревшие советы скрываются сразу, старые ответы анализа не перетирают новые, раздел «Синтаксис и компиляция», кнопка «✨ Исправить с ИИ»
- [x] История запусков по каждому файлу (2 последних), сравнение «предыдущий ↔ последний», статусы (исключение, таймаут, остановка, лимит вывода), пометка «Ввод отличался»
- [x] Скачать активный файл; «Скачать изменённые» — zip с папками; опасные пути отклоняются
- [x] Документация (README, CLAUDE.md, docs/architecture.md)
- [x] Финальное ревью всей ветки и исправления по нему (устаревшие ответы ИИ скрываются; javac главнее парсера для ошибок; гонки в консоли и анализе)
- [ ] Ручная проверка ИИ-функций (делаете вы): «Объяснить с ИИ», «✨ Исправить с ИИ», авто-ревью «✨ N идей»

Отложенные мелочи (не мешают работе, можно сделать позже):
- [ ] Тесты, зависящие от `javac`, пропускать, если `javac` нет (docker/CI)
- [ ] `/api/files/zip`: отклонять `C:`, сегменты `.`, управляющие символы, дубликаты путей; лимит размера/числа файлов
- [ ] Проверка правок ИИ: компилировать исходный код один раз на ответ, а не на каждую правку
- [ ] Режим «Исправить»: учитывать сдвиг строк от добавленных `import`

---

## Этап 4 — Покрытие кода (аналог JavaScope)

**Цель.** После каждого Run видно, какие строки, методы, ветки, условия и граничные случаи сравнений выполнились.
Покрытие накапливается по запускам одного и того же кода. Дизайн: раздел 4.

**Подход.** Инструментирование исходника Java по AST (javalang): в копию кода вставляются вызовы
счётчика, номера строк сохраняются (вставки — в той же строке). Данные пишутся в файл во временной папке
запуска, а не в stdout/stderr. Байткодные агенты (JaCoCo) не подходят — не дают логического и реляционного покрытия.

**Модель данных (бэкенд → фронтенд).**
```
Probe = { id: int, kind: "line"|"method"|"branch"|"cond"|"rel", line: int, method: "Class.m",
          label: str,            # "if (x > 0) → да", "x > 0 && y", "a < b"
          outcomes: [str] }      # branch: ["true","false"]; cond: ["true","false"]; rel: ["<","==",">"]; line/method: ["hit"]
CoverageRun = { codeHash: str, probes: [Probe], hits: { "<probeId>:<outcome>": count } }
```

**Задачи.**
- [ ] **4.1 Каталог проб + инструментатор (бэкенд).** Новый `backend/core/coverage/instrument.py`:
  `instrument_java(code: str) -> tuple[str, list[Probe]]`. Вставляет:
  `__Cov.l(id)` в начало каждого оператора; `__Cov.m(id)` в начало тела метода/конструктора;
  ветки: `if`/`else`, `case`, тело цикла (вошли/не вошли), `?:`, `catch`;
  условия: каждое элементарное условие внутри `&&`/`||`/`!` оборачивается `__Cov.c(id, <expr>)` (возвращает boolean);
  сравнения: `a < b` → `__Cov.r(id, a, b, "<")` (перегрузки для int/long/double/char; для объектов `==`/`!=` не трогать).
  Нельзя ломать: `switch`-метки-константы, инициализаторы полей-констант, `final`-локали в лямбдах, конструкторы с `this(...)`/`super(...)` первой строкой.
  Тест: инструментированный `test_monoliths/*.java` компилируется и печатает тот же вывод, что исходник.
- [ ] **4.2 Класс-счётчик.** `backend/core/coverage/Cov.java` (добавляется в папку запуска как `__Cov.java`):
  статические `l/m/c/r`, счётчики в `int[]`, сброс в файл `cov.bin`/`cov.json` через `Runtime.addShutdownHook`
  (срабатывает при обычном выходе, исключении, `System.exit`; при `kill` — данные теряются → пометить запуск «покрытие неполное»).
  Путь к файлу — через системное свойство `-Djb.cov=<path>`.
- [ ] **4.3 Запуск с покрытием.** `core/interactive.py::start_session` и `runner.run_files`: компилировать
  инструментированный код + `__Cov.java`; после завершения прочитать файл покрытия; в WebSocket добавить сообщение
  `{type: "coverage", codeHash, probes, hits}` перед `exit`. Если инструментирование/компиляция инструментированного кода
  упали — запустить исходный код как раньше и прислать `{type: "coverage", error: "<причина>"}`.
  Docker-режим: тот же файл в смонтированной папке. Тест: `tests/test_coverage.py` через WebSocket-клиент (как `test_ws.py`).
- [ ] **4.4 Метрики.** `backend/core/coverage/metrics.py`: `summarize(probes, hits) -> {lines, methods, branches, conditions, relational: {covered, total, percent}, perMethod: {...}, missing: [{line, kind, label, outcome}]}`.
  Строка «частично» = выполнена, но у её веток/условий/сравнений есть непройденные исходы. Юнит-тесты на ручных наборах проб.
- [ ] **4.5 Накопление (фронтенд).** `frontend/src/utils/coverage.ts`: `mergeCoverage(prev, run)` — складывает `hits`,
  если `codeHash` совпадает, иначе начинает заново; хранится в `useProject` по `fileId` (`coverage: Record<fileId, {codeHash, probes, hits, runs: number}>`).
  Правка кода (хеш текущего текста ≠ `codeHash`) → покрытие считается сброшенным. Кнопка «Сбросить покрытие». vitest-тесты.
  Метрики считать на фронте той же формулой, что `metrics.py` (или прислать готовые с бэкенда и суммировать hits на фронте — решить в подробном плане; проще: метрики на фронте).
- [ ] **4.6 Редактор.** `AceEditor.tsx`: метки в gutter — зелёная (выполнена), красная (не выполнена), жёлтая (частично);
  тултип «выполнено N раз; не пройдено: …». Показывать только если покрытие относится к текущему коду.
- [ ] **4.7 Панель «Покрытие».** Новая вкладка в `BottomPanel`: проценты по 5 метрикам для файла и по методам,
  «запусков учтено: N», «Сбросить покрытие», список непройденного с переходом к строке; состояния «Запустите программу»
  и «Код изменён — покрытие сброшено, запустите снова»; причина, если покрытие недоступно.
- [ ] **4.8 Документация + финальная проверка.** README/CLAUDE.md/architecture.md.

**Риски.** Перегрузки `__Cov.r` для смешанных типов (`int < long`, `char < int`) — проще приводить к `double` для
числовых и `compareTo` не трогать; дженерики/автоупаковка (`Integer == Integer`) — не оборачивать `==`/`!=` для не-примитивов
(тип неизвестен без типизации — оборачивать только если оба операнда — литералы/локали примитивного типа из объявлений).

---

## Этап 5 — Сложность «сейчас → после ИИ» и ожидаемое ускорение

**Цель.** В строке «Сложность методов · Big O» видно текущую сложность и сложность после предложенных ИИ правок,
с ожидаемым ускорением по формуле. Дизайн: раздел 5.

**Задачи.**
- [ ] **5.1 Big O для патча (бэкенд).** В `ai/patcher.build_patch` после валидной проверки: `analyze_ast(parse_java(patched)["ast"])`
  vs `analyze_ast` исходника → поля патча `bigo_before: {method: O}`, `bigo_after: {method: O}` только для методов, у которых
  изменилась строка (или чей спан пересекает правку). Схема `AiPatch` + camelCase. Тест: патч `mergeItems` (вложенный цикл →
  HashMap) даёт `O(n²)` → `O(n)`.
- [ ] **5.2 Ожидаемое ускорение.** `frontend/src/utils/speedup.ts`: `speedup(before: string, after: string, n = 1000): {factor: number | null, label: string, worse: boolean}`.
  Оценка `f(n)` для классов: 1, log n, n, n log n, n², n³, 2ⁿ, n! (как в `utils/bigo.ts`); `factor = f_before/f_after`;
  округление к ~2×, ~5×, ~10×, ~100×, ~1000× (ближайшее «красивое»); та же сложность → `null`; хуже → `worse=true`.
  vitest на таблицу случаев.
- [ ] **5.3 «После ИИ» по методу.** `frontend/src/utils/bigoAfter.ts`: из текущих применимых советов (`aiReview.items` + `ai.patch`)
  собрать для каждого метода лучший `bigo_after`. Несколько непересекающихся советов на один метод — сервер считает совместное
  применение: новый эндпоинт `POST /api/ai/bigo-combined {code, patches[]}` → применяет по очереди через `patcher.replace_range`
  (сдвиги строк), при пересечении спанов берёт патч с лучшей сложностью, возвращает `{method: O}`. Тесты бэкенда.
- [ ] **5.4 UI.** `DiagnosticsPanel` строка метода: `O(n²) → O(n) · ~1000× быстрее` (тултип «при n ≈ 1000»); красным, если хуже;
  без «быстрее» при той же сложности. Тот же бейдж в `PatchView` рядом с diff.
- [ ] **5.5 Документация + проверка.**

---

## Этап 6 — Stream API и Collectors (Java)

**Цель.** Стримы — полноценные граждане: конвейер на графе, правка шагов через граф, правильный Big O, дефекты/советы.
Дизайн: раздел 6.

**Задачи.**
- [ ] **6.1 Разбор цепочек (парсер).** В `core/parser.py` для выражений с `.stream()`/`.parallelStream()`/`Arrays.stream`/`Stream.of`/`IntStream.range`:
  поле оператора `stream: {source: str, ops: [{name, args: str, line}], terminal: {name, args}}` из дерева javalang
  (`MethodInvocation` с `qualifier`/`selectors`). Тест на цепочку `list.stream().filter(x -> x > 0).map(String::valueOf).collect(Collectors.toList())`.
- [ ] **6.2 Узлы конвейера (CFG).** `core/cfg_builder.py`: оператор со `stream` разворачивается в цепочку узлов типа
  `stream-source` → `stream-op` × N → `stream-terminal`, id детерминированные (продолжают нумерацию `n…`), карта узел→шаг.
  Фронт: новые виды узлов в `GraphCanvas/nodes/kinds.ts` и `CFGNode.tsx` (иконка/цвет по `DESIGN.md`).
- [ ] **6.3 Правка шагов через граф.** `core/code_generator.py`: правка метки узла `stream-op` (`filter(x -> x >= 0)`) →
  пересборка выражения цепочки и вставка в исходный оператор по спану; `/api/generate` уже сравнивает метки — добавить
  поддержку новых типов. Тест roundtrip: без правок — тот же вывод; правка `filter` меняет код ожидаемо.
- [ ] **6.4 Big O.** `core/bigo_analyzer.py`: вместо regex `.stream(` — по `stream.ops`: каждый проход O(n); `sorted` O(n log n);
  `distinct`/`groupingBy`/`toSet`/`toMap` O(n); `flatMap` — умножение на внутренний размер (m → O(n·m), выводить O(n²) при той же коллекции);
  стрим в цикле — умножение; `limit`/`findFirst`/`anyMatch` не снижают оценку. Тесты.
- [ ] **6.5 Дефекты/советы (5–8 правил).** `core/defect_detector.py`: стрим в цикле по той же коллекции;
  `collect(toList()).size()` → `count()`; `filter(..).findFirst().isPresent()` → `anyMatch`; `sorted().findFirst()` → `min`;
  `forEach` с изменением внешней коллекции; `map(..).filter(Objects::nonNull)` порядок; «цикл можно заменить стримом» (hint).
  Статические подсказки в `ai/static_tips.py`. Тесты на каждое правило.
- [ ] **6.6 Демо-пример** со стримами в `test_monoliths/` и `frontend/src/examples/`; документация.

---

## Этап 7 — Python

**Цель.** `.py`-файлы работают как Java: графы, дефекты, Big O, правка через граф, запуск, сравнение, покрытие,
декомпозиция, ИИ. Дизайн: разделы 7–8.

**Архитектура (общая с этапом 8).** Слой языков `backend/core/lang/`:
```
class Language(Protocol):
    name: str                       # "java" | "python" | "cpp"
    extensions: tuple[str, ...]
    def parse(code) -> {"ast", "line_map", "errors"}      # нормализованный AST как у Java
    def render_method(method, edits) -> str               # перегенерация тела функции
    def check(code) -> list[dict] | None                  # ошибки компиляции/синтаксиса
    def run_cmd(tmp, files, entry) -> list[str]           # команда запуска (subprocess/docker)
    def decompose(code, ast) -> DecomposeResponse
    def instrument(code) -> (code, probes)                # покрытие
LANGS = {"java": Java(), "python": Python(), "cpp": Cpp()}; def by_filename(name) -> Language
```
Нормализованный AST — те же типы операторов, что у javalang (`IfStatement`, `ForStatement`, `WhileStatement`,
`DoStatement`, `SwitchStatement`, `TryStatement`, `ReturnStatement`, `ThrowStatement`, `BreakStatement`,
`ContinueStatement`, `StatementExpression`, `LocalVariableDeclaration`, `BlockStatement`), чтобы `cfg_builder`,
`bigo_analyzer`, `call_graph`, `class_diagram` и общая часть `defect_detector` работали без изменений.
Свободные функции модуля → псевдокласс с именем модуля (`demo.main`).

**Задачи.**
- [ ] **7.1 Слой языков + Java как первый адаптер.** Вынести Java-специфику (`parse_java`, `runner`, `code_generator`,
  `decomposer`, `check_compiles`) за интерфейс `Language`, не меняя поведение. Поле `language` во всех запросах с кодом
  (по умолчанию `"java"`), `state.SESSION.language`. Все существующие тесты проходят.
- [ ] **7.2 Фронтенд: язык по расширению.** `utils/language.ts`: `languageOf(name) -> 'java'|'python'|'cpp'`; `useProject`
  хранит язык файла; все вызовы API передают `language`; Ace-режим (`mode-python`, `mode-c_cpp`); загрузка `.py`/`.cpp` в `FileUpload`;
  название `"Java Blueprints"` оставить.
- [ ] **7.3 Парсер Python.** `core/lang/python/parser.py` на `ast`: классы, методы, функции модуля (псевдокласс), поля
  (присваивания `self.x` в `__init__`), параметры, спаны (`lineno`/`end_lineno`), операторы → нормализованные типы:
  `if/elif/else` → `IfStatement` (elif = вложенный if в else), `for`/`while` (+`else` — отдельная ветка), `break`/`continue`,
  `return`, `try/except/else/finally` → `TryStatement`, `raise` → `ThrowStatement`, `with` → блок, `match` → `SwitchStatement`;
  прочее → `StatementExpression` с исходным текстом (`ast.get_source_segment`). Синтаксические ошибки — с номером строки.
- [ ] **7.4 Big O и дефекты Python.** Big O: comprehensions/генераторы — цикл; `sorted`/`.sort()` O(n log n); `in list` O(n);
  `sum/any/all/map/filter/min/max` O(n). Дефекты: конкатенация строк в цикле (`s += ...`), `x in list` в цикле,
  вложенный цикл по одной коллекции, пустой `except:`/`except Exception: pass`, изменяемый аргумент по умолчанию, `range(len(x))`.
- [ ] **7.5 Перегенерация кода Python.** `render_method`: операторы → текст с отступами 4 пробела, правка меток узлов,
  вставка по спану функции. Тест roundtrip как у Java.
- [ ] **7.6 Запуск Python.** `python3 -u main.py` (subprocess, таймаут 10 с, лимит памяти через `resource.setrlimit`
  в `preexec_fn`); docker — образ sandbox с `python3`. Интерактивная консоль (`interactive.py` через `Language.run_cmd`),
  `check` = `py_compile` (ошибки с номерами строк), сравнение и история запусков без изменений.
- [ ] **7.7 Покрытие Python.** `sys.settrace`/`sys.monitoring` для строк и функций + AST-трансформация условий и сравнений
  (`__cov.c(id, expr)`, `__cov.r(id, a, b, op)`), запись в файл; тот же формат `Probe`/`hits`.
- [ ] **7.8 Декомпозиция Python.** Группировка функций/классов как у Java → модули `.py` с `from x import ...`;
  исходный файл — фасад с `main`. Quality Gate запускает набор файлов и сравнивает вывод.
- [ ] **7.9 ИИ под Python.** Промпты с параметром языка (`{language}`, блок ```python```, `imports` → `import` строки);
  `patcher.add_imports`/`validate` через `Language.check`.
- [ ] **7.10 Демо-примеры** `test_monoliths/*.py` (аналоги Calculator/Store/Analyzer/Logger с теми же дефектами), на экране
  приветствия; `python3` в `backend/Dockerfile` (уже есть) и `sandbox/Dockerfile`; документация.

---

## Этап 8 — C++

**Цель.** То же для `.cpp`/`.cc`/`.cxx`/`.hpp`/`.h` (C++17). Использует слой языков из этапа 7.

**Задачи.**
- [ ] **8.1 Парсер C++.** `core/lang/cpp/parser.py` на `tree-sitter` + `tree-sitter-cpp` (pip, добавить в `requirements.txt`):
  классы/структуры, методы (включая определённые вне класса `A::f` — привязать к классу), конструкторы, свободные функции
  (псевдокласс по имени файла), `namespace` (префикс в имени), поля, параметры, спаны. Операторы: `if/else`, `for`,
  range-`for`, `while`, `do-while`, `switch`, `break`/`continue`, `return`, `try/catch`, `throw` → нормализованные типы;
  прочее (лямбды, шаблоны, макросы, перегрузка операторов, `goto`) → `StatementExpression` с исходным текстом.
  Ошибки синтаксиса — узлы `ERROR` дерева с номерами строк.
- [ ] **8.2 Big O и дефекты C++.** `<algorithm>`: `std::sort` O(n log n); `std::find`/`count_if`/`accumulate`/`copy` O(n);
  `vector::insert/erase` в начале в цикле; `std::find` в цикле. Дефекты: `std::string +=` в цикле, передача больших
  объектов по значению (`const T&`), `new` без `delete`, `catch (...)` без обработки, вложенный цикл по одному контейнеру.
- [ ] **8.3 Перегенерация кода C++.** `render_method` с фигурными скобками и отступами; roundtrip-тест.
- [ ] **8.4 Сборка и запуск.** `g++ -std=c++17 -O0 -o main main.cpp` (ошибки `g++` → `{line, message}` для `check` и панели),
  запуск бинаря с таймаутом/лимитом памяти; docker — `g++` в `sandbox/Dockerfile` и `backend/Dockerfile`.
  `.h`/`.hpp` — анализ есть, кнопка Run неактивна с подсказкой.
- [ ] **8.5 Покрытие C++.** Инструментирование исходника (как Java): `__cov_l(id)`, `__cov_c(id, expr)`,
  шаблонная `__cov_r(id, a, b, op)`; заголовок `__cov.h` пишет файл в `atexit`.
- [ ] **8.6 Декомпозиция C++.** Свободные функции/классы → пары `.h`/`.cpp` с `#pragma once` и `#include "x.h"`;
  Quality Gate компилирует все `.cpp` вместе и сравнивает вывод.
- [ ] **8.7 ИИ под C++.** Промпты (`cpp`, `imports` → `#include <...>`), проверка через `g++ -fsyntax-only`.
- [ ] **8.8 Демо-примеры** `test_monoliths/*.cpp`; документация; финальное ревью всей ветки после всех этапов.
