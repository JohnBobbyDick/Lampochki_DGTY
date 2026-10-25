import java.util.*;
import java.util.function.*;

sealed interface Shape permits Circle, Square, Base {}

record Circle(double r) implements Shape {
    Circle {
        if (r < 0) throw new IllegalArgumentException("r");
    }

    double area() { return Math.PI * r * r; }
}

final record Square(double side) implements Shape {}

non-sealed class Base implements Shape {}

public class Modern {
    record Pair<A, B>(A first, B second) {}

    enum Op { ADD, SUB }

    static String describe(Object o) {
        if (o instanceof Circle c && c.r() > 1) {
            return "big circle " + c.r();
        }
        return o instanceof Square ? "square" : "other";
    }

    static int apply(Op op, int a, int b) {
        return switch (op) {
            case ADD -> a + b;
            case SUB -> {
                int r = a - b;
                yield r;
            }
        };
    }

    static String day(int d) {
        String kind = switch (d) {
            case 1, 7 -> "weekend";
            case 2, 3, 4, 5, 6 -> "workday";
            default -> throw new IllegalStateException("bad " + d);
        };
        switch (d) {
            case 1 -> System.out.println("sun");
            case 2 -> { System.out.println("mon"); }
            default -> {}
        }
        int old = switch (d) { case 1: yield 10; default: yield 0; };
        return kind + old;
    }

    public static void main(String[] args) {
        var text = """
            Привет,
              "мир"\s
            """;
        var list = new ArrayList<String>();
        list.add("x");
        BiFunction<Integer, Integer, Integer> f = (var x, var y) -> x + y;
        record Local(int v) {}
        System.out.print(text);
        System.out.println(describe(new Circle(2)) + " " + describe(new Square(1)) + " " + new Local(3).v());
        System.out.println(apply(Op.ADD, 1, 2) + " " + apply(Op.SUB, 5, 3) + " " + day(1) + " " + day(3));
        System.out.println(new Pair<>(1, "a").first() + list.get(0) + f.apply(2, 3));
    }
}
