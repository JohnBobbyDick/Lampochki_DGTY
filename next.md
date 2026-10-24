# С чего продолжить

Ветка `feature/multilang-coverage`, последний запушенный коммит `122a17b`. В `main` не сливать до конца всех этапов.

## Состояние

- Этапы 1–6 готовы.
- Python из ветки `backend` (коммит `18d386f`) влит, коммит слияния `89c8967`. Тесты на тот момент: backend 287 passed,
  vitest 55 passed, `npm run build` OK.
- Этап 7 выполнен частично. План доделки: `docs/superpowers/plans/2026-10-24-stage7-python.md` (10 задач).
  Ни одна задача плана ещё не начата.
- Разбор того, что уже было сделано для Python, лежит в `.superpowers/sdd/python-merge-report.md`
  (папка в `.gitignore`, только локально).

## Незакоммиченная правка (не проверена)

Это исправление замечания проверки безопасности: ввод в консоль (`stdin`) писался в канал прямо в цикле событий.
Если программа не читает ввод, канал переполняется, и весь сервер зависает, даже «Стоп» не срабатывает.

- `backend/core/interactive.py`:
  - `InteractiveProcess.send` с очередью и отдельным потоком-писателем;
  - `STDIN_LIMIT` = 1 МБ на запуск;
  - `feed` теперь возвращает `bool`;
  - новая функция `close_stdin`.
- `backend/api/ws.py`: при превышении лимита отправляется `stderr` «Слишком много ввода: лимит 1 МБ на запуск»;
  `eof` обрабатывается через `close_stdin`.
- `backend/tests/test_ws.py`: два новых теста, `test_unread_stdin_does_not_block_stop` и `test_stdin_limit_is_reported`.

Тесты ещё не запускались. Тест полагается на сообщение `{"type": "stop"}`; сначала проверить, как `api/ws.py` на самом
деле называет остановку (`grep -n 'kind ==' backend/api/ws.py`). Потом запустить
`cd backend && venv/bin/python -m pytest -q tests/test_ws.py`, затем все тесты, и закоммитить
`fix(console): stdin writes off the event loop, 1 MB input cap`.

## Дальше

1. Довести и закоммитить правку выше.
2. Выполнять план этапа 7 по задачам с проверкой (subagent-driven), начиная с Task 1 «Реестр языков».
3. После этапа 7 — слияние в `main` (этап 8, C++, отменён 25.10).

## Правила

- Не коммитить `AGENTS.md`, `.DS_Store`, `backend/package-lock.json`; не трогать `to-do.md`.
- Функции ИИ вручную не проверять, это делает пользователь.
- Сообщения коммитов заканчиваются строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
