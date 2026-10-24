# TODO — Java Blueprints: исправления, покрытие, стримы, Python и C++

Дизайн (главный документ, все решения пользователя): `docs/superpowers/specs/2026-10-24-multilang-coverage-design.md`
Ветка: `feature/multilang-coverage` (в `main` сливаем только после всех этапов)

## Этапы

- [x] **1. Дефекты всегда актуальны + ИИ-исправление ошибок** — код готов, ИИ-функции проверите вы
- [x] **2. Сравнение выводов по файлу (предыдущий ↔ последний запуск)**
- [x] **3. Выгрузка: текущий файл и zip изменённых**
- [x] **4. Покрытие кода (аналог JavaScope)**
- [x] **5. Сложность «сейчас → после ИИ» и ожидаемое ускорение**
- [x] **6. Stream API и Collectors (Java)**
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

**Задачи** (фактические; план: `docs/superpowers/plans/2026-10-24-stage4-coverage.md`).
- [x] **4.1 Каталог проб + инструментатор (бэкенд):** `core/coverage/conditions.py`, `instrument.py`.
- [x] **4.2 Класс-счётчик:** `core/coverage/Cov.java` (`__Cov`, mmap-файл через `-Djb.cov`).
- [x] **4.3 Сборка с деградацией:** `core/coverage/build.py` (`CovPlan`, `read_hits`).
- [x] **4.4 Запуск с покрытием:** `core/interactive.py`, `api/ws.py`: сообщение `coverage` перед `exit`, docker-режим.
- [x] **4.5 Накопление (фронтенд):** `utils/coverage.ts`, `useProject.coverage` (сброс при любой правке), vitest.
- [x] **4.6 Редактор:** полосы в gutter `AceEditor` и тултип.
- [x] **4.7 Панель «Покрытие»** во вкладках `BottomPanel`.
- [x] **4.8 Документация + финальная проверка:** README/CLAUDE.md/architecture.md.

**Риски.** Перегрузки `__Cov.r` для смешанных типов (`int < long`, `char < int`) — проще приводить к `double` для
числовых и `compareTo` не трогать; дженерики/автоупаковка (`Integer == Integer`) — не оборачивать `==`/`!=` для не-примитивов
(тип неизвестен без типизации — оборачивать только если оба операнда — литералы/локали примитивного типа из объявлений).

---

## Этап 5 — Сложность «сейчас → после ИИ» и ожидаемое ускорение

**Цель.** В строке «Сложность методов · Big O» видно текущую сложность и сложность после предложенных ИИ правок,
с ожидаемым ускорением по формуле. Дизайн: раздел 5.

**Подробный план:** `docs/superpowers/plans/2026-10-24-stage5-bigo-after-ai.md` (6 задач, все выполнены, 24.10).

**Задачи.**
- [x] **1. Big O «было/станет» в патче (бэкенд).** `ai/bigo_diff.py`, `AiPatch.bigoBefore/bigoAfter` для затронутых методов — `d815deb`.
- [x] **2. `POST /api/ai/bigo-combined`.** Совместное применение советов (непересекающиеся по очереди, при пересечении — лучший одиночный) — `6fd3909`, `1f383e6`.
- [x] **3. `frontend/src/utils/speedup.ts`.** Ожидаемое ускорение по формуле при n = 1000, «красивое» округление — `eaba4dc`.
- [x] **4. «После ИИ» по методу.** `utils/bigoAfter.ts`, `hooks/useBigoAfter.ts`, `useApi.bigoCombined`, `useStore.bigoAfterAi` — `afa6423`.
- [x] **5. Бейдж в UI.** `components/BigoChange` + `utils/bigoChange.ts` в строке «Сложность методов · Big O» (`DiagnosticsPanel`) и в `PatchView` — `3b19a52`.
- [x] **6. Документация и отметки.** README, CLAUDE.md, `docs/architecture.md`, этот файл.

**Отложенные мелочи:**
- 4 разбора кода на каждый валидный патч.
- У `/api/ai/bigo-combined` нет лимитов на размер кода и число патчей.
- `useBigoAfter` перезапрашивает на каждое нажатие клавиши при ≥2 советах (мигание).
- Пустой ответ `{}` эндпоинта стирает запасной вариант.
- Пустая строка сетки `.bigo-row` даёт лишний отступ.
- Windows: тесты бэкенда — `backend/.venv/Scripts/python.exe` и JDK в `PATH` (`backend/venv` — от macOS).

---

## Этап 6 — Stream API и Collectors (Java)

**Цель.** Стримы — полноценные граждане: конвейер на графе, правка шагов через граф, правильный Big O, дефекты/советы.
Дизайн: раздел 6.

**Подробный план:** `docs/superpowers/plans/2026-10-24-stage6-streams.md` (6 задач, все выполнены, 24.10).

**Задачи** (фактические).
- [x] **1. Разбор цепочек.** `core/streams.py` (`stream_of`, `compose`), поле `stmt["stream"]` в парсере — `baa54dc`.
- [x] **2. Узлы конвейера и правка шагов.** CFG `stream-source`/`stream-op`/`stream-terminal`, правка в `code_generator` (пустая метка шага удаляет его; вставка цепочки в источник не дублирует) — `dd62ee3`, `c020bda`.
- [x] **3. Узлы на графе (фронтенд).** `kinds.ts`, `CFGView.tsx`, `index.css` (семейство `stream`, легенда «Стрим»), высота dagre в `useSync.ts` — `95f57bf`.
- [x] **4. Big O по шагам.** `bigo_analyzer._stream_cost` — `03c4b29`.
- [x] **5. Дефекты и советы.** 6 правил в `defect_detector._stream_defects` + `ai/static_tips.py` — `fa6f7ad`.
- [x] **6. Демо и документация.** `Streams.java` (`test_monoliths/`, `frontend/src/examples/`), тесты, README, CLAUDE.md, `docs/architecture.md`, этот файл.

**Отложенные мелочи.**
- `flatMap` — эвристика «умножить на размер внутреннего потока»: переоценивает частый случай разворачивания
  (`orders.flatMap(o -> o.getItems().stream())` → O(n²), хотя это O(суммы размеров)) и недооценивает дорогие
  внутренние лямбды.
- Правило 5: ложные срабатывания на локальной коллекции внутри лямбды-блока и на поле параметра (`p.items.add`).
- Правило 6: жадный шаблон `add(...)`.
- Правило 1 берёт первый `.size()` в составном условии.
- Цвет узла стрима в светлой теме не проверен глазами.

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
