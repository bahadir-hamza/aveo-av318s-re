// Seçilen fonksiyona yapılan tüm çağrıların sabit parametrelerini listeler
// x64 çağrı düzeni: RCX=p1, RDX=p2, R8=p3, R9=p4, [RSP+0x20]=p5, [RSP+0x28]=p6, [RSP+0x30]=p7
// usb_vendor_request için: p2=bRequest, p3=wValue, p4=wIndex, p5=tampon, p6=uzunluk, p7=yön(1=IN)
//@category Aveo
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.address.*;
import ghidra.program.model.scalar.Scalar;
import java.util.*;

public class CallArgs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String ad = askString("Fonksiyon", "Hangi fonksiyonun çağrıları listelensin?", "usb_vendor_request");
        List<Function> fl = getGlobalFunctions(ad);
        if (fl.isEmpty()) { println(ad + " bulunamadi"); return; }
        Function target = fl.get(0);
        Listing L = currentProgram.getListing();
        String[] keys = {"p2", "p3", "p4", "p5", "p6", "p7"};

        println("adres      fonksiyon                 p2(req)  p3(val)  p4(idx)  p5(buf)  p6(len)  p7(dir)");
        for (Reference r : getReferencesTo(target.getEntryPoint())) {
            if (!r.getReferenceType().isCall()) continue;
            Address a = r.getFromAddress();
            Function f = getFunctionContaining(a);
            Map<String, String> v = new HashMap<>();
            Instruction ins = L.getInstructionAt(a);
            for (int i = 0; i < 40 && ins != null; i++) {
                ins = ins.getPrevious();
                if (ins == null) break;
                if (f != null && !f.getBody().contains(ins.getAddress())) break;
                String m = ins.getMnemonicString().toUpperCase();
                if (m.startsWith("CALL")) break;
                if (!(m.startsWith("MOV") || m.equals("XOR") || m.equals("LEA"))) continue;
                String dst = ins.getDefaultOperandRepresentation(0).toUpperCase();
                String key = null;
                if (dst.matches("(RDX|EDX|DX|DL)")) key = "p2";
                else if (dst.matches("R8[DWB]?")) key = "p3";
                else if (dst.matches("R9[DWB]?")) key = "p4";
                else if (dst.contains("RSP + 0X20")) key = "p5";
                else if (dst.contains("RSP + 0X28")) key = "p6";
                else if (dst.contains("RSP + 0X30")) key = "p7";
                if (key == null || v.containsKey(key)) continue;
                String src;
                if (m.equals("XOR")) src = "0";
                else {
                    Object[] o = ins.getOpObjects(1);
                    if (o.length == 1 && o[0] instanceof Scalar)
                        src = "0x" + Long.toHexString(((Scalar) o[0]).getUnsignedValue());
                    else src = ins.getDefaultOperandRepresentation(1).replace(" ", "");
                }
                v.put(key, src);
            }
            StringBuilder sb = new StringBuilder(String.format("%s  %-24s", a, f == null ? "?" : f.getName()));
            for (String k : keys) sb.append(String.format("  %-8s", v.getOrDefault(k, "?")));
            println(sb.toString());
        }
    }
}
