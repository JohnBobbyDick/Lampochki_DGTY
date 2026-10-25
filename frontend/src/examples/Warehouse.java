import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.io.StringReader;
import java.io.UnsupportedEncodingException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

/**
 * Warehouse — a ~1000-line monolith for Java Blueprints.
 *
 * One class does everything: parsing the input, analysing stock and orders, "optimising"
 * (deduplication, restocking plan) and printing reports. It covers the mandatory Java scope of the
 * case (language and java.lang, console I/O, java.util collections, exceptions) plus enums,
 * generics, lambdas and the Stream API. The output is deterministic, so a refactoring can be checked
 * by comparing it before and after.
 *
 * Input: CSV-like lines on stdin (if any is waiting), otherwise the built-in DEFAULT_DATA.
 *   P;<sku>;<name>;<category>;<price>;<quantity>
 *   C;<id>;<name>;<city>;<vip>
 *   O;<id>;<customerId>;<status>;<sku>:<qty>,<sku>:<qty>...
 */

// ── Domain ──────────────────────────────────────────────────────────────────────

interface Identifiable {
    String id();
}

interface Priced {
    double price();

    default String currency() {
        return "RUB";
    }

    default String formatted() {
        return String.format(Locale.ROOT, "%.2f %s", price(), currency());
    }
}

abstract class Entity implements Identifiable {
    private static int created = 0;
    protected final String id;

    protected Entity(String id) {
        if (id == null || id.isEmpty()) {
            throw new IllegalArgumentException("Пустой идентификатор");
        }
        this.id = id;
        created++;
    }

    public String id() {
        return id;
    }

    static int createdCount() {
        return created;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (o == null || getClass() != o.getClass()) {
            return false;
        }
        return id.equals(((Entity) o).id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}

enum Category {
    FOOD("Продукты", 0.10),
    TECH("Техника", 0.20),
    BOOKS("Книги", 0.0),
    HOME("Дом", 0.15);

    private final String title;
    private final double vat;

    Category(String title, double vat) {
        this.title = title;
        this.vat = vat;
    }

    String title() {
        return title;
    }

    double withVat(double net) {
        return net * (1 + vat);
    }

    static Category fromCode(String code) {
        for (Category c : values()) {
            if (c.name().equalsIgnoreCase(code)) {
                return c;
            }
        }
        throw new IllegalArgumentException("Неизвестная категория: " + code);
    }
}

enum Status {
    NEW, PAID, SHIPPED, CANCELLED;

    boolean isFinal() {
        return this == SHIPPED || this == CANCELLED;
    }
}

class Product extends Entity implements Priced, Comparable<Product> {
    private final String name;
    private final Category category;
    private double price;
    private int quantity;

    Product(String sku, String name, Category category, double price, int quantity) {
        super(sku);
        this.name = name;
        this.category = category;
        this.price = price;
        this.quantity = quantity;
    }

    String name() {
        return name;
    }

    Category category() {
        return category;
    }

    public double price() {
        return price;
    }

    int quantity() {
        return quantity;
    }

    void changePrice(double newPrice) {
        if (newPrice <= 0) {
            throw new IllegalArgumentException("Цена должна быть положительной: " + newPrice);
        }
        price = newPrice;
    }

    void take(int amount) throws OutOfStockException {
        if (amount > quantity) {
            throw new OutOfStockException(id, amount, quantity);
        }
        quantity -= amount;
    }

    void put(int amount) {
        quantity += amount;
    }

    double stockValue() {
        return price * quantity;
    }

    @Override
    public int compareTo(Product other) {
        return id.compareTo(other.id);
    }

    @Override
    public String toString() {
        return id + " " + name + " (" + category.title() + ")";
    }
}

class Customer extends Entity {
    private final String name;
    private final String city;
    private final boolean vip;

    Customer(String id, String name, String city, boolean vip) {
        super(id);
        this.name = name;
        this.city = city;
        this.vip = vip;
    }

    String name() {
        return name;
    }

    String city() {
        return city;
    }

    boolean vip() {
        return vip;
    }
}

class OrderLine {
    final String sku;
    final int quantity;

    OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }
}

class Order extends Entity {
    private final String customerId;
    private Status status;
    private final List<OrderLine> lines = new ArrayList<>();

    Order(String id, String customerId, Status status) {
        super(id);
        this.customerId = customerId;
        this.status = status;
    }

    String customerId() {
        return customerId;
    }

