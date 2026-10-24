# Архитектура

Browser SPA (React, Ace, React Flow, Zustand) → REST `/api` → FastAPI.

| Модуль | Назначение |
|---|---|
| `core/parser.py` | javalang → JSON-AST, line_map, спаны деклараций (по токенам) |
| `core/cfg_builder.py` | CFG метода; детерминированные id узлов (`n0…`), карта узел→оператор |
| `core/call_graph.py`, `class_diagram.py` | графы вызовов / классов |
| `core/bigo_analyzer.py`, `defect_detector.py` | Big O по вложенности циклов/рекурсии; дефекты |
| `core/code_generator.py` | правки узлов → перегенерация тела метода и вставка в исходник по спану |
| `core/decomposer.py` | группировка static-методов по префиксам имён + графу вызовов |
| `core/runner.py`, `comparator.py` | javac/java (subprocess или docker), diff stdout (маскирует timestamps) |
| `core/coverage/` | покрытие: инструментирование исходника по токенам (`instrument.py`, `conditions.py`), счётчик `Cov.java` (mmap-файл), сборка с деградацией и чтение hits (`build.py`) |

Поток: правка кода → debounce 500 мс → `/parse` → `/analyze` + `/graph`. Правка узла → `/generate`
(сервер сравнивает присланные label с собственным CFG, применяет изменённые) → новый код → снова `/parse`.
Quality Gate: `/quality-gate`, `/decompose/verify` — компиляция + сравнение вывода.

AI-правки: `ai/ai_analyzer.py` (запросы, повторы с `repair.txt`), `ai/patcher.py` (поиск фрагмента, проверка
«не добавляет новых ошибок»). Эндпоинты: `POST /api/ai/fix` (правка одной ошибки javac), `POST /api/analyze`
(поле `compileErrors`), `POST /api/files/zip` (zip изменённых файлов проекта, `api/files.py`).
Фронтенд: история запусков по файлам — `useProject.runs` / `utils/runs.ts`; тесты — `npx vitest run`.

Покрытие: интерактивный запуск (`core/interactive.py`, `/api/ws/run`) компилирует инструментированную копию и после
вывода, перед `exit`, шлёт `{type:"coverage", probes, hits}` (или `{type:"coverage", error}`). Фронтенд накапливает
hits по файлу (`useProject.coverage`, `utils/coverage.ts`), рисует полосы в gutter `AceEditor` и вкладку «Покрытие».

Ограничения: см. README.
