/** Files of the built-in demo project shown in the file tree. */

export const DEMO = `import java.util.*;

public class Demo {
    public static int sumPairs(List<Integer> items) {
        int total = 0;
        for (Integer a : items) {
            for (Integer b : items) {
                if (a < b) {
                    total += a * b;
                }
            }
        }
        return total;
    }

    public static void main(String[] args) {
        List<Integer> xs = Arrays.asList(1, 2, 3, 4);
        System.out.println("pairs = " + sumPairs(xs));
    }
}
`;

/* the same monoliths as in /test_monoliths (copied so the frontend image builds on its own) */
const raw = import.meta.glob('../examples/*.java', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

export const EXAMPLES: { name: string; code: string }[] = Object.entries(raw)
  .map(([path, code]) => ({ name: path.split('/').pop()!, code }))
  .sort((a, b) => a.name.localeCompare(b.name));
