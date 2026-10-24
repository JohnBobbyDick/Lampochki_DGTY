# Этап 5: сложность «сейчас → после ИИ» и ожидаемое ускорение — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** До нажатия «Применить» видно, какой станет сложность методов после применимых советов ИИ и во сколько раз
это ускорит программу: `O(n²) → O(n) · ~1000× быстрее` в списке «Сложность методов · Big O» и в карточке совета.

**Architecture:** Бэкенд для каждого применимого патча считает `analyze_ast` исходника и пропатченного кода и кладёт в
патч `bigo_before`/`bigo_after` для затронутых методов; новый эндпоинт считает сложность при совместном применении
нескольких советов. Фронтенд собирает применимые советы, берёт «после ИИ» по методу (один совет — из патча,
несколько — из эндпоинта) и считает ожидаемое ускорение по формуле при n = 1000.

**Tech Stack:** FastAPI, Pydantic (`CamelModel`), javalang; React 18, Zustand, vitest.

**Spec:** `docs/superpowers/specs/2026-10-24-multilang-coverage-design.md` — раздел 5.

## Global Constraints

- UI и тексты — на русском; стиль — `DESIGN.md`; цвета — существующие токены (`--ok`, `--err`, `--warn`, `--accent-ink`).
- Ускорение — только по формуле, без запуска: `f_before(n) / f_after(n)` при n = 1000; тултип «при n ≈ 1000».
- «Красивое» округление: ближайшее по логарифму из `2, 5, 10, 100, 1000, 10000, 100000, 1000000`; больше 10⁶ (включая `O(2^n)`) → «>1000000×».
- Та же сложность — ускорение не показывается; стало хуже — бейдж красный, без слова «быстрее» (текст «~N× медленнее»).
- `log` — по основанию 2. Неизвестная сложность (`O(?)`, `O(?) рекурсия`, пустая строка) — без стрелки и без ускорения.
- «После ИИ» по методу = сложность после **всех** текущих применимых советов, затрагивающих метод; непересекающиеся
  советы применяются последовательно, при пересечении строк — берётся лучший одиночный.
- Применимый совет = `patch.valid` и `fragmentPresent(code, patch.oldCode)` (как уже делает `useStore` для устаревших советов).
- Проверка после каждой задачи: `cd backend && venv/bin/python -m pytest -q`; `cd frontend && npm run build && npx vitest run`
  (на Windows — `backend/.venv/Scripts/python.exe`, JDK в `PATH`).
- Не коммитить чужие неотслеживаемые файлы (`AGENTS.md`, `.DS_Store`, `backend/package-lock.json`). ИИ-функции вручную не проверять.

## Решения (обязательны для исполнителей)

- **Затронутые методы патча** = методы исходника, чей `span` пересекается со строками `[start_line, end_line]`,
  **плюс** все `Класс.метод`, у которых метка `analyze_ast` изменилась (так `main`, вызывающий исправленный метод, тоже
  получает «было → станет»). Ключи — только с точкой (`Класс.метод`), как в `analyze_ast`.
- `bigo_before`/`bigo_after` заполняются только у валидного патча (`valid=True`); у невалидного — пустые словари.
- Совместное применение: каждый патч ищется в текущем коде через `patcher.locate(code, old_code, start_line)`;
  ненайденные пропускаются; пересечения — по найденным диапазонам строк; замены — снизу вверх через
  `patcher.replace_range(..., imports=None)`, затем один `patcher.add_imports` с объединением `imports`. Компиляция
  совместного результата не проверяется (это оценка).
- «Лучший одиночный» в группе пересекающихся патчей: минимальная сумма рангов `bigo_after` по его затронутым методам
  (ранг: `(p, l)` из `n^p·log^l n`, `O(2^n)` — выше всех полиномов, неизвестная — как `bigo_before`); при равенстве — первый по порядку.
- Фронтенд: при одном применимом совете — `patch.bigoAfter`; при двух и более — ответ эндпоинта (запрос с задержкой
  400 мс после изменения набора советов); пока ответа нет — лучшее из одиночных `bigoAfter` по методу.

## Review Focus

