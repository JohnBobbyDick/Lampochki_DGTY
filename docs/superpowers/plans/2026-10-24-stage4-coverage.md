# Этап 4: покрытие кода (аналог JavaScope) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** После каждого Run в интерактивной консоли видно, какие строки, методы, ветки, элементарные условия и
граничные случаи сравнений выполнились; покрытие накапливается по запускам одного и того же текста файла и
показывается метками в редакторе и в панели «Покрытие».

**Architecture:** Бэкенд инструментирует исходник Java по токенам javalang + AST (вставки без переводов строк,
номера строк сохраняются), добавляет класс-счётчик `__Cov`, который пишет счётчики в отображённый в память
файл (данные не теряются при Stop/таймауте/`kill`), и после завершения процесса присылает по WebSocket
сообщение `coverage` с каталогом проб и массивом счётчиков. Фронтенд хранит покрытие по `ProjectFile.id`,
суммирует запуски одинакового текста, считает метрики (`utils/coverage.ts`) и рисует метки в gutter и панель.

**Tech Stack:** FastAPI, javalang, javac 11+, Java `MappedByteBuffer`; React 18, Zustand, Ace, vitest.

**Spec:** `docs/superpowers/specs/2026-10-24-multilang-coverage-design.md` — раздел 4 (Java). Python и C++
получают покрытие в этапах 7–8 через тот же формат проб и те же фронтенд-утилиты.

## Global Constraints

- Все строки UI — на русском; стиль по `DESIGN.md`; цвета меток — существующие токены `--ok` (выполнена), `--err` (не выполнена), `--warn` (частично).
- Метрики: строки, методы, ветвления (`if`/`else`, `case`, тело цикла выполнялось/пропускалось, `?:`, `catch`), логическое (каждое элементарное условие внутри `&&`/`||`/`!` принимало `true` и `false`), реляционное (`<`,`<=`,`>`,`>=`: встречались `a<b`, `a==b`, `a>b`).
- Покрытие собирается всегда при Run в интерактивной консоли, без отдельного режима; ввод `Scanner` работает как раньше.
- Вывод программы (stdout/stderr) не меняется из-за инструментирования; данные покрытия идут только через файл в temp-каталоге запуска.
- Если инструментирование невозможно — программа запускается без покрытия, а панель показывает причину. Ошибки компиляции пользователя показываются как раньше (номера строк исходника).
- Накопление: запуски одного и того же текста файла суммируются; любая правка текста сбрасывает накопление окончательно (возврат текста через Ctrl+Z его не восстанавливает); кнопка «Сбросить покрытие»; счётчик «Запусков учтено: N».
- В покрытие идут все запуски, дошедшие до выполнения: исключение, ненулевой exit, таймаут, Stop, лимит вывода.
- Таймаут сессии и `-Xmx256m` не меняются.
- Проверка после каждой задачи: `cd backend && venv/bin/python -m pytest -q`; `cd frontend && npm run build && npx vitest run`.
- Не коммитить чужие неотслеживаемые файлы (`AGENTS.md`, `.DS_Store`, `backend/package-lock.json`). ИИ-функции вручную не проверять.

## Решения контроллера (обязательны для исполнителей)

- Инструментируется только интерактивный запуск (`/api/ws/run`). Пакетный `runner.run_files` (Quality Gate, проверка декомпозиции) не трогаем.
- Метрики считаются только на фронтенде (накопление тоже там) — бэкенд-модуля `metrics.py` нет.
- Вместо `codeHash` фронтенд хранит сам текст кода, с которым был запуск, и сравнивает строки.
- Счётчики — `int32` little-endian в файле, который `__Cov` отображает в память (`MappedByteBuffer`); Python заранее создаёт файл нужного размера из нулей. Shutdown hook не нужен.
- Пробы ставятся только в «решениях»: условия `if`, `while`, `do`, `for`, `?:`. Логическое и реляционное покрытие — только внутри этих условий (`boolean ok = a < b;` не инструментируется).
- `==`/`!=` — тоже реляционные пробы, но с исходами `["==","!="]` (тип операндов неизвестен; для объектов и `boolean` сравнение «меньше/больше» невозможно).
- `case`-группа и `catch` — ветки с одним исходом `["выполнен"]`; неявный «ни один case не подошёл» не учитывается.
- Перегруженные методы с одинаковым именем в таблице «по методам» объединяются под одним `Класс.метод`.
- Деградация при ошибке компиляции инструментированного кода (только локальный режим): компилируем исходник; если он тоже не компилируется — это ошибка пользователя (обычный `compile_error`). Иначе до двух повторов: раунд 1 — на строках с ошибками javac убираем пробы `branch/cond/rel` (и связанные с ними вставки), раунд 2 — убираем все пробы на этих строках; если и это не скомпилировалось — запуск исходника без покрытия с причиной.
- Docker-режим: без деградации — в контейнере компилируется инструментированный код, а при неудаче исходный; Python узнаёт об этом по файлу-маркеру.

