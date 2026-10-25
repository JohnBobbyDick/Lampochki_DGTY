import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class Analyzer {
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

    static long checksum(String text) {
        long h = 1125899906842597L;
        for (int i = 0; i < text.length(); i++) {
            h = 31 * h + text.charAt(i);
            h ^= (h >>> 7);
        }
        return h & 0xFFFFFFL;
    }
}
