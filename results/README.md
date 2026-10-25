# Результаты проверки

Сформировано 25.10.2026 на ветке `feature/multilang-coverage`. Всё ниже воспроизводится командами из раздела
«Как повторить».

## Сводка

| Проверка | Окружение | Результат | Файлы |
|---|---|---|---|
| Автотесты бэкенда (pytest) | Docker-образ `backend`, Linux, Python 3.11, JDK 17 | **539 passed**, 1 skipped | `backend-pytest-docker.txt`, `.xml` |
| Автотесты бэкенда (pytest) | macOS, Python 3.11, JDK 17 | **538 passed**, 2 skipped | `backend-pytest-jdk17.txt`, `.xml` |
| Автотесты бэкенда (pytest) | macOS, Python 3.11, JDK 11 | **535 passed**, 5 skipped | `backend-pytest-jdk11.txt`, `.xml` |
| Автотесты фронтенда (vitest) | Node | **115 passed** (18 файлов) | `frontend-vitest.txt`, `.xml` |
| Проверка типов и сборка фронтенда | `tsc -b && vite build` | ✅ без ошибок | `frontend-build.txt` |
| Сборка Docker-стека | `docker compose build` | ✅ | `docker-build.log` |
| Демо-сценарий кейса на `Warehouse.java` | собранный Docker-стек, `http://localhost` | **9 из 9** | `demo-warehouse/summary.md` |

Пропущенные тесты (их причины есть в логах, `-rs`):
- `test_compose_trusted_ip_matches_nginx_ip` — нет модуля `yaml`; это необязательная проверка конфигурации.
- `test_ws.py` (лимит памяти) — macOS игнорирует `RLIMIT_AS`; в Docker на Linux тест проходит.
- 3 теста Java 17 (record, sealed, switch-выражения) на JDK 11 пропускаются — на JDK 17 проходят.

## Демо-сценарий («Монолит → Граф → Диагноз → Улучшение → Тесты»)

`demo_scenario.py` проходит путь из кейса через HTTP API собранного стека. Результат каждого шага лежит в
`demo-warehouse/`:

| Шаг | Что проверяется | Файл |
|---|---|---|
| Монолит | `Warehouse.java` (≈1060 строк, обязательный Java scope) разбирается: 83 метода | — |
| Граф | CFG, Call Graph, Class Diagram строятся | `graph-cfg.json`, `graph-call.json`, `graph-class.json` |
| Диагноз | javac без ошибок. У дефекта O(n²) в `findDuplicateNames` есть строка, узел графа, рекомендация и ожидаемый эффект O(n²) → O(n) | `analyze.json` |
| Запуск | программа выполняется, вывод на кириллице | `run-original.txt` |
| Улучшение через граф | правка узла цикла без смены поведения → вывод совпадает | `edit-preserving.json` |
| Тесты ловят регрессию | правка узла, меняющая вывод → расхождение найдено | `edit-changing.json` |
| Декомпозиция | 6 файлов: `Warehouse` (фасад), `Parser`, `Analyzer`, `Printer`, `Helpers`, `AuditLog` | `decompose.json`, `decomposed/` |
| Quality Gate | файлы компилируются, вывод совпадает с монолитом | `quality-gate.json` |

`screenshots/01-warehouse-diagnosis.png` — интерфейс на Docker-стеке: код ↔ блок-схема `findDuplicateNames`,
дефекты с рекомендацией и ожидаемым эффектом.

## Как повторить

```bash
# автотесты бэкенда (локально; JAVA_HOME выбирает JDK)
cd backend && source venv/bin/activate && python -m pytest -v -rs

# автотесты бэкенда в Docker-образе (Linux + JDK 17)
docker compose build
docker compose run --rm --no-deps -v "$PWD/test_monoliths:/test_monoliths:ro" -v "$PWD/frontend:/frontend:ro" \
  backend python -m pytest -v -rs -p no:cacheprovider

# фронтенд
cd frontend && npx vitest run && npm run build

# демо-сценарий на собранном стеке
docker compose up -d --build
python3 results/demo_scenario.py            # → results/demo-warehouse/
```