## Формат данных (бэкенд → фронтенд)

```
Probe = { id: int, kind: "line"|"method"|"branch"|"cond"|"rel", line: int, method: str,  # "Demo.main"
          label: str, outcomes: [str], slot: int }    # счётчики исходов: hits[slot + i]
WS:  {type: "coverage", probes: [Probe], hits: [int]}   |   {type: "coverage", error: str}
```
Сообщение `coverage` приходит после всех `stdout`/`stderr` и перед `exit`; после `compile_error` его нет.

Исходы и подписи (`label` — исходный текст условия, пробелы схлопнуты, длиннее 60 символов → обрезка с «…»):

| kind | где | label | outcomes |
|---|---|---|---|
| line | каждый оператор | `""` | `["выполнено"]` |
| method | начало тела метода/конструктора именованного класса | `"Класс.метод"` | `["выполнено"]` |
| branch | `if`, `?:`, `do…while` | `"if (x > 0)"`, `"?: (x > 0)"`, `"do…while (n > 0)"` | `["истина","ложь"]` |
| branch | `while`, `for`, for-each | `"while (i < n)"`, `"for (int v : xs)"` | `["тело выполнялось","тело ни разу не выполнялось"]` |
| branch | `case`-группа / `default` | `"case 1, 2"`, `"default"` | `["выполнен"]` |
| branch | `catch` | `"catch (ArithmeticException)"` | `["выполнен"]` |
| cond | элементарное условие, если в решении есть `&&`/`||`/`!` | `"i > 2"` | `["истина","ложь"]` |
| rel | `<` `<=` `>` `>=` | `"a < b"` | `["<","==",">"]` |
| rel | `==` `!=` | `"i == 1"` | `["==","!="]` |

`while (true)`, `do … while (true)` и `for (;;)` — без branch-пробы (константа; обёртка сломала бы анализ достижимости javac).

## Review Focus

- Тело без фигурных скобок (`if (x) return;`, `else if`, `for (...) n++;`, «висячий» `else`) — после вставок семантика та же (тесты в Task 2 и Task 3).
- Программа с `Scanner` (Logger) — приглашения и вывод идут как раньше, байт в байт (тест в Task 2 и Task 4).
- Stop / таймаут / исключение / `System.exit` — покрытие всё равно приходит с ненулевыми счётчиками (тест в Task 4).
- Сравнения смешанных типов (`Integer == int`, `s == null`, `char < 'z'`, `long < int`, `boolean == boolean`) — компилируется или деградирует, запуск не теряется (тест в Task 3).
- Код изменили, пока программа работала — покрытие старого текста не приклеивается к новому (тест в Task 6).

---

### Task 1: Разбор условий по токенам

**Files:**
- Create: `backend/core/coverage/__init__.py` (пустой), `backend/core/coverage/conditions.py`
- Test: `backend/tests/test_coverage_conditions.py`

**Interfaces:**
- Produces (все индексы — позиции в списке токенов `javalang.tokenizer.tokenize`, диапазоны полуоткрытые `[a, b)`):
  - `@dataclass Cond: kind: Literal["or","and","not","paren","leaf"]; a: int; b: int; children: list[Cond]`
  - `parse_condition(tokens: list, a: int, b: int) -> Cond` — `||` слабее `&&`, слабее `!`; скобочная группа (скобка, перед которой не идентификатор, `)`, `]` или `>`) — `paren` с разбором внутри; `!` раскладывается, только если за ним `paren` или «первичное» выражение без бинарных операторов (иначе весь `!…` — `leaf`); `paren`, внутри которого на верхнем уровне есть `?`, — `leaf`.
  - `has_logic(c: Cond) -> bool` — есть ли в дереве `or`/`and`/`not`.
  - `leaves(c: Cond) -> list[Cond]` — листья слева направо.
  - `split_relation(tokens, a, b) -> tuple[int, str, int] | None` — `(индекс_оператора, оператор, b)`, если в листе на верхнем уровне ровно один токен из `< <= > >= == !=`, обе стороны непусты и на верхнем уровне нет `? : = += -= *= /= %= &= |= ^= <<= >>= >>>= instanceof & | ^ -> new`; иначе `None` (так отсекаются дженерики `Foo.<T>m() > 0`, `new ArrayList<String>()`).
  - `ternary_conditions(tokens, a, b) -> list[tuple[int, int]]` — диапазоны условий `?:` внутри `[a,b)`: для каждого `?`, который не wildcard (wildcard — `?`, за которым `extends`, `super`, `>` или `,`), условие тянется назад на том же уровне вложенности до ближайшего из `( [ , ; { } = <составные присваивания> : ? -> return throw`.

