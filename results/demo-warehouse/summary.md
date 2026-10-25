# Демо-сценарий на Warehouse.java (http://localhost)

Итого: **9 из 9** проверок пройдено.

| Шаг | Результат | Детали |
|---|---|---|
| Разбор Warehouse.java | ✅ | 1066 строк, методов: 83 |
| Графы CFG / Call Graph / Class Diagram | ✅ | cfg: 8 узлов, 10 рёбер, call: 81 узлов, 62 рёбер, class: 14 узлов, 11 рёбер |
| javac без ошибок | ✅ |  |
| Дефект O(n²) в findDuplicateNames: строка, узел, рекомендация, эффект | ✅ | стр. 639, узел n4, O(n²) → O(n) |
| Запуск монолита | ✅ | exit 0, 59 мс |
| Правка узла без смены поведения → поведение совпадает | ✅ | «for (int i = 0; i < Math.min(count, width); i++)» → «for (int i = 0; i < count && i < width; i++)» |
| Правка узла, меняющая вывод → расхождение поймано | ✅ | «bar += "#"» → «bar += "="» |
| Декомпозиция на файлы | ✅ | Warehouse.java, Parser.java, Analyzer.java, Printer.java, Helpers.java, AuditLog.java |
| Quality Gate: сборка + поведение сохранено | ✅ | {"compiled": true, "behaviorPreserved": true, "compileErrors": [], "diff": "", "stderr": "WARN: пропущена строка 14: не число: abc\nWARN: заказ R5: Недостаточно T200: нужно 10, есть 5\n"} |
