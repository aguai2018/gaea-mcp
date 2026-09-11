using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Windows.Automation;

// Adaptive UI Automation driver for QuadSpinner Gaea.
//
// Gaea's UI Automation tree exposes the buttons we need by Name/AutomationId:
//   Build Settings and Regions : 'Execute Build' (btnBuild),
//                                'Copy Command Line' (btnCLI),
//                                'Close' (btnCancel)
//   Build and Export?          : 'Start Build' (CommandLink_10),
//                                'Close Gaea and Build' (CommandLink_11),
//                                '取消' (CommandButton_2)
//
// Hard-coding a PID breaks as soon as Gaea restarts, so the PID is resolved
// from the running process list every invocation.
//
// usage: uia <pid|find|findc|invoke|dump|keys> [arg]
public class Uia {
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr h);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr h, int cmd);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    static int GaeaPid() {
        foreach (var p in Process.GetProcessesByName("Gaea")) {
            try { if (p.MainWindowHandle != IntPtr.Zero) return p.Id; }
            catch { }
        }
        foreach (var p in Process.GetProcessesByName("Gaea")) return p.Id;
        return -1;
    }

    static List<AutomationElement> TopWindows(int pid) {
        var cond = new PropertyCondition(AutomationElement.ProcessIdProperty, pid);
        var all = AutomationElement.RootElement.FindAll(TreeScope.Children, cond);
        var list = new List<AutomationElement>();
        foreach (AutomationElement w in all) list.Add(w);
        return list;
    }

    static string Desc(AutomationElement e) {
        string name = "", aid = "", ct = "";
        try { name = e.Current.Name; } catch { }
        try { aid = e.Current.AutomationId; } catch { }
        try { ct = e.Current.ControlType.ProgrammaticName.Replace("ControlType.", ""); } catch { }
        return string.Format("[{0}] name='{1}' id='{2}'", ct, name, aid);
    }

    static int FindExact(string needle) {
        int pid = GaeaPid();
        if (pid < 0) { Console.WriteLine("no Gaea process"); return 2; }
        int hits = 0;
        foreach (var w in TopWindows(pid)) {
            string wt = ""; try { wt = w.Current.Name; } catch { }
            AutomationElementCollection found;
            try {
                found = w.FindAll(TreeScope.Descendants,
                    new PropertyCondition(AutomationElement.NameProperty, needle));
            } catch { continue; }
            foreach (AutomationElement e in found) {
                Console.WriteLine("  win='" + wt + "'  " + Desc(e));
                hits++;
            }
        }
        Console.WriteLine("matches: " + hits);
        return hits > 0 ? 0 : 1;
    }

    static int FindContains(string needle) {
        int pid = GaeaPid();
        if (pid < 0) { Console.WriteLine("no Gaea process"); return 2; }
        int hits = 0;
        foreach (var w in TopWindows(pid)) {
            string wt = ""; try { wt = w.Current.Name; } catch { }
            AutomationElementCollection all;
            try { all = w.FindAll(TreeScope.Descendants, Condition.TrueCondition); }
            catch { continue; }
            foreach (AutomationElement e in all) {
                string n = ""; try { n = e.Current.Name; } catch { }
                if (n != null && n.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0) {
                    Console.WriteLine("  win='" + wt + "'  " + Desc(e));
                    if (++hits > 80) { Console.WriteLine("  ...truncated"); return 0; }
                }
            }
        }
        Console.WriteLine("matches: " + hits);
        return hits > 0 ? 0 : 1;
    }

    // Invoke the best match. Prefers an exact Name match on an invokable
    // element; also tries AutomationId and substring matches.
    static int Invoke(string needle) {
        int pid = GaeaPid();
        if (pid < 0) { Console.WriteLine("no Gaea process"); return 2; }

        AutomationElement exact = null, sub = null, byId = null;
        string exactWin = "", subWin = "", idWin = "";
        foreach (var w in TopWindows(pid)) {
            string wt = ""; try { wt = w.Current.Name; } catch { }
            AutomationElementCollection all;
            try { all = w.FindAll(TreeScope.Descendants, Condition.TrueCondition); }
            catch { continue; }
            foreach (AutomationElement e in all) {
                string n = "", a = "";
                try { n = e.Current.Name; } catch { }
                try { a = e.Current.AutomationId; } catch { }
                if (exact == null && n == needle) { exact = e; exactWin = wt; }
                if (byId == null && a == needle) { byId = e; idWin = wt; }
                if (sub == null && n != null &&
                    n.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0) {
                    sub = e; subWin = wt;
                }
            }
        }
        var pick = exact ?? byId ?? sub;
        string win = exact != null ? exactWin : (byId != null ? idWin : subWin);
        if (pick == null) {
            Console.WriteLine("no element matching '" + needle + "'");
            return 1;
        }
        object pat;
        if (pick.TryGetCurrentPattern(InvokePattern.Pattern, out pat)) {
            ((InvokePattern)pat).Invoke();
            Console.WriteLine("INVOKED  win='" + win + "'  " + Desc(pick));
            return 0;
        }
        // Fall back to focusing + space for toggle-like controls.
        try {
            pick.SetFocus();
            Console.WriteLine("FOCUSED (no InvokePattern)  " + Desc(pick));
            return 0;
        } catch (Exception ex) {
            Console.WriteLine("no InvokePattern and focus failed: " + ex.Message + "  " + Desc(pick));
            return 1;
        }
    }

    static int Dump(string filter) {
        int pid = GaeaPid();
        if (pid < 0) { Console.WriteLine("no Gaea process"); return 2; }
        foreach (var w in TopWindows(pid)) {
            string wt = ""; try { wt = w.Current.Name; } catch { }
            if (filter != null && filter.Length > 0 &&
                wt.IndexOf(filter, StringComparison.OrdinalIgnoreCase) < 0) continue;
            Console.WriteLine("=== WINDOW '" + wt + "' ===");
            DumpEl(w, 1);
        }
        return 0;
    }

    static void DumpEl(AutomationElement e, int depth) {
        if (depth > 12) return;
        Console.WriteLine(new string(' ', depth * 2) + Desc(e));
        AutomationElementCollection kids;
        try { kids = e.FindAll(TreeScope.Children, Condition.TrueCondition); }
        catch { return; }
        foreach (AutomationElement k in kids) DumpEl(k, depth + 1);
    }

    // Find the Windows file dialog: the only reliable marker is the "File name"
    // combo box, whose AutomationId is 1148. Matching on the button name
    // ("打开"/"Open") gives false positives from Gaea's own menu.
    static AutomationElement FileDialogEdit() {
        int pid = GaeaPid();
        if (pid < 0) return null;
        foreach (var w in TopWindows(pid)) {
            AutomationElementCollection all;
            try { all = w.FindAll(TreeScope.Descendants, Condition.TrueCondition); }
            catch { continue; }
            foreach (AutomationElement e in all) {
                string aid = "", ct = "";
                try { aid = e.Current.AutomationId; } catch { }
                try { ct = e.Current.ControlType.ProgrammaticName; } catch { }
                if (aid == "1148" || aid == "1001") return e;
                if (ct == "ControlType.Edit" && aid == "") {
                    // keep looking; an unnamed edit is not proof of a dialog
                }
            }
        }
        return null;
    }

    static int HasFileDialog() {
        var e = FileDialogEdit();
        Console.WriteLine(e == null ? "nofiledialog" : "filedialog");
        return e == null ? 1 : 0;
    }

    static int Windows() {
        int pid = GaeaPid();
        if (pid < 0) { Console.WriteLine("no Gaea process"); return 2; }
        foreach (var w in TopWindows(pid)) {
            string wt = ""; try { wt = w.Current.Name; } catch { }
            Console.WriteLine("WINDOW '" + wt + "'");
        }
        return 0;
    }

    // The main window title ("Gaea - <project>") is the most reliable signal
    // that a project actually loaded.
    static int Title() {
        int pid = GaeaPid();
        if (pid < 0) { Console.WriteLine("no Gaea process"); return 2; }
        string best = "";
        foreach (var w in TopWindows(pid)) {
            string wt = ""; try { wt = w.Current.Name; } catch { }
            if (wt != null && wt.StartsWith("Gaea -") && wt.Length > best.Length)
                best = wt;
        }
        Console.WriteLine(best);
        return best.Length > 0 ? 0 : 1;
    }

    // ---- keyboard helpers (SendInput, Unicode-safe) -----------------------
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

    const uint INPUT_KEYBOARD = 1;
    const uint KEYEVENTF_KEYUP = 0x0002;
    const uint KEYEVENTF_UNICODE = 0x0004;

    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    public struct KEYBDINPUT {
        public ushort wVk; public ushort wScan; public uint dwFlags;
        public uint time; public IntPtr dwExtraInfo;
    }
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Explicit)]
    public struct InputUnion {
        [System.Runtime.InteropServices.FieldOffset(0)] public KEYBDINPUT ki;
        [System.Runtime.InteropServices.FieldOffset(0)] public byte pad0;
    }
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    public struct INPUT { public uint type; public InputUnion u; }

    static void TapVk(ushort vk) {
        INPUT[] a = new INPUT[1];
        a[0].type = INPUT_KEYBOARD; a[0].u.ki.wVk = vk;
        a[0].u.ki.dwFlags = 0; a[0].u.ki.dwExtraInfo = IntPtr.Zero;
        SendInput(1, a, System.Runtime.InteropServices.Marshal.SizeOf(typeof(INPUT)));
        System.Threading.Thread.Sleep(40);
        a[0].u.ki.dwFlags = KEYEVENTF_KEYUP;
        SendInput(1, a, System.Runtime.InteropServices.Marshal.SizeOf(typeof(INPUT)));
        System.Threading.Thread.Sleep(40);
    }

    static void TypeUnicode(string s) {
        foreach (char c in s) {
            INPUT[] a = new INPUT[2];
            a[0].type = INPUT_KEYBOARD; a[0].u.ki.wVk = 0; a[0].u.ki.wScan = (ushort)c;
            a[0].u.ki.dwFlags = KEYEVENTF_UNICODE; a[0].u.ki.dwExtraInfo = IntPtr.Zero;
            a[1].type = INPUT_KEYBOARD; a[1].u.ki.wVk = 0; a[1].u.ki.wScan = (ushort)c;
            a[1].u.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP; a[1].u.ki.dwExtraInfo = IntPtr.Zero;
            SendInput(2, a, System.Runtime.InteropServices.Marshal.SizeOf(typeof(INPUT)));
            System.Threading.Thread.Sleep(8);
        }
    }

    // Set a path in the currently focused file dialog and confirm it.
    // Order of attempts:
    //   1. ValuePattern on an Edit whose AutomationId is 1148 (the classic
    //      "File name" box) or whose name looks like a filename field.
    //   2. Ctrl+L then type (Explorer's address bar) then Enter, Enter.
    //   3. plain typing then Enter.
    static int SetPath(string path) {
        int pid = GaeaPid();
        if (pid < 0) { Console.WriteLine("no Gaea process"); return 2; }

        AutomationElement edit = null;
        foreach (var w in TopWindows(pid)) {
            string wt = ""; try { wt = w.Current.Name; } catch { }
            AutomationElementCollection all;
            try { all = w.FindAll(TreeScope.Descendants, Condition.TrueCondition); }
            catch { continue; }
            foreach (AutomationElement e in all) {
                string ct = "", aid = "", nm = "";
                try { ct = e.Current.ControlType.ProgrammaticName; } catch { }
                try { aid = e.Current.AutomationId; } catch { }
                try { nm = e.Current.Name; } catch { }
                if (ct != "ControlType.Edit") continue;
                bool looks = aid == "1148" || aid == "1001"
                    || (nm != null && (nm.Contains("文件名") || nm.Contains("File name")
                                       || nm.Contains("Name")));
                if (looks) { edit = e; break; }
                if (edit == null) edit = e;   // remember the first Edit as a fallback
            }
            if (edit != null && wt.Length > 0) break;
        }

        if (edit != null) {
            try {
                object vp;
                if (edit.TryGetCurrentPattern(ValuePattern.Pattern, out vp)) {
                    ((ValuePattern)vp).SetValue(path);
                    System.Threading.Thread.Sleep(400);
                    Console.WriteLine("SET-VALUE ok");
                    TapVk(0x0D);   // Enter
                    System.Threading.Thread.Sleep(600);
                    return 0;
                }
            } catch (Exception ex) {
                Console.WriteLine("SetValue failed: " + ex.Message);
            }
        }

        // keyboard fallbacks
        Console.WriteLine("SetValue unavailable, using the keyboard");
        // Ctrl+L focuses the address bar in the Explorer-style dialog
        INPUT[] l = new INPUT[2];
        l[0].type = INPUT_KEYBOARD; l[0].u.ki.wVk = 0x11; l[0].u.ki.dwFlags = 0;
        l[1].type = INPUT_KEYBOARD; l[1].u.ki.wVk = 0x4C; l[1].u.ki.dwFlags = 0;
        SendInput(2, l, System.Runtime.InteropServices.Marshal.SizeOf(typeof(INPUT)));
        System.Threading.Thread.Sleep(50);
        l[0].u.ki.dwFlags = KEYEVENTF_KEYUP; l[1].u.ki.dwFlags = KEYEVENTF_KEYUP;
        SendInput(2, l, System.Runtime.InteropServices.Marshal.SizeOf(typeof(INPUT)));
        System.Threading.Thread.Sleep(400);
        TypeUnicode(path);
        System.Threading.Thread.Sleep(500);
        TapVk(0x0D);
        System.Threading.Thread.Sleep(1200);
        TapVk(0x0D);
        System.Threading.Thread.Sleep(800);
        Console.WriteLine("KEYBOARD path sent");
        return 0;
    }

    public static int Main(string[] args) {
        if (args.Length == 0) {
            Console.WriteLine("usage: uia <pid|windows|find|findc|invoke|dump|openpath> [arg]");
            return 1;
        }
        switch (args[0].ToLower()) {
            case "pid": Console.WriteLine(GaeaPid()); return 0;
            case "windows": return Windows();
            case "title": return Title();
            case "hasfiledialog": return HasFileDialog();
            case "find": return FindExact(args.Length > 1 ? args[1] : "");
            case "findc": return FindContains(args.Length > 1 ? args[1] : "");
            case "invoke": return Invoke(args.Length > 1 ? args[1] : "");
            case "dump": return Dump(args.Length > 1 ? args[1] : null);
            case "openpath": return SetPath(args.Length > 1 ? args[1] : "");
        }
        Console.WriteLine("unknown command " + args[0]);
        return 1;
    }
}