- Совет устарел (код изменили, фрагмента больше нет) — его «после ИИ» не показывается и не участвует в совмещении (тест в Task 4).
- Метод с `O(?) рекурсия` до или после — без стрелки и без ускорения, без падений (тесты в Task 3 и Task 4).
- Два совета правят пересекающиеся строки одного метода — берётся лучший, а не применяются оба (тест в Task 2).
- Совет добавляет `import` — совмещение с другим советом ниже в файле не сдвигает его строки (тест в Task 2).
- `O(n) → O(2^n)` и `O(2^n) → O(n)` — не `Infinity`/`NaN` в тексте (тест в Task 3).

---

### Task 1: Big O «было/станет» в патче

**Files:**
- Create: `backend/ai/bigo_diff.py`
- Modify: `backend/ai/patcher.py` (`build_patch`), `backend/models/schemas.py` (`AiPatch`), `frontend/src/store/useStore.ts` (тип `AiPatch`)
- Test: `backend/tests/test_bigo_diff.py`

**Interfaces:**
- Produces:
  - `affected_methods(code: str, start: int, end: int) -> set[str]` — `Класс.метод`, чей `span` в `parse_java(code)` пересекает `[start, end]`.
  - `bigo_change(code: str, patched: str, start: int, end: int) -> tuple[dict[str, str], dict[str, str]]` — `(before, after)` по правилу «Затронутые методы» из раздела «Решения»; методы, которых нет в одном из анализов, пропускаются.
  - `AiPatch.bigo_before: dict[str, str] = {}`, `AiPatch.bigo_after: dict[str, str] = {}` (JSON: `bigoBefore`, `bigoAfter`); `build_patch` возвращает эти ключи.
  - TS: `AiPatch.bigoBefore?: Record<string, string>; bigoAfter?: Record<string, string>`.

- [ ] **Step 1: Тесты** в `test_bigo_diff.py` на `read_java("Analyzer")`:
  - `test_merge_items_quadratic_to_linear` — патч, заменяющий тело `mergeItems` (вложенный цикл) проходом с `HashMap`, через `patcher.build_patch(code, old, new, ["java.util.HashMap"], hint)`: `p["valid"]`; `p["bigo_before"]["Analyzer.mergeItems"] == "O(n²)"`, `p["bigo_after"]["Analyzer.mergeItems"] == "O(n)"`; `"Analyzer.main"` есть в обоих словарях и тоже меняется `O(n²) → O(n)`.
  - `test_untouched_methods_absent` — в словарях нет `Analyzer.parseValue` (не правился, сложность не изменилась).
  - `test_invalid_patch_has_no_bigo` — патч с неизвестной переменной (как в `test_patcher.py`) → `bigo_before == bigo_after == {}`.
  - `test_same_complexity_kept` — правка внутри метода без изменения сложности (переименование локальной переменной) → метод есть в обоих словарях с одинаковой меткой.
- [ ] **Step 2:** `pytest tests/test_bigo_diff.py -q` → FAIL.
- [ ] **Step 3:** Реализовать `bigo_diff.py`, поля схемы, вызов из `build_patch` после `validate` (только если `valid`), тип на фронтенде.
- [ ] **Step 4:** `pytest -q` весь — зелёный; `npm run build`.
- [ ] **Step 5:** Commit `feat(ai): Big O before/after for each AI patch`.

---

### Task 2: Совместное применение советов — `POST /api/ai/bigo-combined`

**Files:**
- Modify: `backend/ai/bigo_diff.py`, `backend/api/ai.py`, `backend/models/schemas.py`
- Test: `backend/tests/test_bigo_diff.py`

**Interfaces:**
- Consumes: Task 1 `bigo_change`; `patcher.locate`, `patcher.replace_range`, `patcher.add_imports`.
- Produces:
  - `combined_bigo(code: str, patches: list[dict]) -> dict[str, str]` — патчи в формате `AiPatch` (snake_case, как из `build_patch`); возвращает «станет» для затронутых методов итогового кода (правило «Затронутые методы» относительно объединения диапазонов выбранных патчей); пустой список/все ненайдены → `{}`.
  - Схемы `AiBigoCombinedRequest {code: str, patches: list[AiPatch]}`, `AiBigoCombinedResponse {bigo: dict[str, str]}`; эндпоинт `POST /api/ai/bigo-combined` (не требует `state`/LLM).