- [ ] **Step 1: Написать тесты** (вспомогательная `toks(s)` токенизирует строку; `text(c)` склеивает значения токенов листа через пробел):
  - `if`-условие `i > 2 && !(n < 3) || i == 1` → корень `or`, слева `and` с листом `i > 2` и `not(paren(leaf n < 3))`, справа лист `i == 1`; `has_logic` — `True`; `[text(l) for l in leaves(...)] == ["i > 2", "n < 3", "i == 1"]`.
  - `list.isEmpty()` → один `leaf`, `has_logic` — `False`; `!list.isEmpty()` → `not(leaf)`; `!a == b` → один `leaf`.
  - `(a ? b : c) && d` → `and(leaf("( a ? b : c )"), leaf(d))`.
  - `split_relation`: `a + b > c` → оператор `>`; `(int) x < y` → `<`; `Foo.<T>bar(x) > 0` → `None`; `x instanceof Foo` → `None`; `(y = f()) > 0` → `>` (присваивание в скобках не на верхнем уровне); `a < b == c` → `None`.
  - `ternary_conditions` для `int y = x > 0 ? 1 : 2;` → одно условие `x > 0`; `f(a, b ? 1 : c ? 2 : 3)` → `b` и `c`; `List<? extends T> l = null;` → пусто; `r = v -> v ? 1 : 2;` → `v`.
- [ ] **Step 2:** `cd backend && venv/bin/python -m pytest tests/test_coverage_conditions.py -q` → FAIL (модуля нет).
- [ ] **Step 3:** Реализовать `conditions.py` (чистые функции, без javac).
- [ ] **Step 4:** Тот же запуск → PASS; весь `pytest -q` зелёный.
- [ ] **Step 5:** Commit `feat(coverage): token-level condition parsing`.

---

### Task 2: Инструментатор (строки, методы), счётчик `__Cov`, сборка с деградацией

**Files:**
- Create: `backend/core/coverage/Cov.java` (шаблон; в начало подставляется `package …;`, если он есть у пользователя), `backend/core/coverage/instrument.py`, `backend/core/coverage/build.py`
- Test: `backend/tests/test_coverage_instrument.py`

**Interfaces:**
- Consumes: Task 1 (пока не используется — подключается в Task 3); `core/source_map.tokenize`, `declaration_span`.
- Produces:
  - `@dataclass Probe(id: int, kind: str, line: int, method: str, label: str, outcomes: list[str], slot: int)` с `to_json() -> dict`.
  - `@dataclass Instrumented(code: str, probes: list[Probe], slots: int, cov_source: str)`.
  - `class CoverageUnavailable(Exception)` — сообщение на русском (например «Не удалось разобрать код для покрытия: …»).
  - `instrument_java(code: str, *, strip: dict[int, int] | None = None) -> Instrumented` — `strip[line] = 1` убирает на строке `branch/cond/rel` (и связанные вставки), `2` — все пробы строки.
  - `build.py`: `@dataclass CovPlan(probes: list[Probe], slots: int, data_file: Path | None, error: str | None)`;
    `compile_local(tmp: Path, fname: str, code: str) -> tuple[subprocess.CompletedProcess | None, CovPlan]` — пишет файлы, компилирует в `tmp/"out"` и возвращает `(None, plan)` при успехе (инструментированный или исходный код скомпилирован, `plan.error` объясняет, если покрытия нет) или `(proc, plan)` с неудачным `javac` **исходника**, если ошибка у пользователя;
    `read_hits(plan: CovPlan) -> list[int] | None` — `None`, если файла нет или размер не `slots*4`.
  - API `__Cov` (вызывается только с литералами-слотами): `h(int s)`; `boolean c(int s, boolean v)` (истина → `s`, ложь → `s+1`); `boolean r(int s, int op, long a, long b)`, `r(int, int, double, double)`, `r(int, int, boolean, boolean)`, `r(int, int, Object, Object)` — `op`: 0 `<`, 1 `<=`, 2 `>`, 3 `>=`, 4 `==`, 5 `!=`; для 0–3 пишет `s+0/1/2` для `a<b / a==b / a>b` (NaN — ничего), для 4–5 `s+0` если равны, иначе `s+1`; возвращает результат исходного оператора; `boolean lp(int s, boolean entered, boolean v)` — если `!v && !entered`, пишет `s+1`; возвращает `v`. Файл — `System.getProperty("jb.cov")`; если свойства нет или файл не открылся — счётчики в памяти, программа не падает.

