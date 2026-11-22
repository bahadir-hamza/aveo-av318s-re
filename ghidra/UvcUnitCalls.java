// uvc_unit_request çağrılarının sabit parametrelerini listeler
// x64 çağrı düzeni: RCX=ctx, RDX=request, R8=selector, R9=unit,
// [RSP+0x20]=tampon, [RSP+0x28]=uzunluk, [RSP+0x30]=yön
//@category Aveo
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.address.*;
import ghidra.program.model.scalar.Scalar;
import java.util.*;

public class UvcUnitCalls extends GhidraScript {
    @Override
    public void run() throws Exception {
        List<Function> fl = getGlobalFunctions("uvc_unit_request");
        if (fl.isEmpty()) { println("uvc_unit_request bulunamadi"); return; }
        Function target = fl.get(0);
        Listing L = currentProgram.getListing();

        println("adres      fonksiyon                     req    sel    unit   len    dir");
        for (Reference r : getReferencesTo(target.getEntryPoint())) {
            if (!r.getReferenceType().isCall()) continue;
            Address a = r.getFromAddress();
            Function f = getFunctionContaining(a);
            Map<String, String> v = new HashMap<>();
            Instruction ins = L.getInstructionAt(a);
            for (int i = 0; i < 30 && ins != null; i++) {
                ins = ins.getPrevious();
                if (ins == null) break;
                if (f != null && !f.getBody().contains(ins.getAddress())) break;
                String m = ins.getMnemonicString().toUpperCase();
                if (m.startsWith("CALL")) break;
                if (!(m.startsWith("MOV") || m.equals("XOR") || m.equals("LEA"))) continue;
                String dst = ins.getDefaultOperandRepresentation(0).toUpperCase();
                String key = null;
                if (dst.matches("(RDX|EDX|DX|DL)")) key = "req";
                else if (dst.matches("R8[DWB]?")) key = "sel";
                else if (dst.matches("R9[DWB]?")) key = "unit";
                else if (dst.contains("RSP + 0X28")) key = "len";
                else if (dst.contains("RSP + 0X30")) key = "dir";
                if (key == null || v.containsKey(key)) continue;
                String src;
                if (m.equals("XOR")) {
                    src = "0";
                } else {
                    Object[] o = ins.getOpObjects(1);
                    if (o.length == 1 && o[0] instanceof Scalar)
                        src = "0x" + Long.toHexString(((Scalar) o[0]).getUnsignedValue());
                    else
                        src = ins.getDefaultOperandRepresentation(1);
                }
                v.put(key, src);
            }
            println(String.format("%s  %-28s  %-6s %-6s %-6s %-6s %s",
                    a, f == null ? "?" : f.getName(),
                    v.getOrDefault("req", "?"), v.getOrDefault("sel", "?"),
                    v.getOrDefault("unit", "?"), v.getOrDefault("len", "?"),
                    v.getOrDefault("dir", "?")));
        }
    }
}
