// DumpFuncs.java - decompile every (or matching) function to C, headless.
// Usage: -postScript DumpFuncs.java <outfile> [nameFilter]
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import java.io.*;

public class DumpFuncs extends GhidraScript {
    public void run() throws Exception {
        String[] a = getScriptArgs();
        String out = a.length > 0 ? a[0] : "decomp.txt";
        String filt = a.length > 1 ? a[1] : null;
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        PrintWriter w = new PrintWriter(new FileWriter(out));
        FunctionManager fm = currentProgram.getFunctionManager();
        int n = 0;
        for (Function f : fm.getFunctions(true)) {
            if (filt != null && !f.getName().contains(filt)) continue;
            w.println("/* ===== " + f.getName() + " @ " + f.getEntryPoint() + " ===== */");
            DecompileResults r = di.decompileFunction(f, 60, monitor);
            if (r != null && r.decompileCompleted()) {
                w.println(r.getDecompiledFunction().getC());
                n++;
            } else {
                w.println("// decompile failed: " + (r == null ? "null" : r.getErrorMessage()));
            }
            w.println();
        }
        w.close();
        println("DumpFuncs: wrote " + n + " functions to " + out);
    }
}