import java.util.*;

/**
 * Store monolith — demonstrates collections (HashMap, ArrayList), 
 * exceptions, and multiple responsibilities.
 */
public class Store {

    private Map<String, List<String>> inventory;
    private Map<String, Double> prices;
    private List<String> transactionLog;

    public Store() {
        inventory = new HashMap<>();
        prices = new HashMap<>();
        transactionLog = new ArrayList<>();
    }

    // Add product to inventory
    public void addProduct(String category, String product, double price) {
        if (!inventory.containsKey(category)) {
            inventory.put(category, new ArrayList<>());
        }
        inventory.get(category).add(product);
        prices.put(product, price);
        logTransaction("Added: " + product + " ($" + price + ") to " + category);
    }

    // Remove product — throws exception if not found
    public void removeProduct(String product) throws IllegalArgumentException {
        boolean found = false;
        for (Map.Entry<String, List<String>> entry : inventory.entrySet()) {
            if (entry.getValue().remove(product)) {
                found = true;
                break;
            }
        }
        if (!found) {
            throw new IllegalArgumentException("Product not found: " + product);
        }
        prices.remove(product);
        logTransaction("Removed: " + product);
    }

    // Find products by category — O(1) lookup
    public List<String> getProductsByCategory(String category) {
        List<String> products = inventory.get(category);
        if (products == null) {
            return Collections.emptyList();
        }
        return Collections.unmodifiableList(products);
    }

    // Search product across all categories — O(n*m)
    public String findProductCategory(String product) {
        for (Map.Entry<String, List<String>> entry : inventory.entrySet()) {
            for (String p : entry.getValue()) {
                if (p.equals(product)) {
                    return entry.getKey();
                }
            }
        }
        return null;
    }

    // Calculate total inventory value — mixes calculation with formatting
    public void printInventoryReport() {
        System.out.println("=== Inventory Report ===");
        double totalValue = 0;
        int totalItems = 0;

        for (Map.Entry<String, List<String>> entry : inventory.entrySet()) {
            System.out.println("Category: " + entry.getKey());
            for (String product : entry.getValue()) {
                double price = prices.getOrDefault(product, 0.0);
                System.out.println("  - " + product + ": $" + String.format("%.2f", price));
                totalValue += price;
                totalItems++;
            }
        }

        System.out.println("---");
        System.out.println("Total items: " + totalItems);
        System.out.println("Total value: $" + String.format("%.2f", totalValue));
    }

    // Get most expensive product — O(n)
    public String getMostExpensive() {
        String mostExpensive = null;
        double maxPrice = -1;
        for (Map.Entry<String, Double> entry : prices.entrySet()) {
            if (entry.getValue() > maxPrice) {
                maxPrice = entry.getValue();
                mostExpensive = entry.getKey();
            }
        }
        return mostExpensive;
    }

    // Logging mixed with business logic
    private void logTransaction(String message) {
        String timestamp = new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new Date());
        String logEntry = "[" + timestamp + "] " + message;
        transactionLog.add(logEntry);
        System.out.println("LOG: " + logEntry);
    }

    // Print all logs
    public void printTransactionLog() {
        System.out.println("=== Transaction Log ===");
        for (String log : transactionLog) {
            System.out.println(log);
        }
    }

    // Apply discount with exception handling
    public void applyDiscount(String product, double discountPercent) {
        try {
            if (discountPercent < 0 || discountPercent > 100) {
                throw new IllegalArgumentException("Invalid discount: " + discountPercent);
            }
            Double currentPrice = prices.get(product);
            if (currentPrice == null) {
                throw new NoSuchElementException("Product not found: " + product);
            }
            double newPrice = currentPrice * (1 - discountPercent / 100);
            prices.put(product, newPrice);
            logTransaction("Discount " + discountPercent + "% on " + product + ": $" + 
                          String.format("%.2f", currentPrice) + " -> $" + String.format("%.2f", newPrice));
        } catch (IllegalArgumentException e) {
            System.err.println("Error: " + e.getMessage());
        } catch (NoSuchElementException e) {
            System.err.println("Error: " + e.getMessage());
        }
    }

    public static void main(String[] args) {
        Store store = new Store();

        store.addProduct("Fruits", "Apple", 1.50);
        store.addProduct("Fruits", "Banana", 0.75);
        store.addProduct("Dairy", "Milk", 2.99);
        store.addProduct("Dairy", "Cheese", 5.49);
        store.addProduct("Bakery", "Bread", 3.25);

        store.printInventoryReport();

        store.applyDiscount("Apple", 20);
        store.applyDiscount("Cheese", 10);

        System.out.println("\nMost expensive: " + store.getMostExpensive());

        String category = store.findProductCategory("Milk");
        System.out.println("Milk is in: " + category);

        try {
            store.removeProduct("NonExistent");
        } catch (IllegalArgumentException e) {
            System.out.println("Caught: " + e.getMessage());
        }

        store.printInventoryReport();
        store.printTransactionLog();
    }
}