    Status status() {
        return status;
    }

    void moveTo(Status next) {
        status = next;
    }

    List<OrderLine> lines() {
        return Collections.unmodifiableList(lines);
    }

    void addLine(OrderLine line) {
        lines.add(line);
    }
}

class Pair<A, B> {
    private final A first;
    private final B second;

    Pair(A first, B second) {
        this.first = first;
        this.second = second;
    }

    A first() {
        return first;
    }

    B second() {
        return second;
    }

    @Override
    public String toString() {
        return "(" + first + ", " + second + ")";
    }
}

// ── Exceptions ──────────────────────────────────────────────────────────────────

class InvalidRecordException extends Exception {
    private final int lineNumber;

    InvalidRecordException(int lineNumber, String message) {
        super("строка " + lineNumber + ": " + message);
        this.lineNumber = lineNumber;
    }

    int lineNumber() {
        return lineNumber;
    }
}

class OutOfStockException extends Exception {
    OutOfStockException(String sku, int wanted, int available) {
        super("Недостаточно " + sku + ": нужно " + wanted + ", есть " + available);
    }
}

class OrderRejectedException extends RuntimeException {
    OrderRejectedException(String orderId, Throwable cause) {
        super("Заказ " + orderId + " отклонён", cause);
    }
}

// ── The monolith ────────────────────────────────────────────────────────────────

public class Warehouse {

    static final String DEFAULT_DATA = String.join("\n",
            "# products: P;sku;name;category;price;quantity",
            "P;A100;Яблоки;food;89.90;120",
            "P;A101;Молоко;food;79.50;40",
            "P;A102;Хлеб;food;45.00;60",
            "P;A103;яблоки;food;95.00;10",
            "P;T200;Ноутбук;tech;84990.00;5",
            "P;T201;Наушники;tech;5990.00;25",
            "P;T202;Мышь;tech;1490.00;0",
            "P;B300;Java. Полное руководство;books;3200.00;12",
            "P;B301;Алгоритмы;books;2750.00;3",
            "P;H400;Лампа;home;1990.00;14",
            "P;H401;Плед;home;2490.00;9",
            "P;A100;Яблоки;food;89.90;30",
            "P;X999;Сломанная строка;food;abc;1",
            "# customers: C;id;name;city;vip",
            "C;U1;Анна;Москва;true",
            "C;U2;Борис;Казань;false",
            "C;U3;Вера;Москва;false",
            "C;U4;Глеб;Самара;true",
            "# orders: O;id;customer;status;sku:qty,...",
            "O;R1;U1;paid;A100:10,T201:1",
            "O;R2;U2;new;T200:1,B300:2",
            "O;R3;U3;shipped;A101:5,A102:2,H400:1",
            "O;R4;U1;new;T202:3",
            "O;R5;U4;paid;T200:10",
            "O;R6;U4;cancelled;B301:1",
            "O;R7;U2;paid;H401:2,A102:4,B301:1",
            "O;R8;U9;new;A100:1");

    static final int LOW_STOCK = 5;
    static int warnings = 0;

    private final Map<String, Product> products = new TreeMap<>();
    private final Map<String, Customer> customers = new LinkedHashMap<>();
    private final List<Order> orders = new ArrayList<>();
    private final List<String> auditLog = new LinkedList<>();
    private int auditSeq = 0;

    // ── audit trail (a self-contained part of the state) ─────────────────────────

    void audit(String event) {
        auditSeq++;
        auditLog.add(String.format(Locale.ROOT, "#%03d %s", auditSeq, event));
    }

    void printAudit(int limit) {
        System.out.println("=== Журнал (" + auditLog.size() + " событий) ===");
        Iterator<String> it = auditLog.iterator();
        int shown = 0;
        while (it.hasNext() && shown < limit) {
            System.out.println("  " + it.next());
            shown++;
        }
        if (auditLog.size() > limit) {
            System.out.println("  … ещё " + (auditLog.size() - limit));
        }
    }

    // ── loading ─────────────────────────────────────────────────────────────────

