# Этап 7: Python — доделка после слияния 18d386f — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.py`-файлы работают «всё как у Java»: полный разбор конструкций Python, CFG в синтаксисе Python, правка
через граф без порчи кода, Big O и дефекты Python, рабочая декомпозиция с Quality Gate, покрытие кода, демо-примеры
и документация. База — слияние `89c8967` (Python из ветки `backend`, коммит `18d386f`).

**Architecture:** Поддержка Python уже есть (`core/py_parser.py`, ветки `language == "python"` в раннере, консоли,
генераторе, декомпозиторе, ИИ). План (1) собирает языковые ветки за реестр `core/lang/`, (2) доводит парсер и CFG до
списка конструкций спеки, (3) заменяет перерисовку тела функции точечной заменой по спанам узлов, (4) добавляет
Python-правила Big O и дефектов, (5) переписывает Python-декомпозицию на «модули из функций и классов», (6) делает
покрытие Python через AST-трансформацию в дочернем процессе с тем же форматом `Probe`/`hits`.

**Tech Stack:** FastAPI, стандартный `ast`/`tokenize`, pytest; React 18 + Zustand, vitest.

**Spec:** `docs/superpowers/specs/2026-10-24-multilang-coverage-design.md` — разделы «7–8. Python и C++», «Ограничения
и инварианты»; `todo.md` — «Этап 7». Отчёт о слиянии с разбором пробелов: `.superpowers/sdd/python-merge-report.md`.

## Global Constraints

- UI, сообщения дефектов, ошибки — на русском; стиль — `DESIGN.md`. Название «Java Blueprints» не меняется.
- Python 3.11+ на сервере; разбор — встроенный `ast` (без новых зависимостей).
- Id узлов CFG детерминированы (`n0…`); один и тот же код — те же id; `stmt_of` — основа правки через граф.
- Java-поведение и форма Java-ответов API не меняются; все существующие тесты проходят.
- Модель «один файл = одна программа»: импорт соседних файлов проекта не поддерживается (стандартная библиотека — да).
- Запуск Python: `python3 -u main.py`, таймаут 10 с (пакетный), `RLIMIT_AS` 512 МБ, docker-режим без отката на хост,
  окружение ребёнка — только `runner.python_env()` (без ключей ИИ/прокси). Эти свойства не ослаблять.
- Свободные функции модуля — псевдокласс `Module` (как сейчас); ссылка `Module.f` работает как `Class.method`.
- Проверка после каждой задачи: `cd backend && venv/bin/python -m pytest -q`; `cd frontend && npm run build && npx vitest run`.
- Не коммитить `AGENTS.md`, `.DS_Store`, `backend/package-lock.json`; не трогать `to-do.md`. ИИ-функции вручную не проверять
  (юнит-тесты без сети — можно). Не пушить, не сливать в `main`.

## Решения (обязательны для исполнителей)

- **Реестр языков** `core/lang/__init__.py`: `Language` (dataclass) с полями `name`, `extensions`, `parse(code) -> dict`,
  `check(code) -> list[dict]` (ошибки `{file, line, message}`), `entry_file` (`"Main.java"`/`"main.py"`),
  `regenerate(code, method, edits) -> tuple[str, list[str]]`, `decompose(code, ast) -> DecomposeResponse`;
  `LANGS = {"java": JAVA, "python": PYTHON}`, `get(name: str | None) -> Language` (неизвестное/None → Java),
  `by_filename(name: str) -> Language`. Адаптеры — тонкие обёртки над существующими функциями. Раннер/консоль
  (команды запуска) в реестр не переносятся — у них уже есть `runner.python_command`/Java-ветки; C++ добавит своё.
- **Язык запроса:** сервер не угадывает язык по тексту там, где он известен: `/ai/apply` и `/ai/bigo-combined` получают
  поле `language` (по умолчанию — `state.SESSION.language`); `runner.is_python_code` остаётся только как запасной путь
  для запросов без `language` и без сессии.
