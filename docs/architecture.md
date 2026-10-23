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

Поток: правка кода → debounce 500 мс → `/parse` → `/analyze` + `/graph`. Правка узла → `/generate`
(сервер сравнивает присланные label с собственным CFG, применяет изменённые) → новый код → снова `/parse`.
Quality Gate: `/quality-gate`, `/decompose/verify` — компиляция + сравнение вывода.

Ограничения: см. README.