    void load(List<String> rows) {
        int lineNo = 0;
        for (String row : rows) {
            lineNo++;
            String line = row.trim();
            if (line.isEmpty() || line.startsWith("#")) {
                continue;
            }
            try {
                switch (line.charAt(0)) {
                    case 'P':
                        addProduct(parseProduct(lineNo, line));
                        break;
                    case 'C':
                        Customer c = parseCustomer(lineNo, line);
                        customers.put(c.id(), c);
                        audit("клиент " + c.id());
                        break;
                    case 'O':
                        orders.add(parseOrder(lineNo, line));
                        break;
                    default:
                        throw new InvalidRecordException(lineNo, "неизвестный тип записи '" + line.charAt(0) + "'");
                }
            } catch (InvalidRecordException e) {
                warn("пропущена " + e.getMessage());
            }
        }
    }

    void addProduct(Product p) {
        Product known = products.get(p.id());
        if (known != null) {
            known.put(p.quantity());
            audit("пополнение " + p.id() + " +" + p.quantity());
            return;
        }
        products.put(p.id(), p);
        audit("товар " + p.id());
    }

    // ── parsing (static: no state) ──────────────────────────────────────────────

    static String[] parseFields(int lineNo, String line, int expected) throws InvalidRecordException {
        String[] parts = line.split(";", -1);
        if (parts.length != expected) {
            throw new InvalidRecordException(lineNo, "ожидалось полей: " + expected + ", получено: " + parts.length);
        }
        for (int i = 0; i < parts.length; i++) {
            parts[i] = parts[i].trim();
        }
        return parts;
    }

    static double parseMoney(int lineNo, String text) throws InvalidRecordException {
        try {
            double value = Double.parseDouble(text);
            if (value < 0 || Double.isNaN(value)) {
                throw new InvalidRecordException(lineNo, "отрицательная цена " + text);
            }
            return Math.round(value * 100) / 100.0;
        } catch (NumberFormatException e) {
            throw new InvalidRecordException(lineNo, "не число: " + text);
        }
    }

    static int parseCount(int lineNo, String text) throws InvalidRecordException {
        try {
            int value = Integer.parseInt(text);
            if (value < 0) {
                throw new InvalidRecordException(lineNo, "отрицательное количество " + value);
            }
            return value;
        } catch (NumberFormatException e) {
            throw new InvalidRecordException(lineNo, "не целое: " + text);
        }
    }

    static Product parseProduct(int lineNo, String line) throws InvalidRecordException {
        String[] f = parseFields(lineNo, line, 6);
        Category category;
        try {
            category = Category.fromCode(f[3]);
        } catch (IllegalArgumentException e) {
            throw new InvalidRecordException(lineNo, e.getMessage());
        }
        return new Product(f[1], f[2], category, parseMoney(lineNo, f[4]), parseCount(lineNo, f[5]));
    }

    static Customer parseCustomer(int lineNo, String line) throws InvalidRecordException {
        String[] f = parseFields(lineNo, line, 5);
        boolean vip = Boolean.parseBoolean(f[4]);
        return new Customer(f[1], f[2], f[3], vip);
    }

    static Order parseOrder(int lineNo, String line) throws InvalidRecordException {
        String[] f = parseFields(lineNo, line, 5);
        Status status;
        try {
            status = Status.valueOf(f[3].toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException e) {
            throw new InvalidRecordException(lineNo, "статус " + f[3]);
        }
        Order order = new Order(f[1], f[2], status);
        for (String item : f[4].split(",")) {
            String[] kv = item.split(":");
            if (kv.length != 2) {
                throw new InvalidRecordException(lineNo, "позиция " + item);
            }
            order.addLine(new OrderLine(kv[0].trim(), parseCount(lineNo, kv[1].trim())));
        }
        return order;
    }

    static List<String> readInput(String fallback) {
        List<String> rows = new ArrayList<>();
        try {
            if (System.in.available() > 0) {
                BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
                String line;
                while ((line = in.readLine()) != null) {
                    rows.add(line);
                }
            }
        } catch (IOException e) {
            warn("stdin недоступен: " + e.getMessage());
        }
        if (rows.isEmpty()) {
            Scanner sc = new Scanner(fallback);
            while (sc.hasNextLine()) {
                rows.add(sc.nextLine());
            }
            sc.close();
        }
        return rows;
    }

    // ── validation ──────────────────────────────────────────────────────────────

    List<String> validateOrders() {
        List<String> problems = new ArrayList<>();
        for (Order o : orders) {
            if (!customers.containsKey(o.customerId())) {
                problems.add(o.id() + ": нет клиента " + o.customerId());
            }
            for (OrderLine line : o.lines()) {
                if (!products.containsKey(line.sku)) {
                    problems.add(o.id() + ": нет товара " + line.sku);
                } else if (line.quantity == 0) {
                    problems.add(o.id() + ": нулевое количество " + line.sku);
                }
            }
        }
        return problems;
    }

    static boolean isValidSku(String sku) {
        if (sku == null || sku.length() != 4) {
            return false;
        }
        char kind = sku.charAt(0);
        if (kind < 'A' || kind > 'Z') {
            return false;
        }
        for (int i = 1; i < sku.length(); i++) {
            if (!Character.isDigit(sku.charAt(i))) {
                return false;
            }
        }
        return true;
    }

    // ── order processing ────────────────────────────────────────────────────────

    double orderTotal(Order o) {
        double total = 0;
        for (OrderLine line : o.lines()) {
            Product p = products.get(line.sku);
            if (p == null) {
                continue;
            }
            total += p.category().withVat(p.price()) * line.quantity;
        }
        Customer c = customers.get(o.customerId());
        if (c != null && c.vip()) {
            total = applyDiscount(total, 5);
        }
        return round2(total);
    }

    static double applyDiscount(double amount, int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("Скидка " + percent + "%");
        }
        return amount * (100 - percent) / 100.0;
    }

