import java.util.*;
import java.util.stream.*;

/**
 * Streams demo — Stream API pipelines (filter / map / sorted / groupingBy / flatMap)
 * plus one case for each stream defect rule:
 * 1) repeated stream over the collection the loop iterates
 * 2) collect(...).size()    3) filter(...).findFirst().isPresent()
 * 4) sorted(...).findFirst()    5) forEach that mutates an outer collection
 * 6) a plain loop that could be a stream
 */
public class Streams {

    static class Item {
        String name;
        String category;
        int price;

        Item(String name, String category, int price) {
            this.name = name;
            this.category = category;
            this.price = price;
        }

        String getName() { return name; }
        String getCategory() { return category; }
        int getPrice() { return price; }
    }

    static class Order {
        int id;
        List<Item> items;

        Order(int id, List<Item> items) {
            this.id = id;
            this.items = items;
        }

        List<Item> getItems() { return items; }
        int total() { return items.stream().mapToInt(Item::getPrice).sum(); }
    }

    static List<Order> buildOrders() {
        List<Order> orders = new ArrayList<>();
        orders.add(new Order(1, Arrays.asList(new Item("pen", "office", 3), new Item("book", "paper", 12))));
        orders.add(new Order(2, Arrays.asList(new Item("laptop", "tech", 900), new Item("mouse", "tech", 25))));
        orders.add(new Order(3, Arrays.asList(new Item("notebook", "paper", 5), new Item("pen", "office", 3))));
        return orders;
    }

    // --- ordinary pipelines ---

    static List<String> expensiveNames(List<Item> items, int limit) {
        return items.stream()
                .filter(i -> i.getPrice() > limit)
                .map(Item::getName)
                .collect(Collectors.toList());
    }

    static List<Item> cheapestFirst(List<Item> items) {
        List<Item> sorted = items.stream()
                .sorted(Comparator.comparingInt(Item::getPrice))
                .collect(Collectors.toList());
        return sorted;
    }

    static Map<String, List<String>> namesByCategory(List<Item> items) {
        Map<String, List<String>> result = items.stream()
                .collect(Collectors.groupingBy(Item::getCategory, TreeMap::new,
                        Collectors.mapping(Item::getName, Collectors.toList())));
        return result;
    }

    static List<Item> allItems(List<Order> orders) {
        return orders.stream()
                .flatMap(o -> o.getItems().stream())
                .collect(Collectors.toList());
    }

    static int totalRevenue(List<Order> orders) {
        int sum = orders.stream().mapToInt(Order::total).sum();
        return sum;
    }

    // --- rule cases ---

    // 1. stream over the same list inside a loop over it: O(n^2)
    static int countCheaper(List<Item> items) {
        int pairs = 0;
        for (Item a : items) {
            long cheaper = items.stream().filter(b -> b.getPrice() < a.getPrice()).count();
            pairs += (int) cheaper;
        }
        return pairs;
    }

    // 2. collect(...).size() instead of count()
    static int countPaper(List<Item> items) {
        int n = items.stream().filter(i -> i.getCategory().equals("paper")).collect(Collectors.toList()).size();
        return n;
    }

    // 3. filter(...).findFirst().isPresent() instead of anyMatch(...)
    static boolean hasTech(List<Item> items) {
        boolean found = items.stream().filter(i -> i.getCategory().equals("tech")).findFirst().isPresent();
        return found;
    }

    // 4. sorted(...).findFirst() instead of min(...)
    static Optional<Item> cheapest(List<Item> items) {
        return items.stream().sorted(Comparator.comparingInt(Item::getPrice)).findFirst();
    }

    // 5. forEach that fills an outer collection instead of collect(...)
    static List<String> upperNames(List<Item> items) {
        List<String> out = new ArrayList<>();
        items.stream().map(Item::getName).forEach(n -> out.add(n.toUpperCase()));
        return out;
    }

    // 6. a loop that could be a stream
    static List<String> paperNames(List<Item> items) {
        List<String> names = new ArrayList<>();
        for (Item it : items) {
            if (it.getCategory().equals("paper")) {
                names.add(it.getName());
            }
        }
        return names;
    }

    public static void main(String[] args) {
        List<Order> orders = buildOrders();
        List<Item> items = allItems(orders);
        System.out.println("expensive: " + expensiveNames(items, 10));
        System.out.println("by price: " + cheapestFirst(items).stream().map(Item::getName).collect(Collectors.toList()));
        System.out.println("by category: " + namesByCategory(items));
        System.out.println("revenue: " + totalRevenue(orders));
        System.out.println("cheaper pairs: " + countCheaper(items));
        System.out.println("paper: " + countPaper(items));
        System.out.println("has tech: " + hasTech(items));
        System.out.println("cheapest: " + cheapest(items).get().getName());
        System.out.println("upper: " + upperNames(items));
        System.out.println("paper names: " + paperNames(items));
    }
}