- **Текст операторов Python** берётся из исходника (`ast.get_source_segment`), а не из `ast.unparse` — кавычки,
  числа, f-строки и переносы сохраняются. В многострочном тексте отступы продолжения нормализуются `textwrap.dedent`
  относительно первой строки.
- **Спаны:** каждый словарь оператора Python получает `span = {"line", "col", "end_line", "end_col"}` (как в `ast`,
  `col` — 0-based offset в символах строки) и, у составных, `header = {"line", "col", "end_line", "end_col"}` — от
  ключевого слова (`if`/`elif`/`for`/`while`/`with`/`match`/`case`/`except`/`try`/`finally`) до `:` заголовка
  (без двоеточия). `:` ищется через `tokenize` — первый `OP ':'` на глубине скобок 0, не принадлежащий `lambda`
  на глубине 0.
- **Нормализованный AST Python** (дополнения к текущему `py_parser`):
  - `elif` — `IfStatement` в `else` родителя с флагом `"elif": True`;
  - `for/while … else` — поле `"else": [...]` у `ForStatement`/`WhileStatement`;
  - `try … else` — поле `"else": [...]` у `TryStatement`; голый `except:` — `"types": []` (метка `except`);
  - `with` — `{"type": "WithStatement", "items": "open(p) as f", "body": [...]}` (вместо `BlockStatement`+`raw`);
  - `match` — `SwitchStatement` с `"no_fallthrough": True`; у case `labels = [исходный текст паттерна]` и `"guard"`;
  - вложенный `def` в теле функции — оператор `{"type": "StatementExpression", "expression": "def inner(a, b)",
    "nested_def": True}` в теле родителя + отдельный метод того же класса/`Module` с именем `outer.inner`
    (точка в имени; `state.find_method` режет ссылку по **первой** точке после имени класса — поправить на
    `ref.split(".", 1)` при наличии класса с таким именем, иначе прежний `rpartition`);
  - каждый метод Python получает `"language": "python"`; синтетический метод верхнего уровня — `"synthetic": True`.
- **Метки CFG для Python** (без двоеточий и скобок Java): `if x > 0`, `elif x > 0`, `while cond`, `for x in xs`,
  `with open(p) as f`, `match cmd`, `case 1 | 2 if n > 0`, `try`, `except ValueError as e`, `except`, `finally`,
  `return x`, `raise X`, `break`, `continue`, простые операторы — их исходный текст. Типы узлов — существующие
  (`condition`, `loop`, `switch`, `case`, `try`, `catch`, `finally`, `return`, `throw`, `statement`); `with` — `statement`.
  Ветка `else` у цикла: ребро `false` с меткой `else` из узла цикла на первый оператор `else`; `break` её обходит.
  `try … else`: нормальный выход из тела `try` → тело `else` → `finally`/дальше. `match`: хвосты каждого `case` идут на
  выход (без провала в следующий case); без `case _` есть ребро `no match`.
- **Правка через граф Python — точечная замена:** для каждого изменённого узла заменяется только его фрагмент исходника:
  у простого оператора — `span`, у составного/except/case — `header` (ключевое слово сохраняется исходное: метка
  `if y` на узле `elif` даёт `elif y`). Замены применяются снизу вверх; многострочная метка получает отступ строки
  оператора на продолжении. Пустая метка простого оператора → `pass`; пустая метка заголовка — правка игнорируется.
  Неизменённый код (комментарии, пустые строки, кавычки, докстринги) остаётся байт-в-байт. Узлы `try`/`finally`/`else`
  не правятся. После замен — `parse_python`, ошибка → 422 с русским текстом (как сейчас). `render_python_stmt(s)` и
  `_splice_python` удаляются, если не остаётся пользователей.