    static double round2(double value) {
        return Math.round(value * 100) / 100.0;
    }

    void ship(Order o) throws OutOfStockException {
        if (o.status() != Status.PAID) {
            throw new IllegalStateException("Заказ " + o.id() + " в статусе " + o.status());
        }
        for (OrderLine line : o.lines()) {
            Product p = products.get(line.sku);
            if (p == null) {
                throw new OrderRejectedException(o.id(), new NoSuchElementException(line.sku));
            }
            p.take(line.quantity);
        }
        o.moveTo(Status.SHIPPED);
        audit("отгружен " + o.id());
    }

    Map<Status, Integer> shipPaidOrders() {
        Map<Status, Integer> result = new EnumMap<>(Status.class);
        for (Order o : orders) {
            if (o.status() != Status.PAID) {
                result.merge(o.status(), 1, Integer::sum);
                continue;
            }
            try {
                ship(o);
                result.merge(Status.SHIPPED, 1, Integer::sum);
            } catch (OutOfStockException e) {
                warn("заказ " + o.id() + ": " + e.getMessage());
                o.moveTo(Status.CANCELLED);
                result.merge(Status.CANCELLED, 1, Integer::sum);
            } catch (OrderRejectedException e) {
                warn(e.getMessage() + " (" + e.getCause().getMessage() + ")");
            } finally {
                audit("обработан " + o.id());
            }
        }
        return result;
    }

    // ── analysis ────────────────────────────────────────────────────────────────

    double totalStockValue() {
        double sum = 0;
        for (Product p : products.values()) {
            sum += p.stockValue();
        }
        return round2(sum);
    }

    List<Product> findLowStock() {
        List<Product> low = new ArrayList<>();
        for (Product p : products.values()) {
            if (p.quantity() < LOW_STOCK) {
                low.add(p);
            }
        }
        low.sort(Comparator.comparingInt(Product::quantity).thenComparing(Product::id));
        return low;
    }

    Map<Category, Double> valueByCategory() {
        Map<Category, Double> byCat = new TreeMap<>();
        for (Product p : products.values()) {
            byCat.put(p.category(), byCat.getOrDefault(p.category(), 0.0) + p.stockValue());
        }
        return byCat;
    }

    /** Pairs of products with the same name: compares every pair — O(n²). */
    static List<Pair<String, String>> findDuplicateNames(List<Product> items) {
        List<Pair<String, String>> pairs = new ArrayList<>();
        for (Product a : items) {
            for (Product b : items) {
                if (a.compareTo(b) < 0 && a.name().equalsIgnoreCase(b.name())) {
                    pairs.add(new Pair<>(a.id(), b.id()));
                }
            }
        }
        return pairs;
    }

    /** Customers who ordered the same product: nested loops over the orders. */
    List<String> findSharedPurchases() {
        List<String> shared = new ArrayList<>();
        for (int i = 0; i < orders.size(); i++) {
            for (int j = i + 1; j < orders.size(); j++) {
                Order a = orders.get(i);
                Order b = orders.get(j);
                if (a.customerId().equals(b.customerId())) {
                    continue;
                }
                for (OrderLine la : a.lines()) {
                    for (OrderLine lb : b.lines()) {
                        if (la.sku.equals(lb.sku)) {
                            String key = la.sku + ": " + a.customerId() + "+" + b.customerId();
                            if (!shared.contains(key)) {
                                shared.add(key);
                            }
                        }
                    }
                }
            }
        }
        Collections.sort(shared);
        return shared;
    }