Правила вставок (Task 2 — только `line` и `method`):
- Инструментируются только тела методов, конструкторов, блоков-инициализаторов и всё вложенное в них (лямбды-блоки, анонимные и локальные классы); инициализаторы полей не трогаются.
- `__Cov.h(slot);` — перед каждым оператором. Начало оператора — токен позиции javalang, сдвинутый назад через метку (`outer:`) и модификаторы/аннотации локального объявления (`final int x`).
- Тело ветки/цикла без `{}` при вставке в него оборачивается в `{ … }` (конец оператора: по AST для составных, `;` на нулевой глубине для простых; `do … while (…);` включает хвост).
- Метод-проба — сразу после `{` тела; если первый оператор — `this(…)`/`super(…)`, то метод-проба и line-проба этого оператора ставятся сразу после его `;`. Методы анонимных классов получают только line-пробы; `method` у их проб — имя объемлющего именованного метода.
- Все вставки — без `\n`; номера строк исходника сохраняются; `id` и `slot` — по порядку в исходнике (детерминированно).
- `cov_source` — `Cov.java` с именем класса `__Cov` и строкой `package` пользователя, если она есть.

- [ ] **Step 1: Написать тесты:**
  - `test_line_numbers_preserved` — для каждого из `test_monoliths/*.java`: `code.count("\n")` совпадает, и для каждой `line`-пробы её строка инструментированного кода содержит `__Cov.h(<slot>)`.
  - `test_monoliths_same_output` (параметризован 4 файлами) — `compile_local` + запуск `java -Djb.cov=<data_file> -cp out <Main>` даёт тот же stdout, что исходник (stdin пустой, как в `test_runner.py::test_monoliths_run`); `read_hits` не `None`; хотя бы одна `method`-проба `main` имеет счётчик 1.
  - `test_unbraced_and_labels` — программа с `if (x) return;`, `if (a) if (b) p(); else q();`, `outer: for (...) { for (...) { continue outer; } }`, `final int k = 1;`, `while (true) { ... return ...; }` в методе без `return` в конце, конструктор с `this(1)` — компилируется, вывод совпадает с исходником, пробы `else`-ветки висячего `else` считаются только когда выполняется внутренний `else`.
  - `test_counts` — цикл из 5 итераций с одним оператором в теле → `line`-проба этой строки = 5.
  - `test_degrade` — если `instrument_java` вернул код, который javac не принимает (подменить в тесте: `monkeypatch` `instrument_java` так, чтобы без `strip` он вставлял мусор на строку 3), `compile_local` возвращает `(None, plan)` с `plan.error is None` после повторов и без проб на строке 3.
  - `test_user_compile_error` — код с ошибкой → `(proc, plan)`, `proc.returncode != 0`, ошибки `parse_compile_errors(proc.stderr)` указывают на строку исходника.
  - `test_unparseable_runs_without_coverage` — код, который javac 11 принимает, а javalang нет (например, `var` в лямбде `(var x) -> x` или текстовые блоки нельзя — проверить, что javac 11 принимает выбранный пример) → `(None, plan)`, `plan.error` начинается с «Не удалось разобрать код для покрытия».
- [ ] **Step 2:** `venv/bin/python -m pytest tests/test_coverage_instrument.py -q` → FAIL.
- [ ] **Step 3:** Реализовать `Cov.java`, `instrument.py` (line/method), `build.py` (компиляция `javac -encoding UTF-8 -d out <fname> __Cov.java`, деградация по правилам из «Решений контроллера», ошибки берутся только для `fname` через `runner.parse_compile_errors`; `data_file` = `tmp/"cov"/"cov.bin"`, заполненный нулями до `slots*4` байт, права каталога `0o777` и файла `0o666` — для docker).
- [ ] **Step 4:** Тесты → PASS; весь `pytest -q` зелёный.
- [ ] **Step 5:** Commit `feat(coverage): Java instrumenter (lines, methods), __Cov counter, build with fallback`.

