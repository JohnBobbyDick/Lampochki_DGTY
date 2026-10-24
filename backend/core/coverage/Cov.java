/* Coverage counters (Java Blueprints). Template: instrument.cov_java() fills in the slot count
 * and prepends the user's package line. Counters are int32 little-endian, slot s at byte s*4,
 * in the file named by -Djb.cov (memory-mapped, so data survives kill); in memory otherwise. */
final class __Cov {
    private static final int SLOTS = /*SLOTS*/0;
    private static final java.nio.ByteBuffer B = open();

    private __Cov() {}

    private static java.nio.ByteBuffer open() {
        String f = System.getProperty("jb.cov");
        if (f != null) {
            try (java.nio.channels.FileChannel ch = java.nio.channels.FileChannel.open(
                    java.nio.file.Paths.get(f),
                    java.nio.file.StandardOpenOption.READ, java.nio.file.StandardOpenOption.WRITE)) {
                return ch.map(java.nio.channels.FileChannel.MapMode.READ_WRITE, 0, SLOTS * 4L)
                        .order(java.nio.ByteOrder.LITTLE_ENDIAN);
            } catch (Throwable ignored) {
                // fall through: count in memory
            }
        }
        return java.nio.ByteBuffer.allocate(SLOTS * 4).order(java.nio.ByteOrder.LITTLE_ENDIAN);
    }

    static void h(int s) {
        int i = s << 2;
        B.putInt(i, B.getInt(i) + 1);
    }

    /** Decision / condition: true -> s, false -> s+1. */
    static boolean c(int s, boolean v) {
        h(v ? s : s + 1);
        return v;
    }

    /** op: 0 <, 1 <=, 2 >, 3 >=, 4 ==, 5 !=. For 0-3 records a<b / a==b / a>b in s / s+1 / s+2. */
    static boolean r(int s, int op, long a, long b) {
        if (op >= 4) {
            h(a == b ? s : s + 1);
        } else {
            h(a < b ? s : a == b ? s + 1 : s + 2);
        }
        switch (op) {
            case 0: return a < b;
            case 1: return a <= b;
            case 2: return a > b;
            case 3: return a >= b;
            case 4: return a == b;
            default: return a != b;
        }
    }

    static boolean r(int s, int op, double a, double b) {
        if (op >= 4) {
            h(a == b ? s : s + 1);
        } else if (a < b) {
            h(s);
        } else if (a == b) {
            h(s + 1);
        } else if (a > b) {
            h(s + 2);
        }
        switch (op) {
            case 0: return a < b;
            case 1: return a <= b;
            case 2: return a > b;
            case 3: return a >= b;
            case 4: return a == b;
            default: return a != b;
        }
    }

    /** float operands compare as float in Java (int == float is not exact as double). */
    static boolean r(int s, int op, float a, float b) {
        if (op >= 4) {
            h(a == b ? s : s + 1);
        } else if (a < b) {
            h(s);
        } else if (a == b) {
            h(s + 1);
        } else if (a > b) {
            h(s + 2);
        }
        switch (op) {
            case 0: return a < b;
            case 1: return a <= b;
            case 2: return a > b;
            case 3: return a >= b;
            case 4: return a == b;
            default: return a != b;
        }
    }

    static boolean r(int s, int op, boolean a, boolean b) {
        h(a == b ? s : s + 1);
        return op == 4 ? a == b : a != b;
    }

    static boolean r(int s, int op, Object a, Object b) {
        h(a == b ? s : s + 1);
        return op == 4 ? a == b : a != b;
    }

    /** Loop condition: records "body never ran" (s+1) when the loop exits without entering. */
    static boolean lp(int s, boolean entered, boolean v) {
        if (!v && !entered) {
            h(s + 1);
        }
        return v;
    }
}
