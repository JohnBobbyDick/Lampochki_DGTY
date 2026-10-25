import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class Parser {
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
        String[] f = Parser.parseFields(lineNo, line, 6);
        Category category;
        try {
            category = Category.fromCode(f[3]);
        } catch (IllegalArgumentException e) {
            throw new InvalidRecordException(lineNo, e.getMessage());
        }
        return new Product(f[1], f[2], category, Parser.parseMoney(lineNo, f[4]), Parser.parseCount(lineNo, f[5]));
    }

    static Customer parseCustomer(int lineNo, String line) throws InvalidRecordException {
        String[] f = Parser.parseFields(lineNo, line, 5);
        boolean vip = Boolean.parseBoolean(f[4]);
        return new Customer(f[1], f[2], f[3], vip);
    }

    static Order parseOrder(int lineNo, String line) throws InvalidRecordException {
        String[] f = Parser.parseFields(lineNo, line, 5);
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
            order.addLine(new OrderLine(kv[0].trim(), Parser.parseCount(lineNo, kv[1].trim())));
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
            Parser.warn("stdin недоступен: " + e.getMessage());
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

    static void warn(String message) {
        Warehouse.warnings++;
        System.err.println("WARN: " + message);
    }
}