- **Big O Python:** list/set/dict-comprehension и генераторное выражение — цикл O(n) × стоимость элемента;
  `sorted(x)`/`x.sort()` — O(n log n); `sum/any/all/min/max/len(list(…))/list(…)/set(…)/map/filter/enumerate/zip/reversed`
  от коллекции — O(n), `len(x)` — O(1); `x in y` / `x not in y` — O(n), если `y` известен как список/кортеж/строка
  (литерал `[...]`/`(...)`, `list(...)`, аннотация `list`/`List`/`Sequence`/`tuple`/`str`), O(1) если известен как
  `set`/`dict` (литерал, `set()`/`dict()`/`{}`, аннотация `set`/`dict`/`Set`/`Dict`/`Mapping`), иначе O(1).
  `bigo` для Python содержит только ключи `Module.f`/`Class.m` (без дублей `f`).
- **Дефекты Python** (warning, если не сказано иное; `node_id` — узел строки; тексты рекомендаций — про Python):
  1. конкатенация строки в цикле `s += …`, где `s` инициализирована строковым литералом/`str(...)` — «соберите части в
     список и `''.join(...)`», `O(n²)`;
  2. `x in lst` в цикле, где `lst` — известный список — «превратите в `set` до цикла», `O(n²)`;
  3. вложенный цикл по той же коллекции — существующее правило 1 (рекомендация для Python: «`dict`/`set` или
     `itertools.combinations`»);
  4. `except:`/`except Exception:`/`except BaseException:` с телом из одного `pass`/`...` — error «исключение
     проглатывается»; голый `except:` также — warning «общий except»;
  5. изменяемый аргумент по умолчанию (`[]`, `{}`, `set()`, `list()`, `dict()`) — warning «используйте `None`»;
  6. `for i in range(len(x))` — hint «`for item in x` / `enumerate(x)`».
  Java-тексты в общих правилах (HashMap, IOException) для Python заменяются Python-аналогами. Правило «неиспользуемый
  импорт» для Python учитывает `from m import n` (строки `from …` исключаются из текста) и `import a as b` (ищется `b`).
- **Декомпозиция Python:** единицы переноса — функции верхнего уровня и классы целиком (методы из класса не выносятся).
  Не переносятся: `main`, синтетический метод верхнего уровня, единицы, использующие глобальные имена модуля, которые
  не переносятся с ними (константы, глобальные переменные), — с предупреждением. Группировка функций — `HEURISTICS`
  (как у Java), класс — отдельный модуль `snake_case(Имя).py`. Каждый модуль получает нужные ему `import` исходника и
  `from <модуль> import <имя>` для используемых единиц из других модулей; циклические зависимости модулей → обе единицы
  остаются в фасаде с предупреждением. Фасад `main.py` — исходник без перенесённых единиц + `from … import …` после
  исходных импортов (и после `from __future__`, докстринга). Quality Gate (`/decompose/verify`) проходит на всех
  `test_monoliths/*.py`.
- **Покрытие Python:** формат `Probe`/`hits` и WS-сообщение `coverage` — как у Java. Инструментирование —
  `ast.NodeTransformer` в автономном модуле `core/coverage/py_cov.py` (только stdlib; копируется в tmp рядом с
  `main.py`). Сервер вызывает его для списка проб, ребёнок — для кода; детерминированный порядок проб
  (обход в порядке исходника). Ребёнок запускается как `python3 -u _jb_run.py`: загрузчик читает `main.py`,
  инструментирует, компилирует с именем файла `main.py` (номера строк и трейсбеки — пользовательские), создаёт маркер
  `<cov>/compiled`, выполняет код с `__name__ == "__main__"`, `sys.argv = ["main.py"]`, `sys.path[0]` = каталог.
  Счётчики — int32 little-endian в файле `<cov>/hits.bin` через `mmap` (переживают Stop/таймаут/kill); путь и число
  слотов — в переменных `JB_COV`, `JB_COV_SLOTS`. Имя рантайма в коде — `_jb_cov` (не `__cov`: двойное подчёркивание
  искажается внутри классов). Пробы:
  `line` (`_DONE`) перед каждым оператором функции, класса и верхнего уровня (после докстринга и `from __future__`);
  `method` (`_DONE`) на входе в каждую функцию/метод; `branch`: условия `if`/`elif`/`while`/тернарного `IfExp` (`_TF`),
  `for` (`_LOOP`, через обёртку итерируемого), `except` и `case` (`_HIT`); `cond`: листья `and`/`or`/`not` в условиях
  (`_TF`); `rel`: одиночное сравнение `<,<=,>,>=` (`_ORDER`) и `==,!=` (`_EQ`) в условиях; цепочки сравнений и
  `in`/`is` — без `rel`. Обёртки возвращают исходное значение, операнды вычисляются один раз, порядок и
  short-circuit не меняются. Ошибка инструментирования → запуск оригинала без покрытия и
  `{type:"coverage", error:"Покрытие недоступно: …"}`; синтаксическая ошибка пользователя → `compile_error` без покрытия.