- [ ] **Step 1: Тесты:**
  - `test_combined_two_methods` — два валидных патча в разных методах `Analyzer` (`mergeItems` → `O(n)`; второй — в `sortByValue`: пузырёк → `items.sort(Comparator.comparingInt(Item::getValue))`, `O(n²) → O(n log n)`) → в ответе оба метода с новыми метками и `main` = максимум из них.
  - `test_overlapping_takes_best` — два патча на одни и те же строки `mergeItems` (один → `O(n)`, другой → без изменения сложности) → `mergeItems` = `O(n)`.
  - `test_imports_do_not_shift_lower_patch` — верхний патч добавляет `import java.util.HashMap`, нижний ниже в файле → оба применены (метки обоих методов изменились).
  - `test_stale_patch_ignored` — патч, чьего `old_code` нет в коде, не влияет на ответ.
  - `test_endpoint` — `TestClient` `POST /api/ai/bigo-combined` с camelCase-телом → 200 и `{"bigo": {...}}`.
- [ ] **Step 2:** Тесты → FAIL.
- [ ] **Step 3:** Реализовать по разделу «Решения» (группы пересечений, «лучший одиночный», замены снизу вверх, один `add_imports`).
- [ ] **Step 4:** `pytest -q` — зелёный.
- [ ] **Step 5:** Commit `feat(ai): Big O for several AI suggestions applied together`.

---

### Task 3: Ожидаемое ускорение

**Files:**
- Create: `frontend/src/utils/speedup.ts`
- Test: `frontend/src/utils/speedup.test.ts`

**Interfaces:**
- Produces:
```ts
export interface Speedup { factor: number | null; label: string; worse: boolean }
export const growth: (bigo: string, n?: number) => number | null;     // f(n); null — неизвестно
export const speedup: (before: string, after: string, n?: number) => Speedup;   // n по умолчанию 1000
```
- Разбор меток, которые выдаёт `bigo_analyzer`: `O(1)`, `O(log n)`, `O(log² n)`, `O(n)`, `O(n log n)`, `O(n²)`, `O(n² log n)`, `O(n³)`, `O(n^k)`, `O(2^n)`; прочее → `null`.
- `label`: `"~1000× быстрее"`, `"~10× медленнее"`; та же сложность или неизвестная → `{factor: null, label: '', worse: false}`.

- [ ] **Step 1: Тесты** (таблица): `O(n²)→O(n)` = `~1000× быстрее`; `O(n)→O(log n)` = `~100× быстрее`; `O(n²)→O(n log n)` = `~100× быстрее`; `O(n log n)→O(n)` = `~10× быстрее`; `O(n)→O(1)` = `~1000× быстрее`; `O(n)→O(n²)` = `~1000× медленнее`, `worse: true`; `O(n)→O(n)` → `label ''`; `O(?) рекурсия→O(n)` → `label ''`; `O(2^n)→O(n)` = `>1000000× быстрее` (без `Infinity`); `O(n)→O(2^n)` = `>1000000× медленнее`; `O(n³)→O(n²)` = `~1000× быстрее`.
- [ ] **Step 2:** `npx vitest run src/utils/speedup.test.ts` → FAIL.
- [ ] **Step 3:** Реализовать (2^n при n = 1000 — не считать числом: любой переход через `O(2^n)` сразу в `>1000000×`).
- [ ] **Step 4:** `npx vitest run`, `npm run build`.
- [ ] **Step 5:** Commit `feat(ai): expected speedup from Big O classes`.

---

### Task 4: «После ИИ» по методу

**Files:**
- Create: `frontend/src/utils/bigoAfter.ts`, `frontend/src/hooks/useBigoAfter.ts`
- Modify: `frontend/src/hooks/useApi.ts` (`bigoCombined`), `frontend/src/store/useStore.ts` (`bigoAfterAi`)
- Test: `frontend/src/utils/bigoAfter.test.ts`

