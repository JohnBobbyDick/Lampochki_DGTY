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

export const DEMO_PY = `def sum_pairs(items: list[int]) -> int:
    total = 0
    for a in items:
        for b in items:
            if a < b:
                total += a * b
    return total

def main():
    xs = [1, 2, 3, 4]
    print(f"pairs = {sum_pairs(xs)}")

if __name__ == '__main__':
    main()
`;

const rawJava = import.meta.glob('../examples/*.java', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
const rawPy = import.meta.glob('../examples/*.py', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

export const EXAMPLES: { name: string; code: string }[] = [
  ...Object.entries(rawJava).map(([path, code]) => ({ name: path.split('/').pop()!, code })),
  ...Object.entries(rawPy).map(([path, code]) => ({ name: path.split('/').pop()!, code })),
].sort((a, b) => a.name.localeCompare(b.name));
