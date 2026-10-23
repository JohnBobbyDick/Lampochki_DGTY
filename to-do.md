
## 📐 Архитектура системы

```
┌─────────────────────────────────────────────────────────┐
│                     BROWSER (SPA)                       │
│  ┌──────────────┐   ┌────────────────────────────────┐  │
│  │  Ace Editor  │◄──►  React Flow Graph Canvas       │  │
│  │  (Java code) │   │  CFG / Call Graph / Class Diag │  │
│  └──────┬───────┘   └──────────────┬─────────────────┘  │
│         │   двусторонняя синхронизация (REST polling)    │
└─────────┼──────────────────────────┼────────────────────┘
          │                          │
          ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│                  FastAPI Backend (Python)                │
│  ┌──────────────┐  ┌────────────┐  ┌─────────────────┐  │
│  │ Java Parser  │  │  Analyzer  │  │  Code Generator │  │
│  │ (javalang /  │  │ (CFG/Call/ │  │  (AST → Java)   │  │
│  │  tree-sitter)│  │  BigO)     │  │                 │  │
│  └──────────────┘  └────────────┘  └─────────────────┘  │
│  ┌──────────────────────────────────────────────────┐    │
│  │        Docker Sandbox (javac + java runner)      │    │
│  │   изолированный запуск .java файлов + stdout     │    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
          │
          ▼  (отдельный блок — опционально, в конце)
┌─────────────────────────────────────────────────────────┐
│              LLM / AI Agent Layer                        │
│  Google Gemini API / local Ollama — советы, диагностика │
└─────────────────────────────────────────────────────────┘
```

### Компоненты фронтенда

| Компонент | Назначение |
|-----------|-----------|
| `FileUpload` | Загрузка `.java` файлов (drag-n-drop) |
| `AceEditor` | Редактор с подсветкой синтаксиса Java |
| `GraphCanvas` | React Flow — CFG / Call Graph / Class Diagram (переключаемые режимы) |
| `DiagnosticsPanel` | Список дефектов + Big O + рекомендации |
| `RunComparePanel` | Запуск кода, вывод stdout до/после, diff |
| `DecomposePanel` | Предложение разбиения монолита на файлы |

### Компоненты бэкенда

| Модуль | Назначение |
|--------|-----------|
| `parser.py` | Парсинг Java → внутреннее AST (javalang / tree-sitter-java) |
| `cfg_builder.py` | Построение CFG внутри методов (ветвления, циклы, исключения) |
| `call_graph.py` | Построение Call Graph между методами/классами |
| `class_diagram.py` | Извлечение структуры классов, полей, наследования |
| `bigo_analyzer.py` | Статический анализ Big O по структуре циклов |
| `defect_detector.py` | Поиск дефектов: двойные циклы, пустые catch, дублирование |
| `code_generator.py` | Граф → обратная генерация Java-кода |
| `decomposer.py` | Анализ зависимостей → предложения по декомпозиции |
| `runner.py` | Запуск Java в Docker-сандбоксе, перехват stdout/stderr |
| `comparator.py` | Сравнение вывода оригинала и изменённой версии |

---

## 🗂️ Структура проекта

```
Lampochki_DGTY/
├── backend/
│   ├── main.py                  # FastAPI entry point
│   ├── api/
│   │   ├── parse.py             # POST /api/parse
│   │   ├── graph.py             # GET /api/graph/{type}
│   │   ├── analyze.py           # POST /api/analyze
│   │   ├── generate.py          # POST /api/generate
│   │   ├── run.py               # POST /api/run
│   │   └── decompose.py         # POST /api/decompose
│   ├── core/
│   │   ├── parser.py
│   │   ├── cfg_builder.py
│   │   ├── call_graph.py
│   │   ├── class_diagram.py
│   │   ├── bigo_analyzer.py
│   │   ├── defect_detector.py
│   │   ├── code_generator.py
│   │   ├── decomposer.py
│   │   ├── runner.py
│   │   └── comparator.py
│   ├── models/
│   │   └── schemas.py           # Pydantic-модели
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── FileUpload/
│   │   │   ├── AceEditor/
│   │   │   ├── GraphCanvas/
│   │   │   │   ├── CFGView.tsx
│   │   │   │   ├── CallGraphView.tsx
│   │   │   │   └── ClassDiagramView.tsx
│   │   │   ├── DiagnosticsPanel/
│   │   │   ├── RunComparePanel/
│   │   │   └── DecomposePanel/
│   │   ├── hooks/
│   │   │   ├── useSync.ts       # двусторонняя синхронизация
│   │   │   └── useApi.ts        # обёртки для API
│   │   ├── store/               # Zustand state management
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── sandbox/
│   └── Dockerfile               # JDK 17 для изолированного запуска
├── docker-compose.yml
├── README.md
└── to-do.md
```