    Map<String, Long> countOrdersByCity() {
        return orders.stream()
                .map(o -> customers.get(o.customerId()))
                .filter(Objects::nonNull)
                .collect(Collectors.groupingBy(Customer::city, TreeMap::new, Collectors.counting()));
    }

    Optional<Customer> findBestCustomer() {
        Map<String, Double> spent = new HashMap<>();
        for (Order o : orders) {
            if (o.status() == Status.CANCELLED) {
                continue;
            }
            spent.merge(o.customerId(), orderTotal(o), Double::sum);
        }
        return spent.entrySet().stream()
                .filter(e -> customers.containsKey(e.getKey()))
                .max(Map.Entry.<String, Double>comparingByValue().thenComparing(Map.Entry.comparingByKey()))
                .map(e -> customers.get(e.getKey()));
    }

    static <T extends Comparable<T>> T maxOf(Collection<T> items) {
        if (items.isEmpty()) {
            throw new NoSuchElementException("пустая коллекция");
        }
        Iterator<T> it = items.iterator();
        T best = it.next();
        while (it.hasNext()) {
            T next = it.next();
            if (next.compareTo(best) > 0) {
                best = next;
            }
        }
        return best;
    }

    static int sizeOf(Iterable<?> items) {
        int n = 0;
        for (Object ignored : items) {
            n++;
        }
        return n;
    }

    static String kindOf(Object value) {
        if (value instanceof Product) {
            return "товар " + ((Product) value).id();
        } else if (value instanceof Identifiable) {
            return "сущность " + ((Identifiable) value).id();
        } else if (value instanceof Number) {
            return "число " + ((Number) value).intValue();
        }
        return "строка «" + value + "»";
    }

    static int countMatching(Collection<Product> items, Predicate<Product> test) {
        int n = 0;
        for (Product p : items) {
            if (test.test(p)) {
                n++;
            }
        }
        return n;
    }

    static double average(double... values) {
        if (values.length == 0) {
            return 0;
        }
        double sum = 0;
        for (double v : values) {
            sum += v;
        }
        return sum / values.length;
    }

    static int[] histogram(Collection<Product> items, int buckets, double maxPrice) {
        int[] counts = new int[buckets];
        Arrays.fill(counts, 0);
        for (Product p : items) {
            int b = (int) (p.price() / maxPrice * buckets);
            counts[Math.min(b, buckets - 1)]++;
        }
        return counts;
    }

    // ── optimisation ────────────────────────────────────────────────────────────

    /** Restocking plan: how much to order so that every product reaches the target. */
    Map<String, Integer> planRestock(int target) {
        Map<String, Integer> plan = new TreeMap<>();
        for (Product p : products.values()) {
            int missing = target - p.quantity();
            if (missing > 0) {
                plan.put(p.id(), missing);
            }
        }
        return plan;
    }

    /** Products sorted by value, the most valuable first; at most *limit*. */
    List<Product> topByValue(int limit) {
        return products.values().stream()
                .sorted(Comparator.comparingDouble(Product::stockValue).reversed().thenComparing(Product::id))
                .limit(limit)
                .collect(Collectors.toList());
    }

    /** Raises prices of scarce products by *percent*: returns how many changed. */
    int repriceScarce(int percent) {
        int changed = 0;
        for (Product p : products.values()) {
            if (p.quantity() > 0 && p.quantity() < LOW_STOCK) {
                p.changePrice(round2(p.price() * (100 + percent) / 100.0));
                audit("цена " + p.id() + " -> " + formatMoney(p.price()));
                changed++;
            }
        }
        return changed;
    }

    /** Distinct categories of products that are out of stock. */
    Set<Category> categoriesWithGaps() {
        Set<Category> gaps = new TreeSet<>();
        for (Product p : products.values()) {
            if (p.quantity() == 0) {
                gaps.add(p.category());
            }
        }
        return gaps;
    }

    static long checksum(String text) {
        long h = 1125899906842597L;
        for (int i = 0; i < text.length(); i++) {
            h = 31 * h + text.charAt(i);
            h ^= (h >>> 7);
        }
        return h & 0xFFFFFFL;
    }

    // ── output ──────────────────────────────────────────────────────────────────