**Interfaces:**
- Consumes: Task 1 `AiPatch.bigoBefore/bigoAfter`; Task 2 эндпоинт; `fragmentPresent` из `utils/fragment.ts`; `AiAnswer` (`ai`, `aiReview` в `useStore`).
- Produces:
```ts
export const applicablePatches: (code: string, answers: (AiAnswer | null)[]) => AiPatch[];   // valid && fragmentPresent; items[].patch и answer.patch; без дублей по oldCode+newCode
export const bestSingle: (patches: AiPatch[]) => Record<string, string>;   // по методу — лучший bigoAfter (ранг как в «Решениях»)
export const bigoAfter: (patches: AiPatch[], combined: Record<string, string> | null) => Record<string, string>;
// 0 патчей → {}; 1 → его bigoAfter; ≥2 → combined ?? bestSingle(patches)
```
  - `useStore`: `bigoAfterAi: Record<string, string>` + `setBigoAfterAi`.
  - `useBigoAfter()` (вызывается один раз в `App`): следит за `code`, `ai`, `aiReview`; считает `applicablePatches`; при ≥2 — запрос `POST /api/ai/bigo-combined` через 400 мс после изменения набора (старый ответ отбрасывается, если набор уже другой); пишет `bigoAfter(...)` в `bigoAfterAi`.
  - `useApi.bigoCombined(code: string, patches: AiPatch[]): Promise<Record<string, string> | null>` (тихий: без спиннера и без тоста об ошибке).

- [ ] **Step 1: Тесты** `bigoAfter.test.ts`: невалидный и устаревший (фрагмента нет в `code`) патчи отбрасываются; один патч → его `bigoAfter`; два патча и `combined` → `combined`; два патча без `combined` → лучший по каждому методу; одинаковый патч в `ai.patch` и в `aiReview.items` учитывается один раз; `O(?) рекурсия` в `bigoAfter` не побеждает известную сложность.
- [ ] **Step 2:** → FAIL. **Step 3:** Реализовать. **Step 4:** `npx vitest run`, `npm run build`.
- [ ] **Step 5:** Commit `feat(ai): Big O after AI per method`.

---

### Task 5: Интерфейс — бейдж «было → станет»

**Files:**
- Create: `frontend/src/components/BigoChange/BigoChange.tsx`
- Modify: `frontend/src/components/DiagnosticsPanel/DiagnosticsPanel.tsx` (строка метода), `frontend/src/components/AiDrawer/PatchView.tsx`, `frontend/src/index.css`

**Interfaces:**
- Consumes: Task 3 `speedup`; Task 4 `useStore.bigoAfterAi`; `classifyBigO` (`utils/bigo.ts`).
- Produces: `<BigoChange before={string} after={string} />` — `before → after · <label>`; если `after` нет, совпадает с `before` или неизвестна — ничего не рендерит; `title="при n ≈ 1000"` на части с ускорением; при `worse` — цвет `--err`, иначе ускорение `--ok`; цвет не единственный носитель смысла (слова «быстрее»/«медленнее» и стрелка).

- [ ] **Step 1:** Строка метода в «Сложность методов · Big O»: текущий чип остаётся; если `bigoAfterAi[метод]` отличается — рядом `<BigoChange>` (подпись класса сложности под именем метода не меняется). Ширина правой панели ~280–600 px — бейдж переносится на новую строку, а не обрезается.
- [ ] **Step 2:** `PatchView`: над diff — по одной строке `<BigoChange>` на каждый метод из `patch.bigoBefore`, у которого `bigoAfter` отличается (имя метода — моноширинным).
- [ ] **Step 3:** `npm run build`, `npx vitest run`.
- [ ] **Step 4:** Визуальная проверка без ИИ: в dev-режиме подставить в стор `bigoAfterAi` и `aiReview` с одним патчем через консоль браузера (Playwright `page.evaluate` на модули Vite не опирается — допустимо временно экспортировать стор в `window` только в `import.meta.env.DEV`) и снять скриншоты правой панели и карточки совета в тёмной и светлой темах. Временный код не коммитить, если он не нужен приложению.
- [ ] **Step 5:** Commit `feat(ai): show Big O now → after AI with expected speedup`.

---

### Task 6: Документация и отметки

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/architecture.md`, `todo.md`

- [ ] **Step 1:** README — абзац про «было → станет» и ожидаемое ускорение (формула, n ≈ 1000, округление, когда не показывается). CLAUDE.md — `ai/bigo_diff.py`, `/api/ai/bigo-combined`, `utils/speedup.ts`, `utils/bigoAfter.ts`, `useBigoAfter`. `docs/architecture.md` — модули.
- [ ] **Step 2:** `todo.md` — отметить этап 5 и его пункты (переписать под задачи этого плана, со ссылкой на план).
- [ ] **Step 3:** Полная проверка бэкенда и фронтенда — зелёная.
- [ ] **Step 4:** Commit `docs: Big O after AI (stage 5)`.