---

### Task 3: Ветки, логические условия, сравнения

**Files:**
- Modify: `backend/core/coverage/instrument.py`
- Test: `backend/tests/test_coverage_branches.py`

**Interfaces:**
- Consumes: Task 1 (`parse_condition`, `has_logic`, `leaves`, `split_relation`, `ternary_conditions`), Task 2 (`Probe`, `instrument_java`, `compile_local`, `read_hits`).
- Produces: те же функции, пробы `branch/cond/rel` по таблице «Формат данных».

Вставки:
- Решение `D` (условие `if`/`do`/`?:`): `__Cov.c(sb, D')`, где `D'` — `D` с обёрнутыми листьями. Лист `L` при `has_logic(D)` → `__Cov.c(sc, L')`; `L'` — `__Cov.r(sr, op, A, B)`, если `split_relation` нашёл оператор, иначе `L`. Если логики нет, но лист — сравнение, он всё равно получает `rel`-пробу.
- `while (C) S` / `for (I; C; U) S`: `{ boolean __cN = false; while (__Cov.lp(sb, __cN, C')) { if (!__cN) { __cN = true; __Cov.h(sb); } S } }` (метка, если есть, остаётся прямо перед `while`/`for` внутри блока; `N` — id пробы).
- for-each: `{ boolean __cN = false; for (T x : xs) { if (!__cN) { __cN = true; __Cov.h(sb); } S } if (!__cN) __Cov.h(sb + 1); }`.
- `case`-группа: `__Cov.h(s);` перед первым оператором группы (пустая группа — без пробы). `catch`: `__Cov.h(s);` сразу после `{` блока `catch`.
- Константы `true` в `while`/`do`/`for (;;)` — без branch-пробы; листья внутри таких условий не оборачиваются.

- [ ] **Step 1: Написать тесты** на одной программе `SAMPLE` (в файле теста) с `if/else`, `&&`/`||`/`!`, `<`, `==`, `while`, for-each по пустому и непустому массиву, `switch` с `case 1: case 2:` и `default`, `try/catch` с делением на ноль, `?:`, `do…while`; запуск через `compile_local` + `java`; проверка по `label` и исходу, например:
  - `if (x > 0)` при `x = 5` → исход «истина» = 1, «ложь» = 0;
  - в `i > 2 && n < 3` лист `n < 3` вычислялся только при `i > 2` (счётчики соответствуют short-circuit);
  - `rel` для `i < 3` в цикле от 0 до 5 → `<` = 3, `==` = 1, `>` = 2 (подогнать под цикл в `SAMPLE`);
  - for-each по пустому массиву → «тело ни разу не выполнялось» = 1; по непустому → «тело выполнялось» = 1 (а не число итераций);
  - `catch (ArithmeticException)` → «выполнен» = 1;
  - stdout `SAMPLE` совпадает с исходником.
  - `test_mixed_types` — `Integer boxed = 5; int p = 5; String s = null; char ch = 'a'; long L = 3; boolean f = true;` и решения `boxed == p`, `s == null`, `ch < 'z'`, `L < p`, `f == true` → `compile_local` даёт `(None, plan)` с `plan.error is None`, вывод совпадает; на строке `boxed == p` либо есть `rel`-проба, либо её убрала деградация (тест проверяет, что запуск прошёл и line-проба этой строки есть).
  - `test_overhead` — цикл на 5 000 000 итераций с `if (i % 3 == 0 && i > 10)` выполняется с покрытием быстрее 10 с.
- [ ] **Step 2:** Тесты → FAIL.
- [ ] **Step 3:** Реализовать вставки в `instrument.py` (уровень `strip` 1 убирает именно эти вставки, включая блоки `{ boolean __cN … }`).
- [ ] **Step 4:** Тесты Task 2 и Task 3 → PASS; весь `pytest -q` зелёный.
- [ ] **Step 5:** Commit `feat(coverage): branch, logical and relational probes`.

---

### Task 4: Запуск с покрытием в интерактивной консоли

**Files:**
- Modify: `backend/core/interactive.py`, `backend/api/ws.py` (docstring протокола тоже), `backend/core/runner.py` (`docker_command`)
- Test: `backend/tests/test_coverage_ws.py`, `backend/tests/test_runner.py` (команда docker)

