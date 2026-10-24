"""Анализатор-монолит: comprehensions, сортировка и поиск."""


def find_duplicates(items: list[int]) -> list[int]:
    """Квадратичный поиск повторов: O(n^2)."""
    dups = []
    for i in range(len(items)):
        for j in range(len(items)):
            if i != j and items[i] == items[j] and items[i] not in dups:
                dups.append(items[i])
    return dups


def sum_pairs(items: list[int]) -> int:
    total = 0
    for a in items:
        for b in items:
            if a < b:
                total += a * b
    return total


def squares_of_evens(items: list[int]) -> list[int]:
    return [x * x for x in items if x % 2 == 0]


def histogram(items: list[int]) -> dict[int, int]:
    return {x: items.count(x) for x in set(items)}


def top_three(items: list[int]) -> list[int]:
    return sorted(items, reverse=True)[:3]


def has_negative(items: list[int]) -> bool:
    return any(x < 0 for x in items)


def find_first_prime(items: list[int]) -> int | None:
    for x in items:
        if x < 2:
            continue
        for d in range(2, x):
            if x % d == 0:
                break
        else:
            return x
    return None


def stats(items: list[int]) -> dict[str, float]:
    def mean(values: list[int]) -> float:
        return sum(values) / len(values)

    return {
        "min": min(items),
        "max": max(items),
        "mean": round(mean(items), 2),
    }


def lengths_total(words: list[str]) -> int:
    return sum(len(w) for w in words)


def pair_sums(items: list[int]) -> list[int]:
    return [a + b for a in items for b in items if a < b]


def main():
    data = [5, 3, 8, 3, 1, 8, 9, -2]
    print("Повторы:", find_duplicates(data))
    print("Сумма пар:", sum_pairs(data))
    print("Квадраты чётных:", squares_of_evens(data))
    print("Гистограмма:", sorted(histogram(data).items()))
    print("Топ-3:", top_three(data))
    print("Есть отрицательные:", has_negative(data))
    print("Первое простое:", find_first_prime(data))
    print("Статистика:", stats(data))
    print("Длина слов:", lengths_total(["один", "два", "три"]))
    print("Сумм пар:", len(pair_sums(data)), "максимум:", max(pair_sums(data)))


if __name__ == "__main__":
    main()
