import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class AuditLog {
    private final List<String> auditLog = new LinkedList<>();
    private int auditSeq = 0;

    void audit(String event) {
        auditSeq++;
        auditLog.add(String.format(Locale.ROOT, "#%03d %s", auditSeq, event));
    }

    void printAudit(int limit) {
        System.out.println("=== Журнал (" + auditLog.size() + " событий) ===");
        Iterator<String> it = auditLog.iterator();
        int shown = 0;
        while (it.hasNext() && shown < limit) {
            System.out.println("  " + it.next());
            shown++;
        }
        if (auditLog.size() > limit) {
            System.out.println("  … ещё " + (auditLog.size() - limit));
        }
    }
}