**Interfaces:**
- Consumes: Task 2 `compile_local`, `read_hits`, `CovPlan`, `instrument_java`.
- Produces:
  - `start_session(...) -> tuple[Process, Path, CovPlan] | None` (третий элемент новый).
  - `coverage_message(plan: CovPlan) -> dict` — `{type:"coverage", probes:[p.to_json()], hits}`; при `plan.error` → `{type:"coverage", error}`; если `read_hits` вернул `None` → `{type:"coverage", error:"Данные покрытия не получены"}`.
  - `runner.docker_command(tmp, names, main_class, cov: bool = False)` — при `cov=True`: исходник в `orig/`, инструментированный код и `__Cov.java` в `cov/`, каталог данных `tmp/"cov"` монтируется как `/cov:rw`; скрипт: компилировать `cov/*.java` → при успехе `touch /cov/compiled`, иначе компилировать `orig/<fname>` (ошибка → `exit 98`, как сейчас); `java -Xmx256m -Djb.cov=/cov/cov.bin -cp /tmp/out <Main>`. Python после выхода: маркера нет → `plan.error = "Покрытие недоступно: инструментированный код не скомпилировался"`.
- Локальный режим: `java -Xmx256m -Dfile.encoding=UTF-8 -Djb.cov=<data_file> -cp out <Main>` (cwd по-прежнему `tmp`). Если `plan.data_file is None` — без `-Djb.cov`.
- `ws.run_and_report`: после `pump` → `emit(coverage_message(plan))` → `emit(exit)`.

- [ ] **Step 1: Написать тесты** (по образцу `tests/test_ws.py`, функция `collect`):
  - `test_coverage_before_exit` — ECHO из `test_ws.py`: сообщения идут `stdout… → coverage → exit`; `len(hits) == сумма len(outcomes)`; stdout такой же, как без покрытия (`"name: "`, затем `"hello Bob\n"`).
  - `test_coverage_after_kill` — бесконечный цикл с `i++` в теле: дождаться первого `stdout` (программа печатает перед циклом), отправить `kill`, получить `coverage` с ненулевым счётчиком line-пробы тела цикла и затем `exit`.
  - `test_coverage_on_exception` — программа бросает `RuntimeException` после пары операторов → `coverage` без `error`, счётчики выполненных строк ≥ 1.
  - `test_no_coverage_after_compile_error` — после `compile_error` сразу `exit`, `coverage` нет; строка ошибки — строка исходника.
  - `test_coverage_unavailable_reason` — код, который javalang не разбирает (пример из Task 2) → программа работает, приходит `{type:"coverage", error: …}`.
  - `test_docker_command_with_coverage` (в `test_runner.py`) — в команде есть `/cov:rw`, `-Djb.cov=/cov/cov.bin`, `touch /cov/compiled`; без `cov` команда прежняя.
- [ ] **Step 2:** Тесты → FAIL.
- [ ] **Step 3:** Реализовать (в docker-режиме `start_session` вызывает `instrument_java` и раскладывает файлы; `CoverageUnavailable` → запуск с `cov=False` и `plan.error`).
- [ ] **Step 4:** Весь `pytest -q` зелёный (старые `test_ws.py` проходят, т.к. клиент получает лишнее сообщение до `exit` — `collect` это допускает).
- [ ] **Step 5:** Commit `feat(coverage): collect coverage in the interactive run`.

---

### Task 5: Фронтенд — накопление и метрики

**Files:**
- Create: `frontend/src/utils/coverage.ts`
- Test: `frontend/src/utils/coverage.test.ts`

