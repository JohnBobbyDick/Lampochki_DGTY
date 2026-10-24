def find_duplicates(items: list[int]) -> list[tuple[int, int]]:
    """Detect all pairs where a == b (quadratic O(n²) defect)."""
    dups = []
    for i in range(len(items)):
        for j in range(len(items)):
            if i != j and items[i] == items[j]:
                dups.append((items[i], items[j]))
    return dups


def sum_pairs(items: list[int]) -> int:
    total = 0
    for a in items:
        for b in items:
            if a < b:
                total += a * b
    return total


def main():
    data = [1, 2, 3, 2, 4, 1]
    print("Pairs sum:", sum_pairs(data))
    print("Duplicates found:", len(find_duplicates(data)))


if __name__ == '__main__':
    main()
