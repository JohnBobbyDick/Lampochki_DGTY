import java.util.*;

/**
 * Calculator monolith — demonstrates branching (if/else, switch),
 * recursion, and exception handling.
 */
public class Calculator {

    // Parse and evaluate expression — complex branching
    public static double evaluate(String expression) {
        expression = expression.trim();
        
        // Try to parse as a plain number first
        try {
            return Double.parseDouble(expression);
        } catch (NumberFormatException e) {
            // Not a plain number, continue parsing
        }

        // Find the operator with lowest precedence (rightmost + or -)
        int parenDepth = 0;
        int opIndex = -1;
        char opChar = ' ';

        for (int i = expression.length() - 1; i >= 0; i--) {
            char c = expression.charAt(i);
            if (c == ')') parenDepth++;
            else if (c == '(') parenDepth--;
            
            if (parenDepth == 0 && (c == '+' || c == '-') && i > 0) {
                opIndex = i;
                opChar = c;
                break;
            }
        }

        // If no +/- found, look for * or /
        if (opIndex == -1) {
            for (int i = expression.length() - 1; i >= 0; i--) {
                char c = expression.charAt(i);
                if (c == ')') parenDepth++;
                else if (c == '(') parenDepth--;
                
                if (parenDepth == 0 && (c == '*' || c == '/') && i > 0) {
                    opIndex = i;
                    opChar = c;
                    break;
                }
            }
        }

        if (opIndex != -1) {
            double left = evaluate(expression.substring(0, opIndex));
            double right = evaluate(expression.substring(opIndex + 1));
            
            switch (opChar) {
                case '+': return left + right;
                case '-': return left - right;
                case '*': return left * right;
                case '/':
                    if (right == 0) {
                        throw new ArithmeticException("Division by zero");
                    }
                    return left / right;
                default:
                    throw new IllegalArgumentException("Unknown operator: " + opChar);
            }
        }

        // Handle parentheses
        if (expression.startsWith("(") && expression.endsWith(")")) {
            return evaluate(expression.substring(1, expression.length() - 1));
        }

        throw new IllegalArgumentException("Invalid expression: " + expression);
    }

    // Factorial — recursive O(n)
    public static long factorial(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("Negative factorial: " + n);
        }
        if (n <= 1) {
            return 1;
        }
        return n * factorial(n - 1);
    }

    // Fibonacci — naive recursive O(2^n) — defect!
    public static long fibonacci(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("Negative fibonacci: " + n);
        }
        if (n <= 1) {
            return n;
        }
        return fibonacci(n - 1) + fibonacci(n - 2);
    }

    // Power — recursive O(log n) using fast exponentiation
    public static double power(double base, int exp) {
        if (exp < 0) {
            return 1.0 / power(base, -exp);
        }
        if (exp == 0) {
            return 1.0;
        }
        if (exp % 2 == 0) {
            double half = power(base, exp / 2);
            return half * half;
        } else {
            return base * power(base, exp - 1);
        }
    }

    // GCD — Euclidean algorithm O(log(min(a,b)))
    public static int gcd(int a, int b) {
        while (b != 0) {
            int temp = b;
            b = a % b;
            a = temp;
        }
        return a;
    }

    // Statistics calculator — multiple responsibilities
    public static void printStatistics(List<Integer> numbers) {
        if (numbers == null || numbers.isEmpty()) {
            System.out.println("No numbers provided");
            return;
        }

        // Calculate sum
        int sum = 0;
        for (int num : numbers) {
            sum += num;
        }

        // Calculate average
        double avg = (double) sum / numbers.size();

        // Find min and max
        int min = numbers.get(0);
        int max = numbers.get(0);
        for (int num : numbers) {
            if (num < min) min = num;
            if (num > max) max = num;
        }

        // Calculate variance
        double variance = 0;
        for (int num : numbers) {
            variance += (num - avg) * (num - avg);
        }
        variance /= numbers.size();

        // Print everything — mixing calculation and I/O
        System.out.println("=== Statistics ===");
        System.out.println("Count: " + numbers.size());
        System.out.println("Sum: " + sum);
        System.out.printf("Average: %.2f%n", avg);
        System.out.println("Min: " + min);
        System.out.println("Max: " + max);
        System.out.printf("Variance: %.2f%n", variance);
        System.out.printf("Std Dev: %.2f%n", Math.sqrt(variance));
    }

    public static void main(String[] args) {
        // Expression evaluation
        String[] expressions = {"2+3", "10-4*2", "100/5+3"};
        for (String expr : expressions) {
            try {
                System.out.println(expr + " = " + evaluate(expr));
            } catch (Exception e) {
                System.out.println(expr + " -> Error: " + e.getMessage());
            }
        }

        // Factorial
        for (int i = 0; i <= 10; i++) {
            System.out.println(i + "! = " + factorial(i));
        }

        // Fibonacci
        System.out.println("Fibonacci sequence:");
        for (int i = 0; i <= 15; i++) {
            System.out.print(fibonacci(i) + " ");
        }
        System.out.println();

        // Power
        System.out.println("2^10 = " + power(2, 10));

        // GCD
        System.out.println("GCD(48, 18) = " + gcd(48, 18));

        // Statistics
        List<Integer> numbers = new ArrayList<>(Arrays.asList(5, 12, 3, 8, 21, 7, 15, 1, 9, 18));
        printStatistics(numbers);
    }
}