**Interfaces:**
- Produces:
```ts
export type ProbeKind = 'line' | 'method' | 'branch' | 'cond' | 'rel';
export interface Probe { id: number; kind: ProbeKind; line: number; method: string; label: string; outcomes: string[]; slot: number }
export interface Coverage { code: string; probes: Probe[]; hits: number[]; runs: number }
export interface Metric { covered: number; total: number }
export interface MethodCoverage { method: string; called: boolean; lines: Metric; branches: Metric; conditions: Metric; relational: Metric }
export interface Missing { line: number; kind: ProbeKind; label: string; outcome: string }
export interface CoverageSummary { lines: Metric; methods: Metric; branches: Metric; conditions: Metric; relational: Metric; perMethod: MethodCoverage[]; missing: Missing[] }
export interface LineState { state: 'hit' | 'miss' | 'partial'; count: number; missing: string[] }   // missing: "i > 2 → ложь"
export const mergeCoverage: (prev: Coverage | undefined, code: string, probes: Probe[], hits: number[]) => Coverage;
export const summarize: (c: Coverage) => CoverageSummary;
export const lineStates: (c: Coverage) => Map<number, LineState>;
export const percent: (m: Metric) => string;   // "75%"; total 0 → "—"
```
Правила: `mergeCoverage` суммирует `hits` поэлементно и увеличивает `runs`, если `prev.code === code` и длины `hits` равны, иначе `{code, probes, hits, runs: 1}`. Строки: `total` — число разных строк с line-пробами, `covered` — из них с ненулевым счётчиком. Методы — method-пробы. Ветки/условия/сравнения — число исходов (каждый исход — единица). `missing` — исходы `branch/cond/rel` с нулём, по строкам, затем по `id`. Состояние строки: `miss` — все line-пробы строки 0; `partial` — выполнена, но на строке есть исход `branch/cond/rel` с нулём; иначе `hit`; `count` — максимум по line-пробам строки. `called` метода — его method-проба > 0.

- [ ] **Step 1: Написать тесты** на ручном наборе проб (2 метода, `if` с `&&` и `<`): слияние одинакового кода суммирует и `runs: 2`; другой код начинает заново (`runs: 1`); `percent({covered:0,total:0}) === '—'`, `percent({covered:3,total:4}) === '75%'`; строка с `if`, у которой «ложь» = 0, — `partial` с `missing` вида `"x > 0 → ложь"`; невызванный метод — `called: false`, его строки — `miss`; `missing` упорядочен по строке.
- [ ] **Step 2:** `cd frontend && npx vitest run src/utils/coverage.test.ts` → FAIL.
- [ ] **Step 3:** Реализовать `coverage.ts`.
- [ ] **Step 4:** `npx vitest run` и `npm run build` — без ошибок.
- [ ] **Step 5:** Commit `feat(coverage): frontend merge and metrics`.

---

### Task 6: Хранение покрытия по файлу и приём из консоли

**Files:**
- Modify: `frontend/src/store/useProject.ts`, `frontend/src/components/Console/Console.tsx`
- Test: `frontend/src/store/useProject.test.ts` (новый)

**Interfaces:**
- Consumes: Task 5 `Coverage`, `Probe`, `mergeCoverage`.
- Produces (в `ProjectState`):
  - `coverage: Record<string, Coverage>`; `coverageError: Record<string, string | null>`; `coverageReset: Record<string, boolean>` (покрытие сброшено правкой).
  - `recordCoverage(fileId: string, code: string, probes: Probe[], hits: number[]): void` — если текущий текст файла (живой `useStore.code` для активного, `ProjectFile.code` для остальных) ≠ `code` → не сохранять, `coverageReset[fileId] = true`; иначе `mergeCoverage`, `coverageError[fileId] = null`, `coverageReset[fileId] = false`.
  - `setCoverageError(fileId: string, error: string): void` — накопленное не трогает.
  - `resetCoverage(fileId: string): void` — удаляет покрытие, ошибку и флаг сброса (кнопка «Сбросить покрытие»).
  - Подписка `useStore.subscribe` (один раз при создании стора): при изменении `code`, если у активного файла есть покрытие и `coverage.code !== code`, — удалить его и поставить `coverageReset[activeId] = true`. Переключение файлов покрытие не сбрасывает (у каждого файла свой текст).
- `Console.tsx`: сообщение `coverage` (только если не было `compile_error`) → `m.error ? setCoverageError(fileId, m.error) : recordCoverage(fileId, st.code, m.probes, m.hits)`; `fileId` и `st.code` — снятые при старте, как для `recordRun`.

- [ ] **Step 1: Написать тесты:** два `recordCoverage` с тем же текстом → `runs: 2`; `useStore.getState().setCode(другой текст)` → покрытия нет, `coverageReset` = `true`; вернуть прежний текст → покрытия всё ещё нет; `recordCoverage` с текстом, отличным от текущего (правка во время запуска) → не сохраняется, `coverageReset` = `true`; `open` другого файла и обратно — покрытие первого цело; `resetCoverage` очищает всё.
- [ ] **Step 2:** `npx vitest run src/store/useProject.test.ts` → FAIL.
- [ ] **Step 3:** Реализовать.
- [ ] **Step 4:** `npx vitest run` и `npm run build` — без ошибок.
- [ ] **Step 5:** Commit `feat(coverage): per-file coverage store and console wiring`.