---

## 🎨 Дизайн интерфейса

### Макет — Split View (три колонки)

```
┌──────────────────────────────────────────────────────────────────┐
│  🔵 Java Blueprints                    [Upload .java]  [Run ▶]   │  ← Header
├─────────────────┬────────────────────────┬───────────────────────┤
│                 │  [CFG] [Call] [Class]  │                       │
│   Ace Editor    │                        │   Diagnostics Panel   │
│   (Java code)   │   React Flow Graph     │   ┌─────────────────┐ │
│                 │                        │   │ ⚠ O(n²) line 5  │ │
│                 │   интерактивные узлы   │   │ ✦ Рефактор...   │ │
│  ↕ hover-связь  │   ← drag & drop →     │   │ 🔍 Диагноз...   │ │
│  код ↔ граф    │                        │   └─────────────────┘ │
│                 │                        │                       │
├─────────────────┴────────────────────────┴───────────────────────┤
│  Run Output: [BEFORE stdout]            [AFTER stdout]   [DIFF]  │  ← Bottom
└──────────────────────────────────────────────────────────────────┘
```

### Ключевые UX-правила
- **Hover sync**: наведение на строку кода → подсветка узла графа и наоборот
- **Click-to-jump**: клик на узел CFG → курсор в редакторе перепрыгивает на нужную строку
- **Live sync**: каждый `onChange` в редакторе через debounce 500ms → пересборка графа
- **Graph editing**: двойной клик на узел → inline-редактор текста узла → по `Enter` → регенерация кода
- **Drag edge**: перетаскивание рёбер для изменения порядка вызовов
- **Decompose suggestion**: кнопка → правая панель показывает предлагаемое разбиение на файлы
- **Цветовая схема узлов CFG**: start (зелёный) / end (красный) / if (жёлтый) / loop (синий) / try (фиолетовый) / normal (серый)

---

## ✅ TODO — Задачи

### 🔧 SETUP (0–1 ч)
- [x] Инициализировать Vite + React + TypeScript проект (`frontend/`)
- [x] Установить зависимости: `reactflow`, `react-ace ace-builds`, `zustand`, `axios`
- [x] Инициализировать FastAPI проект (`backend/`)
- [x] Установить: `fastapi`, `uvicorn`, `javalang`, `pydantic`, `python-multipart`
- [x] Создать `docker-compose.yml` (backend + sandbox)
- [x] Создать `sandbox/Dockerfile` (JDK 17 slim + timeout + memory limit 256MB)
- [x] Настроить CORS на FastAPI
- [x] Базовый `App.tsx` с тремя колонками (CSS Grid)

### 📤 UPLOAD & PARSE (1–3 ч)
- [x] `FileUpload` компонент — drag-n-drop загрузки `.java`
- [x] `POST /api/parse` — принимает `.java` текст, возвращает внутренний AST JSON
- [x] `parser.py` — парсинг через `javalang`:
  - Классы, интерфейсы, поля, методы
  - Примитивы, обёртки, массивы
  - Импорты, аннотации
- [x] Pydantic-схемы: `JavaFile`, `ClassNode`, `MethodNode`, `FieldNode`
- [x] Маппинг `nodeId ↔ lineNumber` (для hover-синхронизации)
- [x] Сохранение AST в Zustand store на фронте

### 📊 GRAPH BUILDING (3–7 ч)
- [x] `cfg_builder.py` — CFG для каждого метода:
  - `if/else` → ветвления (true/false рёбра)
  - `for/while/do-while` → циклы (back-edge, пунктирное ребро)
  - `try/catch/finally` → исключительные рёбра (красные)
  - `break/continue/return` → прерывание потока
  - `switch` → множественные рёбра по case
