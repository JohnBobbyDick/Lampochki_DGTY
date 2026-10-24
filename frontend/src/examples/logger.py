"""Логгер-монолит: разбор записей, итоги и типичные небрежности."""
import os
import sys


def parse_entry(raw: str) -> dict:
    parts = raw.split(":", 1)
    level = parts[0].strip() if len(parts) > 1 else "INFO"
    message = parts[1].strip() if len(parts) > 1 else raw.strip()
    return {"level": level, "message": message}


def parse_batch(lines: list[str]) -> list[dict]:
    return [parse_entry(line) for line in lines if line.strip()]


def format_entry(entry: dict) -> str:
    return f"[{entry['level']}] {entry['message']}"


def build_report(entries: list[dict]) -> str:
    report = ""
    for entry in entries:
        report = report + format_entry(entry) + "\n"
    return report


def to_number(text: str) -> int:
    try:
        return int(text)
    except:
        return 0


def read_optional(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        pass
    return ""


def count_levels(entries: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in entries:
        level = e["level"]
        counts[level] = counts.get(level, 0) + 1
    return counts


def print_summary(entries: list[dict]) -> None:
    # итоги по уровням
    for level, count in sorted(count_levels(entries).items()):
        print(f"{level}: {count} событий")


def print_errors(entries: list[dict]) -> None:
    # только ошибки
    for e in entries:
        if e["level"] == "ERROR":
            print(f"Внимание: {format_entry(e)}")


def main():
    raw_logs = [
        "INFO: Сервис запущен",
        "WARN: Мало памяти",
        "ERROR: Тайм-аут соединения",
        "",
        "Запрос обработан",
    ]
    entries = parse_batch(raw_logs)
    print(build_report(entries), end="")
    print_summary(entries)
    print_errors(entries)
    print("число:", to_number("42"), to_number("abc"))
    print("файл:", repr(read_optional("no-such-file.txt")))


if __name__ == "__main__":
    main()
