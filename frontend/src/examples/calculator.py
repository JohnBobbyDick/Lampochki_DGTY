class Calculator:
    def __init__(self):
        self.history: list[str] = []

    def add(self, a: float, b: float) -> float:
        res = a + b
        self.history.append(f"{a} + {b} = {res}")
        return res

    def multiply(self, a: float, b: float) -> float:
        res = a * b
        self.history.append(f"{a} * {b} = {res}")
        return res


def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)


def main():
    calc = Calculator()
    print("3 + 4 =", calc.add(3, 4))
    print("3 * 4 =", calc.multiply(3, 4))
    print("fact(5) =", factorial(5))


if __name__ == '__main__':
    main()
