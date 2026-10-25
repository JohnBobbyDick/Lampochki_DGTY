import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class Helpers {
    static double applyDiscount(double amount, int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("Скидка " + percent + "%");
        }
        return amount * (100 - percent) / 100.0;
    }

    static double round2(double value) {
        return Math.round(value * 100) / 100.0;
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

    static int[] histogram(Collection<Product> items, int buckets, double maxPrice) {
        int[] counts = new int[buckets];
        Arrays.fill(counts, 0);
        for (Product p : items) {
            int b = (int) (p.price() / maxPrice * buckets);
            counts[Math.min(b, buckets - 1)]++;
        }
        return counts;
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
        return quantity == 0 ? "none" : quantity < Warehouse.LOW_STOCK ? "low" : quantity < 50 ? "ok" : "high";
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
}