## Review Focus

- Правка одного узла в файле с комментариями, f-строками и двойными кавычками меняет только этот фрагмент — тест в Task 5.
- Правка узла в коде верхнего уровня (`if __name__ == "__main__":` и операторы модуля) не ломает файл — тест в Task 5.
- Метод внутри класса с `__`-именами и вложенными функциями: покрытие не падает на искажении имён — тест в Task 9.
- Программа, прерванная Stop/таймаутом посреди цикла, всё равно присылает покрытие — тест в Task 10.
- Декомпозиция файла, где функция использует глобальную константу, не ломает Quality Gate — тест в Task 8.

---

### Task 1: Реестр языков и язык в оставшихся запросах

**Files:**
- Create: `backend/core/lang/__init__.py`
- Modify: `backend/state.py` (`load`, `find_method`), `backend/api/generate.py`, `backend/api/decompose.py`,
  `backend/api/ai.py` (`/ai/apply`, `/ai/bigo-combined`), `backend/models/schemas.py` (`AiApplyRequest`,
  `BigoCombinedRequest` — поле `language: str | None = None`), `backend/ai/patcher.py` (выбор языка), `frontend/src/hooks/useApi.ts`
- Create: `frontend/src/utils/language.ts`, `frontend/src/utils/language.test.ts`
- Test: `backend/tests/test_lang.py`

**Interfaces:**
- Produces: `core.lang.get(name: str | None) -> Language`, `core.lang.by_filename(name: str) -> Language`,
  `Language.parse/check/regenerate/decompose/entry_file/name/extensions` (см. «Решения»);
  `languageOf(name: string): 'java' | 'python'` в `utils/language.ts`.

- [ ] **Step 1: Тесты** `test_lang.py`: `get("python").name == "python"`, `get(None).name == get("cobol").name == "java"`,
  `by_filename("a/b.py").name == "python"`, `by_filename("Main.java").name == "java"`; `get("python").check("x = (\n")`
  возвращает одну ошибку с `line == 1`; `/api/ai/apply` с `language: "python"` и Python-кодом, где нет `System.out`,
  не уходит в Java-валидацию (патч применим). `language.test.ts`: `languageOf('x.py') === 'python'`,
  `languageOf('X.java') === 'java'`, `languageOf('README') === 'java'`.
- [ ] **Step 2:** Запустить — FAIL (модуля нет).
- [ ] **Step 3:** Реализовать реестр как тонкие адаптеры; заменить разбросанные `if language == "python"` в `state.load`,
  `api/generate.py`, `api/decompose.py`, `patcher` на `lang.get(...)`, где это прямая замена (не переписывать логику
  раннера/консоли). `useApi` передаёт `language` в `/ai/apply` и `/ai/bigo-combined`; `useProject.mk` использует `languageOf`.
- [ ] **Step 4:** Полный прогон backend + frontend — PASS.
- [ ] **Step 5:** Commit `refactor(lang): language registry, language in apply/bigo-combined`.

### Task 2: Демо-примеры Python — аналоги Java-монолитов

**Files:**
- Modify: `test_monoliths/{calculator,store,analyzer,logger}.py` и копии в `frontend/src/examples/` (идентичны)
- Test: `backend/tests/test_python_examples.py`

