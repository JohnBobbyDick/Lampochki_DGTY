import java.util.*;
import java.util.Scanner;

/**
 * Logger monolith — three responsibilities mixed together:
 * 1) Parsing log entries
 * 2) Analyzing/filtering logs
 * 3) Formatting and printing output
 * 
 * Ideal for decomposition into Parser.java, Analyzer.java, Printer.java
 */
public class Logger {

    // Log entry class
    static class LogEntry {
        String level;      // INFO, WARN, ERROR
        String timestamp;
        String source;
        String message;

        LogEntry(String level, String timestamp, String source, String message) {
            this.level = level;
            this.timestamp = timestamp;
            this.source = source;
            this.message = message;
        }

        @Override
        public String toString() {
            return "[" + level + "] " + timestamp + " [" + source + "] " + message;
        }
    }

    // === PARSING RESPONSIBILITY ===

    // Parse a single log line: "LEVEL|timestamp|source|message"
    public static LogEntry parseLine(String line) {
        if (line == null || line.isEmpty()) {
            throw new IllegalArgumentException("Empty log line");
        }
        String[] parts = line.split("\\|");
        if (parts.length < 4) {
            throw new IllegalArgumentException("Invalid log format: " + line);
        }
        return new LogEntry(
            parts[0].trim(),
            parts[1].trim(),
            parts[2].trim(),
            parts[3].trim()
        );
    }

    // Parse multiple log lines
    public static List<LogEntry> parseAll(String[] lines) {
        List<LogEntry> entries = new ArrayList<>();
        for (String line : lines) {
            try {
                entries.add(parseLine(line));
            } catch (IllegalArgumentException e) {
                System.err.println("Skipping invalid line: " + e.getMessage());
            }
        }
        return entries;
    }

    // === ANALYSIS RESPONSIBILITY ===

    // Filter by level
    public static List<LogEntry> filterByLevel(List<LogEntry> entries, String level) {
        List<LogEntry> filtered = new ArrayList<>();
        for (LogEntry entry : entries) {
            if (entry.level.equalsIgnoreCase(level)) {
                filtered.add(entry);
            }
        }
        return filtered;
    }

    // Filter by source
    public static List<LogEntry> filterBySource(List<LogEntry> entries, String source) {
        List<LogEntry> filtered = new ArrayList<>();
        for (LogEntry entry : entries) {
            if (entry.source.equalsIgnoreCase(source)) {
                filtered.add(entry);
            }
        }
        return filtered;
    }

    // Count entries by level — O(n)
    public static Map<String, Integer> countByLevel(List<LogEntry> entries) {
        Map<String, Integer> counts = new TreeMap<>();
        for (LogEntry entry : entries) {
            counts.put(entry.level, counts.getOrDefault(entry.level, 0) + 1);
        }
        return counts;
    }

    // Find entries containing keyword — O(n*m) where m = message length
    public static List<LogEntry> searchByKeyword(List<LogEntry> entries, String keyword) {
        List<LogEntry> results = new ArrayList<>();
        for (LogEntry entry : entries) {
            if (entry.message.toLowerCase().contains(keyword.toLowerCase())) {
                results.add(entry);
            }
        }
        return results;
    }

    // Find duplicate messages — O(n²) defect! Should use Set
    public static List<LogEntry> findDuplicates(List<LogEntry> entries) {
        List<LogEntry> duplicates = new ArrayList<>();
        for (int i = 0; i < entries.size(); i++) {
            for (int j = i + 1; j < entries.size(); j++) {
                if (entries.get(i).message.equals(entries.get(j).message)) {
                    if (!duplicates.contains(entries.get(i))) {
                        duplicates.add(entries.get(i));
                    }
                    if (!duplicates.contains(entries.get(j))) {
                        duplicates.add(entries.get(j));
                    }
                }
            }
        }
        return duplicates;
    }

    // === FORMATTING/PRINTING RESPONSIBILITY ===

    // Print summary report
    public static void printSummary(List<LogEntry> entries) {
        System.out.println("=== Log Summary ===");
        System.out.println("Total entries: " + entries.size());

        Map<String, Integer> counts = countByLevel(entries);
        for (Map.Entry<String, Integer> entry : counts.entrySet()) {
            System.out.println("  " + entry.getKey() + ": " + entry.getValue());
        }
    }

    // Print entries in table format
    public static void printTable(List<LogEntry> entries) {
        System.out.println("+---------+---------------------+------------+---------------------------+");
        System.out.println("| Level   | Timestamp           | Source     | Message                   |");
        System.out.println("+---------+---------------------+------------+---------------------------+");
        for (LogEntry entry : entries) {
            System.out.printf("| %-7s | %-19s | %-10s | %-25s |%n",
                entry.level, entry.timestamp, entry.source, 
                entry.message.length() > 25 ? entry.message.substring(0, 22) + "..." : entry.message);
        }
        System.out.println("+---------+---------------------+------------+---------------------------+");
    }

    // Print filtered report
    public static void printFilteredReport(List<LogEntry> entries, String level) {
        List<LogEntry> filtered = filterByLevel(entries, level);
        System.out.println("\n=== " + level + " Entries ===");
        if (filtered.isEmpty()) {
            System.out.println("No entries found.");
        } else {
            for (LogEntry entry : filtered) {
                System.out.println(entry);
            }
        }
    }

    public static void main(String[] args) {
        String[] rawLogs = {
            "INFO|2024-01-15 10:00:01|AuthService|User login successful",
            "WARN|2024-01-15 10:00:05|DBService|Connection pool running low",
            "ERROR|2024-01-15 10:00:10|PaymentService|Payment failed: timeout",
            "INFO|2024-01-15 10:00:12|AuthService|User login successful",
            "INFO|2024-01-15 10:00:15|APIService|Request processed in 250ms",
            "WARN|2024-01-15 10:00:20|DBService|Slow query detected: 5000ms",
            "ERROR|2024-01-15 10:00:25|AuthService|Invalid token received",
            "INFO|2024-01-15 10:00:30|CacheService|Cache hit ratio: 85%",
            "ERROR|2024-01-15 10:00:35|PaymentService|Payment failed: timeout",
            "INFO|2024-01-15 10:00:40|APIService|Health check passed"
        };

        // Parse
        List<LogEntry> entries = parseAll(rawLogs);

        // Summary
        printSummary(entries);

        // Table view
        System.out.println();
        printTable(entries);

        // Filtered views
        printFilteredReport(entries, "ERROR");
        printFilteredReport(entries, "WARN");

        // Search
        System.out.println("\n=== Search: 'timeout' ===");
        List<LogEntry> searchResults = searchByKeyword(entries, "timeout");
        for (LogEntry entry : searchResults) {
            System.out.println(entry);
        }

        // Duplicates
        System.out.println("\n=== Duplicate Messages ===");
        List<LogEntry> duplicates = findDuplicates(entries);
        for (LogEntry entry : duplicates) {
            System.out.println(entry);
        }
    }
}