- [x] `call_graph.py` — какой метод какой вызывает (внутри класса + между классами)
- [x] `class_diagram.py` — классы, поля, методы, `extends`, `implements`
- [x] `GET /api/graph?type=cfg|call|class&method=MethodName` → возвращает `{nodes, edges}` для React Flow
- [x] `GraphCanvas` компонент с переключателем типа графа (табы сверху)
- [x] Кастомные React Flow nodes:
  - `CFGNode` (прямоугольник, цвет по типу: start/end/if/loop/try/normal)
  - `CallNode` (эллипс для метода, с иконкой Big O если известна)
  - `ClassNode` (UML-блок с полями и методами внутри)
- [x] Кастомные рёбра:
  - Обычные (чёрные стрелки)
  - Back-edge циклов (пунктир, синий)
  - Исключение (красный)
  - True/False ветвления (зелёный/красный с меткой)
- [x] Auto-layout (dagre или ELK через `@dagrejs/dagre`)

### ✏️ ДВУСТОРОННЯЯ СИНХРОНИЗАЦИЯ (7–12 ч)
- [x] `useSync.ts` хук — debounce 500ms на изменение кода → `POST /api/parse` → обновить граф
- [x] Хранить маппинг `lineNumber ↔ nodeId` из ответа API в Zustand
- [x] При hover на строку в Ace → выделить (highlight) соответствующий React Flow node
- [x] При click на React Flow node → установить курсор Ace Editor на нужную строку
- [x] Inline-редактирование узла CFG (double-click) → popup с textarea → `Enter` → `POST /api/generate` → обновить код
- [x] Подсветка изменённых строк (diff от предыдущей версии) в Ace Editor

### 🔍 ДИАГНОСТИКА И BIG O (12–18 ч)
- [x] `defect_detector.py`:
  - Вложенные циклы → пометка O(n²) / O(n³)
  - Пустые `catch {}` блоки
  - Повторная обработка одинаковых пар (двойной цикл с сравнением id)
  - Неиспользуемые переменные и импорты
  - Общий catch Exception вместо конкретных
- [x] `bigo_analyzer.py`:
  - Один цикл по коллекции → O(n)
  - Два вложенных цикла → O(n²)
  - Три вложенных цикла → O(n³)
  - Рекурсия → O(?) с пометкой «требует анализа»
  - Annotate каждый метод с меткой Big O
- [x] `POST /api/analyze` → возвращает список `Defect`:
  ```json
  {
    "lineStart": 5, "lineEnd": 9,
    "nodeId": "node_12",
    "severity": "warning",
    "bigO": "O(n²)",
    "message": "Вложенный цикл — повторная обработка пар",
    "recommendation": "Индексировать элементы по id через HashMap"
  }
  ```
- [x] `DiagnosticsPanel` компонент:
  - Список дефектов с иконками (⚠️ warning, 🔴 error, 💡 hint)
  - Клик на дефект → подсветка строки в редакторе + узла в графе
  - Big O аннотации рядом с названием метода в узлах графа
- [x] Ace Editor markers для дефектов (красная/жёлтая полоска в gutter)

### ⚙️ ГЕНЕРАЦИЯ КОДА (18–22 ч)
- [x] `code_generator.py` — обход графа → Java-код:
  - CFG → тело метода (if/else/loop/try блоки)
  - Class Diagram → каркас классов (поля, сигнатуры методов)
  - Форматирование с отступами
- [x] `POST /api/generate` → принимает изменённый граф JSON, возвращает Java-код
- [x] При редактировании узла графа → регенерация только затронутого метода
- [x] Простой стек undo/redo (Ctrl+Z / Ctrl+Y) — хранить историю состояний AST

### 🧩 ДЕКОМПОЗИЦИЯ МОНОЛИТА (22–27 ч)
- [x] `decomposer.py`:
  - Анализ coupling/cohesion между методами (общие поля, вызовы)
  - Группировка методов по зонам ответственности
  - Эвристика по именам: `parse*` → Parser, `analyz*` → Analyzer, `print*`/`format*` → Printer
  - Предложение: `{Parser.java: [methods...], Analyzer.java: [methods...]}`
- [x] `POST /api/decompose` → возвращает предлагаемые файлы + методы
- [x] `DecomposePanel` компонент:
  - Визуальное дерево: методы → файлы
  - Кнопка «Применить» → генерирует несколько `.java` файлов (zip-архив)
  - Quality Gate: после декомпозиции → запустить тесты