**Interfaces:**
- Produces: примеры, на которые опираются тесты Task 3–10. Состав (каждый — 80–200 строк, запускается без ввода,
  детерминированный вывод, `if __name__ == "__main__": main()`):
  - `calculator.py` — аналог `Calculator.java`: рекурсия `fib` (O(2^n)), `factorial`, `power`, разбор выражений
    (`parse_*`), печать (`print_*`) — группы для декомпозиции; `try/except ValueError … else … finally`; `match` по
    операции с guard; `while … else`.
  - `store.py` — аналог `Store.java`: класс `Product` и `Store` с полями `self.x`, `@staticmethod`/`@classmethod`,
    `x in list` в цикле, вложенный цикл по одной коллекции, изменяемый аргумент по умолчанию, `with` (например,
    `contextlib.suppress` или `io.StringIO`), модульная константа, используемая функцией.
  - `analyzer.py` — аналог `Analyzer.java`: comprehensions, `sorted`, `sum/any/max`, `for … else` с `break`,
    `range(len(x))`, вложенная функция, генераторное выражение.
  - `logger.py` — аналог `Logger.java`: конкатенация строки в цикле, `except: pass`, голый `except:`, неиспользуемый
    импорт, f-строки и комментарии.
- [ ] **Step 1: Тест** `test_python_examples.py`: для каждого примера — `parse_python` без ошибок; `runner.run_code(code,
  language="python")` → exit 0 и непустой stdout; копии в `frontend/src/examples/` совпадают с `test_monoliths/`.
- [ ] **Step 2:** Переписать примеры; прогнать тест — PASS; полный прогон (существующие Python-тесты могут опираться на
  старые примеры — обновить их ожидания, не ослабляя проверок).
- [ ] **Step 3:** Commit `feat(python): demo examples mirroring the Java monoliths`.

### Task 3: Парсер Python — полный набор конструкций

**Files:**
- Modify: `backend/core/py_parser.py`, `backend/state.py` (`find_method` — см. «Решения»)
- Test: `backend/tests/test_py_parser.py`

**Interfaces:**
- Produces: поля AST из «Решений»: `span`, `header`, `elif`, `else` у циклов и `try`, `types: []` у голого except,
  `WithStatement{items, body}`, `SwitchStatement.no_fallthrough`, `case.guard`, `nested_def`, методы `outer.inner`,
  `method.language`, `method.synthetic`; текст операторов — из `ast.get_source_segment`.

- [ ] **Step 1: Тесты** (`test_py_parser.py`), по одному на конструкцию:
  - `s = "a"; print("x", 1.50)` → `expression == 'print("x", 1.50)'` (кавычки и `1.50` сохранены);
  - `if a: … elif b: … else: …` → `then`, `else[0]["elif"] is True`, `else[0]["condition"] == "b"`;
  - `for x in xs: … else: …` и `while c: … else: …` → непустой `else`; `try/except/else/finally` → `else` и `finally`;
  - `except:` → `types == []`; `with open(p) as f:` → `type == "WithStatement"`, `items == "open(p) as f"`;
  - `match c:\n case 1 | 2 if n > 0:` → `no_fallthrough`, `labels == ["1 | 2"]`, `guard == "n > 0"`;
  - вложенный `def inner(a, b)` в `outer` → оператор `nested_def` в теле `outer` и метод `outer.inner` в `Module`;
    `state.find_method(ast, "Module.outer.inner")` находит его;
  - `header` у `if x > 0:  # c` равен диапазону `if x > 0`; у `if f(lambda y: y):` — до последнего `:`;
  - многострочный вызов → `span.end_line > span.line`; синтаксическая ошибка → `errors[0]` содержит номер строки.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Реализовать в `py_parser` (заголовки — через `tokenize` по сегменту от `lineno/col_offset`).
- [ ] **Step 4:** Полный прогон — PASS (CFG/Big O/дефекты старых тестов не должны измениться для Java).
- [ ] **Step 5:** Commit `feat(python): full statement set in the parser, source text, spans`.

### Task 4: CFG в синтаксисе Python

**Files:**
- Modify: `backend/core/cfg_builder.py`
- Test: `backend/tests/test_py_cfg.py`