---

### Task 7: Метки покрытия в редакторе

**Files:**
- Modify: `frontend/src/components/AceEditor/AceEditor.tsx`, глобальный CSS (тот же файл, где `.ace-defect`, `.ace-changed`)

**Interfaces:**
- Consumes: Task 5 `lineStates`; Task 6 `useProject.coverage[activeId]`.
- Метки — `session.addGutterDecoration(row, 'ace-cov-hit' | 'ace-cov-miss' | 'ace-cov-partial')` (снимать прежние при каждом пересчёте); вид — узкая полоса у левого края номера строки цветом `--ok` / `--err` / `--warn`; не конфликтует с иконками аннотаций дефектов.
- Показывать, только если `coverage.code === code` активного файла.
- Подсказка при наведении на номер строки (`guttermousemove` / `mouseout` редактора; собственный абсолютный блок в контейнере редактора, стиль как у существующих подсказок): `hit` → «Выполнений: N»; `miss` → «Не выполнялась»; `partial` → «Выполнений: N · не пройдено: a → ложь; b → истина».

- [ ] **Step 1:** Реализовать.
- [ ] **Step 2:** `npm run build` и `npx vitest run` — без ошибок.
- [ ] **Step 3:** Ручная проверка (`docker compose` не нужен: `uvicorn` + `npm run dev`): запустить Demo, увидеть зелёные/красные/жёлтые метки и подсказки; правка текста — метки исчезают. Скриншот приложить к отчёту.
- [ ] **Step 4:** Commit `feat(coverage): gutter markers and hover counts`.

---

### Task 8: Панель «Покрытие»

**Files:**
- Create: `frontend/src/components/CoveragePanel/CoveragePanel.tsx`
- Modify: `frontend/src/components/BottomPanel/BottomPanel.tsx` (вкладка `coverage`, иконка `FiPercent`, подпись «Покрытие»), глобальный CSS

**Interfaces:**
- Consumes: Task 5 `summarize`, `percent`; Task 6 стор; `useStore.jumpToLine(line)`.
- Состояния (тексты точно такие):
  - нет данных: «Запустите программу, чтобы увидеть покрытие.»
  - `coverageReset`: «Код изменён — покрытие сброшено, запустите снова.»
  - `coverageError`: «Покрытие недоступно: <причина>» — над данными, если накопленное покрытие есть.
- Данные: строка «Запусков учтено: N» + кнопка «Сбросить покрытие»; пять строк метрик «Строки», «Методы», «Ветвления», «Условия (логическое)», «Сравнения (реляционное)» — `covered / total · percent` и полоса; таблица «По методам» (метод, строки, ветвления, условия, сравнения; невызванный — пометка «не вызывался»); список «Не пройдено»: «строка N · label → outcome», клик → `jumpToLine(N)`; пустой список → «Всё пройдено».
- Вкладка не переключается автоматически после Run (консоль остаётся активной).

- [ ] **Step 1:** Реализовать.
- [ ] **Step 2:** `npm run build` и `npx vitest run` — без ошибок.
- [ ] **Step 3:** Ручная проверка: два запуска Logger с разным вводом — «Запусков учтено: 2», логическое/реляционное покрытие растёт; «Сбросить покрытие»; правка — сообщение о сбросе; клик по непройденному переходит к строке. Скриншот к отчёту.
- [ ] **Step 4:** Commit `feat(coverage): coverage panel`.

---

### Task 9: Документация и отметки

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/architecture.md`, `todo.md`

- [ ] **Step 1:** README — раздел «Покрытие кода»: какие метрики, где видно, накопление и сброс, ограничения (только решения `if/while/for/do/?:`; `==`/`!=` — два исхода; при неподдерживаемом синтаксисе — запуск без покрытия с причиной). CLAUDE.md — абзац про `core/coverage/` (инструментирование по токенам, `__Cov` + mmap-файл, деградация, сообщение `coverage` в `/api/ws/run`) и `utils/coverage.ts`/`useProject.coverage`. `docs/architecture.md` — модули.
- [ ] **Step 2:** `todo.md` — отметить этап 4 и пункты 4.1–4.8 (переписать список пунктов этапа 4 под фактические задачи этого плана, со ссылкой на план).
- [ ] **Step 3:** `cd backend && venv/bin/python -m pytest -q`; `cd frontend && npm run build && npx vitest run` — всё зелёное.
- [ ] **Step 4:** Commit `docs: coverage (stage 4)`.