### ▶️ ЗАПУСК И СРАВНЕНИЕ (27–32 ч)
- [x] `runner.py`:
  - Запись `.java` во временную директорию Docker-сандбокса
  - `javac MainClass.java` → компиляция (перехват ошибок)
  - `java -cp . MainClass` с таймаутом 10с и `-Xmx256m`
  - Возвращает `{stdout, stderr, exitCode, durationMs}`
- [x] `comparator.py` — unified diff двух `stdout`
- [x] `POST /api/run` — запуск текущего кода
- [x] `POST /api/run/compare` — запуск оригинала и изменённого → diff вывода
- [x] `RunComparePanel` компонент:
  - Две колонки: BEFORE | AFTER stdout
  - Подсветка различий (зелёный добавлено / красный удалено)
  - Статус: ✅ Поведение сохранено / ❌ Поведение изменилось
  - Ошибки компиляции → показывать inline в редакторе

### 🧪 ТЕСТЫ И QUALITY GATE (32–38 ч)
- [x] Создать тестовые Java-монолиты (`test_monoliths/`):
  - `Analyzer.java` — вложенные циклы с O(n²) дефектом (из PDF)
  - `Store.java` — коллекции HashMap/ArrayList, исключения
  - `Calculator.java` — ветвления, switch, рекурсия
  - `Logger.java` — монолит на 3 обязанности (для декомпозиции)
- [x] `pytest` тесты бэкенда:
  - `test_parser.py` — корректность AST, количество классов/методов
  - `test_cfg.py` — рёбра CFG для if/loop/try
  - `test_bigo.py` — определение сложности O(n), O(n²)
  - `test_runner.py` — компиляция и запуск, сравнение stdout
- [x] `POST /api/quality-gate` → compile + run + compare → `{passed: bool, details}`

### 🖥️ UI POLISH (38–42 ч)
- [x] Тёмная тема (CSS variables)
- [x] Loading spinners при парсинге/запуске
- [x] Тултипы на узлах графа (тип узла, Big O, найденный дефект)
- [x] Кнопка «Export graph as PNG» (через React Flow `toImage`)
- [x] Горячие клавиши: `Ctrl+Enter` → Run, `Ctrl+D` → Decompose, `Ctrl+Z/Y` → Undo/Redo

### 📦 СБОРКА И ДЕПЛОЙ (42–46 ч)
- [x] `README.md` с инструкцией запуска через `docker-compose up`
- [x] `vite build` → production сборка фронтенда
- [x] Nginx конфиг: раздача статики + проксирование `/api` → FastAPI
- [ ] Подготовить VPS: Docker + Docker Compose
- [ ] Деплой и проверка по публичному IP/домену
- [ ] Получить ссылку на веб-демо

### 🎬 DEMO PREP (46–48 ч)
- [x] Пройти полный сценарий: загрузка → граф → правка → генерация → запуск → сравнение
- [x] Убедиться что Quality Gate проходит (✅ Поведение сохранено)
- [x] `docs/architecture.md` — описание архитектуры и ограничений
- [ ] Отправить ссылку на репозиторий HR до **8:00 25.10**

---

## 🔌 API Reference

| Метод | Endpoint | Тело | Ответ |
|-------|----------|------|-------|
| POST | `/api/parse` | `{code: string}` | `{ast: JavaAST, lineMap: {}}` |
| GET | `/api/graph` | `?type=cfg\|call\|class&method=...` | `{nodes: [], edges: []}` |
| POST | `/api/analyze` | `{ast: JavaAST}` | `{defects: [], bigo: {methodName: "O(n²)"}}` |
| POST | `/api/generate` | `{graph: GraphJSON}` | `{code: string}` |
| POST | `/api/run` | `{code: string, mainClass: string}` | `{stdout, stderr, exitCode, durationMs}` |
| POST | `/api/run/compare` | `{original: string, modified: string, mainClass: string}` | `{before, after, diff, behaviorPreserved: bool}` |
| POST | `/api/decompose` | `{ast: JavaAST}` | `{files: [{name, methods: []}]}` |
| POST | `/api/quality-gate` | `{original: string, modified: string, mainClass: string}` | `{passed: bool, details: {}}` |

---

## 📊 Критерии оценки (из PDF)