**Interfaces:**
- Consumes: поля Task 3; `method["language"] == "python"`.
- Produces: метки и рёбра из «Решений»; для Java вывод `build_cfg` не меняется.

- [ ] **Step 1: Тесты** `test_py_cfg.py`: метки `if x > 0`, `elif y`, `for x in xs`, `while n`, `with open(p) as f`,
  `match c`, `case 1 | 2 if n > 0`, `except ValueError as e`, `except`; у `for … else` есть ребро `false` с меткой
  `else` к первому оператору `else`, а узел `break` не ведёт в `else`; в `try … else` тело `try` → `else` → `finally`;
  в `match` из конца первого `case` нет ребра во второй `case`; ids детерминированы (два построения дают одинаковые
  `n…`); для `test_monoliths/Calculator.java` метки/рёбра совпадают с текущими (снимок до изменения).
- [ ] **Step 2:** FAIL. **Step 3:** Реализовать (флаг `self.py` в `_CFGBuilder`; Java-ветки не трогать).
- [ ] **Step 4:** Полный прогон — PASS. **Step 5:** Commit `feat(python): CFG labels and else/with/match flow`.

### Task 5: Правка через граф — точечная замена по спанам

**Files:**
- Create: `backend/core/py_codegen.py`
- Modify: `backend/core/code_generator.py` (удалить Python-рендер, если не используется), `backend/core/lang/__init__.py`
  (`PYTHON.regenerate`), `backend/api/generate.py`
- Test: `backend/tests/test_py_codegen.py`

**Interfaces:**
- Consumes: `build_cfg_with_map`, поля `span`/`header` Task 3, метки Task 4.
- Produces: `py_codegen.apply_edits(code: str, method: dict, edits: dict[str, str]) -> tuple[str, list[str]]`
  (новый код, id реально изменённых узлов).

- [ ] **Step 1: Тесты** `test_py_codegen.py`:
  - roundtrip: для каждого метода каждого `test_monoliths/*.py` `apply_edits(code, m, {})[0] == code`, и через
    `/api/generate` с неизменёнными узлами ответ `code` равен исходнику;
  - правка `return` в методе с комментарием и f-строкой меняет ровно одну строку (diff — одна строка);
  - метка `if y` на узле `elif` → в коде `elif y:`; правка `while` и `for` заголовков сохраняет тело и комментарий
    в конце строки заголовка;
  - правка оператора в синтетическом методе верхнего уровня (`main()` под `if __name__ …`) меняет только эту строку;
  - многострочная метка (`x = f(\n    1)`) получает отступ оператора;
  - пустая метка простого оператора → `pass`; метка с синтаксической ошибкой → `/api/generate` 422 с русским текстом;
  - правка `except ValueError as e` → `except KeyError as e:`.
- [ ] **Step 2:** FAIL. **Step 3:** Реализовать (смещения `col` — символы строки; замены снизу вверх).
- [ ] **Step 4:** Полный прогон — PASS. **Step 5:** Commit `feat(python): graph edits as in-place span replacement`.

### Task 6: Big O для Python

**Files:**
- Modify: `backend/core/bigo_analyzer.py` (Python-ветка оценки выражений; без изменения Java-результатов)
- Test: `backend/tests/test_py_bigo.py`; `backend/tests/data/bigo_baseline.json` не меняется для Java

**Interfaces:**
- Consumes: AST Task 3. Produces: `analyze_ast(ast)` для Python — только квалифицированные ключи.

- [ ] **Step 1: Тесты** (инлайн-код Python в тесте):
  `return sorted(xs)` → `O(n log n)`; `return [x * 2 for x in xs]` → `O(n)`; `return sum(xs)` → `O(n)`;
  `return len(xs)` → `O(1)`; цикл `for x in xs: if x in ys` при `ys: list` → `O(n²)`, при `ys: set` → `O(n)`;
  `[y for x in xs for y in xs]` → `O(n²)`; цикл с `xs.sort()` внутри → `O(n² log n)`; ключи результата —
  только `Module.*`/`Class.*`; Java-снимок `bigo_baseline.json` совпадает.
