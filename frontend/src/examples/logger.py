def parse_entry(raw: str) -> dict:
    parts = raw.split(":", 1)
    level = parts[0].strip() if len(parts) > 1 else "INFO"
    msg = parts[1].strip() if len(parts) > 1 else raw.strip()
    return {"level": level, "message": msg}


def parse_batch(logs: list[str]) -> list[dict]:
    return [parse_entry(line) for line in logs if line.strip()]


def format_entry(entry: dict) -> str:
    return f"[{entry['level']}] {entry['message']}"


def print_summary(entries: list[dict]) -> None:
    counts: dict[str, int] = {}
    for e in entries:
        lvl = e["level"]
        counts[lvl] = counts.get(lvl, 0) + 1
    for lvl, count in counts.items():
        print(f"{lvl}: {count} events")


def main():
    raw_logs = [
        "INFO: Service started",
        "WARN: Low memory",
        "ERROR: Connection timeout",
        "INFO: Request handled",
    ]
    parsed = parse_batch(raw_logs)
    print_summary(parsed)


if __name__ == '__main__':
    main()
