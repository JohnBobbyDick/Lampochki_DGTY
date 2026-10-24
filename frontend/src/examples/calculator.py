"""Калькулятор-монолит: рекурсия, разбор выражений, обработка ошибок."""

OPERATORS = "+-*/"


def fib(n: int) -> int:
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


def factorial(n: int) -> int:
    if n <= 1:
        return 1
    return n * factorial(n - 1)


def power(base: int, exp: int) -> int:
    if exp == 0:
        return 1
    return base * power(base, exp - 1)


def parse_number(text: str) -> float:
    text = text.strip()
    if not text:
        raise ValueError("пустое число")
    return float(text)


def parse_operator(text: str) -> int:
    """Индекс самого правого оператора с низким приоритетом или -1."""
    depth = 0
    for i in range(len(text) - 1, 0, -1):
        c = text[i]
        if c == ")":
            depth += 1
        elif c == "(":
            depth -= 1
        elif depth == 0 and c in "+-":
            return i
    for i in range(len(text) - 1, 0, -1):
        if text[i] in "*/":
            return i
    return -1


def apply_operation(op: str, left: float, right: float) -> float:
    match op:
        case "+":
            return left + right
        case "-":
            return left - right
        case "*":
            return left * right
        case "/" if right != 0:
            return left / right
        case "/":
            raise ValueError("деление на ноль")
        case _:
            raise ValueError(f"неизвестная операция: {op}")


def evaluate(expression: str) -> float:
    expression = expression.strip()
    index = parse_operator(expression)
    if index == -1:
        return parse_number(expression)
    left = evaluate(expression[:index])
    right = evaluate(expression[index + 1:])
    return apply_operation(expression[index], left, right)


def collatz_steps(n: int) -> int:
    steps = 0
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        steps += 1
        if steps > 1000:
            break
    else:
        return steps
    return -1


def print_result(expression: str, value: float) -> None:
    print(f"{expression} = {value}")


def print_error(expression: str, message: str) -> None:
    print(f"Ошибка в '{expression}': {message}")


def print_table(limit: int) -> None:
    for n in range(limit):
        print(f"fib({n}) = {fib(n)}, {n}! = {factorial(n)}, 2^{n} = {power(2, n)}")


def safe_evaluate(expression: str) -> None:
    try:
        value = evaluate(expression)
    except ValueError as exc:
        print_error(expression, str(exc))
    else:
        print_result(expression, value)
    finally:
        print("--")


def main():
    for expr in ["1 + 2 * 3", "10 / 4 - 1", "8 / 0", "2 * x", "7 * 6"]:
        safe_evaluate(expr)
    print_table(8)
    print("collatz(27) =", collatz_steps(27))


if __name__ == "__main__":
    main()
