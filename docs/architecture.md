# Архитектура

Browser SPA (React, Ace, React Flow, Zustand) → REST `/api` → FastAPI.

| Модуль | Назначение |
|---|---|
| `state.py`, `main.py` | сессия на вкладку браузера: заголовок `X-Session-Id` (UUID; иначе 400) → middleware кладёт `Session` в `ContextVar`, `state.current()`; до 200 сессий, вытеснение LRU, простой > 1 ч удаляет; без заголовка — общая сессия по умолчанию. WebSocket `/api/ws/run` сессию не использует |
| `core/parser.py` | javalang → JSON-AST, line_map, спаны деклараций (по токенам) |
| `core/cfg_builder.py` | CFG метода; детерминированные id узлов (`n0…`), карта узел→оператор |
| `core/call_graph.py`, `class_diagram.py` | графы вызовов / классов |
| `core/bigo_analyzer.py`, `defect_detector.py` | Big O по вложенности циклов/рекурсии; дефекты |
| `core/code_generator.py` | правки узлов → перегенерация тела метода и вставка в исходник по спану |
| `core/decomposer.py` | группировка static-методов по префиксам имён + графу вызовов |
| `core/runner.py`, `comparator.py` | javac/java (subprocess или docker), diff stdout (маскирует timestamps) |
| `core/streams.py` | распознавание цепочек Stream API в операторе: поле `stream` (`prefix`, `source`, `ops`, `terminal`), `compose` собирает цепочку обратно; узлы CFG `stream-source`/`stream-op`/`stream-terminal` |
| `core/coverage/` | покрытие: инструментирование исходника по токенам (`instrument.py`, `conditions.py`), счётчик `Cov.java` (mmap-файл), сборка с деградацией и чтение hits (`build.py`); Python — `py_cov.py` (AST-трансформация, рантайм `_jb_cov`) + загрузчик `_jb_run.py` |
| `core/lang/` | реестр языков `LANGS` (`java`, `python`): parse / check / regenerate / decompose |
| `core/py_parser.py` | Python `ast` → тот же нормализованный AST, что у Java (+ `span`, `header`); функции модуля — псевдокласс `Module` |
| `core/py_codegen.py` | правка узлов Python заменой только `span`/`header` оператора в исходнике |

Поток: правка кода → debounce 500 мс → `/parse` → `/analyze` + `/graph`. Правка узла → `/generate`
(сервер сравнивает присланные label с собственным CFG, применяет изменённые) → новый код → снова `/parse`.
Граф: асинхронная раскладка ELK (`elkjs` 0.12.0 layered, ортогональная маршрутизация, минимизация пересечений, отдельные порты для циклов, `utils/elkLayout.ts`) с ломаными рёбрами по точкам `sections` и `bendPoints` (`components/GraphCanvas/LabeledEdge.tsx`). Кнопка «Граф» в шапке скрывает/показывает панель (изначально закрыта, закрывается при смене языка, редактор растягивается). Нижняя панель появляется только после первого действия (`useStore.hasBottom`). Мини-карта графа прячется через 3 с без движения.
Хранение проекта: IndexedDB (`jb.project.v1`, `utils/projectStorage.ts`) с задержкой сохранения 500 мс, живой текст из `useStore.code`. Корректное объединение с примерами сервера без затирания правок, память списка удалённых примеров. Управление файлами в дереве `components/ProjectTree/ProjectTree.tsx`: создание/переименование файлов и папок, валидация имён на русском (`utils/fileValidation.ts`), автоматическая смена языка (`.java` ↔ `.py`), сохранение покрытия и истории запусков, экспорт изменённых и созданных файлов в zip с манифестом удалённых `DELETED.txt`.
Quality Gate: `/quality-gate`, `/decompose/verify` — компиляция + сравнение вывода.

AI-правки: `ai/ai_analyzer.py` (запросы, повторы с `repair.txt`), `ai/patcher.py` (поиск фрагмента, проверка
«не добавляет новых ошибок»). Эндпоинты: `POST /api/ai/fix` (правка одной ошибки javac), `POST /api/analyze`
(поле `compileErrors`), `POST /api/files/zip` (zip изменённых файлов проекта, `api/files.py`).
Big O «было → станет»: `ai/bigo_diff.py` (поля `bigoBefore/bigoAfter` патча), `POST /api/ai/bigo-combined` (несколько
советов вместе, без LLM). Фронтенд: `utils/speedup.ts` (ускорение при n = 1000), `utils/bigoAfter.ts`,
`hooks/useBigoAfter.ts` → `useStore.bigoAfterAi`, бейдж `components/BigoChange` в `DiagnosticsPanel` и `PatchView`.
Фронтенд: история запусков по файлам — `useProject.runs` / `utils/runs.ts`; тесты — `npx vitest run`.

Python: запросы несут `language`; `cfg_builder`, `bigo_analyzer`, `defect_detector` (`_python_defects`: `in list` в цикле,
вложенный цикл по одной коллекции, конкатенация строки в цикле, `range(len(x))`, проглоченный `except`, изменяемый
аргумент по умолчанию) и `decomposer` (`_decompose_python`: функции/классы → модули, `main.py` — фасад) ветвятся по
`language == "python"`. Запуск — `runner.python_command` (окружение `python_env()`, `RLIMIT_AS` 100 МБ; docker без отката на хост).

Консоль (`core/interactive.py`): сессия не дольше `MAX_SESSION_SEC` = 10 с, включая ожидание ввода. Память: локально
Java `-Xmx100m` (`MAX_MEMORY_MB`), Python `RLIMIT_AS` 100 МБ; в docker — контейнер 256 МБ, Java там по-прежнему
`-Xmx256m` (`runner.docker_command`). В docker при покрытии `--ulimit fsize` ограничивает и файлы, которые пишет сама программа.

Покрытие: интерактивный запуск (`core/interactive.py`, `/api/ws/run`) компилирует инструментированную копию и после
вывода, перед `exit`, шлёт `{type:"coverage", probes, hits}` (или `{type:"coverage", error}`). Python: `build.prepare_python` кладёт
`main.py`, `py_cov.py`, `_jb_run.py`; ребёнок сам инструментирует код и пишет счётчики в `$JB_COV` (`cov/hits.bin`,
в docker — `/cov/hits.bin`). Маркер `cov/compiled` создаётся сервером пустым; программа пишет в него, когда
инструментированный код запущен, и сервер верит только непустому обычному файлу. В docker монтируются только
эти два файла (`rw`), не каталог. Фронтенд накапливает
hits по файлу (`useProject.coverage`, `utils/coverage.ts`), рисует полосы в gutter `AceEditor` и вкладку «Покрытие».

Стримы: парсер ставит оператору поле `stream` (`core/streams.py`), `cfg_builder` разворачивает его в цепочку узлов, `code_generator` правит шаги и собирает цепочку через `compose`, `bigo_analyzer._stream_cost` считает Big O по шагам, `defect_detector._stream_defects` + `ai/static_tips.py` дают 6 правил. Фронтенд: семейство узлов `stream` (`kinds.ts`, `CFGView.tsx`, `index.css`).

Ограничения: см. README.
