// Disassemble Aveo XDATA dump, decompile functions of interest
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.cmd.function.CreateFunctionCmd;
import java.io.*;

public class Fw8051 extends GhidraScript {
  long[] entries = {0xafd7,0xafef,0xaf55,0xaf25,0xb01f,0xac6d,0xaa4a,0xd136,0xb0fc,0xd3dc,0xdcf5,0xc500,0xd556,0xde3b,0xde3c,0xde3d,0xde3e, 0xb007,0xa2c0,0xb10a,0xb10b,0xb10c,0xb10d,0xb10e};
  public void run() throws Exception {
    AddressSpace cs = currentProgram.getAddressFactory().getDefaultAddressSpace();
    for (long e : entries) {
      Address a = cs.getAddress(e);
      new DisassembleCommand(a, null, true).applyTo(currentProgram);
      new CreateFunctionCmd(a).applyTo(currentProgram);
    }
    analyzeChanges(currentProgram);
    String[] args = getScriptArgs();
    PrintWriter out = new PrintWriter(new FileWriter(args[0]));
    DecompInterface di = new DecompInterface(); di.openProgram(currentProgram);
    FunctionManager fm = currentProgram.getFunctionManager();
    out.println("FUNCTIONS: " + fm.getFunctionCount());
    for (int i = 1; i < args.length; i++) {
      Address a = cs.getAddress(Long.parseLong(args[i], 16));
      Function f = fm.getFunctionContaining(a);
      if (f == null) { out.println("// no function at " + a); continue; }
      out.println("\n// ===== " + f.getName() + " @ " + f.getEntryPoint() + " (contains " + a + ")");
      DecompileResults r = di.decompileFunction(f, 120, monitor);
      out.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// decompile failed: " + r.getErrorMessage());
    }
    out.close();
  }
}