- [ ] **Step 2:** FAIL. **Step 3:** Реализовать (разбор выражений Python через `ast.parse(text, mode="eval")` с
  откатом на текущий regex при ошибке; типы — из аннотаций параметров и присваиваний в теле).
- [ ] **Step 4:** Полный прогон — PASS. **Step 5:** Commit `feat(python): Big O for comprehensions, builtins, membership`.

### Task 7: Дефекты и советы для Python

**Files:**
- Modify: `backend/core/defect_detector.py` (новая функция `_python_defects(ast) -> list[Defect]` + языковые тексты
  в общих правилах), `backend/ai/static_tips.py` (`TIPS_PYTHON` — советы к шести правилам)
- Test: `backend/tests/test_py_defects.py`; `backend/tests/data/monolith_defects.json` — Java-часть без изменений

**Interfaces:**
- Consumes: AST Task 3, `bigo` Task 6, примеры Task 2.

- [ ] **Step 1: Тесты:** по одному позитивному и одному негативному случаю на каждое из шести правил «Решений»
  (негатив: `s += 1` у числа; `x in st` при `st = set(...)`; `except ValueError: log(e)`; `def f(a=None)`;
  `for i, x in enumerate(xs)`); неиспользуемый `from os import path` находится, а используемый `import numpy as np`
  при использовании `np` — нет; на `logger.py`/`store.py`/`analyzer.py` из Task 2 находится хотя бы по одному дефекту
  каждого заложенного правила; тексты Python-дефектов не содержат `HashMap`/`IOException`/`catch`; у каждого правила
  есть совет в `static_tips` для `language="python"`; Java-снимок дефектов совпадает.
- [ ] **Step 2:** FAIL. **Step 3:** Реализовать. **Step 4:** Полный прогон — PASS.
- [ ] **Step 5:** Commit `feat(python): Python defect rules and tips`.

### Task 8: Декомпозиция Python и Quality Gate

**Files:**
- Modify: `backend/core/decomposer.py` (`_decompose_python` переписать; `plan()` для Python — единицы из «Решений»)
- Test: `backend/tests/test_py_decompose.py`

**Interfaces:**
- Consumes: AST Task 3, `lang.PYTHON.decompose`, примеры Task 2.
- Produces: `DecomposeResponse` с `main.py` первым файлом (как сейчас).

- [ ] **Step 1: Тесты:** для каждого `test_monoliths/*.py` `/api/decompose/verify` → прошёл (вывод совпал) и файлов ≥ 2
  (кроме случая «Нечего выделять» — тогда предупреждение, а не падение); класс `Store` переносится целиком в `store.py`
  (его методы не разбросаны); функция, использующая модульную константу, остаётся в фасаде с предупреждением на русском;
  модуль, вызывающий функцию другого модуля, получает `from <модуль> import <имя>`; `main` и блок
  `if __name__ == "__main__":` остаются в `main.py`; zip (`/api/decompose/zip`) содержит все файлы.
- [ ] **Step 2:** FAIL (сейчас Quality Gate падает на `analyzer.py`/`store.py`). **Step 3:** Реализовать.
- [ ] **Step 4:** Полный прогон — PASS. **Step 5:** Commit `fix(python): decomposition into modules passes Quality Gate`.

### Task 9: Инструментирование покрытия Python

**Files:**
- Create: `backend/core/coverage/py_cov.py` (трансформер + рантайм `_jb_cov` + загрузчик; только stdlib)
- Modify: `backend/core/coverage/build.py` (`prepare_python(tmp: Path, code: str) -> CovPlan`: копирует `py_cov.py` в tmp
  и пишет `_jb_run.py` — заглушку `import py_cov; py_cov.run("main.py")`, создаёт `cov/` с правами как у Java, файл счётчиков нужного размера)
- Test: `backend/tests/test_py_coverage.py`