| Критерий | Наша реализация |
|----------|----------------|
| Поддержка Java scope (конструкции 1–4) | ✅ javalang: классы, коллекции, исключения, I/O |
| Сохранение поведения (Quality Gate) | ✅ Docker runner + stdout diff |
| Полезность диагностики и оптимизации | ✅ Big O + дефекты + декомпозиция |
| Понятность интерфейса | ✅ Split view, hover-sync, tooltips |
| Качество реализации и демо | ✅ Полный путь: загрузка → граф → правка → запуск → сравнение |

---

---

## 🤖 AI / LLM — Отдельный блок (бонус, реализовывать последним)

> ⚠️ Эти функции зависят от внешних API и реализуются **в последнюю очередь**.
> Основной функционал не зависит от AI-блока.

### Структура

```
backend/ai/
├── llm_client.py         # обёртка над Gemini API / Ollama
├── prompts/
│   ├── defect_explain.txt    # объяснение дефекта на русском
│   ├── optimization.txt      # предложение оптимизации с примером кода
│   └── decompose_hint.txt    # совет по декомпозиции монолита
└── ai_analyzer.py        # POST /api/ai/explain, /api/ai/suggest
```

### AI Эндпоинты

| Метод | Endpoint | Назначение |
|-------|----------|-----------|
| POST | `/api/ai/explain` | Объяснить дефект/узел графа на русском языке |
| POST | `/api/ai/suggest` | Предложить рефакторинг для выделенного фрагмента |
| POST | `/api/ai/decompose` | LLM-рекомендация по декомпозиции монолита |

### Конфигурация

```bash
# backend/.env
GEMINI_API_KEY=...             # https://aistudio.google.com/apikey
GEMINI_MODEL=gemini-2.5-flash
LLM_PROVIDER=gemini            # или: ollama
OLLAMA_MODEL=codellama:7b      # если локально без API ключа
LLM_ENABLED=true               # false — отключить все AI фичи
```

### UX интеграция
- Кнопка «✨ AI Suggest» рядом с каждым дефектом в `DiagnosticsPanel`
- Результат LLM — в выдвижной боковой панели (не заменяет статический анализ)
- Все LLM-вызовы — **асинхронные**, не блокируют UI
- Если `LLM_ENABLED=false` или нет ключа → заглушка с правилами на основе паттернов

### TODO — AI задачи (после основного функционала)
- [x] `llm_client.py` — async обёртка над Gemini REST / Ollama через `httpx` (список прокси, перебор ключей, ретраи с деградацией модели)
- [x] Промпты для объяснения дефектов на русском (с примером кода до/после)
- [x] `POST /api/ai/explain` — принимает `{code_fragment, defect}`, возвращает `{explanation, fixed_code}`
- [x] `POST /api/ai/suggest` — принимает `{code_fragment}`, возвращает `{suggestion, example}`
- [x] Кнопка «✨ AI» в `DiagnosticsPanel` + боковая панель результата
- [x] Fallback: если нет LLM → статические советы из базы паттернов

---

### 📝 Статус (23.10.2026)
Выполнено: основной функционал, интерактивная консоль (WebSocket), AI-блок на Gemini (с fallback на базу
паттернов), 46 pytest-тестов, `vite build`, `docker compose up --build` (образы собраны, API/UI/WebSocket через
nginx проверены). Демо-сценарий и Quality Gate (и пройденный, и провальный) покрыты тестом `test_demo_scenario.py`.
AI с реальным ключом не проверялся (тесты — на моках HTTP).
Осталось вручную: VPS, деплой, ссылка на демо, отправка ссылки HR до 8:00 25.10.
Не реализовано: drag рёбер для смены порядка вызовов; декомпозиция переносит только static-методы.

**AI (доп.):** прокси для Gemini (`GEMINI_PROXIES`), перебор нескольких ключей, ретраи, авто-ревью через 5 с
после последней правки с плашкой «ИИ-модель смотрит, как улучшить код…» (58 pytest-тестов, поведение таймера
проверено в браузере на подделке Gemini).

**AI (применение правок):** `POST /api/ai/apply`; замена фрагмента с проверкой синтаксиса и компиляции, diff-превью и
кнопка «Применить» в панели (72 pytest-теста; применение, блокировка битой правки, undo и «Проверить поведение»
проверены в браузере на подделке Gemini).

*Последнее обновление: 23.10.2026*
