"""Магазин-монолит: классы, поля, статические методы и вложенные циклы."""
import io
from contextlib import suppress

TAX_RATE = 0.2


def with_tax(price: float) -> float:
    return round(price * (1 + TAX_RATE), 2)


class Product:
    def __init__(self, name: str, price: float, tags: list[str] | None = None):
        self.name = name
        self.price = price
        self.tags = tags or []

    @staticmethod
    def validate_price(price: float) -> bool:
        return price >= 0

    @classmethod
    def from_pair(cls, pair: tuple[str, float]) -> "Product":
        return cls(pair[0], pair[1])

    def describe(self) -> str:
        return f"{self.name}: {with_tax(self.price)}"


class Store:
    def __init__(self):
        self.products: list[Product] = []
        self.names: list[str] = []
        self.log: list[str] = []

    def add_product(self, product: Product, history=[]) -> None:
        if not Product.validate_price(product.price):
            raise ValueError("Цена не может быть отрицательной")
        history.append(product.name)
        self.products.append(product)
        self.names.append(product.name)
        self.log.append(f"добавлен {product.name}, всего в истории: {len(history)}")

    def has_product(self, name: str) -> bool:
        return name in self.names

    def find_duplicates(self) -> list[str]:
        dups = []
        for name in self.names:
            if self.names.count(name) > 1 and name not in dups:
                dups.append(name)
        return dups

    def cheaper_pairs(self) -> int:
        count = 0
        for a in self.products:
            for b in self.products:
                if a.price < b.price:
                    count += 1
        return count

    def total_value(self) -> float:
        total = 0.0
        for p in self.products:
            total += p.price
        return total

    def find_missing(self, wanted: list[str]) -> list[str]:
        missing = []
        for name in wanted:
            if not self.has_product(name):
                missing.append(name)
        return missing


def build_report(store: Store) -> str:
    out = io.StringIO()
    with out:
        for p in store.products:
            out.write(p.describe() + "\n")
        return out.getvalue()


def main():
    store = Store()
    for pair in [("Яблоко", 1.5), ("Апельсин", 2.25), ("Банан", 0.99), ("Яблоко", 1.7)]:
        store.add_product(Product.from_pair(pair))
    with suppress(ValueError):
        store.add_product(Product("Брак", -1))
    print(build_report(store), end="")
    print("Итого:", round(store.total_value(), 2))
    print("Дубликаты:", store.find_duplicates())
    print("Пар по цене:", store.cheaper_pairs())
    print("Нет в наличии:", store.find_missing(["Банан", "Киви"]))
    print("Записей в журнале:", len(store.log))


if __name__ == "__main__":
    main()
