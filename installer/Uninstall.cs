using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class Uninstall
{
    const string ProductId = "f9334ef5-a351-4fba-a0a0-b563af7c6697";
    const string Key = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\Silentanator";

    [STAThread]
    static int Main(string[] args)
    {
        bool quiet = Array.IndexOf(args, "--quiet") >= 0;
        try
        {
            string removing = Option(args, "--remove");
            if (removing == null)
            {
                string installed = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                Verify(installed);
                if (!quiet && MessageBox.Show("Uninstall Silentanator? Your Word notes, sessions, and sign-in will be kept.", "Silentanator", MessageBoxButtons.OKCancel) != DialogResult.OK) return 0;
                string copy = Path.Combine(Path.GetTempPath(), "Silentanator-Uninstall-" + Guid.NewGuid().ToString("N") + ".exe");
                File.Copy(Assembly.GetExecutingAssembly().Location, copy);
                var start = new ProcessStartInfo(copy, "--remove \"" + installed + "\" --parent " + Process.GetCurrentProcess().Id + (quiet ? " --quiet" : ""));
                start.UseShellExecute = false;
                start.CreateNoWindow = true;
                start.WindowStyle = ProcessWindowStyle.Hidden;
                Process.Start(start);
                return 0;
            }
            int parent;
            if (Int32.TryParse(Option(args, "--parent"), out parent))
            {
                try { Process.GetProcessById(parent).WaitForExit(10000); }
                catch (ArgumentException) { }
            }
            string target = Path.GetFullPath(removing).TrimEnd(Path.DirectorySeparatorChar);
            Verify(target);
            foreach (string name in new[] { "Silentanator", "SilentanatorSetup" })
            foreach (Process process in Process.GetProcessesByName(name))
            {
                string executable;
                try { executable = process.MainModule.FileName; }
                catch (System.ComponentModel.Win32Exception) { continue; }
                if (Same(Path.GetDirectoryName(executable), target))
                    throw new InvalidOperationException("Close Silentanator and Setup before uninstalling.");
            }
            // Check the exact absolute target and installation marker before
            // recursive removal. Personal data lives outside this directory.
            Verify(target);
            string manifest = Path.Combine(target, ".silentanator-files.txt");
            if (!File.Exists(manifest)) throw new InvalidOperationException("The installed file list is missing. Reinstall before uninstalling.");
            foreach (string relative in File.ReadAllLines(manifest))
            {
                string file = Path.GetFullPath(Path.Combine(target, relative));
                if (!file.StartsWith(target + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("The installed file list contains an unsafe path.");
                if (File.Exists(file)) File.Delete(file);
            }
            RemoveEmptyDirectories(target);
            using (RegistryKey key = Registry.CurrentUser.OpenSubKey(Key))
            {
                if (key != null && Same((string)key.GetValue("InstallLocation", ""), target))
                    Registry.CurrentUser.DeleteSubKeyTree(Key, false);
            }
            string menu = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Silentanator");
            foreach (string shortcut in new[] {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Silentanator Setup.lnk"),
                Path.Combine(menu, "Silentanator Setup.lnk"), Path.Combine(menu, "Run Silentanator.lnk") })
                DeleteShortcutIfMatching(shortcut, target);
            if (Directory.Exists(menu) && Directory.GetFileSystemEntries(menu).Length == 0) Directory.Delete(menu);
            return 0;
        }
        catch (Exception exception)
        {
            if (!quiet) MessageBox.Show(exception.Message, "Silentanator uninstall", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    static string Option(string[] args, string name)
    {
        int index = Array.IndexOf(args, name);
        return index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
    }

    static bool Same(string first, string second)
    {
        return !String.IsNullOrEmpty(first) && String.Equals(Path.GetFullPath(first).TrimEnd('\\'), Path.GetFullPath(second).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase);
    }

    static void Verify(string directory)
    {
        string path = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar);
        if (Same(path, Path.GetPathRoot(path)) || !File.Exists(Path.Combine(path, ".silentanator-install")) ||
            File.ReadAllText(Path.Combine(path, ".silentanator-install")).Trim() != ProductId)
            throw new InvalidOperationException("This folder is not a verified Silentanator installation.");
    }

    static void DeleteShortcutIfMatching(string path, string installation)
    {
        if (!File.Exists(path)) return;
        Type type = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(type);
        object shortcut = type.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { path });
        string destination = (string)shortcut.GetType().InvokeMember("TargetPath", BindingFlags.GetProperty, null, shortcut, null);
        if (Same(Path.GetDirectoryName(destination), installation)) File.Delete(path);
        Marshal.ReleaseComObject(shortcut);
        Marshal.ReleaseComObject(shell);
    }

    static void RemoveEmptyDirectories(string directory)
    {
        foreach (string child in Directory.GetDirectories(directory))
        {
            if ((File.GetAttributes(child) & FileAttributes.ReparsePoint) == 0) RemoveEmptyDirectories(child);
        }
        if (Directory.GetFileSystemEntries(directory).Length == 0) Directory.Delete(directory);
    }
}
