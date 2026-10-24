"""Fallback advice used when no LLM is available (pattern database)."""

from __future__ import annotations

TIPS: list[tuple[str, str, str]] = [
    ("повторный стрим",
     "Стрим по той же коллекции внутри цикла по ней обходит её заново на каждом шаге — O(n²). Вынесите стрим из цикла "
     "или посчитайте всё за один проход (например, сгруппируйте в Map заранее).",
     "Map<String, Long> counts = items.stream().collect(Collectors.groupingBy(Item::getType, Collectors.counting()));\nfor (Item it : items) {\n    long same = counts.get(it.getType());\n}"),
    ("через сбор в коллекцию и size()",
     "collect(Collectors.toList()).size() строит список только ради длины. Метод count() считает элементы без "
     "создания коллекции.",
     "long n = items.stream().filter(i -> i.isActive()).count();"),
    ("isPresent() в",
     "filter(...).findFirst().isPresent() — это проверка «есть ли подходящий элемент». anyMatch(...) выражает её "
     "напрямую и останавливается на первом совпадении.",
     "boolean found = items.stream().anyMatch(i -> i.isActive());"),
    ("сортирует всё ради одного",
     "sorted(...).findFirst() сортирует всю коллекцию за O(n log n) ради одного элемента. min(...)/max(...) "
     "находят его за один проход — O(n).",
     "Optional<Item> first = items.stream().min(Comparator.comparing(Item::getPrice));"),
    ("изменяет внешнюю коллекцию",
     "forEach с add/put/remove во внешнюю коллекцию — побочный эффект: код трудно читать и нельзя безопасно "
     "распараллелить. Соберите результат через collect(...).",
     "List<String> names = items.stream().map(Item::getName).collect(Collectors.toList());"),
    ("цикл можно заменить стримом",
     "Цикл, который только отбирает и/или преобразует элементы в список, проще выразить стримом: filter/map + "
     "collect. Код короче и без изменяемого состояния.",
     "List<Integer> result = xs.stream().filter(x -> x > 0).collect(Collectors.toList());"),
    ("повторная обработка пар",
     "Вложенный цикл по одной коллекции сравнивает каждый элемент с каждым — O(n²). Если сравниваются по ключу "
     "(например, id), достаточно одного прохода с HashMap<ключ, значение>: элементы с одинаковым ключом попадают в одну "
     "корзину, и вторая итерация не нужна.",
     "Map<String, Item> byId = new HashMap<>();\nfor (Item it : items) {\n    byId.merge(it.getId(), it, (a, b) -> {\n        a.setValue(a.getValue() + b.getValue());\n        return a;\n    });\n}\nList<Item> result = new ArrayList<>(byId.values());"),
    ("вложенные циклы",
     "Глубина вложенности циклов определяет степень полинома. Попробуйте заменить внутренний поиск на lookup в "
     "HashSet/HashMap, отсортировать данные один раз или объединить проходы.", ""),
    ("пустой catch",
     "Пустой catch скрывает ошибку: программа продолжит работу с неверным состоянием, а причину не найти. "
     "Как минимум залогируйте исключение, лучше — обработайте или пробросьте.",
     "try {\n    // ...\n} catch (NumberFormatException e) {\n    System.err.println(\"Неверный формат числа: \" + e.getMessage());\n}"),
    ("общий catch",
     "catch (Exception) ловит и программные ошибки, которые стоит увидеть. Перечислите конкретные типы "
     "(IOException, NumberFormatException) и обрабатывайте их по-разному.", ""),
    ("не используется",
     "Неиспользуемая переменная — мёртвый код: она запутывает читателя и может скрывать забытую логику. Удалите её "
     "или используйте по назначению.", ""),
    ("неиспользуемый импорт", "Удалите лишний import — компилятор его не использует, а читателю он мешает.", ""),
    ("дублирование",
     "Одинаковые тела методов нужно держать в одном месте: исправление ошибки придётся делать несколько раз. "
     "Вынесите общий код в один метод и вызывайте его.", ""),
    ("рекурсия",
     "Для рекурсии оцените глубину и число повторных вычислений. Для пересекающихся подзадач (как fibonacci) "
     "помогает мемоизация или итеративная версия.", ""),
]

DEFAULT = ("Подробного совета в базе паттернов нет. Следуйте рекомендации анализатора; для детального разбора "
           "включите AI (LLM_ENABLED=true и GEMINI_API_KEY).", "")


def tip_for(message: str, recommendation: str = "") -> tuple[str, str]:
    low = message.lower()
    for key, text, code in TIPS:
        if key in low:
            return text, code
    return (recommendation or DEFAULT[0]), DEFAULT[1]
