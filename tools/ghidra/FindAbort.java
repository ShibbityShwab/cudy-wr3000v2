// FindAbort.java - print references to the U-Boot abort strings and decompile the containing functions.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class FindAbort extends GhidraScript {
    public void run() throws Exception {
        long[] targets = {
            0x80083216L, 0x80083242L, 0x8008324fL, 0x8008325bL,
            0x8007d9c0L, 0x8007d9d0L, 0x8007d9f8L
        };
        AddressSpace space = currentProgram.getAddressFactory().getDefaultAddressSpace();
        ReferenceManager rm = currentProgram.getReferenceManager();
        FunctionManager fm = currentProgram.getFunctionManager();
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        for (long t : targets) {
            Address a = space.getAddress(t);
            println("=== target " + a + " ===");
            ReferenceIterator refs = rm.getReferencesTo(a);
            int n = 0;
            while (refs.hasNext()) {
                Reference r = refs.next();
                n++;
                Address from = r.getFromAddress();
                println("  from " + from + " type " + r.getReferenceType());
                Function f = fm.getFunctionContaining(from);
                if (f != null) {
                    println("  function " + f.getName() + " @" + f.getEntryPoint());
                    DecompileResults res = di.decompileFunction(f, 60, monitor);
                    if (res != null && res.decompileCompleted()) {
                        println("---- C ----");
                        println(res.getDecompiledFunction().getC());
                        println("-----------");
                    }
                }
            }
            println("refs total: " + n);
        }
    }
}
