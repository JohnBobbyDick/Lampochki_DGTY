class Store:
    def __init__(self):
        self.items: dict[str, float] = {}

    def put_item(self, name: str, price: float) -> None:
        if price < 0:
            raise ValueError("Price cannot be negative")
        self.items[name] = price

    def get_price(self, name: str) -> float:
        if name not in self.items:
            raise KeyError(f"Item not found: {name}")
        return self.items[name]

    def total_value(self) -> float:
        return sum(self.items.values())


def main():
    store = Store()
    store.put_item("Apple", 1.50)
    store.put_item("Orange", 2.25)
    store.put_item("Banana", 0.99)
    print("Store total:", store.total_value())
    try:
        store.get_price("Unknown")
    except KeyError as exc:
        print("Caught expected:", exc)


if __name__ == '__main__':
    main()