    static String formatMoney(double amount) {
        return String.format(Locale.ROOT, "%,.2f", amount).replace(',', ' ');
    }

    static String formatRow(String... cells) {
        StringBuilder sb = new StringBuilder();
        for (String cell : cells) {
            if (sb.length() > 0) {
                sb.append(" | ");
            }
            sb.append(cell);
        }
        return sb.toString();
    }

    static String formatBar(int count, int width) {
        String bar = "";
        for (int i = 0; i < Math.min(count, width); i++) {
            bar += "#";
        }
        return bar;
    }

    static void printHeader(String title) {
        System.out.println();
        System.out.println("=== " + title + " ===");
    }

    void printProducts() {
        printHeader("Товары (" + products.size() + ")");
        for (Product p : products.values()) {
            System.out.printf(Locale.ROOT, "%-5s %-26s %-9s %12s x %3d%n",
                    p.id(), p.name(), p.category().title(), formatMoney(p.price()), p.quantity());
        }
    }

    void printOrders() {
        printHeader("Заказы (" + orders.size() + ")");
        for (Order o : orders) {
            Customer c = customers.get(o.customerId());
            String who = c == null ? "?" : c.name();
            String flag = o.status().isFinal() ? "✓" : " ";
            System.out.println(formatRow(o.id(), who, o.status().name(), flag, formatMoney(orderTotal(o))));
        }
    }

    void printAnalysis() {
        printHeader("Анализ");
        System.out.println("Стоимость склада: " + formatMoney(totalStockValue()));
        Formatter f = new Formatter(new StringBuilder(), Locale.ROOT);
        for (Map.Entry<Category, Double> e : valueByCategory().entrySet()) {
            f.format("  %-9s %14s%n", e.getKey().title(), formatMoney(e.getValue()));
        }
        System.out.print(f.toString());
        f.close();

        List<Product> low = findLowStock();
        System.out.println("Заканчиваются: " + low.stream().map(Product::id).collect(Collectors.joining(", ")));
        System.out.println("Нет в наличии (категории): " + categoriesWithGaps());
        System.out.println("Дубликаты названий: " + findDuplicateNames(new ArrayList<>(products.values())));
        System.out.println("Общие покупки: " + findSharedPurchases());
        System.out.println("Заказы по городам: " + countOrdersByCity());
        Optional<Customer> best = findBestCustomer();
        System.out.println("Лучший клиент: " + best.map(Customer::name).orElse("—"));
        System.out.println("Последний артикул по алфавиту: " + maxOf(products.keySet()));
        int tech = countMatching(products.values(), p -> p.category() == Category.TECH);
        System.out.println("Техники: " + tech + ", средняя цена книг: "
                + formatMoney(average(products.values().stream()
                        .filter(p -> p.category() == Category.BOOKS)
                        .mapToDouble(Product::price)
                        .toArray())));
    }

    void printHistogram() {
        printHeader("Цены");
        double max = products.values().stream().mapToDouble(Product::price).max().orElse(1);
        int[] counts = histogram(products.values(), 4, max);
        for (int i = 0; i < counts.length; i++) {
            long lo = Math.round(max * i / counts.length);
            System.out.printf(Locale.ROOT, "%10d+ %s %d%n", lo, formatBar(counts[i], 20), counts[i]);
        }
    }

    void printPlan(Map<String, Integer> plan) {
        printHeader("План закупки");
        if (plan.isEmpty()) {
            System.out.println("закупка не нужна");
            return;
        }
        int total = 0;
        for (Map.Entry<String, Integer> e : plan.entrySet()) {
            Product p = products.get(e.getKey());
            System.out.println("  " + p + ": +" + e.getValue());
            total += e.getValue();
        }
        System.out.println("  всего единиц: " + total);
    }

    static void warn(String message) {
        warnings++;
        System.err.println("WARN: " + message);
    }

    // ── a small text "report language": label loops, do/while, switch on strings ────

    static String renderTemplate(String template, Map<String, String> vars) {
        StringBuilder out = new StringBuilder();
        int i = 0;
        scan:
        while (i < template.length()) {
            char ch = template.charAt(i);
            if (ch == '{') {
                int close = template.indexOf('}', i);
                if (close < 0) {
                    out.append(template.substring(i));
                    break scan;
                }
                String key = template.substring(i + 1, close);
                String value = vars.get(key);
                out.append(value != null ? value : "{" + key + "}");
                i = close + 1;
                continue;
            }
            out.append(ch);
            i++;
        }
        return out.toString();
    }

