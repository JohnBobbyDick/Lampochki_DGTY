import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class Printer {
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
}
