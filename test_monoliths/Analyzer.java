import java.util.*;

/**
 * Analyzer monolith — demonstrates O(n²) defect with nested loops.
 * This is a test monolith for the Java Blueprints hackathon.
 */
public class Analyzer {

    // Inner class to represent an Item
    static class Item {
        private String id;
        private String name;
        private int value;

        public Item(String id, String name, int value) {
            this.id = id;
            this.name = name;
            this.value = value;
        }

        public String getId() {
            return id;
        }

        public String getName() {
            return name;
        }

        public int getValue() {
            return value;
        }

        public void setValue(int value) {
            this.value = value;
        }

        @Override
        public String toString() {
            return "Item{id='" + id + "', name='" + name + "', value=" + value + "}";
        }
    }

    // O(n²) — defect: nested loops over the same collection
    public static List<Item> mergeItems(List<Item> items) {
        List<Item> result = new ArrayList<>();
        for (Item a : items) {
            for (Item b : items) {
                if (a.getId().equals(b.getId()) && a != b) {
                    a.setValue(a.getValue() + b.getValue());
                }
            }
            result.add(a);
        }
        return result;
    }

    // O(n) — simple linear search
    public static Item findByName(List<Item> items, String name) {
        for (Item item : items) {
            if (item.getName().equals(name)) {
                return item;
            }
        }
        return null;
    }

    // O(n²) — bubble sort
    public static void sortByValue(List<Item> items) {
        for (int i = 0; i < items.size(); i++) {
            for (int j = 0; j < items.size() - 1; j++) {
                if (items.get(j).getValue() > items.get(j + 1).getValue()) {
                    Item temp = items.get(j);
                    items.set(j, items.get(j + 1));
                    items.set(j + 1, temp);
                }
            }
        }
    }

    // Prints report — mixing I/O with logic (SRP violation)
    public static void printReport(List<Item> items) {
        System.out.println("=== Item Report ===");
        int total = 0;
        for (Item item : items) {
            System.out.println(item);
            total += item.getValue();
        }
        System.out.println("Total value: " + total);
        System.out.println("Item count: " + items.size());
    }

    // Empty catch block — defect
    public static int parseValue(String input) {
        try {
            return Integer.parseInt(input);
        } catch (NumberFormatException e) {
            // Empty catch block — bad practice!
        }
        return 0;
    }

    public static void main(String[] args) {
        List<Item> items = new ArrayList<>();
        items.add(new Item("1", "Apple", 10));
        items.add(new Item("2", "Banana", 20));
        items.add(new Item("1", "Apple Duplicate", 5));
        items.add(new Item("3", "Cherry", 15));
        items.add(new Item("2", "Banana Duplicate", 8));

        System.out.println("Before merge:");
        printReport(items);

        List<Item> merged = mergeItems(items);

        System.out.println("\nAfter merge:");
        printReport(merged);

        sortByValue(merged);
        System.out.println("\nSorted by value:");
        printReport(merged);

        Item found = findByName(merged, "Cherry");
        if (found != null) {
            System.out.println("\nFound: " + found);
        }

        int val = parseValue("not_a_number");
        System.out.println("Parsed value: " + val);
    }
}