    static String describeLevel(String level) {
        String text;
        switch (level) {
            case "low":
                text = "мало";
                break;
            case "ok":
            case "normal":
                text = "достаточно";
                break;
            case "high":
                text = "много";
                break;
            default:
                text = "неизвестно";
        }
        return text;
    }

    static String stockLevel(int quantity) {
        return quantity == 0 ? "none" : quantity < LOW_STOCK ? "low" : quantity < 50 ? "ok" : "high";
    }

    static int digitsSum(int n) {
        int sum = 0;
        int x = Math.abs(n);
        do {
            sum += x % 10;
            x /= 10;
        } while (x > 0);
        return sum;
    }

    // ── entry point ─────────────────────────────────────────────────────────────

    public static void main(String[] args) throws UnsupportedEncodingException {
        PrintStream out = new PrintStream(System.out, true, StandardCharsets.UTF_8.name());
        System.setOut(out);

        Warehouse w = new Warehouse();
        List<String> rows = readInput(DEFAULT_DATA);
        w.load(rows);
        System.out.println("Загружено строк: " + rows.size() + ", сущностей: " + Entity.createdCount());

        List<String> problems = w.validateOrders();
        if (!problems.isEmpty()) {
            printHeader("Проблемы во входных данных");
            for (String p : problems) {
                System.out.println("  - " + p);
            }
        }

        w.printProducts();
        w.printOrders();

        printHeader("Отгрузка");
        Map<Status, Integer> shipped = w.shipPaidOrders();
        for (Status s : Status.values()) {
            System.out.println("  " + s + ": " + shipped.getOrDefault(s, 0));
        }

        w.printAnalysis();
        w.printHistogram();

        printHeader("Оптимизация");
        int repriced = w.repriceScarce(10);
        System.out.println("Подорожало товаров: " + repriced);
        w.printPlan(w.planRestock(20));
        System.out.println("Топ-3 по стоимости: " + w.topByValue(3).stream()
                .map(Product::id).collect(Collectors.toList()));

        printHeader("Отчёт");
        Map<String, String> vars = new HashMap<>(Map.of(
                "склад", formatMoney(w.totalStockValue()),
                "заказов", String.valueOf(w.orders.size())));
        System.out.println(renderTemplate("Склад: {склад}, заказов: {заказов}, {нет}", vars));
        for (String sku : List.of("A100", "T202", "B301")) {
            Product p = w.products.get(sku);
            String level = stockLevel(p.quantity());
            System.out.println("  " + sku + " — " + describeLevel(level) + " (" + level + ")");
        }
        Set<String> checked = new HashSet<>(Set.of("A100", "bad", "T2000"));
        int valid = 0;
        for (String sku : new TreeSet<>(checked)) {
            if (isValidSku(sku)) {
                valid++;
            }
        }
        System.out.println("Корректных артикулов: " + valid + " из " + checked.size());
        Object[] sample = {w.products.get("A100"), new Customer("U0", "Гость", "Москва", false), 42, "A100"};
        for (Object o : sample) {
            System.out.println("  " + kindOf(o));
        }
        System.out.println("Товаров: " + sizeOf(w.products.values()) + ", артикулов проверено: " + sizeOf(checked));

        int[] quantities = w.products.values().stream().mapToInt(Product::quantity).toArray();
        Arrays.sort(quantities);
        System.out.println("Остатки по возрастанию: " + Arrays.toString(quantities));
        Integer cached = 127;
        Integer same = 127;
        long big = (long) Integer.MAX_VALUE + quantities.length;
        System.out.println("Кэш Integer: " + (cached == same) + ", long: " + big
                + ", сумма цифр: " + digitsSum(-90210) + ", контрольная сумма: " + checksum(DEFAULT_DATA));

        try (BufferedReader r = new BufferedReader(new StringReader("первая\nвторая"))) {
            System.out.println("Первая строка шаблона: " + r.readLine());
        } catch (IOException e) {
            warn("шаблон: " + e.getMessage());
        }

        try {
            applyDiscount(100, 150);
        } catch (IllegalArgumentException | ArithmeticException e) {
            System.out.println("Ошибка скидки: " + e.getMessage());
        }

        w.printAudit(8);
        System.out.println();
        System.out.println("Предупреждений: " + warnings);
    }
}