**Interfaces:**
- Produces: `py_cov.instrument(source: str) -> tuple[ast.Module, list[Probe]]` (детерминированно; `Probe` — тот же
  dataclass/формат, что `core/coverage/instrument.Probe`, слоты по числу `outcomes`); `build.prepare_python(...)`;
  команда ребёнка `[python, "-u", "_jb_run.py"]` с `JB_COV`, `JB_COV_SLOTS` в окружении.

- [ ] **Step 1: Тесты** (запуск локальным `sys.executable` в tmp, без WS):
  - `if x > 0:` при `x = 1` → у `branch`-пробы hits `[1, 0]`; `for` по пустому списку → `[0, 1]`;
  - `a > 0 and b` → две `cond`-пробы; `a < b` → `rel` с тремя слотами; `a < b < c` — без `rel`;
  - `line`-проба каждого выполненного оператора > 0, невыполненной ветки — 0; `method`-проба у вызванной функции;
  - трейсбек ошибки во время выполнения указывает на строку пользователя в `main.py`;
  - класс с методом `__secret` и вложенной функцией работает (нет `NameError` из-за искажения имён);
  - докстринг модуля и функции остаётся докстрингом (`f.__doc__` не `None`), `from __future__ import annotations` работает;
  - список проб, посчитанный сервером, совпадает по `id/slot/line/kind` с тем, что использовал ребёнок;
  - короткое замыкание и побочные эффекты сохранены (`f() or g()` при истинном `f()` не вызывает `g`).
- [ ] **Step 2:** FAIL. **Step 3:** Реализовать. **Step 4:** Полный прогон — PASS.
- [ ] **Step 5:** Commit `feat(python): coverage instrumentation via AST transform`.

### Task 10: Покрытие Python в консоли, фронтенд, документация

**Files:**
- Modify: `backend/core/interactive.py` (`_start_python` — через `build.prepare_python`, docker: монтирование `/cov`
  и маркер `compiled`, как у Java), `backend/api/ws.py`, `frontend/src/components/CoveragePanel/CoveragePanel.tsx`
  (убрать заглушку «не поддерживается»), `frontend/src/components/Welcome/Welcome.tsx` (Python-примеры на экране
  приветствия, если их там нет), `CLAUDE.md`, `docs/architecture.md`, `README.md`, `todo.md` (отметить 7.1–7.10,
  отложенное — в раздел этапа 7)
- Test: `backend/tests/test_coverage_ws.py` (Python-случаи), `frontend/src/utils/coverage.test.ts` (если нужно)

**Interfaces:**
- Consumes: Task 9. Produces: WS `/api/ws/run` с `language: "python"` шлёт `{type:"coverage", probes, hits}` перед `exit`.

- [ ] **Step 1: Тесты:** WS-запуск `calculator.py` → одно сообщение `coverage` с `probes` и `hits` перед `exit`;
  синтаксическая ошибка → `compile_error`, без `coverage`; программа с бесконечным циклом, остановленная `stop`
  (или по таймауту сессии в тесте с уменьшенным лимитом), всё равно шлёт `coverage` с ненулевыми hits;
  ошибка инструментирования (замокать `py_cov.instrument` на исключение) → программа выполнилась, `coverage.error`
  начинается с «Покрытие недоступно»; окружение ребёнка по-прежнему без `GEMINI_*` (существующий тест не ломается).
- [ ] **Step 2:** FAIL. **Step 3:** Реализовать; фронтенд показывает покрытие Python так же, как Java (полосы в редакторе,
  вкладка «Покрытие»).
- [ ] **Step 4:** Полный прогон backend + `npm run build` + `npx vitest run` — PASS. Ручная проверка без ИИ: dev-серверы,
  открыть `store.py`, запустить, увидеть полосы покрытия и сводку; открыть `Calculator.java` — покрытие Java не сломано.
- [ ] **Step 5:** Документация: в `CLAUDE.md` и `docs/architecture.md` — слой `core/lang/`, `py_parser`, `py_codegen`,
  Python-покрытие (`py_cov.py`, `_jb_run.py`), правила Python; `todo.md` — отметки этапа 7.
- [ ] **Step 6:** Commit `feat(python): coverage in the console, docs`.
